# Prueba con una persona ajena al equipo

> **Cómo quedó (2026-11-15).** La persona ajena al equipo que usa la app es el profesor: el 20-nov clona el repositorio y la prueba sin ayuda del equipo, y el 21-nov la ataca en la presentación (decisión del equipo, 2026-11-15). Esta hoja queda como el protocolo que sigue el equipo
> si alguien más prueba la app, y como guía de las tareas que el profesor puede intentar.

La rúbrica del Momento 3 pide que **alguien que no es del equipo** use la app sin que le expliquen
cómo. Esta hoja es para hacer esa prueba antes del 19-nov y dejarla registrada. Tarda unos 15 minutos.

## Reglas

- La persona no conoce el proyecto. Puede ser de otra carrera.
- Se le da **solo** el enunciado de cada tarea. No se le dice dónde hacer clic. Si pregunta, se
  anota la pregunta y se responde "¿dónde lo buscarías?".
- Un integrante observa y anota; el otro no interviene.
- Antes: `docker compose exec app python -m app.db.migrar --reiniciar-en-vivo`, el usuario
  `supervisor` con la sesión cerrada y la app en http://localhost:8000.

## Tareas (se leen en voz alta, una por una)

| # | Tarea | Se cumple si… |
|---|---|---|
| 1 | "Entra con este usuario y contraseña." (se le dan los de `supervisor`) | Entra sin ayuda |
| 2 | "Pon a correr las compras de la noche y dime cuándo el sistema bloquee la primera tarjeta." | Inicia el simulador y señala un bloqueo en "Decisiones recientes" |
| 3 | "¿Por qué se bloqueó esa tarjeta? Dímelo con tus palabras." | Encuentra el caso y explica al menos una razón con una cifra |
| 4 | "¿Qué mensaje le llegó al dueño de la tarjeta?" | Lo encuentra en el Buzón del titular |
| 5 | "El dueño llamó y dice que la compra sí fue él. Desbloquea la tarjeta." | Desbloquea escribiendo un motivo |
| 6 | "Haz que la IA deje de bloquear sola." | Apaga la autonomía en Supervisión |

## Registro

| Campo | Valor |
|---|---|
| Fecha y hora | |
| Persona (nombre y qué estudia o hace) | |
| Equipo donde se hizo (Windows/Mac) | |
| Observador | |

| # | ¿Lo logró? (sí / con ayuda / no) | Tiempo | Dudas o tropiezos (literal) |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |

**¿Qué le resultó confuso?** (pregunta final, se anota literal):

**Qué cambiamos por esta prueba** (llenarlo después; si no se cambia nada, decir por qué):
