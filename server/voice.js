// Voz realista do Jarvis via ElevenLabs (text-to-speech em streaming)
const { Readable } = require("stream");

const API = "https://api.elevenlabs.io/v1";

async function tts(config, text, res) {
  const key = config.get("ELEVENLABS_API_KEY");
  if (!key) return res.status(400).json({ error: "Configure a chave da ElevenLabs." });
  const voice = config.get("ELEVENLABS_VOICE_ID") || "onwK4e9ZLuTAKqWW03F9";
  const r = await fetch(`${API}/text-to-speech/${encodeURIComponent(voice)}/stream?output_format=mp3_44100_128`, {
    method: "POST",
    headers: { "xi-api-key": key, "content-type": "application/json", accept: "audio/mpeg" },
    body: JSON.stringify({
      text: String(text).slice(0, 2500),
      model_id: config.get("ELEVENLABS_MODEL") || "eleven_flash_v2_5",
      language_code: "pt",
      voice_settings: { stability: 0.45, similarity_boost: 0.8, style: 0.25, use_speaker_boost: true, speed: 1.05 },
    }),
  });
  if (!r.ok) {
    const msg = await r.text().catch(() => "");
    return res.status(502).json({ error: `ElevenLabs ${r.status}: ${msg.slice(0, 300)}` });
  }
  res.setHeader("content-type", "audio/mpeg");
  res.setHeader("cache-control", "no-store");
  Readable.fromWeb(r.body).pipe(res);
}

async function voices(config) {
  const key = config.get("ELEVENLABS_API_KEY");
  if (!key) throw new Error("Configure a chave da ElevenLabs.");
  const r = await fetch(`${API}/voices`, { headers: { "xi-api-key": key } });
  if (!r.ok) throw new Error(`ElevenLabs ${r.status}`);
  const j = await r.json();
  return (j.voices || []).map((v) => ({
    id: v.voice_id,
    name: v.name,
    desc: [v.labels?.gender, v.labels?.accent, v.labels?.description || v.labels?.descriptive, v.labels?.age]
      .filter(Boolean)
      .join(", "),
    preview: v.preview_url,
  }));
}

module.exports = { tts, voices };
