/**
 * GAIA Battlefield Backend Proxy Server
 *
 * Proxies the Python Battlefield API and serves the React UI.
 *
 * Run: node server/index.js
 */

import 'dotenv/config';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';
import express from 'express';
import cors from 'cors';
import { createServer } from 'http';
import { WebSocket, WebSocketServer } from 'ws';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// ─── Battlefield env proxy (Python FastAPI) ──
const BATTLEFIELD_API = process.env.BATTLEFIELD_API || 'http://127.0.0.1:8001';
const BATTLEFIELD_WS = BATTLEFIELD_API.replace(/^http/, 'ws');

app.get('/api/battlefield/scenarios', async (req, res) => {
  try {
    const r = await fetch(`${BATTLEFIELD_API}/scenarios`);
    if (!r.ok) return res.status(r.status).json({ error: `Battlefield API error ${r.status}` });
    res.json(await r.json());
  } catch (err) {
    res.status(503).json({ error: 'Battlefield env not running', detail: err.message });
  }
});

app.get('/api/battlefield/state', async (req, res) => {
  try {
    const r = await fetch(`${BATTLEFIELD_API}/state`);
    if (!r.ok) return res.status(r.status).json({ error: `Battlefield API error ${r.status}` });
    res.json(await r.json());
  } catch (err) {
    res.status(503).json({ error: 'Battlefield env not running', detail: err.message });
  }
});

app.post('/api/battlefield/run_episode', async (req, res) => {
  try {
    const r = await fetch(`${BATTLEFIELD_API}/run_episode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
    });
    if (!r.ok) return res.status(r.status).json({ error: `Battlefield API error ${r.status}` });
    res.json(await r.json());
  } catch (err) {
    res.status(503).json({ error: 'Battlefield env not running', detail: err.message });
  }
});

app.post('/api/battlefield/auto_play/start', async (req, res) => {
  try {
    const r = await fetch(`${BATTLEFIELD_API}/auto_play/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
    });
    if (!r.ok) return res.status(r.status).json({ error: `Battlefield API error ${r.status}` });
    res.json(await r.json());
  } catch (err) {
    res.status(503).json({ error: 'Battlefield env not running', detail: err.message });
  }
});

app.post('/api/battlefield/auto_play/stop', async (req, res) => {
  try {
    const r = await fetch(`${BATTLEFIELD_API}/auto_play/stop`, { method: 'POST' });
    if (!r.ok) return res.status(r.status).json({ error: `Battlefield API error ${r.status}` });
    res.json(await r.json());
  } catch (err) {
    res.status(503).json({ error: 'Battlefield env not running', detail: err.message });
  }
});

app.get('/api/battlefield/auto_play/status', async (req, res) => {
  try {
    const r = await fetch(`${BATTLEFIELD_API}/auto_play/status`);
    if (!r.ok) return res.status(r.status).json({ error: `Battlefield API error ${r.status}` });
    res.json(await r.json());
  } catch (err) {
    res.status(503).json({ error: 'Battlefield env not running', detail: err.message });
  }
});

/** Health check */
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    uptime: process.uptime(),
  });
});

// ─── Production: serve built React app (static + SPA fallback) ───
const distPath = path.join(__dirname, '..', 'dist');
if (fs.existsSync(distPath)) {
  app.use(express.static(distPath));
  app.get('/*splat', (_req, res) => {
    res.sendFile(path.join(distPath, 'index.html'));
  });
}

// ─── Export for Vercel Serverless ──────────────────────────────
export { app };
export default app;

// ─── Start (standalone mode only) ─────────────────────────────
const isDirectRun = process.argv[1] && (
  process.argv[1].endsWith('server/index.js') ||
  process.argv[1].endsWith('server\\index.js')
);

if (isDirectRun) {
  const server = createServer(app);

  const wss = new WebSocketServer({ noServer: true });
  server.on('upgrade', (request, socket, head) => {
    const url = new URL(request.url || '/', 'http://localhost');
    if (url.pathname === '/ws/battlefield') {
      wss.handleUpgrade(request, socket, head, (clientWs) => {
        const backendUrl = `${BATTLEFIELD_WS}/ws/battlefield`;
        const backend = new WebSocket(backendUrl);
        backend.on('open', () => {
          clientWs.on('message', (data) => backend.send(data));
          backend.on('message', (data) => clientWs.send(data));
        });
        clientWs.on('close', () => backend.close());
        backend.on('close', () => clientWs.close());
        clientWs.on('error', () => backend.close());
        backend.on('error', () => clientWs.close());
      });
    } else {
      socket.destroy();
    }
  });

  server.listen(PORT, () => {
    console.log(`
╔═══════════════════════════════════════╗
║   GAIA BATTLEFIELD SERVER             ║
║   Port: ${PORT}                          ║
╚═══════════════════════════════════════╝
    `);
  });
}
