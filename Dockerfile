# Stage 1: build Worldview (React + Vite)
FROM node:20-bookworm-slim AS worldview-build
WORKDIR /worldview
COPY worldview/package.json worldview/package-lock.json ./
RUN npm ci
COPY worldview/ ./
RUN npm run build

# Stage 2: runtime (Node + Python in one image)
FROM node:20-bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Battlefield (Python FastAPI)
COPY battlefield_env/pyproject.toml /app/battlefield_env/
COPY battlefield_env/battlefield /app/battlefield_env/battlefield
COPY battlefield_env/agents /app/battlefield_env/agents
COPY battlefield_env/client /app/battlefield_env/client
RUN cd /app/battlefield_env && pip install --no-cache-dir --break-system-packages -e ".[agents]"

# Worldview (Node server + built static)
COPY --from=worldview-build /worldview/dist /app/worldview/dist
COPY worldview/server /app/worldview/server
COPY worldview/package.json worldview/package-lock.json /app/worldview/
RUN cd /app/worldview && npm ci --omit=dev

ENV NODE_ENV=production
ENV PORT=3001
ENV BATTLEFIELD_API=http://127.0.0.1:8001
ENV PYTHONUNBUFFERED=1

EXPOSE 3001

COPY scripts/start.sh /app/start.sh
RUN chmod +x /app/start.sh
WORKDIR /app
CMD ["/app/start.sh"]
