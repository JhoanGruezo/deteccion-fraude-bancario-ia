# Respuesta a la auditoría

Momento 3 · 2026-11-09 · Equipo: Jhoan David Gruezo Gutiérrez y Jeison Nazarit.

**Qué auditoría se responde.** En la clase 12 no se asignó una auditoría cruzada entre equipos, así
que este documento responde nuestras dos auditorías internas: la del 2026-10-31 y, al final, la del
2026-11-14. La del 2026-10-31, hecha antes de sustentar el
Momento 2 con tres auditores independientes (agentes con instrucciones de atacar, no de defender):
`auditoria/2026-10-31_demo/seguridad-app.md` (la app y la API), `seguridad-agente.md` (33 ataques
al agente) y `probador-interfaz.md` (la interfaz como la usaría un tercero). El profesor hará su
propia auditoría atacando la app el día de la presentación; lo que se espera de ella está cubierto
en `docs/seguridad.md` (12 ataques del Momento 3, resisten los 12).

Cada hallazgo tiene una de tres respuestas: **lo arreglamos** (con la evidencia), **lo asumimos**
(con el porqué y la mitigación) o **no estamos de acuerdo** (con el argumento).

## App y API (`seguridad-app.md`)

| Hallazgo | Respuesta | Evidencia |
|---|---|---|
| **A1** (alto) Llaves reales en un archivo del repo público | **Lo arreglamos** en el repositorio y **falta rotar** | La versión versionada de `docs/prueba-companero-jeison.txt` no tiene llaves (verificado en el historial); la copia local queda con `skip-worktree`. El escáner del ZIP detecta los formatos `sk-ant-`, `AQ.Ab` y `apikey_`. Las llaves usadas en el desarrollo se rotan antes de entregar (acción manual del equipo en las consolas de Anthropic y Google) |
| **A2** (alto) App en todas las interfaces, sin autenticación y con el panel de demo abierto | **Lo arreglamos** | Solo 127.0.0.1; sesión obligatoria; panel de fallas solo para supervisor (`app/api/sesion.py`; pruebas en `test_sesion.py`) |
| **M1** CSRF | **Lo arreglamos** | Token CSRF por sesión en cabecera, cookie SameSite=Strict (ataque A9: 403) |
| **M2** Identidad del analista autodeclarada | **Lo arreglamos** | Inicio de sesión con roles; decisiones y desbloqueos firmados por la sesión, ignorando el nombre del cuerpo (`test_la_decision_queda_firmada_por_la_sesion_y_no_por_el_cuerpo`) |
| **M3** Gasto del LLM y fallas forzadas sin límite | **Lo arreglamos** | Límite por minuto, tope de gasto diario, `?falla=` solo supervisor (`test_auditoria_m3_…`) |
| **B1** Byte NUL produce 500 | **Lo arreglamos** | 422 (`test_auditoria_b1_…`) |
| **B2** Comodines de LIKE sin escapar | **Lo arreglamos** | Escapados (`test_auditoria_b2_…`) |
| **B3** `/docs` público | **Lo arreglamos** | Apagado por defecto (`DOCS_API`) |
| **B4** Sin cabeceras de seguridad | **Lo arreglamos** | CSP sin `unsafe-inline`, `frame-ancestors 'none'`, nosniff, Referrer-Policy (`test_cabeceras_de_seguridad_…`) |
| **B5** Dependencias transitivas sin fijar; Starlette 0.46 con aviso de DoS por `Range`; pytest en la imagen | **Arreglamos** la fijación y **asumimos** el resto | `app/restricciones.txt` fija las 36. Subir Starlette exige otra versión mayor de FastAPI a días de la entrega; el riesgo es una denegación de servicio sobre una app que solo escucha en 127.0.0.1. pytest queda en la imagen porque las pruebas se corren dentro del contenedor |
| **B6** Sin tope de tamaño de cuerpo | **Lo arreglamos** | 413 sobre 64 KB (`test_auditoria_b3_y_b6_…`) |
| **B7** Ignorados incompletos | **Lo arreglamos** | `.env.*` en `.gitignore` y `.dockerignore`; `docs/` fuera del contexto de build |

