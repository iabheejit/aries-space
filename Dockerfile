FROM python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" --uid 10001 missionops \
    && chown missionops:missionops /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=missionops:missionops alembic.ini ./alembic.ini
COPY --chown=missionops:missionops services ./services

USER missionops
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=12s --start-period=15s --retries=4 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=11)"

CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn services.api.aries_api.main:app --host 0.0.0.0 --port 8000 --workers 1"]