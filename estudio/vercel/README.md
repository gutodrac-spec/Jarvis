# Estúdio na Vercel

Pasta pronta para publicar na Vercel (plano grátis):

| Arquivo | O que é |
|---|---|
| `index.html` | a página (cópia de `../modelscope/index.html`: se mudar uma, copie para a outra) |
| `api/ms.js` | função Edge que repassa `/ms/v1/*` ao ModelScope no mesmo domínio, então não há erro de CORS e nem precisa de proxy externo |
| `vercel.json` | redireciona `/ms/*` para a função |

A página detecta a função sozinha (`/ms/ping`). Em outra hospedagem ela chama o ModelScope direto.
A função só aceita `images/generations`, `videos/generations`, `tasks/{id}` e `chat/completions`,
repassa só os 4 cabeçalhos necessários (nada de cookies) e não guarda nada.

## Publicar

1. vercel.com → **Add New → Project** → importe o repositório `gutodrac-spec/Jarvis`.
2. **Root Directory:** `estudio/vercel`. **Framework Preset:** Other. Não precisa de build.
3. O código está no ramo `estudio-video`. Em **Settings → Environments → Production → Branch Tracking**
   escolha `estudio-video` (ou faça o merge para `main`).
4. **Deploy.** Abra o endereço `.vercel.app`, cole o token do ModelScope em ⚙️ Configurações e use.

Pela linha de comando, a partir desta pasta: `npx vercel --prod`.

## Hugging Face (vídeo no ZeroGPU)

O botão "Entrar" só funciona dentro de um Space. Fora dele, crie um token *read* em
huggingface.co/settings/tokens e cole em ⚙️ Configurações: a cota de 5 min/dia passa a ser a sua.
