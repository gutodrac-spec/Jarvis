# J.A.R.V.I.S.

Assistente que **vigia o seu PC sozinho e te liga** pelo app web quando algo importante acontece.
No celular aparece a notificação **"📞 Jarvis está te ligando"** com o motivo, e uma tela de chamada
com **Atender / Recusar**. Ao atender, você conversa por voz e manda o Jarvis fazer coisas no PC.
Ele mexe no **mouse e no teclado** para fazer isso.

- ⚡ **Groq (ultra rápido)**: conversa, decide o que fazer em ~200 ms e vigia a tela (modelo de visão).
- 🧠 **Claude (tarefas complexas)**: com o **Claude Code da sua assinatura** (`claude login`) ou pela **API** (computer use).

```
 Celular / navegador (PWA)  ◄──push + WebSocket──►  server/ (Node)  ◄──WebSocket──►  agent/ (Python, no seu PC)
  - tela "Jarvis está te ligando"                    - Web Push (VAPID)                 - captura de tela (mss)
  - voz (fala e ouve, pt-BR)                         - ponte entre app e PC             - mouse/teclado (pyautogui)
  - tela do PC ao vivo, chat, botão Parar                                               - Groq: roteador + vigia da tela
                                                                                        - Claude: tarefas complexas
```

## Sobre o Parsec

O Parsec **não tem API** para que outro programa mova o mouse ou digite por ele. Por isso o Jarvis
controla o PC com um **agente local** (`agent/`), que gera mouse e teclado direto no Windows, como
o Parsec faz. O Parsec continua sendo útil para **você** ver e assumir o PC: cole o link do Parsec em
*Configurações* no app e aparece um botão **🖥️ Parsec**. O app também tem a opção **👁️ Ver tela**,
que mostra a tela ao vivo sem precisar do Parsec.

---

## 1. Servidor (`server/`)

Precisa do Node 18 ou mais novo. Pode rodar no próprio PC ou numa VPS.

```bash
cd server
npm install
JARVIS_TOKEN="uma-senha-bem-longa" npm start        # Windows PowerShell: $env:JARVIS_TOKEN="..."; npm start
```

**Notificações push só funcionam em HTTPS.** O jeito mais fácil de ter HTTPS:

```bash
cloudflared tunnel --url http://localhost:8787      # gera uma URL https://xxxx.trycloudflare.com
```

Também servem `ngrok http 8787`, `tailscale funnel 8787` ou um domínio próprio com HTTPS.

## 2. App no celular

1. Abra a URL **https** no celular e digite o token.
2. **Android (Chrome):** toque em **Ativar** notificações. Instalar o app ("Adicionar à tela inicial") é recomendado.
3. **iPhone (iOS 16.4 ou mais novo):** primeiro faça **Compartilhar → Adicionar à Tela de Início**, abra o app
   pelo ícone e só então toque em **Ativar**. A Apple só entrega push para apps instalados assim.
4. Em *Configurações*, toque em **Testar chamada**.

## 3. Agente no PC (`agent/`)

Precisa do Python 3.10 ou mais novo. Rode na sua sessão normal do Windows, não como serviço, para que
ele consiga ver a tela.

```bash
cd agent
python -m venv .venv && .venv\Scripts\activate      # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                              # Linux/Mac: cp .env.example .env
# edite o .env: JARVIS_SERVER, JARVIS_TOKEN, GROQ_API_KEY ...
python jarvis_agent.py
```

- `JARVIS_SERVER`: use `wss://xxxx.trycloudflare.com/ws`, ou `ws://localhost:8787/ws` se o servidor roda no mesmo PC.
- **Chave do Groq:** crie em https://console.groq.com/keys

### Claude: assinatura ou API

| `CLAUDE_BACKEND` | Como funciona | O que precisa |
|---|---|---|
| `cli` (padrão) | Usa o **Claude Code** com a sua **assinatura** Pro/Max. Ele vê a tela e controla o PC pelo `pc_cli.py` (screenshot → Read → click/type). | `npm i -g @anthropic-ai/claude-code` e depois `claude login` |
| `api` | Usa a API da Anthropic com **computer use** (`computer_toolset_20260801`, modelo `claude-opus-5-5`). É mais preciso para cliques e cobra por uso. | `ANTHROPIC_API_KEY` |

No modo `api`, o *fallback* automático do servidor (`fallbacks: "default"`) fica ligado: se o modelo
recusar um pedido, a Anthropic tenta outro modelo. Para desligar, remova `fallbacks` e o beta
`server-side-fallback-2026-07-01` em `agent/claude_worker.py`.

---

## Como usar

- **Ele te liga sozinho:** a cada `MONITOR_INTERVAL` segundos o agente olha a tela. Se a tela mudou,
  o modelo de visão do Groq avalia a captura com as suas regras (`WATCH_RULES`) e decide se liga.
  Exemplos: erro, download ou render terminado, mensagem importante, pedido de confirmação.
  Ele também liga para bateria baixa, RAM cheia e disco cheio, sem usar IA.
  Abaixo de `CALL_MIN_URGENCY`, o aviso vira só uma notificação.
- **Ao atender**, ele explica o motivo e pergunta se deve cuidar disso. Responda por voz, por exemplo "sim, resolve".
- **Pedidos rápidos** (Groq): "abre o Spotify", "pausa a música", "o que tem na minha tela?", "bloqueia o PC".
- **Pedidos complexos** (Claude): "abre o Chrome, entra no Gmail e me diz quais e-mails chegaram hoje",
  "o build deu erro, descobre o que é e corrige".
- Se você sair do app enquanto uma tarefa longa roda, ele **te liga quando terminar**.
- **Parar:** diga "parar", toque em **⛔ Parar**, ou **jogue o mouse num canto da tela** (failsafe do pyautogui).

## Segurança e privacidade

- Quem tem o `JARVIS_TOKEN` controla o seu PC. Use um token longo e só acesse por HTTPS.
- As capturas de tela vão para o Groq (vigilância e pedidos rápidos) e para a Anthropic (tarefas do Claude).
  Para desligar a vigilância, use `MONITOR_ENABLED=0`.
- O Claude é instruído a **pedir confirmação** antes de apagar arquivos, enviar mensagens, fazer compras e
  outras ações sensíveis.
- No modo `cli`, o Claude Code roda com Bash liberado (`--allowedTools`) para conseguir operar o PC sozinho.

## Estrutura

```
server/server.js          servidor: Web Push, WebSocket, API /api/call (teste)
server/public/            app web: index.html, app.js, sw.js (notificação de chamada), style.css
agent/jarvis_agent.py     agente principal: conexão, vigia da tela, pedidos, tela ao vivo
agent/brain.py            Groq: roteador rápido, visão ("o que tem na tela"), análise de alertas
agent/claude_worker.py    Claude: modo cli (Claude Code/assinatura) e modo api (computer use)
agent/pc.py               captura de tela, mouse, teclado (com acentos via área de transferência)
agent/pc_cli.py           comandos de tela, mouse e teclado usados pelo Claude Code
```

Para disparar uma ligação a partir de outro script seu:

```bash
curl -X POST https://SEU-SERVIDOR/api/call -H "x-jarvis-token: $JARVIS_TOKEN" \
     -H "content-type: application/json" -d '{"reason":"Senhor, o backup terminou.","urgency":"normal"}'
```
