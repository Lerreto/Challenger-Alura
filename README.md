# Nébula Tech RAG

Asistente documental del challenge de Alura para **Nébula Tech Colombia S.A.S.**, una empresa ficticia de comercio electrónico. Indexa documentos locales y cargados por el usuario, recupera evidencia semántica con LangChain y responde mediante Groq sin salir del corpus.

> Si no encuentra evidencia suficiente responde exactamente: **“No encontré información suficiente en los documentos disponibles para responder esa pregunta.”** En ese caso no llama al LLM.

## Inicio rápido

1. Creá la configuración local sin publicar la clave:

   ```bash
   cp .env.example .env
   # Editá .env y agregá GROQ_API_KEY
   ```

2. Construí e iniciá los servicios:

   ```bash
   docker compose up --build
   ```

3. Abrí `http://localhost:3000`. La API queda disponible en `http://localhost:8000/docs`.

El backend puede iniciar sin `GROQ_API_KEY`. Las preguntas sin evidencia reciben la abstención normal; una pregunta con evidencia devuelve un `503 llm_not_configured` hasta configurar Groq.

## Arquitectura

```text
Browser
  │
  ▼
React + Nginx :3000 ── /api ──► FastAPI :8000
                                      │
                  ┌───────────────────┼────────────────────┐
                  ▼                   ▼                    ▼
          document originals   SQLite catalog       Chroma index
                                      │                    │
                                      └──── same local multilingual embedding model
                                                           │
                                                    ChatGroq (evidence only)
```

| Boundary | Technology | Responsibility |
|---|---|---|
| Web | React, Vite, TypeScript | Biblioteca, carga, chat y fuentes |
| API | FastAPI, Pydantic | Contratos HTTP y errores controlados |
| Ingestion | LangChain splitter + parsers | Extracción, metadatos, chunks y deduplicación |
| Embeddings | `langchain-huggingface` | `paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensiones |
| Vector store | `langchain-chroma` | Persistencia y recuperación semántica |
| Generation | `langchain-groq` | Respuesta con contexto; modelo configurable |
| Catalog | SQLite | Documentos, manifiesto de chunks, puntero Chroma autoritativo, historial de chat y feedback |

El flujo es lineal; esta primera versión no necesita LangGraph. El proveedor LLM está detrás de un protocolo para incorporar OpenAI después sin modificar el servicio RAG.

## Ingesta

Los cinco Markdown de `documents/` se incluyen en la imagen del backend y se copian al volumen únicamente cuando su nombre todavía no existe. Los archivos cargados nunca se sobrescriben al reiniciar.

Formatos aceptados:

| Text | Office | Structured |
|---|---|---|
| `.md`, `.txt`, `.pdf` | `.docx`, `.xlsx`, `.pptx` | `.csv`, `.json`, `.html`, `.htm` |

- Los PDF deben contener texto seleccionable. Un escaneo devuelve `ocr_required`; OCR no está implementado.
- La carga valida extensión, nombre seguro, tamaño, contenido extraído y archivos Office comprimidos.
- SHA-256 evita duplicados y genera IDs de documento estables; cada chunk también tiene un ID determinista.
- Markdown conserva frontmatter y jerarquía de títulos. Word, hojas, diapositivas y páginas conservan su ubicación.
- Documentos y preguntas siempre usan el mismo modelo de embeddings.

## Grounding y fuentes

1. Chroma recupera candidatos y scores.
2. `NEBULA_MIN_RELEVANCE` filtra con un umbral conservador configurable.
3. Sin candidatos suficientes, el backend devuelve la abstención sin llamar a Groq.
4. Con evidencia, pregunta, instrucciones y contexto documental no confiable viajan en mensajes separados.
5. Groq devuelve una respuesta estructurada con los `chunk_id` citados. El backend rechaza citas vacías o ajenas a los fragmentos recuperados.
6. Solo los chunks citados se transforman en fuentes; título, ubicación, extracto y score salen de metadatos recuperados.

El umbral por defecto `0.36` proviene de la calibración documentada más abajo; puede ajustarse con `NEBULA_MIN_RELEVANCE`.

Cada carga, eliminación o reindexación construye una colección Chroma completa, inmutable y versionada. Solo después de validar exactamente sus IDs se publica, dentro de una única transacción SQLite, el nuevo catálogo, el manifiesto de chunks y `active_collection`. La colección previa no se elimina dentro de esa operación crítica.

Al iniciar, SQLite es el puntero autoritativo. Si falta el puntero, la colección apuntada no existe o sus IDs no coinciden exactamente con el manifiesto, el backend conserva todas las colecciones mientras intenta reconstruir una versión completa desde los originales. Solo después de publicar y validar una colección activa puede limpiar versiones inactivas; si la reconstrucción falla, queda `not ready` y no borra ninguna posible copia válida.

### Evaluación de recuperación

`backend/evaluation/retrieval_dataset.json` contiene 24 preguntas balanceadas, 12 del dominio documental y 12 fuera de él. El script usa el corpus y el mismo modelo real de embeddings:

```bash
cd backend
uv run python -m scripts.evaluate_retrieval --output evaluation/retrieval_report.json
```

Resultados con el modelo real (`evaluation/retrieval_report.json`, 63 chunks, 24 preguntas):

| Métrica | Valor |
|---|---|
| Umbral recomendado | `0.364` |
| Exactitud balanceada | `0.958` |
| Score mínimo dentro del dominio | `0.374` |
| Score máximo fuera del dominio | `0.578` |

Por eso el default es `NEBULA_MIN_RELEVANCE=0.36`: el valor anterior `0.52` rechazaba tres preguntas legítimas del corpus (por ejemplo, «¿Qué sucede si mi paquete llega dañado?», score `0.374`). La única pregunta externa que supera el umbral («clima mañana en Bogotá», `0.578`) queda cubierta por la segunda capa de grounding: Groq debe citar `chunk_id` reales que respalden la respuesta, y las citas inválidas fuerzan la abstención.

## Persistencia Docker

| Volume | Content |
|---|---|
| `document_originals` | Archivos seed y cargas |
| `vector_catalog` | Chroma y catálogo SQLite |
| `huggingface_cache` | Modelo local de embeddings |

`docker compose down` conserva los volúmenes. `docker compose down -v` los elimina de forma irreversible.

## Variables

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | empty | Clave usada solo por el backend |
| `NEBULA_GROQ_MODEL` | `llama-3.1-8b-instant` | Modelo disponible en Groq |
| `NEBULA_EMBEDDING_MODEL` | multilingual MiniLM | Modelo local para documentos y consultas |
| `NEBULA_EMBEDDING_DEVICE` | `cpu` | Dispositivo de inferencia; `cuda` si hay GPU dedicada disponible |
| `NEBULA_MIN_RELEVANCE` | `0.36` | Umbral de evidencia calibrado con `evaluation/retrieval_dataset.json` |
| `NEBULA_MAX_UPLOAD_BYTES` | `20971520` | Límite de carga, 20 MB |
| `FRONTEND_PORT` / `BACKEND_PORT` | `3000` / `8000` | Puertos publicados |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health/live` | Proceso activo |
| GET | `/api/health/ready` | Índice, modelo y conteos; devuelve 503 si el índice no es utilizable |
| GET | `/api/documents` | Biblioteca documental |
| POST | `/api/documents` | Carga multipart |
| DELETE | `/api/documents/{id}` | Elimina original, catálogo y vectores |
| POST | `/api/documents/reindex` | Reconstruye Chroma desde originales |
| POST | `/api/chat` | Recupera y responde o se abstiene; persiste la conversación por `session_id` |
| GET | `/api/chat/sessions` | Lista las conversaciones guardadas (título, mensajes, fechas) |
| GET | `/api/chat/history/{session_id}` | Devuelve la conversación persistida |
| DELETE | `/api/chat/history/{session_id}` | Borra la conversación |
| POST | `/api/feedback` | Registra utilidad de una respuesta |

