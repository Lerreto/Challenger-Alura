# Plan implementado del agente RAG

La primera versión transforma el scaffold en un producto local completo: documentos persistentes, procesamiento multiformato, recuperación semántica, respuesta fundamentada y una interfaz web trazable.

## Camino principal

1. El backend copia los cinco documentos seed únicamente si faltan.
2. El extractor preserva estructura y metadatos antes de fragmentar.
3. Hugging Face genera embeddings multilingües y Chroma los persiste.
4. El chat filtra candidatos por relevancia.
5. Solo la evidencia suficiente llega a Groq; las fuentes salen de metadatos.
6. La interfaz permite cargar, listar, eliminar, reindexar y consultar.

## Decisiones

| Area | Decision | Tradeoff |
|---|---|---|
| API | FastAPI sobre Python 3.12 | Contratos claros; un worker para proteger mutaciones locales |
| Orchestration | LangChain lineal | Menos complejidad que LangGraph para un único flujo |
| Embeddings | MiniLM multilingüe local | Sin costo por consulta; descarga y CPU iniciales |
| Vector store | Chroma persistente | Simple para el challenge; no es la topología final multi-réplica |
| LLM | ChatGroq configurable | Prototipado accesible; disponibilidad de modelos cambia |
| Catalog | SQLite | Transacciones y lifecycle simples; un solo backend escritor |
| Frontend | React + Vite + TypeScript | Producto web responsive y testeable |
| Persistence | Tres named volumes | `down` conserva datos; el backup sigue siendo responsabilidad operativa |

## Challenge steps covered

- **Collection:** cinco fuentes curadas con categoría, versión, responsable y lenguaje.
- **Processing:** extracción por formato, limpieza, estructura, límites y chunking con overlap.
- **Indexing:** mismo embedding para corpus y preguntas, IDs deterministas y Chroma.
- **Retrieval:** candidatos con score y umbral configurable.
- **Generation:** prompt restringido, baja temperatura, abstención determinista y citas externas al LLM.
- **Interface and maintenance:** carga, biblioteca, eliminación, reindexación, feedback y estados reales.

## Work units and verification

1. **Ingestion and catalog:** loaders, SHA-256, metadatos, SQLite y lifecycle con pruebas offline.
2. **Grounded answer:** vector protocol, provider protocol, umbral, fuentes y contratos API.
3. **Document workspace:** biblioteca, dropzone, chat, fuentes, accesibilidad y responsive.
4. **Runtime:** imágenes de producción, proxy Nginx, healthchecks y volúmenes.
5. **Documentation:** quick start, límites, API y trabajo pendiente de OCI.

## Known limits

- No hay OCR, autenticación, antivirus ni procesamiento asíncrono.
- La primera descarga del modelo de embeddings requiere red y puede demorar.
- Un solo worker serializa cargas, eliminaciones y reindexación.
- `NEBULA_MIN_RELEVANCE=0.52` es un punto inicial, no una calibración de producción.
- OpenAI está previsto mediante el protocolo de proveedor, pero no está implementado.
- OCI y su evidencia de ejecución continúan pendientes.
