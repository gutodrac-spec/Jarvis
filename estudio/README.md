# 🎬 Estúdio

Gerador de vídeo com IA no estilo Higgsfield: texto ou imagem → vídeo, com
**presets de movimento de câmera** (Dolly In, Crash Zoom, Órbita 360, Drone FPV…).
Usa o modelo aberto [LTX-Video](https://huggingface.co/Lightricks/LTX-Video), então não paga API.

| Arquivo | O que é |
|---|---|
| `app.py` | interface Gradio + API `/gerar` (roda no Colab ou num Space) |
| `presets.py` | os movimentos de câmera. Para criar um novo, é só adicionar uma linha |
| `colab/estudio.ipynb` | notebook: baixa o código, roda com link público e publica o Space |
| `web/index.html` | página própria que chama a API (abra no navegador e cole o link) |

## Usar no Google Colab

1. Abra o notebook direto do GitHub:
   `https://colab.research.google.com/github/gutodrac-spec/Jarvis/blob/estudio-video/estudio/colab/estudio.ipynb`
2. Ative a GPU: **Ambiente de execução → Alterar tipo → T4**.
3. Rode as células. A última imprime um link `https://….gradio.live`, que fica no ar enquanto o Colab estiver rodando.
4. Use a interface desse link, ou abra `web/index.html` e cole o link no campo "Endereço da API".

Na T4 grátis, o codificador de texto é carregado em 8 bits para caber na memória.
Um vídeo de 3 s leva alguns minutos. Se os vídeos saírem pretos, teste `ESTUDIO_DTYPE=fp16`/`bf16`
ou use uma GPU maior (L4/A100).

## Hugging Face Space

A última seção do notebook cria o Space `seu-usuario/estudio` e envia o app (precisa do segredo
`HF_TOKEN` no Colab). O Space grátis só tem CPU: para gerar lá, escolha uma GPU nas configurações
dele ou use ZeroGPU (o `app.py` já é compatível). Na página `web/index.html`, você pode colar
`seu-usuario/estudio` no lugar do link do Colab.

## Remover

Tudo fica isolado nesta pasta e no ramo `estudio-video`. Para remover, apague o ramo
(`git push origin --delete estudio-video`) ou só a pasta `estudio/`.
