# Ficha de gobernanza del sistema de detección y bloqueo de fraude

Momento 3 · 2026-11 · Equipo: Jhoan David Gruezo Gutiérrez y Jeison Nazarit.
Diseño completo en `docs/SPEC.md` y por qué se diseñó así en `docs/analisis-respuesta-fraude.md`.

## 1. ¿Qué decide el sistema solo?

| Decisión | Quién la toma | Por qué puede hacerlo solo |
|---|---|---|
| El riesgo de cada compra (score) y su banda | Modelo de ML + reglas en código, en ~2 ms, sin LLM | Es la parte que tiene que responder antes de la siguiente compra del ladrón |
| Abrir un caso desde la **primera** compra sospechosa | Código | Esperar la segunda dejaba pasar el 13 % del monto (análisis, §2) |
| **Bloquear una tarjeta en banda crítica** (≥ 2 compras sobre el umbral, o viaje imposible) | El agente LLM si responde; si no, la regla en el acto o a los 90 s | El 88 % del fraude empieza de noche, sin analistas; bloquear a los 5 min pierde 7,8 % y a las 24 h, 58,2 % |
| **Bloquear en banda alta** (una compra sobre el umbral) | El agente LLM, leyendo la secuencia del caso | Es la zona gris donde la regla solo sabía decir "verificar"; se mide contra la etiqueta (prueba de necesidad) |
| Pedir verificación al titular | El agente, o la regla si el agente falla | No mueve dinero ni bloquea nada |
| El texto del aviso al titular | Plantilla fija del código + el motivo que redacta el agente, validado | El motivo es lo único libre; el destinatario y el resto del mensaje los pone el código |

**Lo que el bloqueo es y no es:** es **protector y reversible** (la tarjeta deja de autorizar
compras; nada se cobra ni se devuelve) y está previsto por la norma (Circular Básica Jurídica de la
Superfinanciera, procedimientos de bloqueo "cuando existan situaciones o hechos que lo ameriten").
Por eso puede ser automático. Lo irreversible no lo hace el sistema: no mueve dinero, no borra
datos, no cierra cuentas.

## 2. ¿Qué necesita a un humano, y quién?

| Acción | Quién | Cómo lo **exige el sistema** (no el prompt) |
|---|---|---|
| **Desbloquear** una tarjeta (reabrirla al riesgo) | Analista o supervisor con sesión | Ninguna herramienta del agente desbloquea; la ruta exige sesión, token CSRF y un motivo escrito de ≥ 10 caracteres; queda firmada con el usuario (`app/api/rutas_operacion.py`) |
| Confirmar, descartar o escalar un caso | Analista o supervisor con sesión | El agente solo crea propuestas; la decisión la escribe la API con la firma de la sesión |
| Apagar la autonomía del agente / cambiar su tope de bloqueos por hora | Supervisor | Rol verificado en el servidor; los analistas reciben 403 |
| Atender las alertas (tope alcanzado, red de seguridad que actuó) | Supervisor | Vista Supervisión |
| Repetir la demo desde cero, restablecer contraseñas | Quien opera el servidor | Comando con el usuario dueño de la base; no existe por HTTP |

El titular de la tarjeta participa: responde "fui yo" o "no fui yo". "Fui yo" no desbloquea solo
(quien tiene el teléfono podría ser el ladrón): sube el caso al primer lugar de la cola de desbloqueo.
"No fui yo" bloquea la tarjeta si todavía no estaba bloqueada: el titular sabe más que cualquier score.

## 3. ¿Qué queda registrado, dónde y cuánto tiempo?

En Postgres, sin borrado desde la app (el rol de la app no tiene permiso DELETE en ninguna tabla):

- cada compra evaluada con su score, banda, decisión y tiempo (`transacciones_evaluadas`);
- cada tarea del agente con su costo, proveedor y cada paso de su traza (`tareas_agente`, `trazas`);
- cada bloqueo con su actor (agente, regla o analista), motivo, tiempo hasta el bloqueo y quién lo
  levantó y por qué (`bloqueos`);
- cada aviso con lo que escribió el agente, lo que salió de verdad y por qué se rechazó si se
  rechazó (`notificaciones`); cada decisión y cada alerta.

**Retención propuesta:** 5 años para bloqueos, avisos y decisiones (soporte ante una reclamación
del cliente o de la Superfinanciera); 12 meses para las trazas completas del agente. En este
proyecto académico no hay borrado automático; queda como pendiente de operación.

## 4. ¿Qué datos toca y cuáles salen a un tercero?

- **Lee:** compras, perfil e historial de la tarjeta del caso abierto, con un usuario de Postgres
  de **solo lectura** que no puede ver la etiqueta del dataset.
- **Sale al proveedor del LLM** (Anthropic o Google): montos, fechas, comercios, categorías, ciudad,
  señales del modelo y la tarjeta **enmascarada** (`**** **** **** 1234`). No salen nombres, número
  completo de tarjeta, contactos del titular ni datos de otros clientes. El agente no tiene acceso a
  internet ni a otros sistemas.
- **Sale al titular:** el aviso (plantilla + motivo validado), por el buzón simulado. Si se activa el
  correo, solo hacia la lista blanca `CORREOS_PERMITIDOS`.
- Ley 1581 de 2012 (habeas data): los datos de este proyecto son sintéticos (Sparkov); con datos
  reales haría falta el acuerdo de transmisión con el proveedor del LLM.

## 5. ¿Qué hacemos si causa un daño?

| Daño posible | Cómo nos enteramos | Qué hacemos |
|---|---|---|
| El agente bloquea de más (falsos bloqueos) | Vista Supervisión: bloqueos por agente vs. regla, alerta de tope por hora | El supervisor apaga la autonomía (un clic): todo pasa a la cola humana y la regla sigue bloqueando solo los casos críticos. Los analistas desbloquean con motivo; el tiempo hasta el desbloqueo se mide |
| Ataque de inyección por los datos | Trazas del triaje y avisos con `errores_validacion` | Las guardas lo contienen (ver `docs/seguridad.md`); se revisa la traza y se agrega el caso a `eval/` |
| Un cliente reclama por un bloqueo | Respuesta "fui yo" en el buzón; línea oficial | Desbloqueo prioritario; la traza muestra quién bloqueó, por qué y en cuánto tiempo |
| Costo descontrolado del LLM | Gasto del día vs. tope en Supervisión | El tope diario corta el LLM solo; la regla y la plantilla siguen funcionando |
| El proveedor del LLM cae | Proveedor y respaldo visibles en la cabecera | Cascada a Gemini y, si cae todo, regla + plantilla: el bloqueo de los críticos no depende de la IA |

Responsables: el supervisor de turno opera los controles; el equipo (Jhoan y Jeison) mantiene el
sistema y revisa las trazas de cada incidente.
