# Debian slim, igual familia que corre en Azure App Service Linux (ver
# documentacion/brief_infraestructura_carlos.md §3) — minimiza diferencias
# entre dev y producción. Versión confirmada contra el venv de desarrollo
# (python --version), no es un valor arbitrario.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libpq-dev + gcc: por si psycopg necesita compilar contra libpq en alguna
# plataforma donde no haya wheel binario disponible para psycopg-binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Dev: runserver con autoreload (el código se monta como volumen desde
# docker-compose.yml). Producción usará gunicorn — es un cambio de comando
# de despliegue, no de esta imagen base.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
