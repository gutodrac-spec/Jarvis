"""Agente avançado (Claude) para tarefas complexas no PC.

Dois modos (CLAUDE_BACKEND):
- "cli": usa o Claude Code instalado no PC (funciona com a sua ASSINATURA, `claude login`).
         Ele enxerga a tela e mexe mouse/teclado através do pc_cli.py.
- "api": usa a API da Anthropic com a ferramenta de computer use
         (computer_toolset_20260801). Precisa de ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import pc

HERE = Path(__file__).resolve().parent

SYSTEM = """Você é J.A.R.V.I.S., operando o PC do usuário (chame-o de "senhor") a pedido dele, \
que está longe acompanhando pelo celular. Fale em português do Brasil.

- Trabalhe de forma autônoma até concluir a tarefa; confira na tela se cada passo funcionou.
- Antes de ações irreversíveis ou sensíveis (apagar arquivos, enviar mensagens/e-mails em nome dele, \
compras, pagamentos, mudar senhas, desinstalar programas), PARE e pergunte, explicando o que vai fazer.
- Não digite senhas que não foram fornecidas e não contorne avisos de segurança.
- Ao terminar, responda com um resumo curto (1-3 frases) do que foi feito, pois será falado em voz alta."""

Say = Callable[[str], None]


# ======================================================================
# Modo API (computer use)
# ======================================================================
def run_api(task: str, say: Say, stop: threading.Event) -> str:
    import anthropic

    model = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
    effort = os.getenv("CLAUDE_EFFORT", "medium")
    max_steps = int(os.getenv("CLAUDE_MAX_STEPS", "60"))
    client = anthropic.Anthropic()
    screen = pc.Screen(max_side=1280)  # mantém as imagens dentro do limite do modelo

    messages: list = [{"role": "user", "content": [{"type": "text", "text": task}]}]
    for _ in range(max_steps):
        if stop.is_set():
            return "Tarefa interrompida, senhor."
        try:
            resp = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=SYSTEM,
                thinking={"type": "adaptive", "display": "updates"},
                output_config={"effort": effort},
                tools=[{"type": "computer_toolset_20260801"}],
                messages=messages,
                # "updates": notas curtas de progresso; fallback: se o modelo recusar, tenta outro automaticamente
                betas=["thinking-display-updates-2026-08-18", "server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError:
            time.sleep(10)
            continue
        except anthropic.APIStatusError as e:
            return f"A API do Claude retornou erro {e.status_code}: {e.message}"
        except anthropic.APIConnectionError:
            time.sleep(3)
            continue

        if resp.stop_reason == "refusal":
            return "O Claude recusou essa tarefa, senhor."

        messages.append({"role": "assistant", "content": resp.content})

        for b in resp.content:
            if b.type == "thinking" and getattr(b, "thinking", ""):
                say(b.thinking.strip())

        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            final = " ".join(b.text for b in resp.content if b.type == "text").strip()
            return final or "Pronto, senhor."

        results = []
        for b in calls:
            if stop.is_set():
                break
            results.append(_exec_tool(b, screen))
        if stop.is_set():
            return "Tarefa interrompida, senhor."
        messages.append({"role": "user", "content": results})
    return "Atingi o limite de passos, senhor. Parei por segurança."


def _exec_tool(block, screen: pc.Screen) -> dict:
    name = block.name
    a = block.input or {}
    base = {"type": "tool_result", "tool_use_id": block.id, "toolset_name": getattr(block, "toolset_name", None) or "computer"}

    def image(b64):
        return {**base, "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}]}

    try:
        xy = screen.real(a["coordinate"]) if a.get("coordinate") else (None, None)
        mods = a.get("text") if name.endswith("click") or name in ("scroll", "left_click_drag") else None
        if name == "screenshot":
            return image(screen.shot_b64())
        if name == "zoom":
            return image(screen.zoom_b64(a["region"]))
        if name == "left_click":
            pc.click(*xy, mods=mods)
        elif name == "right_click":
            pc.click(*xy, button="right", mods=mods)
        elif name == "middle_click":
            pc.click(*xy, button="middle", mods=mods)
        elif name == "double_click":
            pc.click(*xy, clicks=2, mods=mods)
        elif name == "triple_click":
            pc.click(*xy, clicks=3, mods=mods)
        elif name == "left_click_drag":
            x0, y0 = screen.real(a["start_coordinate"])
            pc.drag(x0, y0, *xy, mods=mods)
        elif name == "mouse_move":
            pc.move(*xy)
        elif name == "left_mouse_down":
            pc.mouse_down()
        elif name == "left_mouse_up":
            pc.mouse_up()
        elif name == "cursor_position":
            x, y = pc.cursor()
            return {**base, "content": f"x={int(x / screen.scale)}, y={int(y / screen.scale)}"}
        elif name == "scroll":
            pc.scroll(a.get("scroll_direction", "down"), a.get("scroll_amount", 3), *xy, mods=mods)
        elif name == "type":
            pc.type_text(a.get("text", ""))
        elif name == "key":
            pc.key(a.get("text", ""), a.get("repeat", 1))
        elif name == "hold_key":
            pc.hold_key(a.get("text", ""), a.get("duration", 1))
        elif name == "wait":
            time.sleep(min(float(a.get("duration", 1)), 300))
        else:
            return {**base, "content": f"Ferramenta desconhecida: {name}", "is_error": True}
        time.sleep(0.3)
        return {**base, "content": "OK"}
    except Exception as e:
        return {**base, "content": f"Erro: {e}", "is_error": True}


# ======================================================================
# Modo CLI (Claude Code com assinatura)
# ======================================================================
CLI_SYSTEM = SYSTEM + f"""

