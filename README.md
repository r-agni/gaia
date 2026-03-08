# GAIA: Geo-Reasoning + Oversight OpenEnv Environment

GAIA is an OpenEnv-compatible RL environment for training and evaluating agents on geospatial reasoning under uncertainty.  
An agent must infer hidden real-world coordinates by combining multi-tool evidence (terrain, weather, sun angle, language, architecture, street-level and aerial cues), then submit latitude/longitude guesses.

This repo includes:
- `geoguess_env/`: OpenEnv environment server, engine, tool providers, agents, and GRPO training script.
- `worldview/`: real-time Cesium-based visualization and control UI.

---

## 1. Hackathon Alignment

### Primary Required Problem Statement
**Statement 1: Multi-Agent Interactions**

Why this fits:
- The environment includes a **playing agent** and a separate **oversight agent**.
- The oversight agent monitors evidence gathering and reasoning quality, flags contradictions, and produces episode-level reliability assessments.
- This creates an explicit multi-agent dynamic: actor + evaluator in a partially observable world.

### Selected Partner Sub-Themes (max 2)
1. **Fleet AI - Scalable Oversight**
2. **Halluminate - Multi-Actor Environments**

Why these two:
- Fleet AI: first-class oversight pipeline (`oversight_flags`, `oversight_summary`) is implemented and streamed live.
- Halluminate: the acting model coordinates multiple evidence channels (tool providers as external actors/data sources) under strict budgets to complete a mission objective.

### Secondary Technical Alignment (not selected for judging cap)
**Statement 3.1: World Modeling (Professional Tasks)**  
The agent interacts with dynamic tools/APIs and must maintain consistent internal beliefs over multiple steps.

---

## 2. Project Rationale and Real-World Relevance

### Defense Use Cases
- **ISR geolocation triage:** rapidly estimate likely location from sparse visual/environmental clues.
- **Mission support under uncertainty:** combine heterogeneous weak signals before committing to an actionable estimate.
- **AI oversight for high-stakes ops:** flag overconfident or contradictory reasoning before decisions propagate.

### Intelligence Use Cases
- **OSINT workflow simulation:** fuse language, architecture, weather, and terrain evidence.
- **Analyst-assistant reliability scoring:** oversight agent surfaces reasoning failure modes (lazy guesses, contradictions, repeated guesses).
- **Tradecraft training:** evaluate how evidence quality changes with tool usage strategy and budget constraints.

### Other Use Cases
- **Disaster response:** fast location inference from partial scene reports.
- **Supply chain and logistics:** route or site identification from environment signals.
- **Insurance, journalism, and verification:** geolocation confidence estimation with transparent evidence trails.

---

## 3. Environment Design

### Core MDP/POMDP Structure
- **Hidden state:** true location `(lat, lon, country, region)` per round.
- **Observation:** sparse scene description + all previous tool outputs and guesses in current round.
- **Action space:** `tool_call` or `guess`.
- **Transition:** tool calls append evidence; guesses trigger reward computation and round progression.
- **Episode:** multi-round game (`total_rounds`, default 5).

### Episode / Round Mechanics
- Per round:
  - max tool/step budget (`max_steps_per_round`, default 7)
  - max guesses (`max_guesses_per_round`, default 2)
- Forced zero-reward round end if budget is exhausted without a guess.
- Episode score is mean of completed round scores.

### Action Schema
`GeoGuessAction`:
- `action_type`: `"tool_call"` or `"guess"`
- tool branch: `tool_name`, `tool_params`
- guess branch: `guess_lat`, `guess_lon`
- always: `reasoning`

### Observation Schema
`GeoGuessObservation` includes:
- round/step metadata
- initial scene description
- tool result history
- guess history (distance, score, country/region correctness)
- remaining budgets
- generated prompt text for LLM agents

### Available Tools
- `globe_view`
- `street_view`
- `terrain_analysis`
- `weather`
- `sun_angle`
- `building_style`
- `language_detection`

