# Deploy Gaia (training + UI) to Northflank

## 1. Northflank build configuration

- Open project **hackathon** → service **gaia** in the Northflank dashboard.
- Go to **Build options**.
- Set **Dockerfile path** to `Dockerfile` and **Build context** to `.` (repo root).
- Add a **branch build rule**: e.g. trigger on push to `main` (or your default branch). Save.

Without this, CI will not start builds when you push.

## 2. Install CLI and log in

```bash
npm i -g @northflank/cli
northflank login -n <context-name> -t <your-account-token>
```

Get your token from Northflank: **Settings** → **Access** → **Create token**.

## 3. Deploy

- **Option A**: Push to the branch that has the build rule; Northflank will build and deploy.
- **Option B**: In the Northflank UI, open **gaia** → **Builds** → **Start build**.

Tail build logs:

```bash
northflank get service build-logs --tail --projectId hackathon --serviceId gaia
```

## 4. Get the UI link

- **In the Northflank UI**: **hackathon** → **gaia** → **Deployments** (or **Overview**). The **public URL** is shown when port **3001** is exposed (e.g. `https://gaia-xxx.northflank.app`).
- **Via CLI**:

```bash
northflank get service --projectId hackathon --serviceId gaia
```

Use the URL shown for the service (or the deployment) as the link to open the UI in the browser.

## 5. Exec into the container (optional)

```bash
northflank exec service --projectId hackathon --serviceId gaia
```
