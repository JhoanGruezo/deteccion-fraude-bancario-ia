# Instrucciones para agentes de IA

Si viene a **instalar, probar o evaluar** este proyecto, siga `GUIA-PROFESOR.md`: tiene los
comandos en orden, el resultado esperado de cada uno y la lista de verificación (V1 a V7).

Lo esencial:

- Todo corre con Docker: `docker compose up --build -d` y luego http://localhost:8000.
- Antes del primer arranque, copie `.env.example` a `.env` y fije `SUPERVISOR_CLAVE` para no
  tener que leer la contraseña del registro. Las llaves de IA son opcionales: sin ellas la app
  funciona con la regla y la plantilla.
- Las pruebas corren dentro del contenedor:
  `docker compose exec app python -m pytest app/pruebas -q -p no:cacheprovider` (deben dar `281 passed, 1 skipped`).
- La API usa una cookie `sesion` y la cabecera `X-CSRF-Token` en cada POST (ver la guía, paso 7).
- No escriba llaves en ningún archivo que no sea `.env`, y no lo suba a git.

Si viene a **modificar el código**, lea primero `CLAUDE.md` (convenciones) y `docs/decisiones.md`
(por qué está hecho así).
