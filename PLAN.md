# Plan del Momento 3

Especificación: `docs/SPEC.md`. Análisis que la sustenta: `docs/analisis-respuesta-fraude.md`.
Entrega: **jueves 19-nov, 23:59**. Presentación: **sábado 21-nov**. El 20-nov el profesor
clona el repositorio desde las 9:00 y lo prueba. El sábado 14-nov hay clase, con un reto
de diseño en grupo.

Reglas del plan:

- Una tarea se marca hecha solo con su verificación cumplida. Al marcarla se anota la fecha
  y una línea de qué quedó.
- Cada tarea termina con `pytest` en verde y un commit en la rama `momento3`. Antes de
  cada push se escanean llaves. **Nunca** `git add .` ni `-A`, porque
  `docs/prueba-companero-jeison.txt` tiene llaves.
- Reparto sugerido, el mismo de la guía de estudio: **Jeison** el motor, los datos y la
  medición; **Jhoan** el agente, la app y el frontend. Cada uno revisa lo del otro antes
  de la entrega.
- ⚠ marca las tareas de mayor riesgo técnico: se atacan primero dentro de su fase.

---

## Fase 0 · Análisis y acuerdos (8-nov)

- [x] **T0.1** Análisis de cómo se actúa (`docs/analisis-respuesta-fraude.md` +
      `scripts/analisis_ritmo_fraude.py`). 2026-11-08.
- [x] **T0.2** Especificación (`docs/SPEC.md`) y este plan. 2026-11-08.
- [ ] **T0.3** Subir ya una primera versión al aula virtual (el enlace del repo), para
      no depender del último día. *Lo hace una persona del equipo a mano.*

## Fase 1 · Seguridad base (9 y 10-nov)

Son cambios cortos que tapan lo primero que el profesor va a intentar, y no dependen
del resto.

- [x] **T1.1** Roles de Postgres con mínimo privilegio (RS3): `fraude_admin` migra,
      `fraude_app` con permisos por tabla, `fraude_agente` de solo lectura sin la etiqueta
      del dataset. Las herramientas del agente usan su propio pool.
      *Verifica:* pruebas que confirman que `fraude_agente` no puede leer la etiqueta ni
      escribir, y que la app sigue funcionando completa.
      2026-11-08: `app/db/roles.py` (contraseñas al azar en cada arranque, permisos de
      columna, nombres por base) y `app/db/repositorio_agente.py`. 19 pruebas nuevas; la
      app real explicó un caso con Claude leyendo con `fraude_agente`. **Ojo para T2.4:**
      `fraude_app` todavía no puede insertar en `historial` ni en `casos`.
- [x] **T1.2** Límite de peticiones por minuto por IP (y por usuario cuando haya sesión)
      y tope de gasto diario en USD que manda el triaje y las preguntas a la plantilla (RS5).
      *Verifica:* pruebas de 429 y de corte por gasto.
      2026-11-08: `app/api/limites.py` (agente 10/min, escritura 30/min, lectura 240/min,
      solo por IP hasta que exista sesión) y `TOPE_GASTO_DIARIO_USD` (2 USD por defecto).
- [x] **T1.3** Cabeceras de seguridad (CSP, nosniff, Referrer-Policy) y escáner de
      llaves ampliado a `apikey_…` y `AQ.…` en `empaquetar_entrega.py` (RS7, RS9).
      2026-11-08: CSP sin `unsafe-inline` (el script del tema pasó a `js/tema-inicial.js`),
      verificada en el navegador sin errores. El escáner ya detectaba los dos formatos: se
      comprobó con las llaves reales sin imprimirlas.

## Fase 2 · Motor en vivo (10 al 12-nov)

- [x] ⚠ **T2.1** Paquete del modelo en `semilla/` (con las versiones de scikit-learn y
      pandas fijadas) y dependencias en la imagen de la app.
      2026-11-08: `semilla/modelo_riesgo_sparkov.joblib` (excepción en .gitignore y
      .dockerignore), `src/` copiado a la imagen (726 MB).
- [x] ⚠ **T2.2** `app/riesgo/`: puntuar una transacción con el historial previo de la
      tarjeta, reutilizando `src/` (features, oclusión, desviaciones, viaje imposible).
      *Verifica:* paridad ≤ 0,001 con el score fuera de línea sobre una muestra de la
      partición de prueba; tiempo p99 medido.
      2026-11-08: perfil incremental por tarjeta (`perfil_incremental.py`, 15 pruebas de
      paridad feature por feature) y `motor_en_vivo.py`. Sobre 200 tarjetas y 111.342
      transacciones: 0 cambios de banda, 2 con diferencia > 0,001 por redondeo del motor
      fuera de línea (no de la app). Puntuar: mediana 1,8 ms, p99 2,7 ms; con señales,
      15,8 ms y 19,9 ms.
