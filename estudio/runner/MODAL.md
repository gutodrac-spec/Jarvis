# Executor na Modal

A Modal liga uma GPU quando alguém usa e desliga sozinha depois de alguns minutos parada: você paga só pelo tempo ligada.
Aqui a GPU é de verdade (não há o risco de "processo filho sem GPU" que existe no xGPU do ModelScope).

## Publicar (uma vez)
```bash
pip install modal
modal setup                                   # login no navegador
modal secret create executor-segredos RUNNER_CHAVE=sua-chave-longa HF_TOKEN=hf_xxxxxxxx
cd estudio/runner
modal deploy deploy_modal.py                  # a 1ª vez monta a imagem (alguns minutos) e imprime o endereço
```
- `RUNNER_CHAVE` é **obrigatória** (quem não tem a chave não carrega nada). `HF_TOKEN` só para modelos/Spaces com login.
- Também podem ir no segredo: `RUNNER_PUBLICOS` (Spaces/modelos que qualquer pessoa pode usar sem a chave) e
  `RUNNER_PRECARREGAR` (Space a carregar toda vez que a GPU liga).
- O endereço sai no formato `https://SEU-USUARIO--executor-executor.modal.run`. Cole-o no site (`../site/index.html`) com a chave.

## Opções do deploy (variáveis de ambiente, lidas ao rodar `modal deploy`)
| Variável | Padrão | O que faz |
|---|---|---|
| `RUNNER_GPU` | `L40S` (48 GB) | `T4`, `L4`, `A10G`, `L40S`, `A100-40GB`, `A100-80GB`, `H100`… A Modal só valida o nome no deploy. |
| `RUNNER_OCIOSO` | `300` | segundos parado até desligar a GPU. Menor gasta menos, mas desliga o Space carregado. |
| `RUNNER_APP` | `executor` | nome do app (muda o endereço). |
| `RUNNER_PROXY_AUTH` | desligado | veja "Proteger o gasto". |

Exemplo: `RUNNER_GPU=A10G RUNNER_OCIOSO=120 modal deploy deploy_modal.py`.
O LTX Video 13B precisa de 48 GB (L40S ou maior). Spaces menores cabem em GPUs menores e mais baratas.

## Como funciona
- Uma função com `max_containers=1`: todas as chamadas caem no mesmo container, onde o Space carregado fica vivo.
  (Com vários containers, cada um teria o seu Space carregado.) `@modal.concurrent` deixa várias conexões dividirem a GPU.
- Os pesos do Hugging Face e o cache do pip ficam num **Volume** (`executor-cache`): o 2º carregamento não baixa de novo.
  O código e os ambientes dos Spaces ficam no disco do container e são refeitos a cada partida (rápido: o pip usa o cache).
- Quando a GPU desliga, o Space carregado some. Na próxima partida use **Carregar** de novo (ou ponha o Space em `RUNNER_PRECARREGAR`).

## Custos e cuidados
- **Não conferi preços.** Veja modal.com/pricing. Cobra-se pelo tempo de GPU ligada, inclusive enquanto o Space carrega e baixa modelos.
  Fontes de terceiros falavam em cerca de US$ 30/mês de crédito grátis no plano inicial; confirme antes de contar com isso.
- **O endereço é público.** Quem o descobrir pode ligar a GPU (e gastar o seu crédito) mesmo sem a chave: a chave impede de *carregar e usar*, não de *acordar*.
  Proteja-se: (1) defina um limite de gastos no painel da Modal; (2) mantenha `RUNNER_OCIOSO` baixo; (3) não divulgue o endereço;
  (4) `RUNNER_PROXY_AUTH=1` exige tokens de proxy da Modal (`Modal-Key` e `Modal-Secret`, criados no painel) antes de qualquer coisa chegar à GPU.
- O `RUNNER_PROXY_AUTH=1` serve para scripts (`Client(url, headers={"Modal-Key": ..., "Modal-Secret": ...})`).
  **No site, no navegador, provavelmente quebra**: o navegador faz uma consulta prévia (CORS) sem esses cabeçalhos. Não consegui testar.

## O que não foi testado na Modal de verdade
Eu validei com o pacote `modal` (1.6.3) que o código monta (decoradores e parâmetros), e que o servidor sobe e grava no Volume pela mesma função
de partida; mas **não fiz deploy** (sem conta aqui). Pontos a observar no primeiro uso:
1. O tempo de partida a frio (`startup_timeout=600`): se a imagem ou o Gradio demorarem mais, aumente em `deploy_modal.py`.
2. Se conexões longas (vídeos demorados) são cortadas pela Modal. Se acontecer, me avise com a mensagem.
3. Se o Volume grava a tempo antes de a GPU desligar (o código grava a cada minuto e a Modal grava ao encerrar).
