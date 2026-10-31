# 🎬 Estúdio

Gerador de vídeo com IA no estilo Higgsfield: texto ou imagem → vídeo, com
**presets de movimento de câmera** (Dolly In, Crash Zoom, Órbita 360, Drone FPV…).
Usa o modelo aberto [LTX-Video 0.9.8 destilado](https://huggingface.co/Lightricks/LTX-Video), então não paga API.

## Como funciona

| Peça | Onde | Papel |
|---|---|---|
| GPU | **Google Colab** | gera os vídeos (`app.py`, interface + API `/gerar`) |
| Modelos | **Hugging Face** | o Colab baixa os pesos de lá a cada sessão |
| Site | **HF Space estático** (grátis, sempre no ar) | a página `web/index.html`, que se conecta sozinha ao Colab ligado |

O link do Colab muda a cada sessão. Por isso, quando o app sobe, ele grava o link novo em
`url.txt` no Space, e a página do site lê esse arquivo para se conectar.

| Arquivo | O que é |
|---|---|
| `app.py` | interface Gradio + API `/gerar` |
| `presets.py` | os movimentos de câmera. Para criar um novo, é só adicionar uma linha |
| `colab/estudio.ipynb` | **notebook principal** |
| `kaggle/estudio.ipynb` | alternativa no Kaggle (2x T4) |
| `web/index.html` | a página do site |

## Usar

1. Abra o notebook no Colab:
   `https://colab.research.google.com/github/gutodrac-spec/Jarvis/blob/estudio-video/estudio/colab/estudio.ipynb`
2. **Ambiente de execução → Alterar tipo → GPU T4** (ou L4/A100 no Colab Pro).
3. Uma vez só: em 🔑 **Secrets**, crie `HF_TOKEN` com um token *write* de huggingface.co/settings/tokens.
4. Rode as 4 células. A 3ª cria o site `https://huggingface.co/spaces/seu-usuario/estudio`;
   a 4ª carrega o modelo e mostra o link `…gradio.live`.
5. Abra o site. Ele se conecta sozinho enquanto a 4ª célula estiver rodando.

Sem `HF_TOKEN`, tudo funciona igual, só que sem o site: use o link `gradio.live` direto.

## Por que é rápido

- O LTX 0.9.8 **destilado** faz 7 passadas por vídeo, contra 60 do modelo normal (30 passos × 2).
- O modelo é carregado **antes** de o link abrir, e prompts repetidos usam **cache**.
- O modo **Rápido** gera em 512×288 e o **Qualidade** em 768×448.
- Com 2 GPUs (Kaggle), o codificador de texto vai na 2ª GPU. Com uma T4 só (Colab), ele vai em 8 bits para caber.

## Se algo der errado

- **Vídeo preto ou com ruído:** rode com `ESTUDIO_DTYPE=bf16` (mais lento na T4).
- **O modelo destilado não carregou:** o app volta sozinho para o LTX 0.9.5 normal (30 passos) e avisa no log.
  Para forçar esse modelo, use `ESTUDIO_MODELO=normal`.
- **O site não conectou:** confira no log da 4ª célula a linha `[estudio] site … agora aponta para …`.
  O site leva alguns segundos para atualizar.

## Remover

Tudo fica isolado nesta pasta e no ramo `estudio-video`. Para remover, apague o ramo
(`git push origin --delete estudio-video`) ou só a pasta `estudio/`. Apague também o Space no Hugging Face, se tiver criado.
