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

# GeoGuess env (Python FastAPI)
COPY geoguess_env/pyproject.toml /app/geoguess_env/
COPY geoguess_env/geoguess /app/geoguess_env/geoguess
COPY geoguess_env/agents /app/geoguess_env/agents
COPY geoguess_env/client /app/geoguess_env/client
COPY geoguess_env/data /app/geoguess_env/data
ARG INSTALL_TRAINING=false
RUN if [ "$INSTALL_TRAINING" = "true" ]; then \
      cd /app/geoguess_env && pip install --no-cache-dir --break-system-packages -e ".[agents,training]"; \
    else \
      cd /app/geoguess_env && pip install --no-cache-dir --break-system-packages -e ".[agents]"; \
    fi

# Worldview (Node server + built static)
COPY --from=worldview-build /worldview/dist /app/worldview/dist
COPY worldview/server /app/worldview/server
COPY worldview/package.json worldview/package-lock.json /app/worldview/
RUN cd /app/worldview && npm ci --omit=dev

ENV NODE_ENV=production
ENV PORT=3001
ENV GEOGUESS_API=http://127.0.0.1:8002
ENV PYTHONUNBUFFERED=1

EXPOSE 3001

COPY scripts/start.sh /app/start.sh
RUN chmod +x /app/start.sh
WORKDIR /app
CMD ["/app/start.sh"]
