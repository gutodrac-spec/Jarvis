// Configuração editável pela interface (chaves de API, voz, Claude, vigilância).
// Fica salva em data/config.json. Variáveis de ambiente servem de valor inicial.
const fs = require("fs");
const path = require("path");

const SECRET_KEYS = ["GROQ_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"];

const DEFAULTS = {
  GROQ_API_KEY: "",
  ANTHROPIC_API_KEY: "",
  ELEVENLABS_API_KEY: "",
  CLAUDE_CODE_OAUTH_TOKEN: "",
  // "Daniel": voz masculina britânica, grave e elegante (bem estilo Jarvis). Troque pelo ID que preferir.
  ELEVENLABS_VOICE_ID: "onwK4e9ZLuTAKqWW03F9",
  ELEVENLABS_MODEL: "eleven_flash_v2_5",
  CLAUDE_BACKEND: "cli",
  CLAUDE_MODEL: "claude-opus-5-5",
  GROQ_FAST_MODEL: "llama-3.1-8b-instant",
  GROQ_SMART_MODEL: "llama-3.3-70b-versatile",
  GROQ_VISION_MODEL: "meta-llama/llama-4-scout-17b-16e-instruct",
  MONITOR_ENABLED: "1",
  WATCH_RULES:
    "Me ligue se aparecer erro, travamento, download/render/build terminado, mensagem importante, aviso de segurança, bateria baixa, ou se algum programa pedir minha confirmação.",
  CALL_MIN_URGENCY: "normal",
};

// O que é repassado ao agente do PC
const AGENT_KEYS = [
  "GROQ_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_BACKEND", "CLAUDE_MODEL",
  "GROQ_FAST_MODEL", "GROQ_SMART_MODEL", "GROQ_VISION_MODEL", "MONITOR_ENABLED", "WATCH_RULES", "CALL_MIN_URGENCY",
];

class Config {
  constructor(dataDir) {
    this.file = path.join(dataDir, "config.json");
    const saved = fs.existsSync(this.file) ? JSON.parse(fs.readFileSync(this.file, "utf8")) : {};
    this.values = {};
    for (const k of Object.keys(DEFAULTS)) this.values[k] = saved[k] ?? process.env[k] ?? DEFAULTS[k];
  }

  get(k) {
    return this.values[k] || "";
  }

  save() {
    fs.writeFileSync(this.file, JSON.stringify(this.values, null, 2), { mode: 0o600 });
  }

  // Atualiza: segredo vazio = mantém o atual; null = apaga
  update(patch) {
    for (const [k, v] of Object.entries(patch || {})) {
      if (!(k in DEFAULTS)) continue;
      if (SECRET_KEYS.includes(k)) {
        if (v === null) this.values[k] = "";
        else if (typeof v === "string" && v.trim()) this.values[k] = v.trim();
      } else if (v !== undefined && v !== null) {
        this.values[k] = String(v);
      }
    }
    this.save();
  }

  // Para a interface: segredos aparecem mascarados
  public() {
    const out = {};
    for (const [k, v] of Object.entries(this.values)) {
      out[k] = SECRET_KEYS.includes(k) ? (v ? { set: true, preview: `${v.slice(0, 6)}…${v.slice(-4)}` } : { set: false }) : v;
    }
    return out;
  }

  agent() {
    const out = {};
    for (const k of AGENT_KEYS) out[k] = this.values[k] || "";
    return out;
  }
}

module.exports = { Config };
