FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY benchmarks ./benchmarks
COPY scripts ./scripts
COPY requirements-training.txt ./requirements-training.txt

RUN pip install --no-cache-dir .

FROM base AS training-runtime

RUN pip install --no-cache-dir -r requirements-training.txt

FROM base

CMD ["python3", "-m", "app.runtime", "api"]
