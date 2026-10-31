// Jarvis - app web (PWA)
const $ = (id) => document.getElementById(id);
const store = {
  get: (k, d = "") => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  del: (k) => { try { localStorage.removeItem(k); } catch {} },
};

let token = store.get("jarvis_token");
let ws = null;
let streaming = false;
let currentCall = null;
let inCall = false;
let callStart = 0;
let timerId = null;
let ringer = null;

// ---------------- UI helpers ----------------
function show(id) {
  ["setup", "home", "incoming", "incall"].forEach((s) => $(s).classList.toggle("hidden", s !== id));
}
function log(text, who = "jarvis") {
  const el = document.createElement("div");
  el.className = `msg ${who}`;
  el.textContent = text;
  $("log").appendChild(el);
  $("log").scrollTop = $("log").scrollHeight;
}
function send(msg) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
}

// ---------------- Conexão ----------------
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?role=client&token=${encodeURIComponent(token)}`);
  ws.onopen = () => log("Conectado ao servidor.", "sys");
  ws.onclose = (e) => {
    $("agentDot").className = "dot off";
    if (e.code === 4001) { store.del("jarvis_token"); token = ""; return show("setup"); }
    setTimeout(connect, 2000);
  };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    handle(m);
  };
}

function handle(m) {
  switch (m.type) {
    case "hello":
      $("agentDot").className = "dot " + (m.agentOnline ? "on" : "off");
      if (m.call && m.call.state === "ringing" && Date.now() - m.call.ts < 90000) incoming(m.call);
      break;
    case "agent_status":
      $("agentDot").className = "dot " + (m.online ? "on" : "off");
      log(m.online ? "PC conectado." : "PC desconectado.", "sys");
      break;
    case "incoming_call":
      incoming(m.call);
      break;
    case "call_state":
      if (m.call && m.call.state === "ended" && !inCall) stopRinging();
      break;
    case "say":
      log(m.text, "jarvis");
      if (inCall) $("liveText").textContent = m.text;
      if (inCall || $("voiceToggle").checked) speak(m.text);
      break;
    case "frame":
      $("screenImg").src = "data:image/jpeg;base64," + m.jpeg;
      $("screenEmpty").classList.add("hidden");
      break;
    case "log":
    case "status":
      log(m.text || JSON.stringify(m), "sys");
      break;
    case "notify":
      log(`🔔 ${m.title}: ${m.body}`, "sys");
      break;
  }
}

// ---------------- Chamada ----------------
function incoming(call) {
  if (inCall) return;
  currentCall = call;
  $("callReason").textContent = call.reason || "";
  $("callUrgency").textContent = call.urgency || "";
  $("callUrgency").className = "tag " + (call.urgency || "");
  show("incoming");
  startRinging();
}

function startRinging() {
  stopRinging();
  if (navigator.vibrate) navigator.vibrate([600, 300, 600, 300, 600]);
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const beep = () => {
      [0, 0.25].forEach((t) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 880; o.type = "sine";
        g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.2);
        o.connect(g).connect(ctx.destination); o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.22);
      });
    };
    beep();
    const iv = setInterval(beep, 1800);
    ringer = { stop: () => { clearInterval(iv); ctx.close(); } };
  } catch {}
}
function stopRinging() {
  if (ringer) ringer.stop();
  ringer = null;
  if (navigator.vibrate) navigator.vibrate(0);
}

function acceptCall() {
  stopRinging();
  send({ type: "call_accepted", callId: currentCall && currentCall.id });
  enterCall(currentCall ? currentCall.reason : "");
}
function declineCall() {
  stopRinging();
  send({ type: "call_declined", callId: currentCall && currentCall.id });
  currentCall = null;
  show("home");
}

function enterCall(reason) {
  inCall = true;
  callStart = Date.now();
  $("liveText").textContent = reason || "Pois não, senhor?";
  $("heard").textContent = "";
  show("incall");
  timerId = setInterval(() => {
    const s = Math.floor((Date.now() - callStart) / 1000);
    $("callTimer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
  startListening();
}
function hangup() {
  inCall = false;
  clearInterval(timerId);
  stopListening();
  speechSynthesis.cancel();
  send({ type: "hangup", callId: currentCall && currentCall.id });
  currentCall = null;
  show("home");
}

// ---------------- Voz ----------------
let voices = [];
const loadVoices = () => (voices = speechSynthesis.getVoices());
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }

function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "pt-BR";
  const v = voices.find((x) => x.lang === "pt-BR" && /male|daniel|antonio|ricardo/i.test(x.name)) ||
            voices.find((x) => x.lang && x.lang.startsWith("pt"));
  if (v) u.voice = v;
  u.rate = 1.05;
  u.onstart = () => { $("talkOrb").classList.add("talking"); pauseListening(true); };
  u.onend = () => { $("talkOrb").classList.remove("talking"); pauseListening(false); };
  speechSynthesis.speak(u);
}

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, micOn = true, paused = false, listening = false;

function startListening() {
  if (!SR) { log("Seu navegador não suporta reconhecimento de voz. Use o chat.", "sys"); return; }
  rec = new SR();
  rec.lang = "pt-BR";
  rec.continuous = true;
  rec.interimResults = true;
  rec.onresult = (e) => {
    let interim = "", final = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) final += t; else interim += t;
    }
    $("heard").textContent = interim || final;
    if (final.trim()) userSays(final.trim());
  };
  rec.onend = () => { listening = false; if (inCall && micOn && !paused) tryStart(); };
  rec.onerror = () => {};
  tryStart();
}
function tryStart() { try { rec.start(); listening = true; } catch {} }
function stopListening() { if (rec) { rec.onend = null; try { rec.stop(); } catch {} } rec = null; listening = false; }
function pauseListening(p) {
  paused = p;
  if (!rec) return;
  if (p && listening) { try { rec.stop(); } catch {} }
  if (!p && inCall && micOn && !listening) tryStart();
}

function userSays(text) {
  log(text, "me");
  send({ type: "user_text", text, inCall });
}

// ---------------- Push ----------------
function b64ToUint8(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}
async function enablePush() {
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return log("Notificações bloqueadas no navegador.", "sys");
    const reg = await navigator.serviceWorker.ready;
    const { publicKey } = await (await fetch("/api/vapid")).json();
    let sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(publicKey) });
    const r = await fetch("/api/subscribe", {
      method: "POST",
      headers: { "content-type": "application/json", "x-jarvis-token": token },
      body: JSON.stringify(sub),
    });
    if (!r.ok) throw new Error("token inválido");
    $("notifBanner").classList.add("hidden");
    log("Notificações ativadas. O Jarvis pode te ligar agora.", "sys");
  } catch (e) {
    log("Falha ao ativar notificações: " + e.message, "sys");
  }
}
async function checkPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    $("notifBanner").classList.remove("hidden");
    $("notifBanner").querySelector("span").textContent =
      "Este navegador não suporta push. No iPhone: Compartilhar → Adicionar à Tela de Início, e abra pelo ícone.";
    $("enablePush").classList.add("hidden");
    return;
  }
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub || Notification.permission !== "granted") $("notifBanner").classList.remove("hidden");
  else enablePush(); // re-registra no servidor (caso tenha sido apagado)
}

// ---------------- Eventos ----------------
$("saveToken").onclick = () => {
  token = $("tokenInput").value.trim();
  if (!token) return;
  store.set("jarvis_token", token);
  boot();
};
$("enablePush").onclick = enablePush;
$("accept").onclick = acceptCall;
$("decline").onclick = declineCall;
$("hangup").onclick = hangup;
$("muteBtn").onclick = () => {
  micOn = !micOn;
  $("muteBtn").classList.toggle("off", !micOn);
  if (micOn) tryStart(); else if (rec) try { rec.stop(); } catch {}
};
$("toggleStream").onclick = () => {
  streaming = !streaming;
  send({ type: "stream", on: streaming });
  $("toggleStream").textContent = streaming ? "🙈 Parar tela" : "👁️ Ver tela";
  if (!streaming) { $("screenImg").removeAttribute("src"); $("screenEmpty").classList.remove("hidden"); }
};
$("callNow").onclick = () => { currentCall = null; send({ type: "user_call" }); enterCall("Pois não, senhor?"); };
$("stopTask").onclick = () => { send({ type: "stop" }); log("Pedido de parada enviado.", "sys"); };
$("chatForm").onsubmit = (e) => {
  e.preventDefault();
  const t = $("chatInput").value.trim();
  if (!t) return;
  $("chatInput").value = "";
  userSays(t);
};
$("testCall").onclick = () =>
  fetch("/api/call", {
    method: "POST",
    headers: { "content-type": "application/json", "x-jarvis-token": token },
    body: JSON.stringify({ reason: "Teste: esta é uma chamada de teste do Jarvis.", urgency: "normal" }),
  });
$("logout").onclick = () => { store.del("jarvis_token"); location.reload(); };
$("parsecInput").value = store.get("parsec_url");
const applyParsec = () => {
  const u = $("parsecInput").value.trim();
  store.set("parsec_url", u);
  $("parsecLink").classList.toggle("hidden", !u);
  if (u) $("parsecLink").href = u;
};
$("parsecInput").onchange = applyParsec;
$("voiceToggle").checked = store.get("voice", "1") === "1";
$("voiceToggle").onchange = () => store.set("voice", $("voiceToggle").checked ? "1" : "0");

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
  navigator.serviceWorker.addEventListener("message", (e) => {
    const m = e.data || {};
    if (m.type === "push" && m.data && m.data.kind === "call") {
      incoming({ id: m.data.callId, reason: m.data.body, urgency: m.data.urgency });
    }
    if (m.type === "notification_action") {
      if (m.action === "accept") { currentCall = { id: m.data.callId, reason: m.data.body }; acceptCall(); }
      else if (m.action === "decline") { currentCall = { id: m.data.callId }; declineCall(); }
      else if (m.data && m.data.kind === "call") incoming({ id: m.data.callId, reason: m.data.body, urgency: m.data.urgency });
    }
  });
}

function boot() {
  if (!token) return show("setup");
  show("home");
  applyParsec();
  connect();
  checkPush();
  // aberto a partir da notificação
  const p = new URLSearchParams(location.search);
  if (p.get("call")) {
    history.replaceState(null, "", "/");
    currentCall = { id: p.get("call") };
    if (p.get("action") === "accept") setTimeout(acceptCall, 500);
    else if (p.get("action") === "decline") setTimeout(declineCall, 500);
  }
}
boot();
