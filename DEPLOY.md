# Deploy Gaia (training + UI) to Northflank

## Overview

- **gaia-app** (project `hackathon`): Combined service running the **UI + Battlefield API**. Public URL: `https://http--gaia-app--bhzgzs6hgvmy.code.run`
- **GPU in this region**: The **meta-openenv** region has **1× NVIDIA H100 (80 GB)** (GPU type id: `h100-80`). You can provision it via the UI or the CLI (see below).

---

## 1. UI + Battlefield API (gaia-app)

### Provision the 1× H100 (80 GB) — CLI

For a **combined** service you must send both **build plan** and **deployment plan**; the GPU deployment plan is `nf-gpu-hack-16-192-gpu` (16 vCPU, 192 GB). Run:

```bash
northflank patch service combined --projectId hackathon --serviceId gaia-app --input '{"billing":{"buildPlan":"nf-gpu-hack-16-32-build","deploymentPlan":"nf-gpu-hack-16-192-gpu","gpu":{"enabled":true,"configuration":{"gpuType":"h100-80","gpuCount":1}}},"deployment":{"gpu":{"enabled":true,"configuration":{"gpuType":"h100-80","gpuCount":1}}}}'
```

Northflank will redeploy with 1× NVIDIA H100 (80 GB) at **$2.74/instance/hour** (billed by the second once provisioned).

### Provision the 1× H100 (80 GB) — UI

1. Open **hackathon** → **gaia-app** in the Northflank dashboard.
2. Go to **Resources** (or **Deployment** → **Resources**).
3. Under **GPU**, select **NVIDIA H100 (80 GB)** and set **GPUs per instance** to **1**.
4. Under **Compute plan**, select **nf-gpu-hack-16-192-gpu** (16 vCPU, 192 GB).
5. Choose **Schedule now and queue for capacity** if prompted, then **Update & restart**.

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

Northflank uses browser-based login (no API tokens for standard auth).

### Deploy

- **Option A**: Push to `main`; Northflank will build and deploy.
- **Option B**: Start build manually in Northflank UI or via CLI:

```bash
northflank start service build --projectId hackathon --serviceId gaia-app --input '{"sha":"<full-40-char-commit-sha>"}'
```

Tail build logs:

```bash
northflank get service build-logs --tail --projectId hackathon --serviceId gaia-app --buildId <build-id>
```

### Get the UI link

- **In Northflank UI**: **hackathon** → **gaia-app** → **Deployments** (or **Overview**). The public URL is shown when port **3001** is exposed.
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

## 2. GRPO Training on H100 GPU

The **meta-openenv** region has **1× NVIDIA H100 (80 GB)** (GPU type id: `h100-80`). You can either attach it to **gaia-app** (UI + Battlefield + training in one service) or run training in a separate **Job** with GPU.

### Option A: Enable GPU on gaia-app (same service)

1. In **hackathon** → **gaia-app** → **Resources**, add **1× NVIDIA H100 (80 GB)** (see “Provision the 1× H100” above).
2. Rebuild/redeploy. The container will have GPU access; you can run training inside it (e.g. via exec or a custom command that runs both Battlefield + `train_grpo.py`).

### Option B: Deploy training as a Job with H100

1. In project **hackathon**, create a **Job** (not a combined service).
2. Link the same GitHub repo (`r-agni/gaia`).
3. Set **Dockerfile** to `Dockerfile` and build context to `.`.
4. Add build arg: `INSTALL_TRAINING=true` so the image includes TRL, vLLM, etc.
5. In **Resources**:
   - Select **H100** (or available GPU) from the GPU dropdown.
   - Set **Number of GPUs** (e.g. 1 for colocate mode).
   - Set CPU/memory as needed (e.g. 16 vCPU, 64 GB RAM).
6. Set **Command** to run the training script, e.g.:

   ```bash
   python battlefield_env/scripts/train_grpo.py --vllm-mode colocate --env-host http://<gaia-app-url>:3001
   ```

   Or use a `start.sh` that runs the training script.

### Step 3: Connect to the Battlefield environment

The training script needs the Battlefield API. Options:

- **Option A**: Use the deployed **gaia-app** URL as `--env-host` (if the job can reach it over the network).
- **Option B**: Run the Battlefield server in the same job container (e.g. start uvicorn in the background, then run `train_grpo.py` with `--env-host http://127.0.0.1:8001`).

### Alternative: Run training locally with H100

If you have local H100 access:

```bash
# Terminal 1: Start Battlefield + UI (or use deployed gaia-app)
./scripts/start.sh

# Terminal 2: Run GRPO training
pip install -e ".[training]"
python battlefield_env/scripts/train_grpo.py --vllm-mode colocate --env-host http://127.0.0.1:8001
```

---

## Summary

| Component        | Resource | Northflank setup |
|-----------------|----------|------------------|
| UI + Battlefield | CPU or 1× H100 | `gaia-app` in `hackathon`; add GPU in **Resources** in the UI |
| GRPO training   | **1× H100 (80 GB)** | Same region (`meta-openenv`): enable GPU on gaia-app (Resources) or create a Job with GPU |
