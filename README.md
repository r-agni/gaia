---
title: GAIA GeoGuess
emoji: 🌍
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 3001
dockerfile: Dockerfile.hf
pinned: false
---

# GAIA: Geo-Reasoning + Oversight OpenEnv Environment

## Demo Video

Google Drive folder:  
https://drive.google.com/drive/u/0/folders/1_pLZXV_S0T2hqcnL-1zmBNeWi-LlVEg7

GAIA is an OpenEnv-compatible RL environment for training and evaluating agents on geospatial reasoning under uncertainty.  
An agent must infer hidden real-world coordinates by combining multi-tool evidence (terrain, weather, sun angle, language, architecture, street-level and aerial cues), then submit latitude/longitude guesses.

This repo includes:
- `geoguess_env/`: OpenEnv environment server, engine, tool providers, agents, and GRPO training script.
- `worldview/`: real-time Cesium-based visualization and control UI.

## Live Deployment Links

- Demo video (Google Drive):  
  https://drive.google.com/drive/u/0/folders/1_pLZXV_S0T2hqcnL-1zmBNeWi-LlVEg7
- Public demo (Northflank, UI + backend proxy):  
  https://http--gaia-app--bhzgzs6hgvmy.code.run/
- Public WebSocket stream (proxied live state):  
  wss://http--gaia-app--bhzgzs6hgvmy.code.run/ws/geoguess
- Public REST examples (via Node proxy):
  - `GET /api/geoguess/state`
  - `POST /api/geoguess/run_game`
  - `POST /api/geoguess/auto_play/start`
  - `POST /api/geoguess/auto_play/stop`
  - `GET /api/geoguess/auto_play/status`
  - `GET /api/geoguess/training/history`

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
2. **Scaler AI Labs - Multi-App RL Environment for Enterprise Workflows**

Why these two:
- Fleet AI: first-class oversight pipeline (`oversight_flags`, `oversight_summary`) is implemented and streamed live.
- Scaler AI Labs: the environment matches Statement 3.1 world-modeling behavior with tool/API interaction, business-rule-like constraints (budgeted actions), and multi-step workflow execution.

### Subcategory Fit (Concrete Mapping)

**Fleet AI - Scalable Oversight**
- Dedicated oversight agent evaluates each guess and emits structured flags:
  `LAZY_GUESS`, `CONTRADICTION`, `REPEATED_GUESS`, `THIN_REASONING`, `OVERCONFIDENT`.
- Episode-level reliability rollup is exposed as `oversight_summary` (`CLEAN` / `CAUTION` / `UNRELIABLE`).
- Oversight is first-class in runtime outputs:
  - Engine state includes `oversight_flags` and `oversight_summary`.
  - Backend emits real-time `oversight_flag` WebSocket events.
  - UI surfaces flag panels and reliability status.
- Why this fits Fleet AI: the system does not only act; it monitors, explains, and scores agent reliability as a parallel oversight process.

**Scaler AI Labs - Multi-App RL Environment for Enterprise Workflows**
- Multi-step workflow under hard budgets:
  agent must sequence tool calls, update beliefs, and guess within step/guess limits.
- Multi-tool app integration:
  weather, terrain/elevation, sun-angle, language, building-style, and map imagery tools are composed in one episode loop.
- Standardized environment contract:
  OpenEnv reset/step/state/schema + WS interface supports reproducible policy evaluation and training.
- Deployment-friendly operations:
  same backend contracts power local dev, containerized demo, and hosted runtime (Northflank / HF Spaces path).
- Why this fits Scaler AI Labs: this is a reusable, enterprise-style RL environment with explicit workflows, guardrails, monitoring signals, and transport-stable APIs.

### Secondary Technical Alignment
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

### Civil and Disaster Response Use Cases
- **Disaster response:** fast location inference from partial scene reports.
- **Humanitarian operations:** prioritize rescue and aid routing when source data is incomplete.
- **Crisis mapping support:** provide confidence-scored geo-estimates for incoming field reports.

### Enterprise and Logistics Use Cases
- **Supply chain and logistics:** route or site identification from environment signals.
- **Asset and route verification:** detect location inconsistencies in operational reports.
- **Field-ops support:** combine weather/terrain cues for planning in low-observability conditions.

### Media, Insurance, and Verification Use Cases
- **Insurance investigations:** cross-check claimed location context against environmental cues.
- **Journalism and OSINT verification:** improve provenance checks for user-generated imagery.
- **Trust and safety workflows:** flag overconfident/low-evidence geo-claims using oversight signals.

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

## 5. Current AI Models and Approaches for Geo-Reasoning (and How GAIA Differs)

### Common Current Approaches

