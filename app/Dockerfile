# Imagen de la app del analista (FastAPI + agente + frontend estático).
# Se construye con contexto en la raíz del proyecto (ver docker-compose.yml) porque
# necesita app/ y semilla/; .dockerignore deja fuera datos/ (los CSV de Kaggle).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Primero solo las dependencias: si cambia el código pero no requirements.txt, esta
# capa se reutiliza y la reconstrucción tarda segundos.
COPY app/requirements.txt app/requirements.txt
RUN pip install -r app/requirements.txt

COPY app/ app/
COPY semilla/ semilla/

# Usuario sin privilegios: la app no necesita ser root dentro del contenedor.
RUN useradd --create-home --uid 1000 analista
USER analista

EXPOSE 8000
CMD ["uvicorn", "app.principal:app", "--host", "0.0.0.0", "--port", "8000"]
