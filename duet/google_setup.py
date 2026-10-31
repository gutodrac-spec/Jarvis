"""Gera o GOOGLE_REFRESH_TOKEN (rode UMA vez, no seu computador).

1. No Google Cloud Console, crie um projeto, ative "Gmail API" e "Google Drive API".
2. Em "Credenciais", crie um "ID do cliente OAuth" do tipo "App para computador"
   e baixe o JSON como client_secret.json nesta pasta.
3. pip install google-auth-oauthlib  &&  python google_setup.py
4. Copie os três valores impressos para os segredos do GitHub.

Nunca faça commit do client_secret.json nem do token.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

from integracoes import GOOGLE_ESCOPOS

fluxo = InstalledAppFlow.from_client_secrets_file("client_secret.json", GOOGLE_ESCOPOS)
cred = fluxo.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nGOOGLE_CLIENT_ID =", cred.client_id)
print("GOOGLE_CLIENT_SECRET =", cred.client_secret)
print("GOOGLE_REFRESH_TOKEN =", cred.refresh_token)
