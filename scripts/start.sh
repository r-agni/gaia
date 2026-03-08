#!/bin/sh
set -e
# Start Battlefield API in background (internal only)
cd /app/battlefield_env && PYTHONPATH=/app/battlefield_env uvicorn battlefield.server:app --host 127.0.0.1 --port 8001 &
# Run Worldview Node server (PID 1, exposes 3001)
cd /app/worldview && exec node server/index.js
