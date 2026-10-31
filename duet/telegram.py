"""Funções mínimas da API do Telegram (sem bibliotecas extras)."""
import os

import requests


def _url(metodo):
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/{metodo}"


def chat_autorizado():
    return int(os.environ["TELEGRAM_CHAT_ID"])


def enviar(texto, chat_id=None):
    chat_id = chat_id or chat_autorizado()
    texto = texto or "(vazio)"
    for i in range(0, len(texto), 4000):  # limite do Telegram: 4096 caracteres
        r = requests.post(
            _url("sendMessage"),
            json={"chat_id": chat_id, "text": texto[i:i + 4000]},
            timeout=30,
        )
        r.raise_for_status()


def digitando(chat_id=None):
    try:
        requests.post(
            _url("sendChatAction"),
            json={"chat_id": chat_id or chat_autorizado(), "action": "typing"},
            timeout=10,
        )
    except requests.RequestException:
        pass


def buscar_atualizacoes(offset=None, espera=50):
    params = {"timeout": espera, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(_url("getUpdates"), params=params, timeout=espera + 15)
    r.raise_for_status()
    return r.json().get("result", [])


def ha_mensagens_pendentes():
    """Olha a fila sem confirmar nada (sem offset), para o bot ainda receber depois."""
    return len(buscar_atualizacoes(espera=0)) > 0
