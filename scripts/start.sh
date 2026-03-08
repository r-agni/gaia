#!/bin/sh
set -e
# Start GeoGuess API in background (internal only)
cd /app/geoguess_env && PYTHONPATH=/app/geoguess_env uvicorn geoguess.server:app --host 127.0.0.1 --port 8002 &

# Auto-start training loop once the Python server is ready
(
  for i in $(seq 1 30); do
    if wget -qO /dev/null http://127.0.0.1:8002/health 2>/dev/null; then
      wget -qO- --post-data='{"use_llm":false,"step_delay_ms":300}' \
        --header='Content-Type: application/json' \
        http://127.0.0.1:8002/auto_play/start || true
      echo "auto_play started"
      break
    fi
    sleep 2
  done
) &

# Run Worldview Node server (PID 1, exposes 3001)
cd /app/worldview && exec node server/index.js
