"""Duet — assistente proativo do Gustavo no Telegram.

Modos:
  python duet.py            -> bot (roda dentro do Codespace, desliga sozinho quando ocioso)
  python duet.py verificar  -> checagem proativa (roda no GitHub Actions, de hora em hora)
  python duet.py acordar    -> liga o Codespace se houver mensagem esperando (Actions, a cada 10 min)
"""
import os
import sys
import time

import requests

import codespace
import telegram

# `agente` (Claude API) é importado só onde é usado: o modo "acordar"
# roda no Actions só com `requests` instalado.

MINUTOS_OCIOSO = int(os.getenv("DUET_MINUTOS_OCIOSO", "15"))

AJUDA = """Comandos:
/status – integrações ativas
/verificar – faz a checagem agora
/esquecer – apaga histórico e memória
/dormir – desliga o servidor agora
Qualquer outra mensagem: é só conversar."""


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def tratar(texto):
    """Devolve (resposta, deve_dormir)."""
    import agente

    cmd = texto.strip().split()[0].lower() if texto.strip() else ""
    if cmd in ("/start", "/ajuda", "/help"):
        return AJUDA, False
    if cmd == "/status":
        ativas = agente.integ.integracoes_ativas()
        linhas = [f"{'✅' if v else '⬜'} {k}" for k, v in ativas.items()]
        return "\n".join(linhas) + f"\nModelo: {agente.MODELO_CHAT}", False
    if cmd == "/verificar":
        return agente.verificar(janela_minutos=24 * 60) or "Nada importante nas últimas 24 h.", False
    if cmd == "/esquecer":
        agente.esquecer_tudo()
        return "Histórico e memória apagados.", False
    if cmd == "/dormir":
        return "Indo dormir 😴 Mande mensagem que eu acordo em até ~10 min.", True
    return agente.conversar(texto), False


def bot():
    chat_ok = telegram.chat_autorizado()
    offset = None
    ultima_atividade = time.time()
    log("Duet no ar")
    while True:
        try:
            atualizacoes = telegram.buscar_atualizacoes(offset)
        except requests.HTTPError as e:
            # 409 = outro processo lendo a fila ao mesmo tempo (ex.: o vigia); tenta de novo
            log("Telegram:", e)
            time.sleep(5)
            continue
        except requests.RequestException as e:
            log("Rede:", e)
            time.sleep(10)
            continue

        dormir = False
        for upd in atualizacoes:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            if msg.get("chat", {}).get("id") != chat_ok:
                continue  # ignora qualquer pessoa que não seja o Gustavo
            texto = msg.get("text")
            if not texto:
                telegram.enviar("Por enquanto só entendo texto.")
                continue
            ultima_atividade = time.time()
            telegram.digitando()
            try:
                resposta, dormir = tratar(texto)
            except Exception as e:
                log("Erro:", repr(e))
                resposta = f"Deu erro aqui: {e}"
            telegram.enviar(resposta)

        ocioso = time.time() - ultima_atividade > MINUTOS_OCIOSO * 60
        if dormir or ocioso:
            log("Desligando o Codespace")
            if codespace.desligar_este():
                time.sleep(120)  # espera o desligamento chegar
            else:
                log("Não consegui me desligar (fora do Codespace?). Saindo.")
                return


def verificar():
    import agente

    aviso = agente.verificar()
    if aviso:
        telegram.enviar("🔔 " + aviso)
        log("Aviso enviado")
    else:
        log("Nada importante")


def acordar():
    if codespace.esta_ligado():
        log("Codespace já está ligado")
        return
    if telegram.ha_mensagens_pendentes():
        log("Mensagem esperando -> ligando:", codespace.ligar())
    else:
        log("Nenhuma mensagem esperando")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "bot"
    {"bot": bot, "verificar": verificar, "acordar": acordar}[modo]()
