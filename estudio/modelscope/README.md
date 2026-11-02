# Estúdio no ModelScope

Página única (`index.html`, sem build) que gera **imagens e vídeos** pela API do ModelScope, com o
mesmo painel de presets de câmera. Hospede em qualquer lugar estático: um Space estático do Hugging Face,
GitHub Pages ou um Studio do ModelScope.

## Como usar

1. Crie um token grátis em https://modelscope.cn/my/myaccesstoken.
2. Abra a página, clique em **⚙️ Configurações** e cole o token (ele fica só no seu navegador).
3. **Imagem:** escolha o modelo (Z-Image Turbo, Qwen-Image, FLUX.2 Klein, FLUX.1 Krea, majicFlus, Qwen-Image-Edit ou qualquer ID em "Outro").
4. **Vídeo:** escolha o motor.
   - **ModelScope (Wan):** `POST /v1/videos/generations`, com o seu token.
   - **ZeroGPU (LTX 13B):** Space oficial da Lightricks, com o login do Hugging Face de cada visitante.
5. Em uma imagem gerada, clique em **🎬 Animar esta imagem**.

## O que está confirmado e o que não está

| Parte | Situação |
|---|---|
| Imagens (`/v1/images/generations` + `/v1/tasks/{id}`) | protocolo usado por vários projetos abertos, com os modelos da lista testados por eles |
| Vídeo no ModelScope (`/v1/videos/generations`, `output_videos`) | usado por 2 projetos abertos (movie-agent, AI-Vision-Studio), **mas eu não testei com um token real** |
| Modelos de vídeo da lista | IDs vistos nesses projetos. Se um falhar, use "Outro" |
| Animar imagem no ModelScope | exige um modelo I2V. Não achei um ID confirmado; teste `Wan-AI/Wan2.1-I2V-14B-480P` em "Outro" |

Limites do plano grátis (segundo terceiros, confira no site): ~2.000 chamadas por dia e 1 vídeo por vez por conta.

## Se der erro de CORS

Se a página disser que o navegador não conseguiu falar com o ModelScope, publique o `worker.js` num
Cloudflare Worker grátis e cole o endereço em **⚙️ Configurações → Proxy**. As instruções estão no topo do arquivo.
