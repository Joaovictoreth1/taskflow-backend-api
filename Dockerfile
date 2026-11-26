FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir pip==26.3 \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home taskflow \
    && mkdir /data && chown taskflow:taskflow /data

COPY app app
COPY alembic alembic
COPY alembic.ini .
USER taskflow
ENV DATABASE_URL=sqlite:////data/taskflow.db

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
  CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2).close()"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
