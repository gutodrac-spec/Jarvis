"""Executor de Spaces e modelos do Hugging Face para o Studio do ModelScope (xGPU).

Este app é a API. Os endpoints (todos com `api_name`):
  /status                                  GPU, Spaces carregados e se há chave configurada
  /diagnostico                             se a GPU aparece no processo principal e num processo filho (onde os Spaces rodam)
  /carregar(chave, alvo)                   começa a carregar um Space (segundo plano); acompanhe em /status
  /apis(chave, alvo)                       endpoints e parâmetros do Space carregado
  /chamar(chave, alvo, api_name, args, arquivos)   chama um endpoint do Space
  /log(chave, alvo)                        últimas linhas do log do Space
  /modelo(chave, modelo, tarefa, entrada, arquivos)  roda um modelo solto (transformers/diffusers)
  /parar(chave)                            desliga tudo e libera a GPU

Segurança: carregar um Space executa o código dele aqui. Por isso só quem tem a RUNNER_CHAVE pode carregar algo;
os Spaces/modelos listados em RUNNER_PUBLICOS (separados por vírgula) podem ser usados por qualquer pessoa.
Sem RUNNER_CHAVE, só os públicos funcionam. Defina a chave nas variáveis do Studio (nunca no repositório).
"""

import ambiente

ambiente.configurar()  # precisa vir antes de importar o gradio (que lê o HF_ENDPOINT)

import hmac  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

import gradio as gr  # noqa: E402

import espacos  # noqa: E402
import modelos  # noqa: E402

VERSAO = "1.0"


def _publicos() -> set[str]:
    return {x.strip() for x in os.environ.get("RUNNER_PUBLICOS", "").split(",") if x.strip()}


def autorizar(chave: str, alvo: str | None = None):
    if alvo and alvo.strip() in _publicos():
        return
    segredo = os.environ.get("RUNNER_CHAVE", "")
    if not segredo:
        raise gr.Error("Este executor não tem RUNNER_CHAVE: só os Spaces e modelos de RUNNER_PUBLICOS podem ser usados.")
    if not hmac.compare_digest(str(chave or "").encode(), segredo.encode()):
        raise gr.Error("Chave inválida.")


def _json(texto: str, padrao):
    if not (texto or "").strip():
        return padrao
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        raise gr.Error(f"JSON inválido: {erro}") from erro


def _gpu() -> dict:
    try:
        import torch

        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            livre, total = torch.cuda.mem_get_info()
            return {"nome": p.name, "memoria_gb": round(total / 2**30, 1), "livre_gb": round(livre / 2**30, 1)}
    except Exception:  # noqa: BLE001
        pass
    return {"nome": None}


def api_status():
    return {"versao": VERSAO, "gpu": _gpu(), "espacos": espacos.estado_geral(),
            "chave_configurada": bool(os.environ.get("RUNNER_CHAVE")), "publicos": sorted(_publicos()),
            "max_ativos": espacos.MAX_ATIVOS}


def api_diagnostico():
    return {"principal": _gpu(), "subprocesso": espacos.diagnostico_gpu()}


def api_carregar(chave: str, alvo: str):
    autorizar(chave, alvo)
    try:
        return espacos.iniciar(alvo).resumo()
    except espacos.ErroRunner as erro:
        raise gr.Error(str(erro)) from erro


def api_apis(chave: str, alvo: str):
    autorizar(chave, alvo)
    try:
        esp = espacos.obter(alvo)
    except espacos.ErroRunner as erro:
        raise gr.Error(str(erro)) from erro
    if esp is None or esp.estado != "pronto":
        raise gr.Error(f"O Space não está pronto ({esp.estado if esp else 'não carregado'}). Use /carregar e espere.")
    return espacos.apis_simples(esp)


def api_log(chave: str, alvo: str):
    autorizar(chave, alvo)
    try:
        esp = espacos.obter(alvo)
    except espacos.ErroRunner as erro:
        raise gr.Error(str(erro)) from erro
    return {"log": espacos.ultimas_linhas(esp.log, 40) if esp else ""}


def api_chamar(chave: str, alvo: str, api_name: str, argumentos: str, arquivos):
    autorizar(chave, alvo)
    entradas = _json(argumentos, [])
    try:
        if espacos.obter(alvo) is None:
            espacos.iniciar(alvo)  # começa a carregar; o site acompanha em /status
        resultado, saidas = espacos.chamar(alvo, api_name or "/predict", entradas, list(arquivos or []))
    except espacos.ErroRunner as erro:
        raise gr.Error(str(erro)) from erro
    except gr.Error:
        raise
    except Exception as erro:  # noqa: BLE001  (erro dentro do Space)
        raise gr.Error(f"O Space devolveu um erro: {str(erro)[:500]}") from erro
    return {"resultado": resultado}, saidas


