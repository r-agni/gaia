#!/bin/sh
set -e

# Resolve app root — works both for /app (Northflank) and /home/user/app (HF Spaces)
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
TRAINING_STATUS_FILE="${TRAINING_STATUS_FILE:-/tmp/gaia_training_status.json}"
TRAINING_LOG_FILE="${TRAINING_LOG_FILE:-/tmp/gaia_train_grpo.log}"
VLLM_LOG_FILE="${VLLM_LOG_FILE:-/tmp/gaia_vllm.log}"
VLLM_HEALTH_RETRIES="${VLLM_HEALTH_RETRIES:-360}"
VLLM_HEALTH_SLEEP_SEC="${VLLM_HEALTH_SLEEP_SEC:-5}"
ALLOW_TRAINING_FALLBACK_NO_VLLM="${ALLOW_TRAINING_FALLBACK_NO_VLLM:-true}"
ALLOW_CPU_TRAINING_FALLBACK="${ALLOW_CPU_TRAINING_FALLBACK:-false}"

# HF Spaces are typically CPU-only; default to disabling background GRPO there
# unless explicitly overridden.
if [ -n "${SPACE_ID:-}" ] && [ "${RUN_GRPO_TRAINING:-false}" = "true" ] && [ "${ALLOW_HF_SPACE_TRAINING:-false}" != "true" ]; then
  echo "[TRAINING] HF Space detected; forcing RUN_GRPO_TRAINING=false (set ALLOW_HF_SPACE_TRAINING=true to override)."
  RUN_GRPO_TRAINING=false
fi

vllm_ready() {
  wget -q -O /dev/null http://127.0.0.1:8000/health 2>/dev/null && return 0
  wget -q -O /dev/null http://127.0.0.1:8000/v1/models 2>/dev/null && return 0
  return 1
}

write_training_status() {
  state="$1"
  message="$2"
  message="$(printf "%s" "$message" | tr '\n\r' ' ' | tr '"' "'")"
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  printf '{"state":"%s","message":"%s","timestamp":"%s","run_grpo_training":"%s","base_model":"%s","output_dir":"%s","log_file":"%s","vllm_log_file":"%s"}\n' \
    "$state" "$message" "$ts" "${RUN_GRPO_TRAINING:-false}" "${BASE_MODEL:-}" "${OUTPUT_DIR:-}" \
    "$TRAINING_LOG_FILE" "$VLLM_LOG_FILE" > "$TRAINING_STATUS_FILE"
  echo "[TRAINING][$state] $message"
}

tail_training_log() {
  if [ -f "$TRAINING_LOG_FILE" ]; then
    tail -n 8 "$TRAINING_LOG_FILE" | tr '\n\r' ' ' | tr '"' "'" | cut -c1-280
  else
    echo "no training log file yet"
  fi
}

# Start GeoGuess API in background (internal only)
cd "$APP_ROOT/geoguess_env" && PYTHONPATH="$APP_ROOT/geoguess_env" uvicorn geoguess.server:app --host 127.0.0.1 --port 8002 &

# Auto-start gameplay loop once the Python server is ready (up to ~90s).
# Keep gameplay loop on by default so training/history keeps updating in the UI
# even when GRPO batches are long-running. Can still be disabled explicitly.
AUTO_PLAY_ON_BOOT="${AUTO_PLAY_ON_BOOT:-true}"
if [ "$RUN_GRPO_TRAINING" = "true" ]; then
  AUTO_PLAY_ON_BOOT="${AUTO_PLAY_ON_BOOT_WHEN_TRAINING:-true}"
fi
if [ "$AUTO_PLAY_ON_BOOT" = "true" ]; then
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
fi

