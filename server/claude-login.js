// Login da ASSINATURA do Claude pelo site.
// Roda `claude setup-token` num terminal virtual, captura o link de login,
// recebe o código que você cola no site e guarda o token (válido por 1 ano).
const { spawn } = require("child_process");

let session = null; // { proc, out, url, token, error, done }

const URL_RE = /https:\/\/[^\s\x07\x1b"'<>]*oauth\/authorize\?[^\s\x07\x1b"'<>]+/;
const TOKEN_RE = /sk-ant-oat\d+-[A-Za-z0-9_\-]{20,}/;

function stop() {
  if (session && session.proc && session.proc.exitCode === null) session.proc.kill("SIGKILL");
  session = null;
}

function start() {
  stop();
  return new Promise((resolve, reject) => {
    if (process.platform === "win32") return reject(new Error("Login pelo site só funciona com o servidor em Linux/Mac (ex: Codespaces)."));
    const env = { ...process.env, COLUMNS: "4000", LINES: "50", BROWSER: "true", TERM: "xterm-256color" };
    delete env.ANTHROPIC_API_KEY;
    delete env.CLAUDE_CODE_OAUTH_TOKEN;
    // `script` cria um terminal (TTY), que o claude exige para o fluxo interativo
    const proc = spawn("script", ["-q", "-c", "stty cols 4000 rows 50; claude setup-token", "/dev/null"], { env });
    const s = (session = { proc, out: "", url: null, token: null, error: null });
    const onData = (d) => {
      s.out += d.toString();
      if (s.out.length > 200000) s.out = s.out.slice(-100000);
      if (!s.url) {
        const m = s.out.match(URL_RE);
        if (m) {
          s.url = m[0];
          resolve(s.url);
        }
      }
      if (!s.token) {
        const t = s.out.match(TOKEN_RE);
        if (t) s.token = t[0];
      }
    };
    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", (e) => reject(new Error("Não consegui rodar o Claude Code: " + e.message)));
    proc.on("exit", () => {
      if (!s.url) reject(new Error("O Claude Code fechou sem gerar link. Ele está instalado? (npm i -g @anthropic-ai/claude-code)"));
    });
    setTimeout(() => !s.url && reject(new Error("Tempo esgotado esperando o link de login.")), 30000);
  });
}

function submitCode(code) {
  return new Promise((resolve, reject) => {
    const s = session;
    if (!s || !s.proc || s.proc.exitCode !== null) return reject(new Error("Comece o login de novo."));
    s.proc.stdin.write(String(code).trim());
    setTimeout(() => s.proc.stdin.write("\r"), 300);
    const t0 = Date.now();
    const iv = setInterval(() => {
      if (s.token) {
        clearInterval(iv);
        const token = s.token;
        stop();
        return resolve(token);
      }
      const clean = s.out.replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, "");
      if (/invalid|error|failed/i.test(clean.slice(-600)) || Date.now() - t0 > 45000) {
        clearInterval(iv);
        stop();
        reject(new Error("Código inválido ou expirado. Tente de novo."));
      }
    }, 500);
  });
}

module.exports = { start, submitCode, stop };