- [ ] **T2.3** Esquema: `transacciones_evaluadas`, `bloqueos`, `notificaciones`,
      `usuarios`, `sesiones`, `ajustes_sistema`; columnas y estados nuevos en `casos` y
      `tareas_agente` (migración idempotente, también sobre una base del M2).
- [ ] **T2.4** `POST /api/transacciones`: bandas (RF2), apertura del caso en la primera
      marca, suma a un caso abierto de 48 h y subida de banda.
      *Verifica:* pruebas de cada banda y de la subida de media a alta y a crítica.
- [ ] **T2.5** Semilla del simulador: un tramo nocturno de la partición de prueba con el
      historial de 30 días de esas tarjetas (`scripts/generar_semilla.py`).

## Fase 3 · Agente de triaje, red de seguridad y avisos (12 al 14-nov)

- [ ] ⚠ **T3.1** Modo `triaje` del agente: prompt, herramientas de acción con las seis
      guardas de RF3, tarea en segundo plano al abrir o subir de banda un caso.
      *Verifica:* una prueba por guarda (banda, otra tarjeta, tope, autonomía apagada,
      repetición, sin desbloqueo).
- [ ] **T3.2** Red de seguridad de 90 s (RF4) en un hilo propio de la app.
      *Verifica:* con todos los proveedores forzados a fallar, todo caso crítico queda
      bloqueado por la regla en ≤ 90 s.
- [ ] **T3.3** Avisos (RF5): plantilla, validación del motivo, directorio simulado,
      canal simulado, canal de correo con lista blanca y respuesta del titular.
      *Verifica:* pruebas de la validación (enlace, correo, teléfono, monto inventado).
- [ ] **T3.4** Desbloqueo humano (RF6) con motivo y medición del tiempo; interruptor de
      autonomía y tope por hora en `ajustes_sistema`.

## Fase 4 · Sesión y frontend (13 al 16-nov)

- [ ] **T4.1** Inicio de sesión, roles y CSRF (RF7), con credenciales generadas si no
      vienen en `.env`. *Verifica:* 401 y 403 en todas las rutas que escriben.
- [ ] **T4.2** Simulador (RF8): reproducción con reloj acelerado, pausa, velocidad,
      inyección manual y resumen final.
- [ ] **T4.3** Vistas nuevas: Ingreso, En vivo, Bloqueos, Buzón del titular y Supervisión
      (RF9).
- [ ] **T4.4** Bandeja y detalle con los estados, el actor, el aviso y el desbloqueo.
- [ ] **T4.5** Pulido visual de toda la app (claro y oscuro, estados vacíos, teclado,
      ancho de teléfono en el buzón).

## Fase 5 · Medición y ataques (15 al 17-nov)

- [ ] **T5.1** `eval/`: casos de triaje con decisión esperada verificada a mano y la
      comparación agente contra regla en la banda alta (prueba de necesidad, §7 del análisis).
- [ ] **T5.2** Ataques propios por comercio malicioso y por la API (formato del reto 12),
      con la traza completa y el antes y el después de cada defensa.
- [ ] **T5.3** Cifras finales de §7 de la SPEC contra la línea base, con fecha
      (`docs/decisiones/semana14.md`).
- [ ] **T5.4** Auditoría con los agentes `probador-fraude`, `validador-fraude` y
      `jefe-fraude`, y corrección de lo que encuentren.

## Fase 6 · Entrega (17 al 19-nov)

- [ ] **T6.1** `docs/seguridad.md`, `docs/gobernanza.md`, `docs/respuesta_auditoria.md`,
      `docs/decisiones.md`, README y guía de estudio actualizados, con los dos integrantes.
- [ ] **T6.2** Prueba de clon limpio sin `.env` y con solo la llave de Gemini; prueba con
      alguien ajeno al equipo, documentada.
- [ ] **T6.3** Rotar las llaves expuestas durante el desarrollo; ZIP, push a `main` y
      subida al aula virtual antes del jueves 19-nov a las 23:59.
- [ ] **T6.4** Guion de la demo del 21-nov: la app funcionando, sin diapositivas. Ataque
      en vivo, bloqueo nocturno sin analistas y desbloqueo. Ensayo de los dos.
