FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY benchmarks ./benchmarks

RUN pip install --no-cache-dir .

CMD ["python3", "-m", "app.runtime", "api"]
