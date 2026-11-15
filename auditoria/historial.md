# Historial de auditorías del proyecto de fraude

| Fecha | Corrida | Veredicto |
|---|---|---|
| 2026-10-24 | `auditoria/2026-10-24_1343/` | No listo (hoy): la llave de Anthropic inyectada no tiene formato válido (401, todo cayó a Gemini: suite 5/8, lote 78,9 %, no comparable con la línea base), llaves reales sin commitear en `docs/prueba-companero-jeison.txt`, prueba del compañero, suite verificada y ZIP final pendientes |
| 2026-11-14 | `auditoria/2026-11-14_m3/` | Listo con condiciones: el 71,4 % de fraude detenido no es defendible (el agente leía compras futuras, H1 y H2 confirmados; cifra defendible hoy 61,8 %), hay que corregir C1 (dominios en el aviso), C2 ("confirmar bloqueo" no bloquea) y A1 ("no fui yo" sin efecto), poner `docs/decisiones.md` al día y cerrar firmas, prueba con tercero y rotación de llaves |