def api_modelo(chave: str, modelo: str, tarefa: str, entrada: str, arquivos):
    autorizar(chave, modelo)
    try:
        resultado, saidas = modelos.executar(modelo, tarefa, _json(entrada, {}), list(arquivos or []))
    except espacos.ErroRunner as erro:
        raise gr.Error(str(erro)) from erro
    except Exception as erro:  # noqa: BLE001
        raise gr.Error(f"O modelo falhou: {str(erro)[:500]}") from erro
    return {"resultado": resultado}, saidas


def api_parar(chave: str):
    autorizar(chave)
    espacos.parar_todos()
    modelos.liberar()
    return {"ok": True}


with gr.Blocks(title="Executor de Spaces", delete_cache=(3600, 7200)) as demo:
    gr.Markdown("# 🧩 Executor de Spaces e modelos\nCarrega qualquer Space Gradio ou modelo do Hugging Face "
                "na GPU deste Studio e deixa usar por API. Veja `cliente.view_api()` ou o site que acompanha.")
    chave = gr.Textbox(label="Chave (RUNNER_CHAVE)", type="password")
    with gr.Tab("Status"):
        saida_status = gr.JSON(label="Estado")
        gr.Button("Atualizar").click(api_status, None, saida_status, api_name="status")
        gr.Button("Testar GPU (processo principal e filho)").click(api_diagnostico, None, saida_status, api_name="diagnostico")
    with gr.Tab("Space"):
        alvo = gr.Textbox(label="Space (dono/nome)", placeholder="Lightricks/ltx-video-distilled")
        saida_space = gr.JSON(label="Resultado")
        with gr.Row():
            gr.Button("Carregar").click(api_carregar, [chave, alvo], saida_space, api_name="carregar")
            gr.Button("Ver APIs").click(api_apis, [chave, alvo], saida_space, api_name="apis")
            gr.Button("Log").click(api_log, [chave, alvo], saida_space, api_name="log")
            gr.Button("Parar tudo").click(api_parar, [chave], saida_space, api_name="parar")
        api_nome = gr.Textbox(label="Endpoint", placeholder="/predict")
        args = gr.Textbox(label="Argumentos (JSON: lista ou objeto)", lines=3, placeholder='["olá", 3]')
        arqs = gr.File(label="Arquivos (cite como \"@arquivo:0\")", file_count="multiple", type="filepath")
        saida_json, saida_arqs = gr.JSON(label="Resultado da chamada"), gr.File(label="Arquivos gerados", file_count="multiple")
        gr.Button("Chamar", variant="primary").click(
            api_chamar, [chave, alvo, api_nome, args, arqs], [saida_json, saida_arqs],
            api_name="chamar", concurrency_limit=1, concurrency_id="gpu")
    with gr.Tab("Modelo solto"):
        modelo_id = gr.Textbox(label="Modelo (dono/nome)", placeholder="stabilityai/sdxl-turbo")
        tarefa = gr.Dropdown(sorted(list(modelos.TAREFAS_DIFUSAO) + list(modelos.ALIAS_TRANSFORMERS)),
                             label="Tarefa", allow_custom_value=True, value="texto-para-imagem")
        entrada = gr.Textbox(label="Entrada (JSON)", lines=3, placeholder='{"prompt": "um gato astronauta"}')
        arqs_m = gr.File(label="Arquivos (cite como \"@arquivo:0\")", file_count="multiple", type="filepath")
        saida_json_m, saida_arqs_m = gr.JSON(label="Resultado"), gr.File(label="Arquivos gerados", file_count="multiple")
        gr.Button("Executar", variant="primary").click(
            api_modelo, [chave, modelo_id, tarefa, entrada, arqs_m], [saida_json_m, saida_arqs_m],
            api_name="modelo", concurrency_limit=1, concurrency_id="gpu")

if __name__ == "__main__":
    espacos.iniciar_limpeza(idade=int(os.environ.get("RUNNER_IDADE_ARQUIVOS", "7200")))
    for item in [x.strip() for x in os.environ.get("RUNNER_PRECARREGAR", "").split(",") if x.strip()][:espacos.MAX_ATIVOS]:
        try:
            espacos.iniciar(item)
        except espacos.ErroRunner as erro:
            print(f"[runner] não pré-carreguei {item}: {erro}")
    demo.queue(default_concurrency_limit=4).launch(
        server_name="0.0.0.0", server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        allowed_paths=[str(espacos.DADOS)],  # permite devolver os arquivos gerados pelos Spaces
        strict_cors=False,                   # o site fica em outro domínio e chama esta API
    )
