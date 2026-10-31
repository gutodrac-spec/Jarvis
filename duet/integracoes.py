"""Integrações do Duet: GitHub, Vercel, Gmail e Google Drive.

Cada integração só fica ativa se as variáveis de ambiente dela existirem.
Todas as funções aqui são de LEITURA: o Duet prepara, você decide.
"""
import base64
import datetime as dt
import os

import requests

TIMEOUT = 30


def _agora():
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- GitHub
def github_ativo():
    return bool(os.getenv("GH_PAT"))


def _gh(path, **params):
    r = requests.get(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GH_PAT']}",
            "Accept": "application/vnd.github+json",
        },
        params=params,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def github_notificacoes(desde_horas=24):
    desde = (_agora() - dt.timedelta(hours=desde_horas)).isoformat()
    itens = _gh("/notifications", since=desde, all="false")
    return [
        {
            "repo": n["repository"]["full_name"],
            "tipo": n["subject"]["type"],
            "titulo": n["subject"]["title"],
            "motivo": n["reason"],
            "atualizado": n["updated_at"],
        }
        for n in itens
    ]


def github_repos_recentes(limite=10):
    itens = _gh("/user/repos", sort="pushed", per_page=limite)
    return [
        {"repo": r["full_name"], "ultimo_push": r["pushed_at"], "privado": r["private"]}
        for r in itens
    ]


def github_issues_abertas(repo):
    itens = _gh(f"/repos/{repo}/issues", state="open", per_page=20)
    return [
        {
            "numero": i["number"],
            "titulo": i["title"],
            "pull_request": "pull_request" in i,
            "autor": i["user"]["login"],
            "atualizado": i["updated_at"],
        }
        for i in itens
    ]


# ---------------------------------------------------------------- Vercel
def vercel_ativo():
    return bool(os.getenv("VERCEL_TOKEN"))


def vercel_deploys(limite=10):
    params = {"limit": limite}
    if os.getenv("VERCEL_TEAM_ID"):
        params["teamId"] = os.environ["VERCEL_TEAM_ID"]
    r = requests.get(
        "https://api.vercel.com/v6/deployments",
        headers={"Authorization": f"Bearer {os.environ['VERCEL_TOKEN']}"},
        params=params,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [
        {
            "projeto": d.get("name"),
            "estado": d.get("state") or d.get("readyState"),
            "alvo": d.get("target"),
            "url": d.get("url"),
            "criado": dt.datetime.fromtimestamp(
                d["created"] / 1000, dt.timezone.utc
            ).isoformat(),
        }
        for d in r.json().get("deployments", [])
    ]


# ---------------------------------------------------------------- Google
GOOGLE_ESCOPOS = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


def google_ativo():
    return all(
        os.getenv(v)
        for v in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    )


def _google_credenciais():
    from google.oauth2.credentials import Credentials

    return Credentials(
        None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=GOOGLE_ESCOPOS,
    )


def _servico(nome, versao):
    from googleapiclient.discovery import build

    return build(nome, versao, credentials=_google_credenciais(), cache_discovery=False)


def gmail_buscar(consulta="is:unread newer_than:1d", limite=15):
    svc = _servico("gmail", "v1")
    lista = svc.users().messages().list(userId="me", q=consulta, maxResults=limite).execute()
    saida = []
    for m in lista.get("messages", []):
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="metadata",
                 metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        cab = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        saida.append(
            {
                "id": m["id"],
                "de": cab.get("From"),
                "assunto": cab.get("Subject"),
                "data": cab.get("Date"),
                "trecho": msg.get("snippet"),
            }
        )
    return saida


def _texto_do_payload(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for parte in payload.get("parts", []) or []:
        texto = _texto_do_payload(parte)
        if texto:
            return texto
    return ""


def gmail_ler(id_mensagem):
    svc = _servico("gmail", "v1")
    msg = svc.users().messages().get(userId="me", id=id_mensagem, format="full").execute()
    cab = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    return {
        "de": cab.get("From"),
        "para": cab.get("To"),
        "assunto": cab.get("Subject"),
        "data": cab.get("Date"),
        "corpo": _texto_do_payload(msg["payload"])[:8000] or msg.get("snippet"),
    }


def drive_recentes(desde_horas=24, limite=15):
    svc = _servico("drive", "v3")
    desde = (_agora() - dt.timedelta(hours=desde_horas)).strftime("%Y-%m-%dT%H:%M:%S")
    res = (
        svc.files()
        .list(
            q=f"modifiedTime > '{desde}' and trashed = false",
            orderBy="modifiedTime desc",
            pageSize=limite,
            fields="files(name,mimeType,modifiedTime,webViewLink,lastModifyingUser(displayName))",
        )
        .execute()
    )
    return [
        {
            "nome": f["name"],
            "tipo": f["mimeType"],
            "modificado": f["modifiedTime"],
            "por": (f.get("lastModifyingUser") or {}).get("displayName"),
            "link": f.get("webViewLink"),
        }
        for f in res.get("files", [])
    ]


def integracoes_ativas():
    return {
        "github": github_ativo(),
        "vercel": vercel_ativo(),
        "gmail": google_ativo(),
        "drive": google_ativo(),
    }
