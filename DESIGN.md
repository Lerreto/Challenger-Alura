# Nébula Design System

## Intent

Nébula es una herramienta de trabajo compacta para consultar documentos durante una jornada ocupada. La escena física —una persona frente a un portátil, frecuentemente bajo luz tenue y necesitando una respuesta inmediata— justifica un tema oscuro de alto contraste, no una estética oscura decorativa.

## Visual Direction

- **Lane:** shell de producto sobrio, técnico y cercano.
- **Strategy:** neutrales grafito con un único acento coral/naranja en menos del 10% de la superficie.
- **Density:** compacta, con separación suficiente para escanear estados y fuentes.
- **Depth:** creada con cambios de superficie y bordes de 1 px; sin vidrio, gradientes ni sombras amplias.

## Color

Los tokens se implementan con OKLCH en `frontend/src/styles.css`.

| Role | Token | Use |
|---|---|---|
| Canvas | `--bg` | Área de conversación y fondo principal |
| Surface 1–3 | `--surface-*` | Barra, biblioteca, controles y estados elevados |
| Line | `--line` | División estructural, nunca decoración |
| Text | `--text` | Contenido principal |
| Soft / muted | `--text-soft`, `--text-muted` | Metadatos y ayuda con contraste legible |
| Action | `--accent` | Acción primaria, foco y selección |
| Success | `--green` | Índice listo y fuentes verificadas |
| Warning | `--amber` | Modelo sin configurar o abstención |
| Error | `--red` | Fallos técnicos y acciones destructivas |

El color semántico siempre aparece junto a texto, icono o forma. No se usa texto con gradiente.

## Typography

- Familia: pila sans del sistema (`Inter` cuando esté instalada localmente).
- Texto de interfaz: 11–14 px para preservar densidad sin bajar de una lectura funcional.
- Títulos: peso 600, tracking entre `-0.01em` y `-0.03em`.
- Respuestas: ancho máximo de 70 caracteres y `line-height` de 1.65.
- Las mayúsculas espaciadas no forman parte de la voz visual.

## Layout

### Desktop

Una barra superior de 58 px muestra identidad y estado real. Debajo, la biblioteca ocupa 372 px y el chat usa el espacio restante. La conversación limita su ancho a 800 px y el compositor permanece en el borde inferior del panel.

### Tablet and mobile

Por debajo de 840 px, la biblioteca se transforma en un drawer controlado con fondo modal. El chat conserva toda la anchura y expone una acción para abrir los documentos. Por debajo de 540 px se apilan las sugerencias, se simplifican los estados superiores y se respetan las áreas seguras del dispositivo.

## Components

- **System status:** estado de índice, cantidad real de fragmentos y disponibilidad de Groq.
- **Dropzone:** activable con ratón, teclado o arrastre; informa formatos, procesamiento y resultado.
- **Document row:** título, categoría, estado, fragmentos y eliminación explícita.
- **Message:** variantes para pregunta, respuesta, abstención, error y carga.
- **Source disclosure:** `details/summary` con documento, ubicación, extracto y relevancia.
- **Composer:** Enter envía, Shift+Enter crea línea, y la acción se desactiva durante la respuesta.

Los radios se limitan a 12 px. Las tarjetas no se anidan; las fuentes se separan mediante líneas estructurales.

## Motion

Las respuestas entran con una transición corta de opacidad y desplazamiento. Los indicadores de carga comunican trabajo en curso. No se animan propiedades de layout ni se usa rebote. `prefers-reduced-motion` reduce todas las transiciones a un cambio prácticamente instantáneo.

## Content

La interfaz usa español claro y distingue tres resultados:

- **Answered:** respuesta y fuentes verificadas.
- **Insufficient context:** “No encontré información suficiente en los documentos disponibles para responder esa pregunta.”
- **Error:** explica qué falló y qué acción permite continuar.

No usa “OK”, “Enviar” genérico ni códigos internos como única explicación.

