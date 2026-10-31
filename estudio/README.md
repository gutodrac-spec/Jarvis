# 🎬 Estúdio

Gerador de vídeo com IA no estilo Higgsfield: texto ou imagem → vídeo, com
**presets de movimento de câmera** (Dolly In, Crash Zoom, Órbita 360, Drone FPV…).
Usa o modelo aberto [LTX-Video 0.9.8 destilado](https://huggingface.co/Lightricks/LTX-Video), então não paga API.

| Arquivo | O que é |
|---|---|
| `app.py` | interface Gradio + API `/gerar` (roda no Kaggle, Colab ou num Space) |
| `presets.py` | os movimentos de câmera. Para criar um novo, é só adicionar uma linha |
| `kaggle/estudio.ipynb` | notebook do Kaggle (**recomendado**: 2x T4 grátis) |
| `colab/estudio.ipynb` | notebook do Colab (1x T4) |
| `web/index.html` | página própria que chama a API (abra no navegador e cole o link) |

## Por que ficou rápido

| | Antes | Agora |
|---|---|---|
| Modelo | LTX 0.9 normal | LTX 0.9.8 **destilado** |
| Passadas do modelo por vídeo | 30 passos × 2 (CFG) = 60 | **7** |
| Codificador de texto (Kaggle) | 8 bits na mesma GPU | fp16 na **2ª GPU** |
| Carregamento | na 1ª geração | **antes** de abrir o link |
| Mesmo prompt de novo | codifica de novo | **cache** |

O modo **Rápido** gera em 512×288 e o **Qualidade** em 768×448.

## Usar no Kaggle (recomendado)

1. Em kaggle.com: **Create → New Notebook → File → Import Notebook**, aba **GitHub**, e cole:
   `https://github.com/gutodrac-spec/Jarvis/blob/estudio-video/estudio/kaggle/estudio.ipynb`
2. No painel **Settings**: **Accelerator → GPU T4 x2** e **Internet → On**
   (a internet só libera com o telefone verificado na conta).
3. Rode as células. A última mostra um link `https://….gradio.live`, que fica no ar enquanto a sessão estiver rodando
   (até 12 h; a cota é de ~30 h de GPU por semana).
4. Use a interface desse link, ou abra `web/index.html` e cole o link no campo "Endereço da API".

## Usar no Google Colab

Abra `https://colab.research.google.com/github/gutodrac-spec/Jarvis/blob/estudio-video/estudio/colab/estudio.ipynb`,
ative a GPU T4 e rode as células. Com uma GPU só, o codificador de texto vai em 8 bits, então é mais lento que no Kaggle.

## Se algo der errado

- **Vídeo preto ou com ruído:** rode com `ESTUDIO_DTYPE=bf16` (mais lento na T4).
- **O modelo destilado não carregou:** o app volta sozinho para o LTX 0.9.5 normal (30 passos) e avisa no log.
  Para forçar esse modelo, use `ESTUDIO_MODELO=normal`.

## Hugging Face Space

A última seção dos notebooks cria o Space `seu-usuario/estudio` e envia o app (precisa do segredo `HF_TOKEN`).
O Space grátis só tem CPU: para gerar lá, escolha uma GPU nas configurações dele ou use ZeroGPU
(o `app.py` já é compatível). Na página `web/index.html`, dá para colar `seu-usuario/estudio` no lugar do link.

## Remover

Tudo fica isolado nesta pasta e no ramo `estudio-video`. Para remover, apague o ramo
(`git push origin --delete estudio-video`) ou só a pasta `estudio/`.
