# Requisitos — persistencia

## Para qué existe

Hoy el motor deja los casos en archivos (`datos/salidas_<fuente>/`). La vista del
analista, el agente y la medición necesitan una base de datos que guarde los casos
con su evidencia, el historial de transacciones que el agente narra, las
explicaciones generadas (caché), las decisiones del analista y las trazas de cada
llamada. Está en el plan desde el 2026-10-09 (`decisiones.md`, paso 4) y la entrega
del Momento 2 exige que la base de datos se levante con `docker-compose` y scripts
de semilla o migraciones automáticas (`decisiones.md`, "Actualización 2026-10-21
(2)").

## Entradas

- `datos/salidas_sparkov/casos_marcados.json` y `datos/salidas_sinteticos/casos_marcados.json`
  (formato en `diseno/motor-riesgo.md`).
- Las transacciones previas de cada tarjeta con caso, para que el agente cuente "qué
  pasó" antes de la alerta (de `datos/fraudTest.csv`, `datos/fraudTrain.csv` y
  `datos/transacciones.csv`, ya traducidas por `src/cargar_datos.py`).
- `metricas_motor.json` de cada fuente (umbrales y modelo), para mostrarlos en la app.

## Salidas

Una base Postgres (contenedor de `docker-compose`) con, como mínimo:

- **casos**: id, fuente (`sparkov`/`sinteticos`), tarjeta, ventana, tipos de fraude,
  score máximo, nivel y motivo de la recomendación, señal principal, perfil previo,
  `fraude_confirmado_dataset` (oculto en la interfaz), estado (`pendiente`,
  `bloqueo_confirmado`, `descartado`, `escalado`).
- **transacciones del caso** con sus desviaciones (contribución, percentil,
  relevante).
- **historial**: transacciones previas de las tarjetas con caso, suficientes para el
  relato (al menos los 30 días anteriores a la ventana).
- **explicaciones**: por caso, el JSON validado que produjo el agente, proveedor y
  modelo, tokens, costo estimado, latencia, fecha, y si salió de la plantilla de
  respaldo. Varias versiones por caso (botón regenerar); la vigente es la última.
- **decisiones**: caso, acción, analista, comentario, fecha. Solo se escriben tras la
  confirmación humana.
- **trazas**: cada paso del agente (llamada al modelo, herramienta pedida, argumentos,
  resultado resumido, error, reintento, conmutación de proveedor, duración).

Una semilla que carga todo lo anterior al levantar el contenedor la primera vez, sin
pasos manuales.

## Criterios de aceptación

1. `docker compose up` deja la base lista con los casos de las dos fuentes cargados,
   sin comandos manuales, en una máquina sin el dataset de Kaggle descargado (la
   semilla viaja en el ZIP).
2. El número de casos y de transacciones cargados coincide con los JSON del motor
   (287 de Sparkov y 52 de sintéticos tras el cierre del motor del 2026-10-21, o los de la
   corrida vigente).
3. Para tres casos al azar, las desviaciones guardadas son idénticas a las del JSON
   (trazabilidad score → features → explicación).
4. Volver a levantar el contenedor no duplica datos.
5. La semilla cabe en el ZIP de entrega (el tamaño se reporta; sin los 500 MB de
   Kaggle).

## Casos borde

- Casos sin historial previo (tarjetas nuevas): el historial queda vacío y la app lo
  dice.
- Caso con viaje imposible y uso no autorizado a la vez.
- Una explicación que falló todas las veces: queda registrada la de plantilla, con la
  marca de respaldo.
- Decisión registrada dos veces sobre el mismo caso: gana la última, sin perder la
  anterior (queda el historial de decisiones).

## Fuera de alcance

- Reentrenar el modelo desde la app.
- Ingesta en tiempo real de transacciones nuevas.
- Usuarios y permisos (alcance del Momento 3).

## Preguntas abiertas

- Cuánto historial por tarjeta cabe en la semilla sin inflar el ZIP (se mide en
  diseño).
- Esquema SQL exacto, migraciones y forma de la semilla (SQL, CSV comprimido o script
  Python): diseño.
