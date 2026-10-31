// Jarvis - servidor central
// - Serve o app web (PWA)
// - Envia "chamadas" via Web Push (aparecem nas notificações do celular/PC)
// - Faz a ponte WebSocket entre o agente do PC (role=agent) e o app (role=client)

const fs = require("fs");
const path = require("path");
const http = require("http");
const crypto = require("crypto");
const express = require("express");
const webpush = require("web-push");
const { WebSocketServer } = require("ws");
const { Config } = require("./config");
const voice = require("./voice");
const claudeLogin = require("./claude-login");

const PORT = Number(process.env.PORT || 8787);
const TOKEN = process.env.JARVIS_TOKEN || "";
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, "data");
const CONTACT = process.env.VAPID_CONTACT || "mailto:jarvis@example.com";

if (!TOKEN) {
  console.error("Defina JARVIS_TOKEN (uma senha longa) antes de iniciar. Ex: JARVIS_TOKEN=minhasenha npm start");
  process.exit(1);
}

fs.mkdirSync(DATA_DIR, { recursive: true });
const VAPID_FILE = path.join(DATA_DIR, "vapid.json");
const SUBS_FILE = path.join(DATA_DIR, "subscriptions.json");

// ---------- VAPID (gerado uma vez e salvo) ----------
let vapid;
if (fs.existsSync(VAPID_FILE)) {
  vapid = JSON.parse(fs.readFileSync(VAPID_FILE, "utf8"));
} else {
  vapid = webpush.generateVAPIDKeys();
  fs.writeFileSync(VAPID_FILE, JSON.stringify(vapid, null, 2));
}
webpush.setVapidDetails(CONTACT, vapid.publicKey, vapid.privateKey);

const config = new Config(DATA_DIR);

// ---------- Assinaturas de push ----------
let subs = fs.existsSync(SUBS_FILE) ? JSON.parse(fs.readFileSync(SUBS_FILE, "utf8")) : [];
const saveSubs = () => fs.writeFileSync(SUBS_FILE, JSON.stringify(subs, null, 2));

