"""Cérebro rápido do Jarvis (Groq).

- route(): entende o pedido do usuário em ~200ms e decide:
    responder, executar uma ação simples, olhar a tela, ou delegar ao Claude.
- analyze_screen(): olha uma captura da tela e decide se deve te ligar.
"""
from __future__ import annotations

import json
import os
import re

from groq import Groq

FAST = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
SMART = os.getenv("GROQ_SMART_MODEL", "llama-3.3-70b-versatile")
VISION = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

_client: Groq | None = None


def client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


ROUTER_PROMPT = """Você é J.A.R.V.I.S., o assistente pessoal do usuário (trate-o por "senhor"), \
rodando no PC dele com controle de mouse e teclado. Fale português do Brasil, frases curtas, \
tom elegante e levemente britânico, como o Jarvis do Homem de Ferro. Suas respostas são faladas em voz alta.

Responda SEMPRE com um JSON:
{
  "reply": "o que você fala agora (curto)",
  "actions": [ ... ações rápidas, opcional ... ],
  "delegate": null ou "descrição completa e autocontida da tarefa para o agente avançado"
}

Ações rápidas disponíveis (use só quando forem suficientes):
- {"tool":"open_url","url":"https://..."}
- {"tool":"open_app","name":"nome do programa, ex: notepad, spotify, chrome, explorer, calc"}
- {"tool":"hotkey","keys":"ctrl+s"}            (atalho de teclado)
- {"tool":"type_text","text":"..."}            (digita onde o cursor está)
- {"tool":"media","key":"playpause|nexttrack|prevtrack|volumeup|volumedown|volumemute"}
- {"tool":"look","question":"o que quer descobrir na tela"}   (você vê a tela e responde)
- {"tool":"lock_pc"}

Use "delegate" para qualquer tarefa com vários passos, que exija clicar em coisas específicas, \
navegar em sites, preencher formulários, resolver erros, programar, mexer em arquivos ou que você \
não tenha certeza de como fazer só com as ações rápidas. Ao delegar, o "reply" deve avisar que \
vai cuidar disso (ex: "Deixa comigo, senhor. Cuidando disso agora.").
Nunca invente que já fez algo que não está nas actions. Se for só conversa, actions=[] e delegate=null."""


def route(history: list[dict], text: str, context: str = "") -> dict:
    msgs = [{"role": "system", "content": ROUTER_PROMPT}]
    if context:
        msgs.append({"role": "system", "content": f"Contexto atual: {context}"})
    msgs += history[-12:]
    msgs.append({"role": "user", "content": text})
    last: Exception | None = None
    for model in (SMART, FAST):  # 70B é rápido no Groq e entende melhor; 8B de reserva
        try:
            r = client().chat.completions.create(
                model=model,
                messages=msgs,
                temperature=0.3,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            data = _json(r.choices[0].message.content)
            if data:
                data.setdefault("reply", "")
                data.setdefault("actions", [])
                data.setdefault("delegate", None)
                return data
        except Exception as e:  # tenta o próximo modelo
            last = e
    return {"reply": f"Tive um problema com o Groq: {last}", "actions": [], "delegate": None}


def look(image_b64: str, question: str) -> str:
    r = client().chat.completions.create(
        model=VISION,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Você é o Jarvis olhando a tela do PC do senhor. Responda em português, "
                        f"curto e direto (vai ser falado em voz alta). Pergunta: {question}",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
        temperature=0.2,
        max_tokens=300,
    )
    return r.choices[0].message.content.strip()


MONITOR_PROMPT = """Você é o Jarvis vigiando a tela do PC do senhor enquanto ele está longe. \
Analise a captura e decida se vale a pena LIGAR para ele.

Regras do senhor: {rules}

Contexto: {context}

Responda só JSON:
{{"alert": true/false,
  "urgency": "baixa" | "normal" | "alta" | "critica",
  "reason": "motivo da ligação em 1 frase, falando com ele (ex: 'Senhor, o render do Premiere terminou.')",
  "key": "identificador curto e estável do evento, ex: 'erro-chrome', 'download-concluido'",
  "summary": "o que está na tela agora, 1 frase"}}

Não alerte para coisas normais (área de trabalho, vídeo tocando, navegação comum). \
Só alert=true se for algo que realmente encaixa nas regras ou é claramente importante."""


def analyze_screen(image_b64: str, rules: str, context: str = "") -> dict:
    r = client().chat.completions.create(
        model=VISION,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": MONITOR_PROMPT.format(rules=rules, context=context or "nenhum")},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
        temperature=0.1,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return _json(r.choices[0].message.content)
