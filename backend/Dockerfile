# ---------- builder ----------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gfortran \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install --prefix=/install .

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime needs gfortran libs for clawpack
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY src/ ./src/

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "tsunami.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
