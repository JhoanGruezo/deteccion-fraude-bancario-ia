#!/usr/bin/env bash
# Levanta todo el entorno con un solo comando: ./run.sh
#
# Existe porque la entrega del Momento 2 exige arrancar con un comando en menos de
# 5 minutos. Crea .env desde .env.example si falta, avisa si no hay llaves de IA (la
# app funciona igual con la explicación de plantilla), construye y levanta los
# contenedores, y espera a que /api/salud responda antes de mostrar la URL.
set -euo pipefail

cd "$(dirname "$0")"

URL="http://localhost:8000"
ESPERA_MAXIMA_S=180

if ! command -v docker >/dev/null 2>&1; then
    echo "No se encontró Docker. Instale Docker Desktop (o Docker Engine con compose) y vuelva a correr ./run.sh." >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "Docker está instalado pero no responde. Abra Docker Desktop, espere a que arranque y vuelva a intentar." >&2
    exit 1
fi

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Se creó .env a partir de .env.example."
fi

# Lee el valor de una variable de .env (sin comillas ni espacios); vacío si no está.
valor_env() {
    grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- | tr -d "\"' \r" || true
}

if [ -z "$(valor_env GEMINI_API_KEY)" ] && [ -z "$(valor_env ANTHROPIC_API_KEY)" ]; then
    echo "AVISO: .env no tiene GEMINI_API_KEY ni ANTHROPIC_API_KEY."
    echo "       La app arranca igual, pero las explicaciones saldrán de la plantilla (sin IA)."
    echo "       Para usar el agente, escriba al menos una llave en .env y vuelva a correr ./run.sh."
elif [ -z "$(valor_env ANTHROPIC_API_KEY)" ]; then
    # Orden por defecto (ORDEN_PROVEEDORES=claude,gemini): Claude es el principal.
    echo "AVISO: falta ANTHROPIC_API_KEY en .env; se usará solo Gemini (el respaldo)."
elif [ -z "$(valor_env GEMINI_API_KEY)" ]; then
    echo "AVISO: falta GEMINI_API_KEY en .env; no habrá proveedor de respaldo si Claude falla."
fi

echo "Construyendo y levantando los contenedores (la primera vez tarda un par de minutos)…"
docker compose up --build -d

echo -n "Esperando a que la app responda en $URL/api/salud "
inicio=$(date +%s)
while true; do
    if curl -fsS "$URL/api/salud" >/dev/null 2>&1; then
        echo " lista."
        break
    fi
    if [ $(( $(date +%s) - inicio )) -ge "$ESPERA_MAXIMA_S" ]; then
        echo
        echo "La app no respondió en ${ESPERA_MAXIMA_S} s. Últimas líneas del log:" >&2
        docker compose logs --tail=40 app >&2 || true
        exit 1
    fi
    echo -n "."
    sleep 2
done

echo
echo "Vista del analista: $URL"
echo "Para detener:        docker compose down"
