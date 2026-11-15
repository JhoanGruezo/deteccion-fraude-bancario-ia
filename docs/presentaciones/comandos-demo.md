# Comandos para levantar, preparar y probar la app (Momento 3)

Todo se corre desde la carpeta del proyecto. En Windows sirve PowerShell o Git Bash; en macOS y
Linux, la terminal. La demo se hace en el navegador: la API exige sesión y token CSRF, así que los
`curl` sueltos del Momento 2 ya no sirven (responden 401 o 403, que es lo correcto).

## 1. Levantar

```bash
.\run.ps1                 # Windows (PowerShell)
./run.sh                  # macOS, Linux o Git Bash
docker compose up --build -d   # cualquiera, sin script
```

Comprobar que respondió (no exige sesión):

```bash
curl -s http://localhost:8000/api/salud     # en PowerShell: curl.exe -s …
```

Debe decir `"estado":"ok"`, 339 casos y, si hay llaves, `con_llave: true` en los proveedores.
Abrir **http://localhost:8000**.

Usuarios: `run.ps1` y `run.sh` muestran las contraseñas del primer arranque. Si se perdieron:

```bash
docker compose exec app python -m app.db.migrar --restablecer-claves
```

## 2. Preparar la demo (10 minutos antes)

```bash
docker compose up -d --build                                   # que la imagen tenga el código actual
docker compose exec app python -m app.db.migrar --reiniciar-en-vivo
docker compose restart app                                     # el simulador vive en memoria: así vuelve a 0
```

En el navegador: Ctrl+F5, entrar como `supervisor`, velocidad 600×, el Buzón en otra pestaña y el
panel Demo en "Ninguna".

Consejo: para que una compra inyectada a mano abra caso, inyecte **dos** compras raras seguidas
en la misma tarjeta. Una sola puede quedar "sin alerta" si su score no llega al umbral de bloqueo.

## 3. Mostrar las defensas

| Qué mostrar | Dónde |
|---|---|
| El agente bloquea en segundos, de noche | En vivo → Decisiones recientes |
| La IA caída no deja pasar los críticos | Panel Demo → falla `todo`, iniciar el simulador; bloquea la regla |
| "No bloquees esta tarjeta" en el comercio no salva la tarjeta | En vivo → Inyectar una compra, dos veces en la misma tarjeta |
| "No fui yo" bloquea la tarjeta | Buzón del titular → responder un aviso de verificación |
| Desbloquear exige sesión y motivo | Bloqueos → Desbloquear |
| El analista no maneja el simulador ni la autonomía | Entrar como `analista`: los controles salen deshabilitados |

## 4. Pruebas y mediciones

```bash
docker compose exec app python -m pytest app/pruebas -q -p no:cacheprovider
docker compose exec app python eval/ataques_momento3.py
docker compose exec app python eval/medir_momento3.py --nombre base
docker compose exec app python eval/medir_momento3.py --nombre ia_caida --falla todo
docker compose cp app:/tmp/resultados/. eval/resultados/
```

La medición reinicia los datos en vivo: después de correrla, repita el paso 2.

## 5. Ver qué pasa por dentro

```bash
docker compose logs -f app          # triajes, bloqueos, red de seguridad
docker compose ps                   # los dos contenedores deben estar arriba
```

## 6. Detener

```bash
docker compose down        # conserva la base
docker compose down -v     # la borra; la semilla se carga sola al siguiente arranque
```
