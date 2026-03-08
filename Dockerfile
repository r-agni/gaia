# Stage 1: build Worldview (React + Vite)
FROM node:20-bookworm-slim AS worldview-build
WORKDIR /worldview
COPY worldview/package.json worldview/package-lock.json ./
RUN npm ci
COPY worldview/ ./
# CesiumJS is large; ensure Node has enough heap for the build
RUN NODE_OPTIONS=--max-old-space-size=4096 npm run build

# Stage 2: runtime (Node + Python in one image)
FROM node:20-bookworm-slim AS runtime

# Ensure a stable non-root user named "user".
# Some base images already have UID 1000 in use; avoid hard failure.
RUN if id -u user >/dev/null 2>&1; then \
      true; \
    elif getent passwd 1000 >/dev/null 2>&1; then \
      useradd -m user; \
    else \
      useradd -m -u 1000 user; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Set INSTALL_TRAINING=true to install TRL/vLLM/torch for auto GRPO (see DEPLOY.md §3)
ARG INSTALL_TRAINING=false

WORKDIR /home/user/app

# GeoGuess env (Python FastAPI)
COPY --chown=user geoguess_env/pyproject.toml /home/user/app/geoguess_env/
COPY --chown=user geoguess_env/geoguess /home/user/app/geoguess_env/geoguess
COPY --chown=user geoguess_env/agents /home/user/app/geoguess_env/agents
COPY --chown=user geoguess_env/client /home/user/app/geoguess_env/client
COPY --chown=user geoguess_env/data /home/user/app/geoguess_env/data
COPY --chown=user geoguess_env/train_grpo.py /home/user/app/geoguess_env/train_grpo.py
RUN if [ "$INSTALL_TRAINING" = "true" ]; then \
      cd /home/user/app/geoguess_env && pip install --no-cache-dir --break-system-packages -e ".[agents,training]"; \
    else \
      cd /home/user/app/geoguess_env && pip install --no-cache-dir --break-system-packages -e ".[agents]"; \
    fi

# Worldview (Node server + built static)
COPY --chown=user --from=worldview-build /worldview/dist /home/user/app/worldview/dist
COPY --chown=user worldview/server /home/user/app/worldview/server
COPY --chown=user worldview/package.json worldview/package-lock.json /home/user/app/worldview/
RUN cd /home/user/app/worldview && npm ci --omit=dev

COPY --chown=user scripts/start.sh /home/user/app/start.sh
RUN sed -i '1s/^\xEF\xBB\xBF//' /home/user/app/start.sh \
    && sed -i 's/\r$//' /home/user/app/start.sh \
    && chmod +x /home/user/app/start.sh

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
