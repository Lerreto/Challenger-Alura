# Despliegue en Oracle Cloud Infrastructure

Guía concreta para publicar Nébula Tech RAG en OCI usando el `compose.yaml` ya
existente en el repo, sin reescribir la arquitectura. Satisface el requisito
del challenge ("al menos un servicio del ecosistema OCI") usando **OCI
Compute** como base; Object Storage y Vault quedan anotados al final como
extensiones opcionales, no obligatorias.

## Estado verificado antes de desplegar

Antes de escribir esta guía se validó localmente, con las imágenes reales
(`docker compose build` + `docker compose up`):

- 122 pruebas backend y 15 frontend en verde, build de Vite y `docker compose
  config` válidos.
- `nebula-tech-rag-backend` construye en **~4.3 GB** (torch CPU + langchain +
  sentence-transformers); `nebula-tech-rag-frontend` en **~75 MB**.
- El backend en reposo, con el índice cargado (5 documentos, 63 chunks) y el
  reranker precargado, usa **~900 MB de RAM**. Bajo carga concurrente (varias
  preguntas con reranking simultáneo) hay que dejar margen por encima de eso.
- Flujo end-to-end real contra Groq (`/api/chat`) devuelve respuesta con
  fuentes citadas correctamente a través del proxy Nginx del frontend.
- `backend/uv.lock` incluye wheels de `torch` para `manylinux_2_28_aarch64` y
  `x86_64`, así que el build funciona igual en una VM Ampere (ARM) que en una
  x86 — importante para la elección de shape de abajo.

Esa medición de memoria descarta el shape `VM.Standard.E2.1.Micro` (1 GB de
RAM) del Always Free: el backend solo, en reposo, ya casi lo agota.

## 1. Elegir y crear la VM

Shape recomendado: **`VM.Standard.A1.Flex`** (Ampere, ARM), Always Free.
Asignar al menos **2 OCPU / 8–12 GB RAM** (el tier gratuito permite hasta 4
OCPU / 24 GB combinados). Imagen: **Ubuntu 22.04 o 24.04 (Canonical)**.

Pasos en la consola de OCI:

1. **Compute → Instances → Create Instance**.
2. Nombre: `nebula-rag-vm`. Compartment del proyecto.
3. *Image and shape* → Change shape → `Ampere` → `VM.Standard.A1.Flex` → 2
   OCPU / 12 GB.
   - Si la región no tiene capacidad Always Free ARM disponible (error "Out
     of host capacity", común en regiones saturadas), reintentar en otro
     Availability Domain o, como último recurso, usar un shape E-series
     pequeño de pago (`VM.Standard.E4.Flex`, 2 OCPU/8 GB) — no usar
     `E2.1.Micro`, es insuficiente para este backend.
4. *Networking*: dejar la VCN/subred pública por defecto (o crear una), con
   **Assign a public IPv4 address** marcado.
5. *Add SSH keys*: pegar tu clave pública (o generar un par nuevo y guardar
   la privada).
6. *Boot volume*: el default (~50 GB) alcanza sobrado para las imágenes
   (~4.4 GB) más el sistema.
7. Create.

## 2. Abrir el puerto HTTP (dos capas, no una)

OCI filtra el tráfico en **dos lugares independientes**; hay que abrir los
dos o la app no será alcanzable desde afuera aunque los contenedores estén
corriendo:

**a) Security List / Network Security Group (firewall de OCI)**

`Networking → Virtual Cloud Networks → <tu VCN> → Security Lists → Default
Security List` (o el NSG asociado a la instancia):

- Add Ingress Rule: Source `0.0.0.0/0`, protocolo TCP, destination port `80`
  (el puerto que sirve el frontend). El `22` para SSH ya suele estar abierto
  por defecto.
- No es necesario abrir `8000`: el frontend (Nginx) es el único punto de
  entrada público y ya proxea `/api/*` hacia el backend por la red interna
  de Docker. Dejar `8000` cerrado hacia afuera reduce superficie de ataque.

**b) iptables dentro de la propia VM**

