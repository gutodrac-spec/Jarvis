"""Estúdio de vídeo com IA: texto/imagem -> vídeo com presets de câmera.

Roda no Kaggle (2x T4, recomendado), no Google Colab (1x T4) e num Hugging Face Space.
A interface Gradio também expõe uma API (`/gerar`) que a página `web/index.html` usa.

Por que é rápido:
  * usa o LTX-Video 0.9.8 **destilado** (2B): 7 passos e sem CFG, contra 30 passos x2 do modelo normal;
  * com 2 GPUs (Kaggle), o codificador de texto fica na segunda GPU e o vídeo na primeira,
    então nada precisa ser quantizado nem ir e voltar da CPU;
  * o texto codificado fica em cache, e o modelo pode ser pré-carregado antes da 1ª geração;
  * modo Turbo: a IA gera 12 fps (metade do trabalho) e o ffmpeg interpola os quadros até 24 fps.

Variáveis de ambiente (todas opcionais):
  ESTUDIO_SHARE        "1" para gerar link público (Kaggle/Colab)
  ESTUDIO_PRECARREGAR  "1" para carregar o modelo antes de abrir a interface
  ESTUDIO_SITE         "usuario/estudio": HF Space estático que recebe o link atual (precisa de HF_TOKEN)
  ESTUDIO_MODELO       "destilado" (padrão) ou "normal" (LTX 0.9.5 completo, mais lento)
  ESTUDIO_DTYPE        "fp16" ou "bf16" (padrão: bf16 se a GPU tiver suporte nativo, senão fp16)
  ESTUDIO_COMPILAR     "1" para compilar com CUDA Graphs (torch.compile reduce-overhead); meça com benchmark.py
"""

import os
import random
import tempfile

# No Studio do ModelScope (servidores na China) o huggingface.co pode estar bloqueado.
# Se não der para alcançá-lo, os pesos vêm do espelho hf-mirror.com (defina HF_ENDPOINT para escolher outro).
# Precisa rodar ANTES de importar o gradio/huggingface_hub, que leem a variável na importação.
if os.environ.get("ESTUDIO_PLATAFORMA") == "modelscope" and not os.environ.get("HF_ENDPOINT"):
    import urllib.request

    try:
        urllib.request.urlopen("https://huggingface.co", timeout=8)
    except Exception:  # noqa: BLE001
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        print("[estudio] huggingface.co inacessível daqui; baixando os modelos de hf-mirror.com")

import gradio as gr
import torch

if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True  # escolhe o algoritmo de convolução mais rápido (VAE)
    torch.backends.cuda.matmul.allow_tf32 = True  # contas mais rápidas em GPUs L4/A100 e mais novas
    torch.backends.cudnn.allow_tf32 = True

from presets import NEGATIVO, PRESETS, montar_prompt

BASE = "Lightricks/LTX-Video-0.9.5"  # configs, VAE, T5 e tokenizer (formato diffusers)
DESTILADO = "https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.8-distilled.safetensors"
PASSOS_DESTILADO = [1000, 993, 987, 981, 975, 909, 725, 0.03]
FPS = 24
FPS_TURBO = 12  # no modo Turbo a IA gera 12 fps e o ffmpeg interpola até 24
TOKENS = 128

RESOLUCOES = {
    "Rápido": {"16:9": (512, 288), "9:16": (288, 512), "1:1": (384, 384)},
    "Qualidade": {"16:9": (768, 448), "9:16": (448, 768), "1:1": (512, 512)},
}

# No Hugging Face Space com ZeroGPU, o Space define SPACES_ZERO_GPU e a GPU só existe
# dentro das funções com @spaces.GPU. Fora delas o PyTorch simula a GPU.
ZERO_GPU = bool(os.environ.get("SPACES_ZERO_GPU"))


