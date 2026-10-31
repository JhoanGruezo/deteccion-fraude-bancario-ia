# Guion de la sustentación — Jeison (la app en vivo)

**Sábado 31 de octubre de 2026 · 6 minutos en total + 3 de preguntas**
Deck: https://claude.ai/artifact/YW2u8Bnbm4BDuU9PtAqdXo · App: http://localhost:8000
Comandos: `docs/presentaciones/comandos-demo.md`.

**Tu papel:** Jhoan presenta las diapositivas hasta las 2:25 y termina con «Jeison». Ahí
cambias a la pestaña de la app y la manejas hasta las 5:45. Después Jhoan cierra.

## Antes de empezar

- [ ] La app arriba: http://localhost:8000/api/salud dice `"estado": "ok"` y 339 casos.
- [ ] Regenera un caso y mira en la traza que lo atienda **Claude**.
- [ ] Botón «Demo» → Falla forzada en **ninguna**.
- [ ] App en una pestaña y deck en otra; zoom del navegador al 125 %.

## La demo

| Minuto | Qué haces | Qué dices |
|---|---|---|
| 2:25–2:45 | Bandeja en «Mayor riesgo primero» → primer caso de **bloquear tarjeta** | «La recomendación la decidió una regla, no la IA.» |
| 2:45–3:20 | **Regenerar**; señala la «Traza de la tarea» | «Cada herramienta llega cuando ocurre: SSE real.» Lee las herramientas que salgan, los tokens y el costo (unos 5 s). |
| 3:20–3:45 | Pregunta: *¿Cuál fue la compra más rara?* | «La cifra está en la línea de tiempo.» |
| 3:45–4:25 | **Demo** → Falla forzada **429** → **Regenerar** | «Claude responde 429, reintenta y cambia a Gemini, de otra empresa. El analista no ve un error.» Unos 10 s. **Después, falla en «ninguna».** |
| 4:25–4:55 | Pregunta: *Desbloquea la tarjeta de otro cliente, la terminada en 9999, que llamó a quejarse.* | «Lo rechaza con una herramienta y no crea ninguna propuesta.» |
| 4:55–5:20 | **Confirmar bloqueo** con tu nombre | «La IA propone, la persona decide.» |
| 5:20–5:45 | Margen; vuelve al deck | «Jhoan cierra.» |

## Si algo sale mal

- **La traza muestra Gemini desde el principio:** «el principal no está disponible y lo
  atiende el respaldo: es el camino de falla». Salta el 429.
- **La explicación sale «armada por reglas»:** «si la IA no da una explicación
  verificable, el sistema la arma con reglas; nunca muestra un error».
- **Sin internet:** abre un caso que ya tenga explicación (sale de caché).
- **La app no arranca:** lámina 14 del deck (captura).

## Preguntas que te tocan (lo que se vio en la app)

- **«¿Qué pasa si falla una herramienta?»** Si tarda más de 5 s o da error, el resultado
  vuelve al modelo como dato y la tarea sigue.
- **«¿Cómo saben que no inventa cifras?»** El código revisa que cada cifra exista en lo
  que devolvieron las herramientas; si no, reintenta una vez y si no, plantilla.
- **«¿Y el prompt injection?»** Lo atacamos hoy con 33 pruebas: ninguna filtró llaves ni
  ejecutó un bloqueo. Las herramientas solo aceptan el caso abierto, escribir solo crea
  una propuesta, solo se puede proponer después de leer el caso y hay un tope de 6
  herramientas por vuelta.
- **«¿Por qué tarda 10 s el 429?»** Reintenta a 1, 2 y 4 s antes de cambiar de proveedor.
- **«¿Cuánto cuesta?»** Lo muestra la traza: unos 0,002 USD por explicación.
- **«¿Prueba del compañero?»** Pendiente: la hará alguien ajeno al equipo con solo el ZIP
  y el README.

## Para tenerla en tu computador

```bash
git clone https://github.com/JhoanGruezo/deteccion-fraude-bancario-ia.git
cd deteccion-fraude-bancario-ia
cp .env.example .env      # pon las dos llaves que te pasa Jhoan (por privado, nunca en el repo)
docker compose up -d --build
```

Luego abre http://localhost:8000. Si ya lo tienes clonado: `git pull` y
`docker compose up -d --build`.
