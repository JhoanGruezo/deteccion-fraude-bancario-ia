# Informe del probador — corrida 2026-10-24_1343

Fecha: 2026-10-24, 13:43 a 13:55 (hora de Colombia). La app ya estaba corriendo (no la levanté ni la toqué). Docker OK, contenedores `app` y `db` arriba, `/api/salud` ok con 339 casos. Variables de llave presentes: ANTHROPIC_API_KEY sí, GEMINI_API_KEY sí (no se imprimió ningún valor).

**Hallazgo central: la llave de Anthropic está presente pero Anthropic la rechaza (HTTP 401 `authentication_error: invalid x-api-key`).** `/api/salud` reporta `con_llave: true` porque solo comprueba que exista. Toda la corrida se sirvió con Gemini 3.1 Flash-Lite vía conmutación; Claude Haiku 5.5 nunca respondió. Por eso las cifras NO son comparables con la línea base (que fue Claude principal).

| Prueba | Comando | Resultado | Detalle | Log |
|---|---|---|---|---|
| Entorno | docker info / compose ps / curl salud | PASA | app y db arriba, db healthy | logs/entorno.txt |
| Unitarias | `docker compose exec -T app python -m pytest app/pruebas -q` | PASA | 136 aprobadas, 0 fallidas, 1 omitida (`test_plantilla.py:93`, faltan `casos_marcados.json` dentro del contenedor), 0 errores | logs/pytest.txt |
| API básica | curl salud, lista, detalle, inexistente | PASA | 200/200/200; 404 con mensaje en español para caso inexistente. `contadores.total` = 339 (la lista devuelve 300 por paginación) | logs/api.txt |
| Suite dorada | `python eval/correr_suite.py` | FALLA | 5 de 8. D1 timeout y plantilla (111,9 s); D2 no menciona 62,83; D6 no menciona 1.038,53. Antes: 8 de 8. Sigue sin verificación humana | logs/suite.txt, eval/resultados/suite_2026-10-24_1344.* |
| Lote | `python eval/correr_lote.py` | FALLA (cifras peores que la base) | ver tabla | logs/lote.txt, eval/resultados/lote_2026-10-24_1351.* |
| Fallas forzadas | cubiertas por L16 a L19 del lote | PASA | 429, timeout, json y todo terminaron con explicación válida; sin stack trace crudo. `falla_forzada` vacío al final (verificado con curl) | lote.txt |
| Rechazo | D7 y D8 de la suite | PASA | ambos con `declarar_fuera_de_alcance`, sin propuesta | suite.txt |

## Cifras recalculadas desde `lote_2026-10-24_1351.json`

| Cifra | Línea base 2026-10-21 | Nueva | Diferencia |
|---|---|---|---|
| Tasa de éxito | 94,7 % (18/19) | 78,9 % (15/19) | -15,8 pts (sin caché: 76,9 % base 92,3 %, 10/13) |
| Costo mediano por tarea | 0,001481 USD | 0,002714 USD | +83 % |
| Latencia mediana / P90 | 5,8 s / 17,1 s | 26,0 s / 54,4 s | +20,2 s / +37,3 s (TTFT mediano 17,0 s vs 0,80 s) |
| Recuperación | 100 % (4/4) | 100 % (4/4 forzadas; 13/13 contando fallos reales) | sin cambio |

Medianas recalculadas por mí sobre las 13 tareas no servidas desde caché; coinciden con las del script. El P90 es el interpolado del script (54,4 s); un cálculo por rango más simple daría 43,6 s. Costo total del lote 0,035 USD; suite aprox. 0,02 USD. Total aprox. 0,055 USD (los dos con Gemini).

## Problemas encontrados

1. **Llave de Anthropic inválida** (401 en cada llamada, 8 de 8 en los logs de la suite, y en la traza de cada tarea del lote). Evidencia: `lote_2026-10-24_1351.json`, traza de L03, evento `conmutacion` motivo `autenticacion`. Cada tarea gasta un salto fallido más la conmutación.
2. **Salud engañosa**: `/api/salud` marca `con_llave: true` con una llave rechazada.
3. **Gemini lento e inestable**: hubo 503 en los logs; D1 (suite) y L04 (D4, lote) terminaron en timeout y plantilla (111 a 123 s). L06/D6 y D2 no citan cifras esperadas (1.038,53 y 62,83), lo que puede ser calidad de Gemini y no del agente; no lo verifiqué.
4. **Un 429/timeout "real" no se distingue del forzado** en el conteo de recuperación: 13/13 mezcla conmutaciones por 401 con fallas forzadas.
5. La prueba omitida de pytest depende de datos del motor no presentes en el contenedor.

No modifiqué código ni documentos. Nota para el caller: para una medición comparable hace falta una llave válida de Anthropic y repetir suite y lote.