Você está no PC do senhor e controla a tela com o utilitário abaixo (rode com Bash):
  {sys.executable} "{HERE / 'pc_cli.py'}" screenshot          -> salva a tela e imprime o caminho do PNG (abra com Read para ver)
  {sys.executable} "{HERE / 'pc_cli.py'}" click X Y [left|right|middle|double]
  {sys.executable} "{HERE / 'pc_cli.py'}" move X Y
  {sys.executable} "{HERE / 'pc_cli.py'}" drag X1 Y1 X2 Y2
  {sys.executable} "{HERE / 'pc_cli.py'}" type "texto"
  {sys.executable} "{HERE / 'pc_cli.py'}" key ctrl+s
  {sys.executable} "{HERE / 'pc_cli.py'}" scroll up|down|left|right N [X Y]
As coordenadas X Y são em pixels da ÚLTIMA screenshot. Sempre tire uma screenshot nova depois de agir \
para confirmar o resultado. Prefira comandos de terminal quando forem mais confiáveis que cliques."""

_proc: subprocess.Popen | None = None


def run_cli(task: str, say: Say, stop: threading.Event) -> str:
    global _proc
    exe = shutil.which(os.getenv("CLAUDE_CLI", "claude")) or os.getenv("CLAUDE_CLI", "claude")
    # No Windows o npm instala "claude.cmd", que passa pelo cmd.exe: lá quebras de linha não são permitidas
    use_shell = os.name == "nt" and not exe.lower().endswith(".exe")
    flat = (lambda t: " ".join(t.split())) if use_shell else (lambda t: t)
    cmd = [
        exe, "-p", flat(task),
        "--output-format", "stream-json", "--verbose",
        "--append-system-prompt", flat(CLI_SYSTEM),
        "--allowedTools", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
    ]
    model = os.getenv("CLAUDE_CLI_MODEL")
    if model:
        cmd += ["--model", model]
    env = {**os.environ}
    env.pop("ANTHROPIC_API_KEY", None)  # garante que use a assinatura, não a API
    try:
        _proc = subprocess.Popen(
            cmd, cwd=str(Path.home()), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            shell=use_shell,
        )
    except FileNotFoundError:
        return "Não encontrei o Claude Code no PC. Instale com: npm i -g @anthropic-ai/claude-code e rode 'claude login'."

    final = ""
    last_say = 0.0
    for line in _proc.stdout:
        if stop.is_set():
            _proc.kill()
            return "Tarefa interrompida, senhor."
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "assistant":
            for c in ev.get("message", {}).get("content", []):
                if c.get("type") == "text" and c.get("text", "").strip() and time.time() - last_say > 4:
                    say(c["text"].strip()[:300])
                    last_say = time.time()
        elif ev.get("type") == "result":
            final = ev.get("result") or ""
            if ev.get("is_error"):
                final = final or "O Claude Code terminou com erro."
    _proc.wait()
    _proc = None
    return final.strip() or "Pronto, senhor."


def kill():
    if _proc and _proc.poll() is None:
        _proc.kill()


def run(task: str, say: Say, stop: threading.Event) -> str:
    backend = os.getenv("CLAUDE_BACKEND", "cli").lower()
    return run_api(task, say, stop) if backend == "api" else run_cli(task, say, stop)
