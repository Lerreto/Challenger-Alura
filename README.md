# Nébula Tech RAG

Scaffold inicial para un agente corporativo RAG del challenge Alura. El proyecto usará como caso ficticio a **Nébula Tech Colombia S.A.S.**, una tienda de tecnología, y responderá preguntas a partir de cinco documentos internos coherentes.

> **Estado actual:** solo están listos la estructura, los contenedores placeholder y el corpus inicial. Todavía no existen interfaz, API, embeddings, índice vectorial ni lógica RAG.

## Inicio rápido

Requisito: Docker con Docker Compose v2.

```bash
docker compose up --build
```

Esto inicia dos contenedores placeholder:

| Servicio | Puerto reservado | Estado |
|---|---:|---|
| `frontend` | `3000` | Contenedor activo, sin servidor HTTP |
| `backend` | `8000` | Contenedor Python activo, sin API |

Los puertos quedan preparados para la implementación futura. Por ahora, `http://localhost:3000` y `http://localhost:8000` **no entregan una aplicación**.

Para detener los contenedores:

```bash
docker compose down
```

## Arquitectura inicial

```text
Usuario
  │
  ▼
frontend :3000        (placeholder)
  │
  ▼
backend :8000         (placeholder Python)
  │
  └── /app/documents  (montaje de solo lectura)
```

`documents/` es el corpus que consumirá el backend. **No es un servicio ni expone archivos por red.**

## Estructura

```text
.
├── backend/
│   ├── .dockerignore
│   └── Dockerfile
├── documents/
│   ├── guia_envios_entregas.md
│   ├── politica_privacidad.md
│   ├── politica_reembolsos_devoluciones.md
│   ├── preguntas_frecuentes.md
│   └── terminos_condiciones.md
├── frontend/
│   ├── .dockerignore
│   └── Dockerfile
├── Docs/plan/README.md
└── compose.yaml
```

## Corpus ficticio

Los cinco documentos siguen la sugerencia oficial para un caso de comercio electrónico:

1. Política de privacidad.
2. Política de reembolso y devoluciones.
3. Preguntas frecuentes (FAQ).
4. Guía de envíos y entregas.
5. Términos y condiciones.

Todo el contenido y la empresa son ficticios. Los documentos incluyen metadatos estables para facilitar su futura carga, fragmentación, trazabilidad y recuperación.

## Decisiones pendientes

- Tecnología y diseño del frontend.
- Framework de API para Python.
- Uso o no de LangChain para la orquestación.
- Modelo de embeddings y proveedor del modelo generativo.
- Base de datos o motor vectorial.
- Estrategia de evaluación, observabilidad y seguridad.
- Servicio de OCI y arquitectura de despliegue.

No se deben agregar dependencias ni implementar lógica de producto hasta confirmar estas decisiones.

## Requisitos del challenge

La entrega final deberá:

- Publicarse en un repositorio público de GitHub.
- Desplegarse usando al menos un servicio de Oracle Cloud Infrastructure (OCI).
- Incluir en este README una imagen o un video del agente ejecutándose en la nube.

Estos requisitos **todavía no están completados**.

## Próximos pasos

1. Confirmar las tecnologías del frontend, API, RAG, embeddings y almacenamiento vectorial.
2. Diseñar el flujo de ingesta y validación del corpus.
3. Implementar una primera prueba de recuperación antes de conectar un modelo generativo.
4. Agregar pruebas y criterios de evaluación.
5. Definir y ejecutar el despliegue en OCI.

El plan de esta fase está en [`Docs/plan/README.md`](Docs/plan/README.md).
