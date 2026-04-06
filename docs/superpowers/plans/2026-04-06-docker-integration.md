# Docker + Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Containerise the full tsunami simulation stack — FastAPI backend, Celery worker, Redis, and React/Nginx frontend — with a single `docker compose up` that brings everything up and wires the services together.

**Architecture:** Four containers share a bridge network. The frontend Nginx container proxies `/api` to the backend, eliminating CORS configuration in development. The backend and worker share one image (built from `backend/`); only the startup command differs. Redis is the Celery broker. SQLite lives on a named volume so data survives restarts.

**Tech Stack:** Docker (multi-stage builds), Docker Compose v2, Python 3.12-slim, Node 22-alpine, nginx:alpine, redis:7-alpine

---

## File Structure

```
backend/
└── Dockerfile

frontend/
├── Dockerfile
└── nginx.conf

docker-compose.yml
```

---

## Task 1: Backend Dockerfile

**Goal:** Multi-stage image — builder installs Python deps, runtime is lean.

- [ ] Create `backend/Dockerfile` with the following content:

```dockerfile
# ---------- builder ----------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools needed by some C-extension deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Install deps into an isolated prefix so we can copy only them to runtime
RUN pip install --upgrade pip \
    && pip install --prefix=/install .

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY src/ ./src/

# SQLite data directory (overridden by volume in compose)
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "tsunami.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] Verify the file was created: `ls -lh backend/Dockerfile`
- [ ] Build and confirm it succeeds:

```bash
docker build -t tsunami-backend backend/
```

Expected output ends with:
```
=> exporting to image
...
Successfully tagged tsunami-backend:latest
```

---

## Task 2: Frontend Dockerfile + Nginx config

**Goal:** Node build stage compiles the Vite app; Nginx serves the static bundle and reverse-proxies `/api` to the backend service.

- [ ] Create `frontend/nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Reverse proxy API calls to the backend service
    location /api/ {
        proxy_pass         http://backend:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }

    # WebSocket upgrade for /ws/* paths
    location /ws/ {
        proxy_pass         http://backend:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
    }

    # SPA fallback — serve index.html for unknown routes
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] Create `frontend/Dockerfile`:

```dockerfile
# ---------- build ----------
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN npm ci --legacy-peer-deps

COPY . .
RUN npm run build

# ---------- serve ----------
FROM nginx:alpine AS serve

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/app.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

- [ ] Verify both files: `ls -lh frontend/Dockerfile frontend/nginx.conf`
- [ ] Build and confirm it succeeds (requires `frontend/` to exist from Plan 3):

```bash
docker build -t tsunami-frontend frontend/
```

Expected: image tagged `tsunami-frontend:latest` with no errors.

---

## Task 3: docker-compose.yml

**Goal:** Single compose file starts all four services with correct dependencies, volumes, ports, and environment variables.

- [ ] Create `docker-compose.yml` in the repo root:

```yaml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    networks:
      - tsunami-net
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: backend
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_healthy
    environment:
      TSUNAMI_REDIS_URL: redis://redis:6379/0
      TSUNAMI_DATABASE_URL: sqlite+aiosqlite:////app/data/tsunami.db
    volumes:
      - backend-data:/app/data
    networks:
      - tsunami-net
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s

  worker:
    build:
      context: backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: >
      celery -A tsunami.workers.celery_app:celery_app worker
      --loglevel=info --concurrency=2
    depends_on:
      redis:
        condition: service_healthy
    environment:
      TSUNAMI_REDIS_URL: redis://redis:6379/0
      TSUNAMI_DATABASE_URL: sqlite+aiosqlite:////app/data/tsunami.db
    volumes:
      - backend-data:/app/data
    networks:
      - tsunami-net

  frontend:
    build:
      context: frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "3000:80"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - tsunami-net

volumes:
  backend-data:

networks:
  tsunami-net:
    driver: bridge
```

- [ ] Verify the file: `cat docker-compose.yml`
- [ ] Validate compose syntax (requires Docker Compose v2):

```bash
docker compose config --quiet
```

Expected: exits 0 with no errors.

---

## Task 4: Integration Verification

**Goal:** Confirm all services start cleanly and the full request path works end-to-end.

- [ ] Build all images:

```bash
docker compose build
```

Expected: all four services build without errors; output ends with `[+] Building ... FINISHED`.

- [ ] Start the stack in detached mode:

```bash
docker compose up -d
```

Expected:
```
[+] Running 4/4
 ✔ Container tsunami-redis-1    Started
 ✔ Container tsunami-backend-1  Started
 ✔ Container tsunami-worker-1   Started
 ✔ Container tsunami-frontend-1 Started
```

- [ ] Confirm all containers are healthy:

```bash
docker compose ps
```

Expected: all four services show `running` (backend and redis show `healthy` once their healthchecks pass within ~30 s).

- [ ] Check backend health endpoint:

```bash
curl -s http://localhost:8000/api/health
```

Expected:
```json
{"status": "ok"}
```

- [ ] Check frontend is reachable:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

Expected: `200`

- [ ] Verify Nginx proxies `/api` through the frontend port:

```bash
curl -s http://localhost:3000/api/health
```

Expected:
```json
{"status": "ok"}
```

- [ ] Create a simulation via the API to exercise backend + worker + Redis:

```bash
curl -s -X POST http://localhost:8000/api/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Docker integration test",
    "earthquake": {
      "latitude": 35.0,
      "longitude": 139.0,
      "depth_km": 10.0,
      "magnitude": 8.0,
      "strike": 200,
      "dip": 15,
      "rake": 90
    },
    "region": {
      "lat_min": 30.0, "lat_max": 40.0,
      "lon_min": 135.0, "lon_max": 145.0
    }
  }'
```

Expected: JSON response containing `"id"` and `"status": "pending"` (or `"running"`).

- [ ] Check worker logs to confirm task was picked up:

```bash
docker compose logs worker --tail 20
```

Expected: lines like `Task tsunami.workers... received` and `Task ... succeeded`.

- [ ] Tear down the stack and verify volumes are preserved:

```bash
docker compose down
docker volume ls | grep backend-data
```

Expected: `docker compose down` exits cleanly; volume `tsunami_backend-data` (or similar) is still listed.

- [ ] Optional — full teardown including volumes:

```bash
docker compose down --volumes
```