1. **Image geolocation classifiers**
- Example family: PlaNet-style global cell classification models.
- Strength: strong single-image prior for broad region prediction.
- Limitation: usually weakly interpretable and less interactive.

2. **Contrastive vision-language geolocalizers**
- Example family: CLIP-style geo-alignment models (for example StreetCLIP/GeoCLIP-style methods).
- Strength: robust zero-shot transfer and retrieval-like behavior.
- Limitation: often optimized for static benchmark prediction rather than sequential tool use.

3. **Retrieval over geotagged databases**
- Uses nearest-neighbor matching against large geotagged corpora.
- Strength: high precision when near-duplicate visual context exists.
- Limitation: brittle in unseen/low-coverage regions and weak on reasoning trace quality.

4. **Frontier multimodal LLMs for visual reasoning**
- Uses general-purpose VLMs for cues like language, architecture, and terrain.
- Strength: broad world knowledge and flexible reasoning.
- Limitation: can be overconfident/hallucinate without explicit environment constraints.

5. **Agentic tool-use pipelines**
- Combines LLM planning with APIs/tools (weather, maps, OCR, etc.).
- Strength: better decomposition and evidence collection than single-pass prediction.
- Limitation: often lacks standardized RL environments and oversight-grounded evaluation loops.

### How GAIA Differs

- **Environment-first, not prompt-only:** GAIA is a formal OpenEnv environment with step-wise dynamics, not just a one-shot benchmark prompt.
- **Multi-turn partial observability:** agents must plan across strict step/guess budgets with delayed outcomes.
- **Explicit oversight agent:** contradiction, overconfidence, and evidence-quality flags are first-class outputs.
- **Rewarded evidence strategy:** reward design balances distance accuracy, tool efficiency, and reasoning depth.
- **Trainable with GRPO end-to-end:** same environment supports online rollouts, reward logging, and policy improvement.
- **Demo-to-training parity:** the visualization, environment state, and RL loop all run on the same backend contracts.

---

## 6. RL Training Pipeline (GRPO + TRL + OpenEnv)

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

## 7. OpenEnv Compliance and APIs

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
- `GET /training/runtime_status`
- `WS /ws/geoguess`

---

## 8. OpenEnv: How We Use It in Practice

GAIA uses OpenEnv as the environment protocol and lifecycle contract, not just as a library dependency.

Implementation points:
- `geoguess_env/geoguess/environment.py`
  - `GeoGuessEnvironment` subclasses `openenv.core.Environment`
  - `reset()`, `step()`, `state`, and metadata are implemented in OpenEnv format
- `geoguess_env/geoguess/server.py`
  - `HTTPEnvServer(...)` registers standard OpenEnv routes
  - OpenEnv WebSocket endpoint (`/ws`) is used by training rollouts
- `geoguess_env/client/env_client.py`
  - `GeoGuessEnvClient` subclasses `openenv.core.env_client.EnvClient`
  - used by GRPO rollout code to run episodes over OpenEnv WS

Operationally:
- Training uses OpenEnv WS (`GEOGUESS_ENV_URL=ws://...`) to reset/step/state-query episodes.
- The Cesium demo UI uses custom REST/WS endpoints for visualization, while environment control remains OpenEnv-compliant.

### GeoGuessEnvClient Method Reference (`geoguess_env/client/env_client.py`)

- `connect()`
  - Opens a persistent WebSocket session to `{base_url}/ws`. Called automatically by `reset`, `step`, or `state` if needed.
- `reset(**kwargs) -> StepResult[GeoGuessObservation]`
  - Sends a `reset` message and returns initial `observation`, `reward`, and `done`.
  - In GeoGuess training this is used with args like `dataset_id`, `location_id`, and `total_rounds`.
- `step(action) -> StepResult[GeoGuessObservation]`
  - Sends one `GeoGuessAction` (`tool_call` or `guess`) and returns the next observation plus reward/terminal flag.
  - `GeoGuessEnvClient._step_payload()` converts the typed action to JSON via `action.model_dump()`.
- `state() -> GeoGuessFullState`
  - Requests full current environment state (server truth/debug state), not just the agent observation.
  - `GeoGuessEnvClient._parse_state()` maps JSON into `GeoGuessFullState`.
- `disconnect()`
  - Closes only the WebSocket session (best-effort close message).
- `close()`
  - Calls `disconnect()`. If the client was created from a provider (`from_env`/`from_docker_image`), it also stops the runtime/container.
- Context manager support
  - `with GeoGuessEnvClient(...) as client:` auto-connects on enter and closes on exit.

Implementation hooks in this file:
- `_step_payload(action)`
  - Serialization hook used by `step`.
- `_parse_result(payload)`
  - Parses reset/step response payloads into `StepResult[GeoGuessObservation]` and copies `reward`, `done`, `metadata` onto the observation model.
