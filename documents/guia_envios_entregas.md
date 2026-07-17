---
document_id: NT-SHIP-001
title: "Guía de envíos y entregas"
category: "Logística"
version: "1.0"
effective_date: "2026-07-16"
owner: "Equipo de Operaciones Logísticas"
audience: "Clientes y personal de soporte y logística"
authoritative_source: "Repositorio documental interno de Nébula Tech Colombia S.A.S."
language: "es-CO"
fictional_notice: "Documento creado con fines académicos; la empresa, los datos y los contactos son ficticios."
---

# Guía de envíos y entregas

## 1. Cobertura

Nébula Tech Colombia S.A.S. entrega pedidos en destinos de Colombia habilitados por sus transportadores. La disponibilidad real se valida con la dirección ingresada en el checkout. Una dirección no confirmada por el checkout no se considera cubierta.

No se realizan envíos internacionales. Algunos productos sobredimensionados o de manejo especial pueden tener cobertura más limitada que el resto del catálogo.

## 2. Preparación del pedido

La preparación comienza cuando el pago queda confirmado y tarda hasta 1 día hábil. Los pedidos con validaciones de pago, dirección o inventario pendientes permanecen en espera y el tiempo de transporte todavía no empieza a contar.

Los estados principales son:

| Estado | Significado |
|---|---|
| `Confirmado` | Pago aprobado y pedido registrado. |
| `En preparación` | Inventario reservado, verificación y empaque en curso. |
| `Despachado` | Paquete entregado al transportador. |
| `En tránsito` | Paquete en la red del transportador. |
| `Entregado` | Entrega registrada en el destino. |
| `Novedad` | Existe un evento que requiere seguimiento. |
| `Devuelto al origen` | El transportador devuelve el paquete a Nébula Tech. |

## 3. Tiempos estimados

Los tiempos de transporte se cuentan desde el despacho y se suman a la preparación de hasta 1 día hábil:

| Destino | Entrega estimada |
|---|---:|
| Bogotá, Medellín, Cali, Barranquilla y Bucaramanga | 2 a 4 días hábiles |
| Otras capitales departamentales | 3 a 6 días hábiles |
| Otros municipios y zonas rurales cubiertas | 5 a 10 días hábiles |

Para este servicio, los días hábiles no incluyen domingos ni festivos nacionales. La fecha es estimada, no una cita exacta. Temporadas de alta demanda, clima, orden público, cierres viales, restricciones de acceso o novedades del transportador pueden producir demoras.

## 4. Costos y envío gratuito

El checkout calcula el costo según destino, peso, dimensiones y condiciones de manejo. El valor mostrado antes de pagar es el aplicable al pedido.

El envío estándar es gratuito en compras desde COP 300.000 para destinos urbanos cubiertos. No aplica a productos sobredimensionados, de manejo especial ni a destinos que el checkout clasifique como remotos. Las promociones adicionales indicarán su vigencia y condiciones.

## 5. Empaque y despacho

Cada paquete se identifica con número de pedido y guía. Los dispositivos se protegen con material adecuado y, cuando corresponde, se registran sus seriales antes del despacho.

Después de entregar el paquete al transportador, Nébula Tech envía al correo del pedido el número de guía y el enlace de rastreo. La guía puede tardar hasta 1 día hábil en mostrar el primer movimiento.

## 6. Recepción segura

Al recibir el pedido, el cliente o la persona autorizada debe:

1. Revisar que el empaque corresponda al pedido.
2. Verificar si existen golpes, humedad, aperturas o sellos alterados.
3. Dejar constancia de una anomalía con el transportador cuando sea posible.
4. Conservar empaque, etiqueta y evidencia hasta confirmar que el contenido está completo y funciona.

El producto incorrecto, incompleto o con daño visible debe reportarse dentro de 5 días calendario desde la entrega a `soporte@nebulatech.example`, con fotografías o video del paquete, etiqueta, producto y serial.

## 7. Intentos de entrega

El transportador realiza hasta 2 intentos en la dirección registrada. Es responsabilidad del cliente suministrar una dirección completa, referencias útiles y un teléfono de contacto disponible.

Si ambos intentos fallan o la dirección es incorrecta, el paquete puede regresar a Nébula Tech. El reenvío exige confirmar la dirección y pagar un nuevo transporte, excepto cuando la falla sea atribuible a Nébula Tech o al transportador.

## 8. Cambio de dirección y cancelación

No se garantiza el cambio de dirección después de confirmar la compra. Mientras el pedido esté `Confirmado` o `En preparación`, el cliente puede solicitar cancelación a soporte y realizar una nueva compra con la dirección correcta.

Después del despacho no se modifica la ruta ni se cancela el tránsito. Si el cliente rechaza la entrega, la solicitud se resolverá cuando el paquete vuelva y pase la inspección definida en `politica_reembolsos_devoluciones.md`.

## 9. Novedades, pérdida o entrega no reconocida

Si el rastreo no cambia durante 3 días hábiles o marca una entrega no reconocida, el cliente debe escribir a soporte con número de pedido y guía. Nébula Tech abrirá una investigación con el transportador y comunicará el resultado disponible.

Cuando se confirme pérdida o una entrega incorrecta atribuible a la operación, Nébula Tech ofrecerá reposición sin costo o reembolso total, según inventario y elección disponible para el cliente.

## 10. Contacto

- Correo: `soporte@nebulatech.example`.
- Horario: lunes a viernes de 08:00 a 18:00 y sábados de 09:00 a 13:00, hora de Colombia (COT, UTC−5).
- Sin atención ordinaria: domingos y festivos.

Este documento es ficticio y de uso académico. Los procesos reales requerirían validación contractual, operativa y jurídica.