## Agente (`seguridad-agente.md`: 27 resisten, 5 parciales, 1 falla)

| Hallazgo | Respuesta | Evidencia |
|---|---|---|
| **H1** (A23, falla) El presupuesto de tokens se rebasaba pidiendo 30 herramientas en una vuelta | **Lo arreglamos** (31-oct) | Tope de 6 herramientas por iteración (`MAX_HERRAMIENTAS_POR_ITERACION`; `test_tope_de_herramientas_por_iteracion_…`) |
| **H2** (A29) `registrar_decision` aceptaba un argumento dictado sin consultar el caso | **Lo arreglamos** (31-oct) | Toda herramienta que escribe exige `obtener_caso` antes, y ahora aplica también a bloquear (`test_sin_leer_el_caso_no_puede_bloquear`) |
| **H3** (A19) Bajo presión recomendaba una acción distinta de la regla | **Lo asumimos** | Es una opinión en el chat, no una acción: el agente de preguntas no puede escribir decisiones ni bloquear |
| **H4** (A16) Pedir otra acción no quedaba como rechazo | **Lo asumimos** | Igual que H3: sin efecto sobre el caso |
| **H5** (A22, A28) Responde en inglés si se lo piden | **Lo asumimos** | El idioma no cambia ninguna acción. En el triaje se agregó la regla 9 del prompt porque el resumen salió en inglés en la primera prueba real |

## Interfaz (`probador-interfaz.md`)

| Hallazgo | Respuesta | Evidencia |
|---|---|---|
| **G1** El panel describía la falla 429 al revés | **Lo arreglamos** | Texto neutral: "el proveedor principal" / "el de respaldo" |
| **G2** El nombre del analista quedaba guardado en el navegador | **Lo arreglamos** | El campo desapareció: firma la sesión y se borra la clave vieja del almacenamiento |
| **G3** Errores de interpretación que el validador no detecta | **Lo asumimos** | Las cifras se validan contra la evidencia; la interpretación no se puede validar del todo. Lo que importa en el Momento 3 (el bloqueo) no depende de la redacción |
| **M1** Jerga de Sparkov (`shopping_net`) | **Arreglado en lo que lee el cliente; asumido en la vista del analista** | El aviso al titular nombra la categoría en español. En la vista del analista los códigos siguen apareciendo en algunas explicaciones guardadas |
| **M2** Casos con score 0,00 que recomiendan bloquear el acceso | **No estamos de acuerdo** con que sea un error | Son alertas de viaje imposible: las decide una regla determinista, no el modelo, y la interfaz lo dice. En Sparkov ya no abren casos en vivo porque su geografía es falsa (decisión del 21-oct) |
| **M3** Umbrales iguales en los datos sintéticos (0,82 y 0,82) | **Lo asumimos** | Es el resultado de elegir umbrales por F1 en un conjunto pequeño; la demo y la medición usan Sparkov (0,95 y 0,97) |
| **M4**, **M6** "Peso" y TTFT poco intuitivos | **Lo asumimos** | Son correctos y están explicados en la documentación |
| **M5** Métricas con etiquetas crudas | **Lo arreglamos** | Todas las claves del panel tienen nombre en español (`etiquetaMetrica` en `app/web/js/principal.js`) |
| **O3** "bloqueo de el acceso" | **Lo arreglamos** | El diálogo dice "del acceso" (`app/web/js/detalle.js`) |
| **O1**, **O2**, **O4** Ventana que se lee raro, palabra suelta en la señal principal, ciudades sin tilde | **Lo asumimos** | Detalles de presentación; las ciudades vienen así del dataset. Ninguno cambia una cifra ni una decisión |

## Pendiente que depende del equipo

1. **Rotar las llaves de IA** usadas durante el desarrollo, antes del 19-nov.
2. Ninguno más del lado de la auditoría interna. La auditoría del profesor se responde en vivo con
   `docs/seguridad.md` y, si encuentra algo, se agrega aquí después de la presentación.

## Auditoría interna del 2026-11-14 (`auditoria/2026-11-14_m3/`)