# Optional: auto-run GRPO training (requires INSTALL_TRAINING=true at build, RUN_GRPO_TRAINING=true at runtime, and GPU)
if [ "$RUN_GRPO_TRAINING" = "true" ]; then
  write_training_status "initializing" "RUN_GRPO_TRAINING=true; waiting for env and dependencies."
  if python3 -c "from trl import GRPOConfig, GRPOTrainer; import vllm" 2>/dev/null && [ -f "$APP_ROOT/geoguess_env/data/training_1k.jsonl" ]; then
    (
      set +e
      export BASE_MODEL="${BASE_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
      export GEOGUESS_ENV_URL="${GEOGUESS_ENV_URL:-ws://127.0.0.1:8002}"
      export VLLM_SERVER_URL="${VLLM_SERVER_URL:-http://127.0.0.1:8000}"
      export DATASET_PATH="${DATASET_PATH:-data/training_1k.jsonl}"
      export OUTPUT_DIR="${OUTPUT_DIR:-$APP_ROOT/geoguess_env/geoguess-grpo-out}"
      mkdir -p "$(dirname "$TRAINING_LOG_FILE")" "$(dirname "$VLLM_LOG_FILE")" "$OUTPUT_DIR"
      if [ ! -f "$APP_ROOT/geoguess_env/train_grpo.py" ]; then
        write_training_status "failed" "Missing training script at $APP_ROOT/geoguess_env/train_grpo.py"
        exit 0
      fi
      write_training_status "starting_vllm" "Launching vLLM server on :8000."
      python3 -m vllm.entrypoints.openai.api_server --model "$BASE_MODEL" --host 0.0.0.0 --port 8000 >"$VLLM_LOG_FILE" 2>&1 &
      VLLM_PID=$!
      VLLM_READY=false
      write_training_status "waiting_for_vllm" "Waiting for vLLM readiness endpoint."
      for i in $(seq 1 "$VLLM_HEALTH_RETRIES"); do
        if ! kill -0 "$VLLM_PID" 2>/dev/null; then
          write_training_status "failed" "vLLM process exited before becoming healthy (see vLLM log)."
          break
        fi
        if vllm_ready; then
          VLLM_READY=true
          write_training_status "running_trainer" "vLLM is healthy; starting train_grpo.py."
          cd "$APP_ROOT/geoguess_env" && PYTHONPATH="$APP_ROOT/geoguess_env" python3 "$APP_ROOT/geoguess_env/train_grpo.py" >>"$TRAINING_LOG_FILE" 2>&1
          TRAIN_EXIT=$?
          if [ "$TRAIN_EXIT" -eq 0 ]; then
            write_training_status "completed" "GRPO training completed successfully."
          else
            write_training_status "failed" "GRPO trainer exited with code $TRAIN_EXIT. Log tail: $(tail_training_log)"
          fi
          break
        fi
        sleep "$VLLM_HEALTH_SLEEP_SEC"
      done
      if [ "$VLLM_READY" != "true" ]; then
        if [ "$ALLOW_TRAINING_FALLBACK_NO_VLLM" = "true" ]; then
          if ! python3 -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" >/dev/null 2>&1 && [ "$ALLOW_CPU_TRAINING_FALLBACK" != "true" ]; then
            write_training_status "skipped" "vLLM unavailable and CUDA not detected; CPU fallback disabled."
            kill "$VLLM_PID" 2>/dev/null || true
            exit 0
          fi
          write_training_status "running_trainer" "vLLM unavailable; falling back to USE_VLLM=false."
          export USE_VLLM=false
          cd "$APP_ROOT/geoguess_env" && PYTHONPATH="$APP_ROOT/geoguess_env" python3 "$APP_ROOT/geoguess_env/train_grpo.py" >>"$TRAINING_LOG_FILE" 2>&1
          TRAIN_EXIT=$?
          if [ "$TRAIN_EXIT" -eq 0 ]; then
            write_training_status "completed" "GRPO training completed in fallback mode (no vLLM)."
          else
            write_training_status "failed" "Fallback trainer exited with code $TRAIN_EXIT. Log tail: $(tail_training_log)"
          fi
        else
          write_training_status "failed" "vLLM did not become healthy in time (see vLLM log)."
        fi
      fi
      kill "$VLLM_PID" 2>/dev/null || true
    ) &
  elif ! python3 -c "from trl import GRPOConfig, GRPOTrainer; import vllm" 2>/dev/null; then
    write_training_status "skipped" "Training deps incompatible (missing GRPOConfig/GRPOTrainer or vllm). Rebuild with INSTALL_TRAINING=true."
  else
    write_training_status "skipped" "Dataset missing at geoguess_env/data/training_1k.jsonl."
  fi
else
  write_training_status "disabled" "RUN_GRPO_TRAINING is not enabled."
fi

# Run Worldview Node server (PID 1, exposes 3001)
cd "$APP_ROOT/worldview" && exec node server/index.js
