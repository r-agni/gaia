#!/bin/sh
set -e
# Start GeoGuess API in background (internal only)
cd /app/geoguess_env && PYTHONPATH=/app/geoguess_env uvicorn geoguess.server:app --host 127.0.0.1 --port 8002 &
# Run Worldview Node server (PID 1, exposes 3001)
cd /app/worldview && exec node server/index.js