---

## 4. Technical Algorithms and Why They Were Chosen

### 4.1 Reward Function
Round reward is computed in `geoguess/rewards.py`:

1. **Distance reward (primary):**  
   Great-circle distance via Haversine, then exponential decay score:
   - near target -> high score
   - far target -> near zero by ~5000 km

2. **Geopolitical correctness bonus:**  
   - +0.10 if guessed country matches
   - +0.05 if region/admin area matches

3. **Reasoning depth bonus:**  
   Reward for distinct tool diversity (up to +0.10) to encourage world-model building.

4. **Tool usage penalty:**  
   `-0.02 * tools_used`, enforcing information-efficiency pressure.

Final score is clamped to `[0,1]`.

Rationale:
- Distance captures core geolocation objective.
- Country/region bonuses stabilize gradient signal for near-miss progress.
- Depth bonus counters degenerate "guess immediately" behavior.
- Tool penalty enforces realistic budget discipline.

### 4.2 Geospatial / Inference Algorithms

- **Haversine distance:** robust Earth-surface metric for global coordinates.
- **Reverse geocoding (`reverse_geocoder`):** offline country/region correctness checks (no external dependency at scoring time).
- **Solar position (`astral`):** compute solar elevation/azimuth and day length for latitude/season inference.
- **Weather (`open-meteo`):** dynamic environmental cue; includes hemisphere-season context.
- **Elevation (`open-elevation`):** terrain realism signal for biome/elevation reasoning.
- **Vision captioning (optional):** Google Street View / Static Maps + HF vision model, with privacy-preserving prompt constraints (no direct location naming).

### 4.3 Oversight Agent Algorithms
`agents/oversight_agent.py` implements deterministic monitoring heuristics:
- no-tool guess detection (`LAZY_GUESS`)
- tool-result vs reasoning contradiction detection (`CONTRADICTION`)
- repeated guess without new evidence (`REPEATED_GUESS`)
- thin reasoning check (`THIN_REASONING`)
- certainty-without-evidence check (`OVERCONFIDENT`)

Then episode-level summarization:
- `CLEAN`, `CAUTION`, `UNRELIABLE`
- issue counts and dominant failure type

Rationale:
- deterministic rules are auditable and easy to demonstrate in a hackathon demo.
- provides immediate safety/reliability observability in multi-agent settings.

### 4.4 LLM Output Robustness
`agents/output_parser.py` uses regex + JSON repair heuristics:
- extracts JSON-like action objects
- fixes common malformed JSON cases (quotes, trailing commas)
- validates tool names
- fallback guess on parse failure

Rationale:
- training/inference pipelines should be resilient to imperfect model formatting.

### 4.5 Dataset Construction Algorithms
`geoguess/scripts/build_datasets.py`:
- downloads GeoNames `cities1000`
- filters to population > 100k
- continent-balanced sampling (target 5k)
- biome inference via country heuristics + latitude fallback
- produces:
  - `world_cities_5k.jsonl`
  - `training_1k.jsonl`

Rationale:
- balanced global coverage avoids overfitting to a small region.
- lightweight synthetic metadata enables fast offline iteration.

---

## 5. RL Training Pipeline (GRPO + TRL + OpenEnv)

### Algorithm
The main training script is `geoguess_env/train_grpo.py`, using:
- `trl.GRPOTrainer`
- custom `rollout_func`
- OpenEnv WebSocket client (`GeoGuessEnvClient`)

At a high level:
1. sample prompts from `training_1k`
2. generate model completions (multi-action traces)
3. parse tool/guess actions and execute in environment
4. collect terminal environment reward + format reward
5. apply GRPO update using grouped generations per prompt

### Reward Signals Used in GRPO
- `reward_from_env`: terminal environment reward from real episode rollout
- `reward_format_quality`: structural quality reward for parseable, schema-like outputs

Rationale:
- env reward optimizes task competence.
- format reward reduces invalid action traces and rollout failure.