Las imágenes Ubuntu que provee Oracle traen un iptables local que por
defecto **solo** permite SSH entrante, incluso si el Security List ya
permite el 80 — esta es la trampa más común en tutoriales de OCI. El script
`deploy/oci-vm-setup.sh` de este repo ya inserta y persiste la regla
correcta; para hacerlo a mano:

```bash
sudo iptables -I INPUT 1 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save   # o: sudo apt install iptables-persistent && sudo netfilter-persistent save
```

## 3. Provisionar la VM

Conectate por SSH y traé el código:

```bash
ssh -i /ruta/a/tu_clave_privada ubuntu@<IP_PUBLICA>

git clone <URL_DE_TU_REPO> nebula-rag
cd nebula-rag
```

Si el repo no es público, empujá el árbol de trabajo con `rsync`/`scp` en
vez de `git clone` (asegurate de no copiar tu `.env` local con la clave real
por un canal que no controlás; mejor recrearlo en la VM en el paso
siguiente).

Corré el script de bootstrap (instala Docker, abre el firewall local, crea
`.env` desde `.env.example` y levanta el stack):

```bash
chmod +x deploy/oci-vm-setup.sh
./deploy/oci-vm-setup.sh
```

Al terminar te va a pedir editar `.env` y setear `GROQ_API_KEY` si es la
primera corrida; después repetir:

```bash
nano .env   # agregar GROQ_API_KEY=...
FRONTEND_PORT=80 docker compose up -d --build
```

## 4. Verificar

```bash
curl -s http://localhost/api/health/ready
```

Debería responder `{"status":"ready","index":"ready","llm":"configured",...}`
(si `GROQ_API_KEY` todavía no está configurada, `llm` sale `"not_configured"`
y el chat solo funciona para abstenciones). Desde tu máquina:

```bash
curl -s http://<IP_PUBLICA>/api/health/ready
```

y abrir `http://<IP_PUBLICA>/` en el navegador.

## 5. Endurecimiento recomendado antes de dejarlo público

El README del proyecto ya marca esto como pendiente: hoy cualquiera con la
URL puede subir/borrar documentos vía `/api/documents`. Para una demo
pública, la opción más barata es HTTP Basic Auth delante de todo en Nginx
(no cambia el código de la app, es puramente infraestructura):

```nginx
# frontend/nginx.conf, dentro del bloque server:
auth_basic "Nébula RAG";
auth_basic_user_file /etc/nginx/.htpasswd;
```

generando el archivo de credenciales y montándolo en la imagen o como bind
mount en la VM. Alternativa sin tocar Nginx: restringir el Security List de
OCI a un rango de IPs conocido en vez de `0.0.0.0/0` si solo tu equipo va a
evaluar la demo. Ninguna de las dos está aplicada por defecto en este repo;
quedan como decisión a tomar antes de compartir la URL ampliamente.

## 6. Evidencia para la entrega

El challenge pide registrar la ejecución en la nube con captura visual o
video (ver `Docs/listos_iniciar/8_registrar_proyecto.md`). Con la VM
corriendo:

- Screenshot/video de `http://<IP_PUBLICA>/` respondiendo una pregunta real
  con fuentes citadas.
- Screenshot de `docker compose ps` en la VM mostrando ambos contenedores
  `healthy`.
- Opcional: screenshot de la instancia en el panel de OCI Compute mostrando
  la IP pública y el shape.

## 7. Extensiones opcionales de OCI (no requeridas)

El documento del curso sugiere otros servicios; ninguno es necesario para
cumplir el requisito mínimo, pero si querés ir más allá:

- **Object Storage**: respaldo periódico de `document_originals` (bucket +
  `oci os object put`), independiente del volumen Docker local.
- **Vault**: mover `GROQ_API_KEY` de `.env` a un secret de OCI Vault y
  leerlo en el arranque del contenedor en vez de pasarlo como variable de
  entorno en texto plano.
- **Load Balancer + certificado**: si se agrega un dominio propio, un OCI
  Load Balancer con certificado gestionado da HTTPS sin correr Certbot a
  mano en la VM.

Ninguno cambia la arquitectura actual (`compose.yaml` sigue siendo la unidad
de despliegue); son mejoras incrementales sobre la misma VM.
