# Deploy Gaia (GeoGuess + UI) to Northflank

## Overview

- **gaia-app** (project `hackathon`): Combined service running the **UI + GeoGuess API**. Public URL: `https://http--gaia-app--bhzgzs6hgvmy.code.run`
- The container runs:
  - **GeoGuess FastAPI** on internal port `8002` (`geoguess_env`)
  - **Worldview Node proxy** on public port `3001` (serves built React + proxies API/WebSocket to 8002)

---

## 1. UI + GeoGuess API (gaia-app)

### Northflank build configuration

- Open project **hackathon** → service **gaia-app** in the Northflank dashboard.
- Go to **Build options**.
- Set **Dockerfile path** to `Dockerfile` and **Build context** to `.` (repo root).
- Add a **branch build rule**: trigger on push to `main`. Save.

### Install CLI and log in

```bash
npm i -g @northflank/cli
northflank login -n <context-name>
```

### Deploy

- **Option A**: Push to `main`; Northflank will build and deploy automatically.
- **Option B**: Start build manually via CLI:

```bash
northflank start service build --projectId hackathon --serviceId gaia-app --input '{"sha":"<full-40-char-commit-sha>"}'
```

Tail build logs:

```bash
northflank get service build-logs --tail --projectId hackathon --serviceId gaia-app --buildId <build-id>
```

### Environment variables to set in Northflank

| Variable | Value |
|---|---|
| `VITE_GOOGLE_API_KEY` | Your Google Maps API key (for 3D tiles) |
| `HF_API_KEY` | HuggingFace token (optional, for LLM agent) |
| `GEOGUESS_API` | `http://127.0.0.1:8002` (default, already set in Dockerfile) |

### Get the UI link

- **In Northflank UI**: **hackathon** → **gaia-app** → **Deployments** (or **Overview**). Public URL is shown when port **3001** is exposed.
- **Via CLI**:

```bash
northflank get service --projectId hackathon --serviceId gaia-app
```

Look for `ports[].dns` (e.g. `http--gaia-app--bhzgzs6hgvmy.code.run`). Full URL: `https://<dns>`.

### Exec into the container (optional)

```bash
northflank exec service --projectId hackathon --serviceId gaia-app
```

---

## 2. GPU (optional — for LLM agent or GRPO training)

The **meta-openenv** region has **1× NVIDIA H100 (80 GB)** (GPU type id: `h100-80`).

### Enable GPU on gaia-app

```bash
northflank patch service combined --projectId hackathon --serviceId gaia-app \
  --input '{"billing":{"buildPlan":"nf-gpu-hack-16-32-build","deploymentPlan":"nf-gpu-hack-16-192-gpu","gpu":{"enabled":true,"configuration":{"gpuType":"h100-80","gpuCount":1}}},"deployment":{"gpu":{"enabled":true,"configuration":{"gpuType":"h100-80","gpuCount":1}}}}'
```

---

## Summary

| Component | Resource | Northflank setup |
|---|---|---|
| UI + GeoGuess API | CPU (default) or 1× H100 | `gaia-app` in `hackathon`; Dockerfile auto-starts both |
| GRPO training | **1× H100 (80 GB)** | Enable GPU on gaia-app or create a Job |
