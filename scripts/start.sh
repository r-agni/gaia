#!/bin/sh
set -e
# Start GeoGuess API in background (internal only)
cd /app/geoguess_env && PYTHONPATH=/app/geoguess_env uvicorn geoguess.server:app --host 127.0.0.1 --port 8002 &

# Auto-start training loop once the Python server is ready (up to ~90s)
(
  for i in $(seq 1 45); do
    if wget -q -O /dev/null http://127.0.0.1:8002/health 2>/dev/null; then
      wget -q -O- --post-data='{"use_llm":false,"step_delay_ms":300}' \
        --header='Content-Type: application/json' \
        http://127.0.0.1:8002/auto_play/start 2>/dev/null || true
      echo "auto_play started"
      break
    fi
    sleep 2
  done
) &

# Optional: auto-run GRPO training (requires INSTALL_TRAINING=true at build, RUN_GRPO_TRAINING=true at runtime, and GPU)
if [ "$RUN_GRPO_TRAINING" = "true" ]; then
  if python3 -c "import trl" 2>/dev/null && [ -f /app/geoguess_env/data/training_1k.jsonl ]; then
    (
      export BASE_MODEL="${BASE_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
      export GEOGUESS_ENV_URL="${GEOGUESS_ENV_URL:-ws://127.0.0.1:8002}"
      export VLLM_SERVER_URL="${VLLM_SERVER_URL:-http://127.0.0.1:8000}"
      export DATASET_PATH="${DATASET_PATH:-data/training_1k.jsonl}"
      export OUTPUT_DIR="${OUTPUT_DIR:-/app/geoguess_env/geoguess-grpo-out}"
      echo "Starting vLLM server on port 8000 (model: $BASE_MODEL)..."
      python3 -m vllm.entrypoints.openai.api_server --model "$BASE_MODEL" --host 0.0.0.0 --port 8000 &
      for i in $(seq 1 120); do
        if wget -q -O /dev/null http://127.0.0.1:8000/health 2>/dev/null; then
          echo "vLLM ready; starting GRPO trainer..."
          cd /app/geoguess_env && PYTHONPATH=/app/geoguess_env python3 train_grpo.py
          break
        fi
        sleep 5
      done
    ) &
  fi
fi

# Run Worldview Node server (PID 1, exposes 3001)
cd /app/worldview && exec node server/index.js
