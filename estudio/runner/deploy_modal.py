"""Publica o executor de Spaces e modelos na Modal (GPU sob demanda).

    pip install modal && modal setup
    modal secret create executor-segredos RUNNER_CHAVE=sua-chave HF_TOKEN=hf_xxx   # HF_TOKEN é opcional
    modal deploy deploy_modal.py        # a partir da pasta estudio/runner

O deploy imprime o endereço (https://SEU-USUARIO--executor-executor.modal.run). Cole-o no site.

Opções (variáveis de ambiente lidas NO MOMENTO DO DEPLOY):
  RUNNER_GPU           GPU: T4, L4, A10G, L40S (48 GB, padrão), A100-40GB, A100-80GB, H100...  (a Modal valida o nome no deploy)
  RUNNER_OCIOSO        segundos sem uso até desligar a GPU (padrão 300; menor = gasta menos)
  RUNNER_APP           nome do app na Modal (padrão "executor")
  RUNNER_PROXY_AUTH    "1" exige tokens de proxy da Modal em toda chamada (veja MODAL.md: bloqueia o site no navegador)
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import modal

AQUI = Path(__file__).resolve().parent
NOME_APP = os.environ.get("RUNNER_APP", "executor")
GPU = os.environ.get("RUNNER_GPU", "L40S")
OCIOSO = int(os.environ.get("RUNNER_OCIOSO", "300"))
PROXY_AUTH = os.environ.get("RUNNER_PROXY_AUTH") == "1"
PORTA = 7860
NOME_SEGREDO = "executor-segredos"  # modal secret create executor-segredos RUNNER_CHAVE=...
NOME_VOLUME = "executor-cache"      # pesos do Hugging Face e cache do pip: sobrevivem ao desligamento da GPU

imagem = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")  # git: requisitos "git+https://..." de Spaces; o resto: vídeo e OpenCV
    .pip_install(
        "torch", "gradio>=6", "huggingface_hub", "pyyaml", "diffusers>=0.34", "transformers>=4.56", "accelerate",
        "sentencepiece", "safetensors", "pillow", "numpy", "imageio", "imageio-ffmpeg",
    )
    .env({
        "HF_HOME": "/cache/hf", "PIP_CACHE_DIR": "/cache/pip",
        "RUNNER_DADOS": "/tmp/runner",      # código e ambientes dos Spaces: reinstalados a cada partida (o pip usa o cache acima)
        "GRADIO_ANALYTICS_ENABLED": "False", "PYTHONUNBUFFERED": "1",
    })
    .add_local_dir(AQUI, remote_path="/app",
                   ignore=["testes/**", "__pycache__/**", "**/__pycache__/**", "dados/**", "*.zip", "*.md", "ms_deploy.json"])
)

app = modal.App(NOME_APP)
volume = modal.Volume.from_name(NOME_VOLUME, create_if_missing=True)
segredos = modal.Secret.from_name(NOME_SEGREDO, required_keys=["RUNNER_CHAVE"])


def iniciar_servidor(pasta: str = "/app", porta: int = PORTA, comitar=None, intervalo: int = 60) -> subprocess.Popen:
    """Sobe o executor (app.py) em segundo plano. Roda uma vez, quando a GPU liga.

    `comitar`: função chamada a cada minuto para gravar o cache no Volume (None = não grava).
    """
    ambiente = {**os.environ, "GRADIO_SERVER_PORT": str(porta)}
    processo = subprocess.Popen([sys.executable, "app.py"], cwd=pasta, env=ambiente)
    if comitar:
        def laco():
            while processo.poll() is None:
                time.sleep(intervalo)
                try:
                    comitar()
                except Exception as erro:  # noqa: BLE001  (não deve derrubar o executor)
                    print(f"[executor] não consegui gravar o cache no Volume: {erro}", flush=True)

        threading.Thread(target=laco, daemon=True, name="commit-volume").start()
    return processo


# max_containers=1 é essencial: cada container teria o SEU Space carregado; com 1 só, todas as chamadas
# caem no mesmo e @modal.concurrent deixa várias conexões (o Gradio usa streams longos) dividirem a GPU.
@app.function(
    image=imagem, gpu=GPU, secrets=[segredos], volumes={"/cache": volume},
    max_containers=1, scaledown_window=OCIOSO, timeout=6 * 3600,
)
@modal.concurrent(max_inputs=200)
@modal.web_server(PORTA, startup_timeout=600, requires_proxy_auth=PROXY_AUTH)
def executor():
    iniciar_servidor(comitar=volume.commit)
