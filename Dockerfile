# Single-stage Dockerfile for HF Spaces
# Pre-built worldview/dist is committed to the repo — no Vite build needed
FROM node:20-bookworm-slim

# HF Spaces requires uid 1000
RUN useradd -m -u 1000 user

RUN apt-get update && apt-get install -y --no-install-recommends     python3 python3-pip python3-venv     && rm -rf /var/lib/apt/lists/*

WORKDIR /home/user/app

# GeoGuess env (Python FastAPI)
COPY --chown=user geoguess_env/pyproject.toml /home/user/app/geoguess_env/
COPY --chown=user geoguess_env/geoguess /home/user/app/geoguess_env/geoguess
COPY --chown=user geoguess_env/agents /home/user/app/geoguess_env/agents
COPY --chown=user geoguess_env/client /home/user/app/geoguess_env/client
COPY --chown=user geoguess_env/data /home/user/app/geoguess_env/data
RUN cd /home/user/app/geoguess_env && pip install --no-cache-dir --break-system-packages -e ".[agents]"

# Worldview — pre-built dist from repo (no Vite build step)
COPY --chown=user worldview/dist /home/user/app/worldview/dist
COPY --chown=user worldview/server /home/user/app/worldview/server
COPY --chown=user worldview/package.json /home/user/app/worldview/package.json
# Use npm install instead of npm ci to avoid lockfile version mismatch
RUN cd /home/user/app/worldview && npm install --omit=dev --no-audit --no-fund

COPY --chown=user scripts/start.sh /home/user/app/start.sh
RUN chmod +x /home/user/app/start.sh

ENV NODE_ENV=production
ENV PORT=3001
ENV GEOGUESS_API=http://127.0.0.1:8002
ENV PYTHONUNBUFFERED=1
ENV HOME=/home/user
ENV PATH=/home/user/.local/bin:$PATH

EXPOSE 3001

USER user
WORKDIR /home/user/app
CMD ["/home/user/app/start.sh"]