- `_parse_state(payload)`
  - Parses state payloads into `GeoGuessFullState`.

Why this matters:
- We can swap agent policies while keeping environment API stable.
- The same environment supports scripted agents, HF-inference agents, and RL rollouts without changing engine logic.

---

## 9. Hugging Face Models and Where They Are Used

### Text Models
- Default playing-agent model:
  - `meta-llama/Llama-3.1-8B-Instruct`
  - configured by `HF_MODEL_ID`
  - used in `agents/llm_agent.py` via `agents/hf_client.py`

### Vision Model
- Default vision captioning model:
  - `meta-llama/Llama-3.2-11B-Vision-Instruct`
  - configured by `VISION_MODEL_ID`
  - used in tool providers:
    - `street_view.py` for street-level clues
    - `terrain.py` (`globe_view`) for satellite-style clues

### Training Base Model
- Default GRPO base model:
  - `Qwen/Qwen2.5-7B-Instruct`
  - configured by `BASE_MODEL` in `geoguess_env/train_grpo.py`

HF usage modes in GAIA:
- Inference API mode for online agent/tool-caption calls (`HF_API_KEY` required).
- Local/vLLM mode for high-throughput RL training.

---

## 10. Northflank and H100 GPU Usage

Deployment notes are documented in `DEPLOY.md`.

Current deployment pattern in this repo:
- Service: `gaia-app` (combined container)
- Process model:
  - FastAPI GeoGuess API on internal `8002`
  - Node/Worldview server on public `3001`

How H100 is used:
- **Primary use:** GRPO training acceleration (`trl` + vLLM + model updates)
- **Optional use:** lower-latency LLM/vision inference during live demos

Recommended split on GPU infra:
- GPU 0: `trl vllm-serve` inference server
- GPU 1 (or same GPU in smaller setups): GRPO trainer process

Northflank specifics already captured in `DEPLOY.md`:
- region with `h100-80` availability
- service patch example enabling `gpuCount: 1` and `gpuType: h100-80`

---

## 11. Hugging Face Spaces Deployment (Docker Space)

Hackathon requirement references OpenEnv on HF Spaces.  
This repo can be deployed as a **Docker Space** using the root `Dockerfile`.

Practical setup:
- Create a new HF Space with SDK type `Docker`.
- Point the Space to this repository.
- Set environment variables in Space settings:
  - `HF_API_KEY`
  - `GOOGLE_MAPS_API_KEY` (if using Street View / Static Maps tools)
  - optional model overrides (`HF_MODEL_ID`, `VISION_MODEL_ID`)
- Expose app on port `3001` (container already does this).

What runs in the container:
- GeoGuess OpenEnv API (`geoguess.server:app`) bound internally to `127.0.0.1:8002`
- Worldview server (public entrypoint) proxies to GeoGuess API

---

## 12. Frontend + Demo Layer

`worldview/` provides:
- Cesium globe rendering
- live guess and ground-truth markers
- guess-to-truth error line
- round history overlays
- oversight flag panels and episode reliability status
- game controls (start game, reset view)

Backend proxy (`worldview/server/index.js`) bridges UI to GeoGuess API and supports websocket relay for live updates.

---

## 13. Run Instructions

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

## 14. Minimal Training Script Path (for Submission Requirement)

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

## 15. Judging Criteria Mapping

- **Environment Innovation (40%)**  
  Multi-tool geolocation under budget + explicit oversight agent + real-time visualization.

- **Storytelling (30%)**  
  Live globe shows guess trajectory, error vectors, and oversight alerts.

- **Training Improvement (20%)**  
  GRPO pipeline with measurable env reward and format reward progression.

- **Reward/Training Pipeline (10%)**  
  Coherent distance-based task reward + structured auxiliary signal + OpenEnv rollout loop.

---

## 16. Known Repository Notes

- The active environment for this project is `geoguess_env`.
- Some files still contain legacy `battlefield` references (not part of the GeoGuess demo path).
- For hackathon submission, use the GeoGuess/OpenEnv pipeline documented above.

---

## 17. Submission Checklist (Hackathon)

- OpenEnv runtime: `openenv-core>=0.2.1` is used in `geoguess_env/pyproject.toml`.
- Demo format: prepare a 1-minute technical demo video (no slide deck).
- Training evidence: include GRPO logs/curves showing reward improvement.
- Partner selection to submit:
  - Fleet AI - Scalable Oversight
  - Scaler AI Labs - Multi-App RL Environment for Enterprise Workflows
- Deployment:
  - HF Spaces (Docker Space) for OpenEnv-compliant hosted demo
  - Northflank `gaia-app` for combined UI + API runtime
  - optional H100 for training/inference acceleration
 

## Credits: inspiration and based code from repo: https://github.com/kevtoe/worldview
