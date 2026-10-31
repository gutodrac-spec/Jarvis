# Duet

Assistente proativo no Telegram, inspirado no Claude Duet. Ele conversa com você,
consulta e-mail, Google Drive, GitHub e Vercel e avisa sozinho quando algo precisa de atenção.
Só tem acesso de **leitura**: prepara rascunhos e pede confirmação, não executa ações.

## Como funciona

| Peça | Onde roda | Quando |
|---|---|---|
| **Vigia** (`duet-acordar.yml`) | GitHub Actions | a cada 10 min: se o Codespace está desligado e há mensagem sua esperando no Telegram, liga o Codespace |
| **Bot** (`duet.py`) | Codespace `duet` | responde em tempo real; depois de 15 min sem mensagens, desliga o Codespace sozinho |
| **Checagem** (`duet-verificar.yml`) | GitHub Actions | de hora em hora, 7h–23h: olha suas contas e só manda aviso se houver algo importante |

O Codespace fica desligado quase o tempo todo, então a cota grátis rende.
O Telegram guarda suas mensagens por 24 h, então nada se perde enquanto ele dorme:
a resposta chega em até ~10 min + 1–2 min para ligar.

O histórico e a memória ficam no disco do Codespace (`~/.duet`), **nunca no Git** —
este repositório é público.

## Configuração (uma vez)

1. **Bot do Telegram:** fale com o @BotFather, `/newbot`, guarde o token.
   Mande qualquer mensagem para o seu bot e abra
   `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver o seu `chat.id`.
2. **Claude API:** crie uma chave em console.anthropic.com (cobrada à parte do plano Pro/Max).
3. **Token do GitHub:** Settings → Developer settings → Tokens (classic), com os escopos
   `codespace`, `repo` e `notifications`.
4. **Vercel (opcional):** vercel.com/account/tokens.
5. **Gmail e Drive (opcional):** siga as instruções no topo de `google_setup.py`.

### Onde colocar os segredos (nos dois lugares)

- **Actions:** repositório Jarvis → Settings → Secrets and variables → Actions.
- **Codespaces:** github.com/settings/codespaces → Secrets, liberando o repositório Jarvis.

| Segredo | Obrigatório |
|---|---|
| `ANTHROPIC_API_KEY` | sim |
| `TELEGRAM_TOKEN` | sim |
| `TELEGRAM_CHAT_ID` | sim |
| `GH_PAT` | sim |
| `VERCEL_TOKEN` | não |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | não |

### Primeiro uso

Em Actions → "Duet - acordar" → **Run workflow** depois de mandar um "oi" ao bot.
Na primeira vez o Codespace é criado (leva alguns minutos). Depois é tudo automático.

## Comandos no Telegram

`/status`, `/verificar`, `/esquecer`, `/dormir` — ou só converse.

## Ajustes por variável de ambiente

- `DUET_MODELO` (padrão `claude-sonnet-5-5`) — modelo da conversa
- `DUET_MODELO_VERIFICACAO` (padrão `claude-haiku-5-5`) — modelo da checagem de hora em hora
- `DUET_MINUTOS_OCIOSO` (padrão `15`) — minutos sem mensagem até desligar

## Custos

- Actions: grátis em repositório público.
- Codespace: só enquanto está conversando; cabe na cota grátis com uso normal.
- Claude API: cobrança por uso. A checagem com Haiku 17×/dia custa pouco; conversas longas com
  Sonnet custam mais.
