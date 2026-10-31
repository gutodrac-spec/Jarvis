"""Provedores de IA do Duet.

- claude-api  : Claude API com chave (ANTHROPIC_API_KEY), cobrada por uso.
- claude-code : Claude Code CLI usando a sua assinatura Pro/Max (CLAUDE_CODE_OAUTH_TOKEN,
                gerado com `claude setup-token`). As ferramentas chegam via MCP.
- groq        : API da Groq (GROQ_API_KEY), compatível com OpenAI; tem camada grátis.
"""
import json
import os
import pathlib
import subprocess
import sys

import requests

AQUI = pathlib.Path(__file__).resolve().parent

PADROES = {
    #               conversa                  verificação de hora em hora
    "claude-api": ("claude-sonnet-5-5", "claude-haiku-5-5"),
    "claude-code": ("sonnet", "haiku"),
    "groq": ("openai/gpt-oss-120b", "openai/gpt-oss-20b"),
}

VARIAVEL = {
    "claude-api": "ANTHROPIC_API_KEY",
    "claude-code": "CLAUDE_CODE_OAUTH_TOKEN",
    "groq": "GROQ_API_KEY",
}

LIMITE_PASSOS = 8
DESISTENCIA = "Parei porque a tarefa ficou longa demais. Pode detalhar o que precisa?"


def disponiveis():
    return [p for p, v in VARIAVEL.items() if os.getenv(v)]


def escolher(para="conversa"):
    """Provedor a usar. DUET_PROVEDOR / DUET_PROVEDOR_VERIFICACAO mandam;
    sem eles, usa o primeiro com chave (assinatura > Groq > API paga)."""
    pedido = os.getenv("DUET_PROVEDOR_VERIFICACAO") if para == "verificacao" else None
    pedido = pedido or os.getenv("DUET_PROVEDOR")
    if pedido:
        if pedido not in VARIAVEL:
            raise ValueError(f"DUET_PROVEDOR inválido: {pedido} (use {', '.join(VARIAVEL)})")
        if not os.getenv(VARIAVEL[pedido]):
            raise RuntimeError(f"Provedor {pedido} escolhido, mas falta {VARIAVEL[pedido]}")
        return pedido
    for p in ("claude-code", "groq", "claude-api"):
        if os.getenv(VARIAVEL[p]):
            return p
    raise RuntimeError("Nenhuma chave de IA configurada (Claude Code, Groq ou Claude API).")


def modelo(provedor, para="conversa"):
    if para == "verificacao" and os.getenv("DUET_MODELO_VERIFICACAO"):
        return os.environ["DUET_MODELO_VERIFICACAO"]
    if para == "conversa" and os.getenv("DUET_MODELO"):
        return os.environ["DUET_MODELO"]
    return PADROES[provedor][0 if para == "conversa" else 1]


# ------------------------------------------------------------- Claude API
def claude_api(mensagens, sistema, defs, executar, modelo, cliente=None):
    import anthropic

    cliente = cliente or anthropic.Anthropic()
    msgs = list(mensagens)
    for _ in range(LIMITE_PASSOS):
        resp = cliente.messages.create(
            model=modelo, max_tokens=2000, system=sistema, tools=defs, messages=msgs
        )
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        msgs.append({"role": "assistant", "content": resp.content})
        resultados = []
        for bloco in resp.content:
            if bloco.type == "tool_use":
                texto, erro = executar(bloco.name, bloco.input)
                resultados.append({"type": "tool_result", "tool_use_id": bloco.id,
                                   "content": texto, "is_error": erro})
        msgs.append({"role": "user", "content": resultados})
    return DESISTENCIA


# ------------------------------------------------------------------- Groq
def _groq_post(corpo):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json=corpo,
        timeout=120,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Groq {r.status_code}: {r.text[:300]}")
    return r.json()


def groq(mensagens, sistema, defs, executar, modelo, post=None):
    post = post or _groq_post
    ferramentas = [
        {"type": "function", "function": {
            "name": d["name"], "description": d["description"], "parameters": d["input_schema"]}}
        for d in defs
    ]
    msgs = [{"role": "system", "content": sistema}] + [
        {"role": m["role"], "content": m["content"]} for m in mensagens
    ]
    for _ in range(LIMITE_PASSOS):
        resp = post({"model": modelo, "messages": msgs, "tools": ferramentas,
                     "tool_choice": "auto", "max_tokens": 2000})
        msg = resp["choices"][0]["message"]
        chamadas = msg.get("tool_calls") or []
        if not chamadas:
            return (msg.get("content") or "").strip()
        msgs.append({"role": "assistant", "content": msg.get("content") or "",
                     "tool_calls": chamadas})
        for ch in chamadas:
            try:
                entrada = json.loads(ch["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                entrada = {}
            texto, _ = executar(ch["function"]["name"], entrada)
            msgs.append({"role": "tool", "tool_call_id": ch["id"], "content": texto})
    return DESISTENCIA


# ------------------------------------------------------------ Claude Code
def claude_code(texto, sistema, modelo, sessao=None, rodar=subprocess.run):
    """Roda `claude -p` com a assinatura. Devolve (resposta, id_da_sessao)."""
    config_mcp = json.dumps({"mcpServers": {"duet": {
        "command": sys.executable,
        "args": [str(AQUI / "mcp_ferramentas.py")],
    }}})
    cmd = [
        "claude", "-p", texto,
        "--output-format", "json",
        "--model", modelo,
        "--tools", "",                       # sem Bash/Edit/etc: só as ferramentas do Duet
        "--mcp-config", config_mcp,
        "--strict-mcp-config",
        "--allowedTools", "mcp__duet",
        "--permission-mode", "dontAsk",
        "--append-system-prompt", sistema,
    ]
    if sessao:
        cmd += ["--resume", sessao]
    amb = dict(os.environ)
    amb.pop("ANTHROPIC_API_KEY", None)  # senão o CLI cobra da API em vez da assinatura
    proc = rodar(cmd, capture_output=True, text=True, timeout=600, env=amb, cwd=str(AQUI),
                 stdin=subprocess.DEVNULL)
    try:
        dados = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Claude Code falhou: {(proc.stderr or proc.stdout)[:400]}")
    if dados.get("is_error"):
        raise RuntimeError(f"Claude Code: {str(dados.get('result'))[:400]}")
    return (dados.get("result") or "").strip(), dados.get("session_id")