def _duracao(prompt, preset, imagem, formato, segundos, qualidade, turbo, semente):
    """Duração dinâmica: reserva só o tempo de GPU que o vídeo precisa (gasta menos cota)."""
    por_segundo = 4 if qualidade == "Rápido" else 10
    return int(min(120, 15 + float(segundos) * por_segundo * (0.6 if turbo else 1)))


try:
    import spaces

    usar_gpu = spaces.GPU(duration=_duracao)
except ImportError:
    def usar_gpu(f):
        return f


def _dtype():
    escolha = os.environ.get("ESTUDIO_DTYPE")
    if escolha in ("fp16", "bf16"):
        return torch.float16 if escolha == "fp16" else torch.bfloat16
    if ZERO_GPU:  # RTX Pro 6000 Blackwell: bf16 nativo
        return torch.bfloat16
    # T4/P100 (Kaggle, Colab) não têm bf16 nativo: fp16 é bem mais rápido nelas.
    if torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8:
        return torch.bfloat16
    return torch.float16


M = {}  # modelos carregados


def _carregar():
    if M:
        return M
    from diffusers import (
        AutoencoderKLLTXVideo,
        FlowMatchEulerDiscreteScheduler,
        LTXConditionPipeline,
        LTXVideoTransformer3DModel,
    )
    from transformers import T5EncoderModel, T5TokenizerFast

    dtype = _dtype()
    if ZERO_GPU:  # 48 GB de VRAM: tudo na mesma GPU, sem quantizar
        n_gpus, dev, dev_texto, vram = 1, "cuda", "cuda", 48
    else:
        n_gpus = torch.cuda.device_count()
        dev = "cuda:0" if n_gpus else "cpu"
        dev_texto = "cuda:1" if n_gpus >= 2 else dev
        vram = torch.cuda.get_device_properties(0).total_memory / 2**30 if n_gpus else 0

    # Codificador de texto (T5-XXL, ~9,5 GB em fp16).
    kw_texto = {"dtype": dtype}
    if n_gpus == 1 and vram < 20:
        # Só 1 GPU pequena (Colab): T5 em 8 bits para caber junto do modelo de vídeo.
        from transformers import BitsAndBytesConfig

        kw_texto = {"quantization_config": BitsAndBytesConfig(load_in_8bit=True), "device_map": {"": dev}}
    texto = T5EncoderModel.from_pretrained(BASE, subfolder="text_encoder", **kw_texto)
    if "device_map" not in kw_texto:
        texto.to(dev_texto)
    texto.eval()

    modo = os.environ.get("ESTUDIO_MODELO", "destilado")
    if modo == "destilado":
        try:
            transformer = LTXVideoTransformer3DModel.from_single_file(
                DESTILADO, config=BASE, subfolder="transformer", torch_dtype=dtype
            )
            vae = AutoencoderKLLTXVideo.from_single_file(DESTILADO, config=BASE, subfolder="vae", torch_dtype=dtype)
        except Exception as erro:  # noqa: BLE001
            print(f"[estudio] não consegui carregar o modelo destilado ({erro}); usando o normal.")
            modo = "normal"
    if modo != "destilado":
        transformer = LTXVideoTransformer3DModel.from_pretrained(BASE, subfolder="transformer", torch_dtype=dtype)
        vae = AutoencoderKLLTXVideo.from_pretrained(BASE, subfolder="vae", torch_dtype=dtype)

    pipe = LTXConditionPipeline(
        scheduler=FlowMatchEulerDiscreteScheduler.from_pretrained(BASE, subfolder="scheduler"),
        vae=vae,
        text_encoder=None,
        tokenizer=None,
        transformer=transformer,
    ).to(dev)
    pipe.vae.enable_tiling()
    if os.environ.get("ESTUDIO_COMPILAR") == "1" and not ZERO_GPU:  # ZeroGPU não aceita torch.compile
        # CUDA Graphs: grava a sequência de operações da GPU e repete com uma ordem só,
        # tirando o custo de lançar cada operação. A 1ª geração de cada formato fica mais lenta (compila).
        pipe.transformer.compile(mode="reduce-overhead")
    pipe.set_progress_bar_config(disable=False)

    M.update(
        pipe=pipe,
        texto=texto,
        tokenizer=T5TokenizerFast.from_pretrained(BASE, subfolder="tokenizer"),
        dev=dev,
        dev_texto=dev_texto,
        dtype=dtype,
        modo=modo,
        cache={},
    )
    print(f"[estudio] pronto: modelo {modo}, {dtype}, vídeo em {dev}, texto em {dev_texto}")
    return M


