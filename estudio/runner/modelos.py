"""Roda modelos soltos do Hugging Face (sem Space) na GPU do Studio, por tarefa.

Um modelo fica carregado por vez (a GPU é pequena): ao pedir outro, o anterior é descartado.
Nunca usa trust_remote_code: só arquiteturas que o transformers/diffusers já conhecem.
"""

import gc
import json
import os
import re
import threading
import uuid
import wave
from pathlib import Path

from espacos import DADOS, ErroRunner, caminho_local, validar_id

# Nomes em português para as tarefas mais comuns; qualquer outra string vai direto ao transformers.pipeline.
TAREFAS_DIFUSAO = {"texto-para-imagem": "t2i", "imagem-para-imagem": "i2i",
                   "texto-para-video": "geral", "imagem-para-video": "geral", "difusao": "geral"}
ALIAS_TRANSFORMERS = {
    "texto": "text-generation", "reconhecimento-de-fala": "automatic-speech-recognition",
    "texto-para-audio": "text-to-audio", "traducao": "translation", "resumo": "summarization",
    "classificacao-de-texto": "text-classification", "classificacao-de-imagem": "image-classification",
    "perguntas-e-respostas": "question-answering", "descricao-de-imagem": "image-to-text",
}
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

_TRAVA = threading.Lock()
_ATUAL: dict = {"chave": None, "objeto": None}


def _dispositivo():
    import torch

    if torch.cuda.is_available():
        dtype = torch.bfloat16 if torch.cuda.get_device_capability(0)[0] >= 8 else torch.float16
        return "cuda", dtype
    return "cpu", torch.float32


def liberar():
    with _TRAVA:
        _ATUAL.update(chave=None, objeto=None)
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _fonte(modelo_id: str) -> str:
    tipo, nome = validar_id(modelo_id)
    return str(caminho_local(nome)) if tipo == "local" else nome


def _carregar(modelo_id: str, tarefa: str):
    chave = (modelo_id, tarefa)
    if _ATUAL["chave"] == chave:
        return _ATUAL["objeto"]
    liberar()
    fonte, token = _fonte(modelo_id), os.environ.get("HF_TOKEN") or None
    dispositivo, dtype = _dispositivo()
    if tarefa in TAREFAS_DIFUSAO:
        import diffusers

        classe = {"t2i": diffusers.AutoPipelineForText2Image, "i2i": diffusers.AutoPipelineForImage2Image,
                  "geral": diffusers.DiffusionPipeline}[TAREFAS_DIFUSAO[tarefa]]
        objeto = classe.from_pretrained(fonte, torch_dtype=dtype, token=token).to(dispositivo)
    else:
        from transformers import pipeline

        nome_tarefa = ALIAS_TRANSFORMERS.get(tarefa, tarefa)
        argumentos = dict(model=fonte, device=0 if dispositivo == "cuda" else -1, token=token)
        try:
            objeto = pipeline(nome_tarefa, dtype=dtype, **argumentos)
        except TypeError:  # transformers mais antigo
            objeto = pipeline(nome_tarefa, torch_dtype=dtype, **argumentos)
    with _TRAVA:
        _ATUAL.update(chave=chave, objeto=objeto)
    return objeto


def _resolver_arquivos(valor, enviados: list[str]):
    """"@arquivo:N" vira uma imagem (PIL) se o arquivo for imagem, ou o caminho dele."""
    if isinstance(valor, str):
        m = re.fullmatch(r"@arquivo:(\d+)", valor)
        if not m:
            return valor
        indice = int(m.group(1))
        if indice >= len(enviados):
            raise ErroRunner(f"O argumento cita o arquivo {indice}, mas só {len(enviados)} foram enviados.")
        caminho = enviados[indice]
        if Path(caminho).suffix.lower() in EXT_IMAGEM:
            from PIL import Image

            return Image.open(caminho).convert("RGB")
        return caminho
    if isinstance(valor, list):
        return [_resolver_arquivos(v, enviados) for v in valor]
    if isinstance(valor, dict):
        return {k: _resolver_arquivos(v, enviados) for k, v in valor.items()}
    return valor


def _novo_arquivo(extensao: str) -> Path:
    pasta = DADOS / "saidas"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / f"{uuid.uuid4().hex}{extensao}"


def _salvar_wav(audio, taxa: int) -> Path:
    import numpy as np

    dados = np.asarray(audio, dtype="float32").reshape(-1)
    pcm = (np.clip(dados, -1, 1) * 32767).astype("<i2")
    caminho = _novo_arquivo(".wav")
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(taxa))
        w.writeframes(pcm.tobytes())
    return caminho


def _normalizar_saida(saida, arquivos: list[str]):
    """Resultado -> valor serializável em JSON; arquivos gerados vão para a lista `arquivos`."""
    from PIL import Image

    def arquivo(caminho: Path):
        arquivos.append(str(caminho))
        return {"__arquivo__": len(arquivos) - 1}

    def imagem(img):
        caminho = _novo_arquivo(".png")
        img.save(caminho)
        return arquivo(caminho)

    if hasattr(saida, "images") and saida.images is not None:  # diffusers (imagens)
        return [imagem(i) for i in saida.images]
    if hasattr(saida, "frames") and saida.frames is not None:  # diffusers (vídeo)
        from diffusers.utils import export_to_video

        caminho = _novo_arquivo(".mp4")
        export_to_video(saida.frames[0], str(caminho), fps=int(os.environ.get("RUNNER_FPS_VIDEO", "16")))
        return arquivo(caminho)
    if isinstance(saida, Image.Image):
        return imagem(saida)
    if isinstance(saida, dict) and "audio" in saida and "sampling_rate" in saida:
        return arquivo(_salvar_wav(saida["audio"], saida["sampling_rate"]))
    if isinstance(saida, (list, tuple)):
        return [_normalizar_saida(x, arquivos) for x in saida]
    if isinstance(saida, dict):
        return {k: _normalizar_saida(v, arquivos) for k, v in saida.items()}
    if hasattr(saida, "tolist"):
        return saida.tolist()
    try:
        json.dumps(saida)
        return saida
    except TypeError:
        return str(saida)


def executar(modelo_id: str, tarefa: str, entrada: dict, enviados: list[str]):
    """Roda `tarefa` com o modelo. `entrada`: {"entrada": ..., outros parâmetros do pipeline}."""
    import torch

    if not isinstance(entrada, dict):
        raise ErroRunner("A entrada deve ser um objeto JSON, ex.: {\"prompt\": \"um gato\"}.")
    tarefa = (tarefa or "").strip()
    if not tarefa:
        raise ErroRunner("Informe a tarefa (ex.: texto-para-imagem, texto, reconhecimento-de-fala).")
    objeto = _carregar(modelo_id, tarefa)
    parametros = _resolver_arquivos(dict(entrada), enviados)
    with torch.inference_mode():
        if tarefa in TAREFAS_DIFUSAO:
            saida = objeto(**parametros)
        else:
            principal = parametros.pop("entrada", None)
            saida = objeto(*([] if principal is None else [principal]), **parametros)
    arquivos: list[str] = []
    return _normalizar_saida(saida, arquivos), arquivos
