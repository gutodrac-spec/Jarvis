"""Publica o Estúdio num HF Space com ZeroGPU.

Uso (no Colab, no Ubuntu ou em qualquer lugar com Python), a partir da pasta estudio/:
    pip install -U huggingface_hub
    hf auth login                      # token do tipo *write*: huggingface.co/settings/tokens
    python space/publicar.py luismurer/Video-generaton

O Space pode já existir (por exemplo, o modelo estático criado pelo site): os arquivos
padrão (index.html, style.css) são removidos e ele passa a ser Gradio.
"""

import sys
from pathlib import Path

from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

PASTA = Path(__file__).resolve().parent.parent  # estudio/
ARQUIVOS = {  # caminho no Space: arquivo local
    "app.py": PASTA / "app.py",
    "presets.py": PASTA / "presets.py",
    "requirements.txt": PASTA / "space" / "requirements.txt",
    "README.md": PASTA / "space" / "README.md",
}
SOBRAS = ["index.html", "style.css"]  # arquivos do modelo estático padrão


def main():
    if len(sys.argv) != 2:
        sys.exit("uso: python space/publicar.py usuario/nome-do-space")
    repo = sys.argv[1]
    api = HfApi()
    print("conta:", api.whoami()["name"])

    api.create_repo(repo, repo_type="space", space_sdk="gradio", exist_ok=True)
    existentes = set(api.list_repo_files(repo, repo_type="space"))
    ops = [CommitOperationAdd(destino, str(origem)) for destino, origem in ARQUIVOS.items()]
    ops += [CommitOperationDelete(f) for f in SOBRAS if f in existentes]
    api.create_commit(repo, ops, repo_type="space", commit_message="Estúdio: gerador de vídeo (ZeroGPU)")
    print("arquivos enviados:", ", ".join(ARQUIVOS))

    try:
        api.request_space_hardware(repo, "zero-a10g")  # nome interno do ZeroGPU
        print("hardware: ZeroGPU pedido")
    except Exception as erro:  # noqa: BLE001
        print(f"não consegui pedir o ZeroGPU ({erro}).\n"
              f"  Escolha em https://huggingface.co/spaces/{repo}/settings > Space hardware > ZeroGPU")
    print(f"pronto: https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
