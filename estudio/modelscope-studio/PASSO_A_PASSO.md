# Publicar o Estúdio num Studio do ModelScope (GPU xGPU)

Estes arquivos formam o Studio inteiro: `README.md`, `ms_deploy.json`, `requirements.txt`, `app.py`, `presets.py`.
(`app.py` e `presets.py` são cópias de `../app.py` e `../presets.py`: se mudar lá, copie para cá.)

## 1. Conta e acesso à GPU
1. Crie a conta em modelscope.cn (grátis).
2. Peça entrada na organização **xGPU乐园 (xGPU Playground)**: https://www.modelscope.cn/organization/xGPU-Explorers
   Sem a aprovação, escolher um recurso xGPU dá erro. O ModelScope avisa o resultado por e-mail/caixa de entrada.

## 2. Criar o Studio
1. Logado, clique em **创建 (Criar) → 创空间 (Studio)**.
2. Nome, dono, licença e visibilidade pública.
3. Na página do Studio, copie o **endereço Git** (e crie um *Access Token* em modelscope.cn/my/myaccesstoken).

## 3. Enviar os arquivos
Pelo Git, a partir desta pasta:
```bash
git init && git add . && git commit -m "Estúdio"
git remote add origin https://oauth2:SEU_TOKEN@www.modelscope.cn/studios/SEU_USUARIO/NOME.git
git push -u origin master
```
Ou pelo site: aba de arquivos do Studio → enviar os 5 arquivos.

## 4. Escolher a GPU e publicar
1. Em **Configurações**, em "Recursos da nuvem do Studio", escolha:
   - `xgpu/8v-cpu-32g-mem-16g` (GPU de 16 GB): serve para o Estúdio, com o codificador de texto em 8 bits.
   - `xgpu/8v-cpu-64g-mem-48g` (GPU de 48 GB): tudo em fp16, mas o tempo grátis dos modelos maiores costuma ser menor.
2. Salve, reinicie e clique em **上线空间展示 (Publicar)**.
3. Na primeira geração ele baixa ~16 GB de modelos. Os pesos vêm do Hugging Face; se o ModelScope não alcançar o
   `huggingface.co`, o app usa sozinho o espelho `hf-mirror.com` (ou o endereço que você pôr em `HF_ENDPOINT`).

## O que eu não consegui confirmar
- As regras do xGPU vêm de uma cópia da documentação no GitHub, não do site oficial (que não abre daqui). O xGPU
  estava em **beta**, com limite de tempo por usuário, limite de Studios com xGPU e suspensão automática quando há pouco acesso.
- Os valores de `sdk_version` (6.17.3) e `base_image` vieram de outros projetos reais. Se o ModelScope reclamar, escolha
  na tela uma imagem Gradio com CUDA (já vi `ubuntu22.04-(cuda12.8.1)-py312-torch2.10.0-modelscope1.37.0`).
- Se a GPU só existir durante cada pedido (como no ZeroGPU), o modelo é carregado no primeiro pedido e pode ser recarregado depois.
  Para carregar na subida, adicione a variável `ESTUDIO_PRECARREGAR` = `1` em `ms_deploy.json`.