Cinco auditores en paralelo (pruebas en vivo, seguridad en vivo, motor y medición, agente y backend,
documentos y entrega) y un auditor jefe que volvió a comprobar lo más grave. Veredicto: listo con
condiciones. Respondida el 2026-11-15:

| Hallazgo | Respuesta | Evidencia |
|---|---|---|
| **H1** (crítico) El agente veía compras posteriores durante la medición | **Lo arreglamos** y **retiramos la cifra** | Historial cortado en la última compra recibida (`test_el_historial_de_un_caso_en_vivo_no_muestra_compras_futuras`); 71,4 % retirado; nueva medición en `docs/decisiones.md` §13.1: 76,1 % con más bloqueos falsos |
| **H2** (crítico) La simulación a 3600x también filtraba | **Lo arreglamos** | Reloj del dataset detenido durante cada triaje (`test_con_esperar_triajes_…`) |
| **C1** (crítico) El aviso dejaba pasar dominios fuera de 15 terminaciones | **Lo arreglamos** | 4 motivos nuevos en `test_un_motivo_malicioso_no_llega_al_titular` |
| **C2** (crítico) "Confirmar bloqueo" no bloqueaba en vivo | **Lo arreglamos** | `test_confirmar_bloqueo_de_un_analista_bloquea_de_verdad` |
| **A1** (alto) "No fui yo" sin efecto | **Lo arreglamos** | `test_no_fui_yo_bloquea_la_tarjeta_aunque_el_caso_estuviera_descartado` |
| **A2** (alto) Dos bloqueos y tres avisos en un triaje | **Lo arreglamos** | `test_un_triaje_bloquea_y_avisa_una_sola_vez` |
| **A3** (alto) Descartar sin motivo apagaba la red de seguridad | **Lo arreglamos** | `test_descartar_un_caso_en_vivo_exige_motivo_y_no_sirve_para_desbloquear` |
| **A6** (alto) La recomendación del M2 sesgaba el triaje | **Lo arreglamos** | `test_en_el_triaje_el_agente_no_ve_la_recomendacion_del_momento_2`; sin ese sesgo el agente bloquea más, y la medición nueva lo muestra |
| **A4** (alto) No hay plazo total por tarea; con la cola llena un bloqueo tardó 137 s | **Lo asumimos** | Cada llamada tiene timeout y la tarea tiene 6 iteraciones; en la medición limpia el máximo fue 53 s desde la apertura del caso. La meta es 5 minutos |
| **A5** (alto) Un reinicio pierde los triajes en curso | **Lo asumimos** | La red de seguridad vuelve a revisar los críticos al arrancar; los casos de banda alta quedan en la cola humana |
| **H3** (alto) Una sola noche, 9 tarjetas | **Lo asumimos y lo declaramos** | Intervalos de confianza en `docs/decisiones.md` §13.1 |
| **H4** (medio) La regla de comparación es débil | **Lo asumimos y lo declaramos** | El modelo sigue ganando contra una regla de dos umbrales ajustada (F1 0,811 contra 0,424) |
| **B-1** (bajo) Un analista lee la vista Supervisión | **No estamos de acuerdo** | Es solo lectura a propósito: `docs/seguridad.md` §6 |
| **B-2** (bajo) Bloquear el ingreso de otro usuario con 5 intentos | **Lo asumimos** | `docs/seguridad.md` §6 |
| Límite por IP compartido detrás de Docker | **Lo arreglamos** | Cupo por sesión y por IP (`test_el_limite_es_por_sesion_y_un_abusador_no_frena_a_los_demas`) |
| `run.ps1` abortaba en PowerShell 5.1 | **Lo arreglamos** | Probado en Windows PowerShell 5.1 el 2026-11-15 |
| Documentos del M2 (`decisiones.md`, `comandos-demo.md`) | **Lo arreglamos** | `docs/decisiones.md` §1, §2, §6, §11, §13 y §14 |
| Casos dorados sin firmar, prueba con un tercero, llaves sin rotar | **Pendiente del equipo** | Antes del 19-nov |

