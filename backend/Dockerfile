# ---------- builder ----------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gfortran \
    && rm -rf /var/lib/apt/lists/*

# Copy source and install the package + all deps
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --upgrade pip \
    && pip install .

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

# Copy all installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "tsunami.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
