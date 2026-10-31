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

## Escolha da IA

| Provedor | Chave | Custo |
|---|---|---|
| `claude-code` | `CLAUDE_CODE_OAUTH_TOKEN` (rode `claude setup-token` no seu computador) | usa a sua assinatura Pro/Max, divide os limites com o seu uso normal |
| `groq` | `GROQ_API_KEY` (console.groq.com) | tem camada grátis; ótimo para a checagem de hora em hora |
| `claude-api` | `ANTHROPIC_API_KEY` | cobrada por uso |

Sem escolha, o Duet usa o primeiro disponível nesta ordem: assinatura › Groq › API.
No Telegram, `/ia groq` (ou `claude-code`, `claude-api`) troca na hora.
Dica: IA principal `claude-code` e checagem `groq` = conversa boa sem gastar a assinatura à toa.

O token da assinatura é de longa duração, mas expira; se o Duet começar a dar erro de
autenticação, gere outro com `claude setup-token` e salve de novo na página.

## Página para colocar as chaves

`docs/index.html` é uma página que cifra as chaves no seu navegador e grava direto
nos segredos do GitHub (Actions e Codespaces). Para abri-la pelo celular, ative uma vez:
repositório → **Settings → Pages** → Source: *Deploy from a branch* → `main` / `/docs` → Save.
Ela fica em **https://gutodrac-spec.github.io/Jarvis/**.

Sem ativar o Pages, baixe o arquivo e abra no navegador do computador: funciona igual.

## Configuração (uma vez)

Tudo abaixo pode ser colado na página acima, em vez de cadastrar segredo por segredo.

1. **Bot do Telegram:** fale com o @BotFather, `/newbot`, guarde o token.
   Mande qualquer mensagem para o seu bot e abra
   `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver o seu `chat.id`.
2. **IA:** pelo menos uma das três da tabela acima.
3. **Token do GitHub:** Settings → Developer settings → Tokens (classic), com os escopos
   `codespace`, `repo` e `notifications`.
4. **Vercel (opcional):** vercel.com/account/tokens.
5. **Gmail e Drive (opcional):** siga as instruções no topo de `google_setup.py`.

### Onde colocar os segredos (nos dois lugares)

- **Actions:** repositório Jarvis → Settings → Secrets and variables → Actions.
- **Codespaces:** github.com/settings/codespaces → Secrets, liberando o repositório Jarvis.

| Segredo | Obrigatório |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN`, `GROQ_API_KEY` ou `ANTHROPIC_API_KEY` | pelo menos um |
| `DUET_PROVEDOR`, `DUET_PROVEDOR_VERIFICACAO` | não |
| `TELEGRAM_TOKEN` | sim |
| `TELEGRAM_CHAT_ID` | sim |
| `GH_PAT` | sim |
| `VERCEL_TOKEN` | não |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | não |

### Primeiro uso

Em Actions → "Duet - acordar" → **Run workflow** depois de mandar um "oi" ao bot.
Na primeira vez o Codespace é criado (leva alguns minutos). Depois é tudo automático.

## Comandos no Telegram

`/status`, `/ia`, `/verificar`, `/esquecer`, `/dormir` — ou só converse.

## Ajustes por variável de ambiente

- `DUET_MODELO` / `DUET_MODELO_VERIFICACAO` — trocam o modelo. Padrões: Claude API
  `claude-sonnet-5-5` / `claude-haiku-5-5`; Claude Code `sonnet` / `haiku`;
  Groq `openai/gpt-oss-120b` / `openai/gpt-oss-20b`
- `DUET_MINUTOS_OCIOSO` (padrão `15`) — minutos sem mensagem até desligar

## Custos

- Actions: grátis em repositório público.
- Codespace: só enquanto está conversando; cabe na cota grátis com uso normal.
- IA: com `claude-code` sai da sua assinatura; com Groq, cabe na camada grátis em uso normal;
  com a Claude API, paga por uso.