function safeEqual(a, b) {
  const x = Buffer.from(String(a || ""));
  const y = Buffer.from(String(b || ""));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

// ---------- Estado da chamada ----------
let currentCall = null; // { id, reason, urgency, ts, state: ringing|active|ended }

async function pushToAll(payload) {
  const body = JSON.stringify(payload);
  const dead = [];
  await Promise.all(
    subs.map((s) =>
      webpush.sendNotification(s, body, { TTL: 60, urgency: "high" }).catch((err) => {
        if (err.statusCode === 404 || err.statusCode === 410) dead.push(s.endpoint);
        else console.warn("push falhou:", err.statusCode || err.message);
      })
    )
  );
  if (dead.length) {
    subs = subs.filter((s) => !dead.includes(s.endpoint));
    saveSubs();
  }
}

// ---------- HTTP ----------
const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public")));

const auth = (req, res, next) =>
  safeEqual(req.get("x-jarvis-token"), TOKEN) ? next() : res.status(401).json({ error: "token inválido" });

app.get("/api/vapid", (_req, res) => res.json({ publicKey: vapid.publicKey }));

app.post("/api/subscribe", auth, (req, res) => {
  const sub = req.body;
  if (!sub || !sub.endpoint) return res.status(400).json({ error: "assinatura inválida" });
  subs = subs.filter((s) => s.endpoint !== sub.endpoint).concat(sub);
  saveSubs();
  res.json({ ok: true, total: subs.length });
});

app.get("/api/status", auth, (_req, res) =>
  res.json({ agentOnline: agents.size > 0, clients: clients.size, call: currentCall })
);

// ---------- Configurações (chaves de API etc. pela interface) ----------
app.get("/api/config", auth, (_req, res) => res.json(config.public()));
app.post("/api/config", auth, (req, res) => {
  config.update(req.body);
  broadcast(agents, { type: "config", config: config.agent() });
  res.json(config.public());
});

// ---------- Voz (ElevenLabs) ----------
app.post("/api/tts", auth, (req, res) =>
  voice.tts(config, req.body?.text || "", res).catch((e) => res.status(500).json({ error: e.message }))
);
app.get("/api/voices", auth, (_req, res) =>
  voice.voices(config).then((v) => res.json(v)).catch((e) => res.status(400).json({ error: e.message }))
);

// ---------- Login da assinatura Claude pelo site ----------
app.post("/api/claude/login/start", auth, async (_req, res) => {
  try {
    res.json({ url: await claudeLogin.start() });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});
app.post("/api/claude/login/code", auth, async (req, res) => {
  try {
    const token = await claudeLogin.submitCode(req.body?.code || "");
    config.update({ CLAUDE_CODE_OAUTH_TOKEN: token, CLAUDE_BACKEND: "cli" });
    broadcast(agents, { type: "config", config: config.agent() });
    res.json({ ok: true, config: config.public() });
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});
app.post("/api/claude/logout", auth, (_req, res) => {
  config.update({ CLAUDE_CODE_OAUTH_TOKEN: null });
  broadcast(agents, { type: "config", config: config.agent() });
  res.json(config.public());
});

// Permite disparar uma chamada de teste (ou de outro sistema seu)
app.post("/api/call", auth, async (req, res) => {
  const call = startCall(req.body?.reason || "Chamada de teste", req.body?.urgency || "normal");
  res.json({ ok: true, call });
});

function startCall(reason, urgency = "normal") {
  currentCall = { id: crypto.randomUUID(), reason, urgency, ts: Date.now(), state: "ringing" };
  broadcast(clients, { type: "incoming_call", call: currentCall });
  pushToAll({
    kind: "call",
    title: "📞 Jarvis está te ligando",
    body: reason,
    callId: currentCall.id,
    urgency,
  });
  console.log(`[chamada] ${urgency}: ${reason}`);
  return currentCall;
}

// ---------- WebSocket ----------
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: "/ws", maxPayload: 8 * 1024 * 1024 });
const agents = new Set();
const clients = new Set();

function broadcast(set, msg) {
  const data = typeof msg === "string" ? msg : JSON.stringify(msg);
  for (const ws of set) if (ws.readyState === 1) ws.send(data);
}

wss.on("connection", (ws, req) => {
  const url = new URL(req.url, "http://x");
  if (!safeEqual(url.searchParams.get("token"), TOKEN)) return ws.close(4001, "token inválido");
  const role = url.searchParams.get("role") === "agent" ? "agent" : "client";
  const group = role === "agent" ? agents : clients;
  group.add(ws);
  ws.isAlive = true;
  ws.on("pong", () => (ws.isAlive = true));
  console.log(`[ws] ${role} conectado (${group.size})`);

  if (role === "client") {
    ws.send(JSON.stringify({ type: "hello", agentOnline: agents.size > 0, call: currentCall }));
  } else {
    ws.send(JSON.stringify({ type: "config", config: config.agent() }));
    broadcast(clients, { type: "agent_status", online: true });
  }

  ws.on("message", (raw, isBinary) => {
    if (isBinary) return;
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return;
    }

    if (role === "agent") {
      if (msg.type === "call") return startCall(msg.reason, msg.urgency);
      if (msg.type === "notify") {
        // aviso simples (sem tocar)
        pushToAll({ kind: "notify", title: msg.title || "Jarvis", body: msg.body || "" });
        return broadcast(clients, msg);
      }
      // say / frame / status / log / task_* -> repassa para o app
      return broadcast(clients, msg);
    }

    // mensagens do app (cliente)
    if (msg.type === "call_accepted" && currentCall) currentCall.state = "active";
    if ((msg.type === "call_declined" || msg.type === "hangup") && currentCall) currentCall.state = "ended";
    if (["call_accepted", "call_declined", "hangup"].includes(msg.type)) {
      broadcast(clients, { type: "call_state", call: currentCall });
    }
    if (agents.size === 0 && msg.type === "user_text") {
      ws.send(JSON.stringify({ type: "say", text: "Meu agente no PC está offline, senhor." }));
    }
    broadcast(agents, { ...msg, call: currentCall });
  });

  ws.on("close", () => {
    group.delete(ws);
    if (role === "agent" && agents.size === 0) broadcast(clients, { type: "agent_status", online: false });
  });
});

setInterval(() => {
  for (const ws of wss.clients) {
    if (!ws.isAlive) {
      ws.terminate();
      continue;
    }
    ws.isAlive = false;
    ws.ping();
  }
}, 25000);

server.listen(PORT, () => console.log(`Jarvis server em http://localhost:${PORT}`));
