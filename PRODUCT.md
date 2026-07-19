# Product

## Register

product

## Platform

web

## Users

La persona principal es un colaborador de Nébula Tech —especialmente de atención al cliente— que consulta políticas durante una jornada con interrupciones y necesita responder sin abandonar su tarea. Usa un portátil, con frecuencia en una oficina con poca luz, y debe encontrar rápido una respuesta y su fuente.

La interfaz también debe resultar comprensible para un cliente que consulta condiciones de compra, privacidad, envíos, devoluciones o garantías sin conocer la arquitectura RAG.

## Product Purpose

Nébula convierte documentos administrados en respuestas breves y verificables. Permite cargar, procesar, indexar, consultar y retirar documentos desde un solo espacio. El éxito no es responder todo: es responder únicamente cuando existe evidencia suficiente y mostrar de dónde salió cada afirmación.

## Positioning

Un asistente documental que prefiere abstenerse antes que inventar y hace visible la evidencia usada para cada respuesta.

## Brand Personality

Precisa, sobria y confiable. La voz es directa, serena y profesional; explica límites y errores sin culpar a la persona ni convertir la interfaz en una consola técnica.

## Anti-references

- No copiar la estructura visual ni el chrome de Streamlit o Lightning AI.
- No presentar métricas decorativas de CPU, RAM o GPU.
- No usar una estética SaaS genérica con gradientes, vidrio, tarjetas flotantes o radios exagerados.
- No esconder la procedencia de las respuestas ni presentar texto del modelo como evidencia.
- No reducir la experiencia móvil hasta volver ilegible el escritorio de dos paneles.

## Design Principles

1. **Evidencia antes que fluidez:** una respuesta útil conserva sus fuentes y su ubicación.
2. **Límites explícitos:** la interfaz diferencia abstención, error técnico y respuesta fundamentada.
3. **Una tarea, un espacio:** documentos y conversación conviven sin obligar a cambiar de contexto.
4. **Estado real, no teatro:** cada indicador comunica información entregada por el backend.
5. **Densidad con calma:** la interfaz aprovecha el espacio sin sacrificar lectura, contraste ni foco.

## Accessibility & Inclusion

La experiencia usa HTML semántico, navegación completa por teclado, foco visible, mensajes anunciados con `aria-live`, contraste compatible con WCAG AA, objetivos táctiles ampliados y una alternativa sin movimiento para `prefers-reduced-motion`. Ningún estado depende únicamente del color.

