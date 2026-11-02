"""Ajustes de ambiente que precisam rodar ANTES de importar gradio/huggingface_hub."""
import os
import urllib.request


def configurar():
    """Dentro da China o huggingface.co pode estar bloqueado: nesse caso usa um espelho.

    Defina HF_ENDPOINT para escolher o endereço, ou RUNNER_SEM_PROBE=1 para pular o teste.
    """
    if os.environ.get("HF_ENDPOINT") or os.environ.get("RUNNER_SEM_PROBE"):
        return
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=8)
    except Exception:  # noqa: BLE001
        os.environ["HF_ENDPOINT"] = os.environ.get("RUNNER_ESPELHO", "https://hf-mirror.com")
        print(f"[runner] huggingface.co inacessível daqui; usando {os.environ['HF_ENDPOINT']}")
