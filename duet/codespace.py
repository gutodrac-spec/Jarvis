"""Ligar e desligar o Codespace do Duet pela API do GitHub.

Precisa de GH_PAT com o escopo `codespace` (token clássico).
"""
import os

import requests

API = "https://api.github.com"
REPO = os.getenv("DUET_REPO", "gutodrac-spec/Jarvis")
DEVCONTAINER = ".devcontainer/duet/devcontainer.json"
NOME_EXIBICAO = "duet"


def _cab():
    return {
        "Authorization": f"Bearer {os.environ['GH_PAT']}",
        "Accept": "application/vnd.github+json",
    }


def encontrar():
    r = requests.get(f"{API}/repos/{REPO}/codespaces", headers=_cab(), timeout=30)
    r.raise_for_status()
    for cs in r.json().get("codespaces", []):
        if cs.get("display_name") == NOME_EXIBICAO:
            return cs
    return None


def criar():
    r = requests.post(
        f"{API}/repos/{REPO}/codespaces",
        headers=_cab(),
        json={
            "ref": "main",
            "devcontainer_path": DEVCONTAINER,
            "display_name": NOME_EXIBICAO,
            "machine": "basicLinux32gb",  # 2 núcleos: o que mais rende a cota grátis
            "idle_timeout_minutes": 30,
            "retention_period_minutes": 43200,  # 30 dias desligado antes de apagar
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def ligar():
    """Liga o Codespace do Duet (cria se ainda não existir). Devolve o estado."""
    cs = encontrar()
    if cs is None:
        return criar().get("state", "Criando")
    if cs["state"] in ("Shutdown", "ShuttingDown"):
        r = requests.post(f"{API}/user/codespaces/{cs['name']}/start", headers=_cab(), timeout=60)
        r.raise_for_status()
        return "Ligando"
    return cs["state"]


def esta_ligado():
    cs = encontrar()
    return cs is not None and cs["state"] not in ("Shutdown", "ShuttingDown")


def desligar_este():
    """Chamado de dentro do Codespace para se desligar."""
    nome = os.getenv("CODESPACE_NAME")
    if not nome:
        return False
    r = requests.post(f"{API}/user/codespaces/{nome}/stop", headers=_cab(), timeout=60)
    return r.ok