@torch.no_grad()
def _codificar(frase: str):
    """Texto -> embeddings do T5, com cache (o mesmo prompt não é codificado duas vezes)."""
    if frase in M["cache"]:
        emb, mascara = M["cache"][frase]
        return emb.to(M["dev"]), mascara.to(M["dev"])
    t = M["tokenizer"]([frase], padding="max_length", max_length=TOKENS, truncation=True,
                       add_special_tokens=True, return_tensors="pt")
    mascara = t.attention_mask.to(M["dev_texto"])
    emb = M["texto"](t.input_ids.to(M["dev_texto"]), attention_mask=mascara)[0]
    emb, mascara = emb.to(M["dev"], M["dtype"]), mascara.to(M["dev"])
    if len(M["cache"]) > 64:
        M["cache"].clear()
    M["cache"][frase] = (emb.cpu(), mascara.cpu())  # cache na CPU: funciona também no ZeroGPU
    return emb, mascara


def _quadros(segundos: float, fps: int = FPS) -> int:
    # O LTX exige número de quadros no formato 8k + 1.
    return int(segundos * fps / 8 + 0.5) * 8 + 1


def _interpolar(entrada: str) -> str:
    """Cria os quadros intermediários (12 -> 24 fps) com interpolação por movimento do ffmpeg.
    Se falhar, devolve o vídeo original em 12 fps."""
    import subprocess

    import imageio_ffmpeg

    saida = entrada.replace(".mp4", "_24fps.mp4")
    filtro = f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
    try:
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", entrada, "-vf", filtro,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", saida],
            check=True, timeout=120,
        )
        return saida
    except Exception as erro:  # noqa: BLE001
        print(f"[estudio] interpolação falhou ({erro}); devolvendo em {FPS_TURBO} fps.")
        return entrada


@usar_gpu
@torch.inference_mode()
def _gerar_quadros(prompt, preset, imagem, formato, segundos, qualidade, turbo, semente):
    """A parte que usa GPU. Tudo que é CPU (salvar o MP4, interpolar) fica fora, para não gastar cota."""
    _carregar()
    largura, altura = RESOLUCOES.get(qualidade, RESOLUCOES["Rápido"]).get(formato, (512, 288))

    fps = FPS_TURBO if turbo else FPS
    emb, mascara = _codificar(montar_prompt(prompt or "", preset))
    args = dict(
        prompt_embeds=emb,
        prompt_attention_mask=mascara,
        width=largura,
        height=altura,
        num_frames=_quadros(float(segundos), fps),
        frame_rate=fps,
        decode_timestep=0.05,
        decode_noise_scale=0.025,
        image_cond_noise_scale=0.0,
        generator=torch.Generator(device="cpu").manual_seed(semente),
        output_type="pil",
    )
    if M["modo"] == "destilado":
        args.update(timesteps=PASSOS_DESTILADO, guidance_scale=1.0)
    else:
        neg, neg_mascara = _codificar(NEGATIVO)
        args.update(num_inference_steps=30, guidance_scale=3.0,
                    negative_prompt_embeds=neg, negative_prompt_attention_mask=neg_mascara)
    if imagem is not None:
        from PIL import Image

        img = Image.open(imagem) if isinstance(imagem, str) else imagem
        args["image"] = img.convert("RGB").resize((largura, altura))

    return M["pipe"](**args).frames[0], largura, altura, M["modo"]