El chat es persistente: cada pregunta y respuesta (con estado y fuentes citadas) se guarda en SQLite bajo un `session_id`. El frontend conserva el `session_id` en `localStorage`, restaura la conversación al recargar y ofrece «Nueva conversación» para borrarla.

Cada mensaje se clasifica antes de llegar al RAG:

1. **Social** (saludos, agradecimientos, despedidas, «¿quién eres?»): respuesta conversacional determinista sin llamar al LLM.
2. **Sobre la conversación** («¿qué te pregunté antes?», «revisa el historial de este chat»): respuesta determinista construida con el historial real de la sesión.
3. **Todo lo demás** —aunque empiece con un saludo— sigue el flujo RAG normal con recuperación, umbral y citas.

El frontend muestra un selector de conversaciones guardadas: podés retomar cualquiera, empezar una nueva sin perder las anteriores, o eliminar la actual de forma explícita.

Las preguntas de seguimiento («dame la información dentro de ese .md», «¿y eso qué cubre?») no se resuelven en el vacío: si el turno anterior fue una respuesta real con fuentes, su pregunta y respuesta se pliegan en la consulta de recuperación y se le pasan al LLM como contexto no citable, solo para interpretar la referencia. Respuestas de charla trivial o abstenciones nunca contaminan este contexto.

## Desarrollo y pruebas

```bash
# Backend (requiere acceso a PyPI la primera vez)
cd backend
uv sync --extra test
uv run pytest --cov=nebula_rag --cov-report=term-missing

# Frontend
cd frontend
npm ci
npm test
npm run build

# Validar Compose sin usar secretos locales
docker compose --env-file /dev/null config --quiet
```

Las pruebas automatizadas usan índices y LLM falsos: no necesitan clave, llamada a Groq ni descarga del modelo. La evaluación de recuperación anterior sí usa el embedding real.

## Estado del challenge

Implementado y validado con 68 pruebas backend (Python 3.12, el mismo del Dockerfile), 11 pruebas frontend, build de Vite, imágenes Docker construidas y una validación end-to-end local con el embedding real: corpus, ingesta, índice persistente versionado, recuperación calibrada, abstención, ChatGroq estructurado, carga y eliminación de documentos, historial de chat persistente, API e interfaz. `torch` se instala desde el índice CPU de PyTorch para que la imagen no arrastre CUDA. No se afirma una prueba end-to-end con Groq sin una clave real.

Pendiente antes de entregar:

- desplegar al menos un servicio en Oracle Cloud Infrastructure;
- registrar evidencia visual o video de la aplicación ejecutándose en OCI;
- probar el flujo `answered` completo con una `GROQ_API_KEY` real;
- añadir autenticación y análisis antimalware antes de aceptar archivos en un entorno público.

El contexto de producto está en [`PRODUCT.md`](PRODUCT.md), el sistema visual en [`DESIGN.md`](DESIGN.md) y el plan técnico en [`Docs/plan/README.md`](Docs/plan/README.md).