### GRPO Config (Current Defaults)
- model: `Qwen/Qwen2.5-7B-Instruct` (env var override)
- `num_generations=8`
- `max_new_tokens=1024`
- server-mode vLLM supported
- output checkpoints saved to `OUTPUT_DIR`

---

## 6. OpenEnv Compliance and APIs

Implemented with `openenv-core>=0.2.1`.

Standard OpenEnv routes (via `HTTPEnvServer`):
- `POST /reset`
- `POST /step`
- `GET /state`
- `GET /schema`
- `GET /metadata`
- `GET /health`
- `WS /ws`

Custom gameplay/ops routes:
- `GET /datasets`
- `POST /run_game`
- `POST /auto_play/start`
- `POST /auto_play/stop`
- `GET /auto_play/status`
- `GET /training/status`
- `GET /oversight/summary`
- `WS /ws/geoguess`

---

## 7. Frontend + Demo Layer

`worldview/` provides:
- Cesium globe rendering
- live guess and ground-truth markers
- guess-to-truth error line
- round history overlays
- oversight flag panels and episode reliability status
- game controls (start game, reset view)

Backend proxy (`worldview/server/index.js`) bridges UI to GeoGuess API and supports websocket relay for live updates.

---

## 8. Run Instructions

### Option A: Combined Container (recommended for demo)

From repo root:

```powershell
docker build -t gaia .
docker run --rm -p 3001:3001 -e GOOGLE_MAPS_API_KEY=... -e HF_API_KEY=... gaia
```

Then open `http://localhost:3001`.

### Option B: Local split services

### 1) Start GeoGuess API

```powershell
cd geoguess_env
pip install -e ".[agents]"
uvicorn geoguess.server:app --host 127.0.0.1 --port 8002
```

### 2) Start Worldview server

```powershell
cd worldview
npm ci
$env:GEOGUESS_API="http://127.0.0.1:8002"
npm run start
```

Then open `http://localhost:3001`.

---

## 9. Minimal Training Script Path (for Submission Requirement)

Run from `geoguess_env/`:

```powershell
pip install -e ".[agents,training]"
```

Start env server:

```powershell
uvicorn geoguess.server:app --host 0.0.0.0 --port 8001
```

Start vLLM server (separate process/GPU):

```powershell
trl vllm-serve --model Qwen/Qwen2.5-7B-Instruct --host 0.0.0.0 --port 8000
```

Run training:

```powershell
$env:GEOGUESS_ENV_URL="ws://localhost:8001"
$env:VLLM_SERVER_URL="http://localhost:8000"
python train_grpo.py
```

Capture reward trends from trainer logs for the demo video.

---

## 10. Judging Criteria Mapping

- **Environment Innovation (40%)**  
  Multi-tool geolocation under budget + explicit oversight agent + real-time visualization.

- **Storytelling (30%)**  
  Live globe shows guess trajectory, error vectors, and oversight alerts.

- **Training Improvement (20%)**  
  GRPO pipeline with measurable env reward and format reward progression.

- **Reward/Training Pipeline (10%)**  
  Coherent distance-based task reward + structured auxiliary signal + OpenEnv rollout loop.

---

## 11. Known Repository Notes

- The active environment for this project is `geoguess_env`.
- Some files still contain legacy `battlefield` references (not part of the GeoGuess demo path).
- For hackathon submission, use the GeoGuess/OpenEnv pipeline documented above.

---

## 12. Submission Checklist (Hackathon)

- OpenEnv runtime: `openenv-core>=0.2.1` is used in `geoguess_env/pyproject.toml`.
- Demo format: prepare a 1-minute technical demo video (no slide deck).
- Training evidence: include GRPO logs/curves showing reward improvement.
- Partner selection to submit:
  - Fleet AI - Scalable Oversight
  - Halluminate - Multi-Actor Environments
- Deployment: containerized via repo Dockerfile; can be deployed to HF Spaces or other container hosts.