def gerar(prompt, preset, imagem, formato, segundos, qualidade, turbo, semente):
    from diffusers.utils import export_to_video

    if not prompt and imagem is None:
        raise gr.Error("Escreva um prompt ou envie uma imagem.")
    semente = int(semente) if semente is not None and int(semente) >= 0 else random.randint(0, 2**31 - 1)
    quadros, largura, altura, modo = _gerar_quadros(
        prompt, preset, imagem, formato, segundos, qualidade, turbo, semente)
    fps = FPS_TURBO if turbo else FPS
    saida = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    export_to_video(quadros, saida, fps=fps)
    if turbo:
        saida = _interpolar(saida)
    return saida, (f"semente {semente} · {largura}x{altura} · {len(quadros)} quadros gerados"
                   f"{' + interpolação' if turbo else ''} · modelo {modo}")


def registrar_link(link: str, site: str):
    """Grava o link público atual em url.txt no site (HF Space estático),
    para a página de lá se conectar sozinha a este Colab."""
    from huggingface_hub import HfApi

    try:
        HfApi(token=os.environ.get("HF_TOKEN")).upload_file(
            path_or_fileobj=link.encode(), path_in_repo="url.txt", repo_id=site, repo_type="space",
            commit_message="link do Colab atualizado",
        )
        print(f"[estudio] site https://huggingface.co/spaces/{site} agora aponta para {link}")
    except Exception as erro:  # noqa: BLE001
        print(f"[estudio] não consegui atualizar o site ({erro}); use o link acima direto.")


with gr.Blocks(title="Estúdio") as demo:
    gr.Markdown("# 🎬 Estúdio\nTexto ou imagem → vídeo, com movimentos de câmera prontos.")
    if ZERO_GPU:
        gr.Markdown("Grátis: cada visitante usa a própria cota de GPU do Hugging Face. "
                    "**Entre na sua conta do huggingface.co** para ter 5 min por dia (sem login são 2 min).")
    with gr.Row():
        with gr.Column():
            prompt = gr.Textbox(label="Prompt", lines=3, placeholder="uma astronauta caminhando num deserto ao pôr do sol")
            imagem = gr.Image(label="Imagem inicial (opcional)", type="filepath")
            preset = gr.Radio(list(PRESETS), value="Dolly In", label="Movimento de câmera")
            with gr.Row():
                formato = gr.Radio(["16:9", "9:16", "1:1"], value="16:9", label="Formato")
                qualidade = gr.Radio(list(RESOLUCOES), value="Rápido", label="Qualidade")
            segundos = gr.Slider(1, 5, value=3, step=0.5, label="Duração (s)")
            turbo = gr.Checkbox(value=True, label="Turbo: a IA gera metade dos quadros e o resto é interpolado (~2x mais rápido)")
            semente = gr.Number(value=-1, label="Semente (-1 = aleatória)", precision=0)
            botao = gr.Button("Gerar", variant="primary")
        with gr.Column():
            video = gr.Video(label="Resultado", autoplay=True)
            info = gr.Markdown()

    botao.click(
        gerar,
        [prompt, preset, imagem, formato, segundos, qualidade, turbo, semente],
        [video, info],
        api_name="gerar",
    )

if ZERO_GPU:
    _carregar()  # no ZeroGPU os modelos têm que ir para a "cuda" no início, fora da função da GPU

if __name__ == "__main__":
    if os.environ.get("ESTUDIO_PRECARREGAR") == "1":
        _carregar()
    _, _, link = demo.queue().launch(
        server_name="0.0.0.0",
        share=os.environ.get("ESTUDIO_SHARE") == "1",
        prevent_thread_lock=True,
    )
    if link and os.environ.get("ESTUDIO_SITE"):
        registrar_link(link, os.environ["ESTUDIO_SITE"])
    demo.block_thread()
