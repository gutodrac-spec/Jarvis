# Executor de Spaces no Studio do ModelScope

O que sobe no Studio (mantenha as pastas): `app.py`, `espacos.py`, `modelos.py`, `ambiente.py`, `shim/spaces/__init__.py`,
`requirements.txt`, `ms_deploy.json`, `README.md`. A pasta `testes/` é opcional.

## 1. Conta e GPU
1. Conta em modelscope.cn.
2. Peça entrada na organização **xGPU Playground**: https://www.modelscope.cn/organization/xGPU-Explorers (aprovação por e-mail).
3. Crie o Studio (**Criar → 创空间**), envie os arquivos (Git ou pelo site) e, em Configurações, escolha o recurso:
   - `xgpu/8v-cpu-64g-mem-48g` (48 GB, o padrão do `ms_deploy.json`): Spaces grandes, como o LTX 13B.
   - `xgpu/8v-cpu-32g-mem-16g` (16 GB): Spaces e modelos menores.

## 2. Segredos (NÃO ponha no repositório)
Em **Configurações → variáveis de ambiente** do Studio:

| Variável | Para quê |
|---|---|
| `RUNNER_CHAVE` | **obrigatória**. Quem não tem a chave não carrega nada. Carregar um Space executa o código dele aqui. |
| `HF_TOKEN` | token *read* do Hugging Face, para Spaces e modelos que exigem login (gated). |
| `RUNNER_PUBLICOS` | lista (separada por vírgula) de Spaces/modelos que qualquer pessoa pode usar sem a chave. |
| `RUNNER_PRECARREGAR` | Space a carregar quando o Studio liga (ex.: `Lightricks/ltx-video-distilled`). |
| `HF_ENDPOINT` | outro endereço para o Hugging Face. Se o `huggingface.co` não abrir, o executor usa `hf-mirror.com` sozinho. |
| `RUNNER_MAX_ATIVOS` | quantos Spaces ao mesmo tempo (padrão 1; a GPU é pequena). |

## 3. Primeiro teste (antes de baixar 16 GB)
Abra o site, cole o endereço `https://seu-usuario-nome.ms.show` e a chave, clique **Conectar** e depois **🔍 Testar GPU**.
- Verde: os processos filhos enxergam a GPU. Siga em frente.
- Aviso: o xGPU só liga a GPU no processo principal. Os Spaces rodariam na CPU; veja "O que não consegui confirmar".

## 4. Usar
- **Space:** digite `dono/nome`, **Carregar**, espere "pronto" (a primeira vez baixa código, pacotes e modelos), escolha o endpoint, preencha o formulário que aparece e **Executar**.
- **Modelo solto:** `dono/nome` + tarefa (`texto-para-imagem`, `texto`, `reconhecimento-de-fala`, qualquer tarefa do `transformers.pipeline`…) + a entrada em JSON.

## Como funciona (e os limites)
- Cada Space ganha uma pasta, um ambiente virtual que enxerga o torch/CUDA da imagem e só instala o que falta. O `torch`, o `gradio` e o `spaces`
  do `requirements.txt` do Space são ignorados: valem os da imagem do Studio (o Gradio específico do Space é instalado no ambiente dele).
- O pacote `spaces` é substituído por um shim: `@spaces.GPU(...)` vira a própria função.
- **Só 1 Space ativo por vez.** Carregar outro desliga o anterior para liberar a GPU.
- Só Spaces com `sdk: gradio`. Não rodam: Spaces que dependem de AoTI (`spaces.aoti_*`, feitos para a GPU do ZeroGPU), Docker/Streamlit,
  `packages.txt` (apt) e Spaces que precisam de mais memória do que a GPU escolhida.
- Os modelos soltos nunca usam `trust_remote_code`.
- Arquivos gerados são apagados do cache depois de ~2 h.

## O que não consegui confirmar (nada disto foi testado no ModelScope real)
1. **A GPU nos processos filhos.** Por isso o botão "Testar GPU". Se der aviso, a saída é rodar o Space no mesmo processo,
   o que exige mudar o executor: me chame com o resultado do teste.
2. **O endereço do `.ms.show`** e se o Studio aceita chamadas vindas de outro site (CORS): o Gradio libera qualquer origem quando o endereço não é localhost,
   o que eu verifiquei com um `Host` simulado, mas não no ModelScope.
3. O **espelho** `hf-mirror.com` serve modelos; não sei se serve o *código* de Spaces. Se o download do Space falhar, defina `HF_ENDPOINT`
   com um endereço que funcione, ou envie o código do Space por upload na pasta `locais/` e use `local:nome`.
4. Os valores `sdk_version` 6.17.3 e a imagem base vieram de outros projetos; se o ModelScope recusar, escolha na tela uma imagem Gradio com CUDA.
5. Os limites do xGPU (beta): tempo máximo por usuário, suspensão automática por pouco uso, limite de Studios.

## Testar localmente (sem GPU, sem internet)
```bash
pip install gradio transformers torch pillow pyyaml
python testes/criar_modelo_tiny.py testes/locais/tiny
python testes/teste_local.py     # sobe o executor de verdade e usa só a API
```
