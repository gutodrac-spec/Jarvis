"""Estúdio de vídeo com IA: texto/imagem -> vídeo com presets de câmera.

Roda igual no Google Colab (GPU T4 grátis) e num Hugging Face Space.
A interface Gradio também expõe uma API (`/gerar`) que a página `web/index.html` usa.

Variáveis de ambiente (todas opcionais):
  ESTUDIO_MODELO  repositório do modelo no Hugging Face (padrão: Lightricks/LTX-Video)
  ESTUDIO_SHARE   "1" para gerar link público (use no Colab)
  ESTUDIO_DTYPE   "fp16" ou "bf16" (padrão: bf16 se a GPU suportar, senão fp16)
"""

import os
import random
import tempfile

import gradio as gr
import torch

from presets import NEGATIVO, PRESETS, montar_prompt

MODELO = os.environ.get("ESTUDIO_MODELO", "Lightricks/LTX-Video")
FPS = 24
FORMATOS = {
    "16:9": (704, 416),
    "9:16": (416, 704),
    "1:1": (512, 512),
}

# No Hugging Face Space com ZeroGPU, o decorador reserva a GPU durante a geração.
try:
    import spaces

    usar_gpu = spaces.GPU(duration=180)
except ImportError:
    def usar_gpu(f):
        return f


def _dtype():
    escolha = os.environ.get("ESTUDIO_DTYPE")
    if escolha == "fp16":
        return torch.float16
    if escolha == "bf16":
        return torch.bfloat16
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


_pipes = {}


def _carregar():
    """Carrega o modelo uma vez. Em GPUs com pouca memória (T4), o codificador
    de texto (T5, o maior pedaço) é carregado em 8 bits para caber."""
    if _pipes:
        return _pipes
    from diffusers import LTXImageToVideoPipeline, LTXPipeline

    kwargs = {"torch_dtype": _dtype()}
    vram = torch.cuda.get_device_properties(0).total_memory / 2**30 if torch.cuda.is_available() else 0
    if 0 < vram < 20:
        from diffusers.quantizers import PipelineQuantizationConfig

        kwargs["quantization_config"] = PipelineQuantizationConfig(
            quant_backend="bitsandbytes_8bit",
            quant_kwargs={"load_in_8bit": True},
            components_to_quantize=["text_encoder"],
        )

    texto = LTXPipeline.from_pretrained(MODELO, **kwargs)
    texto.to("cuda" if torch.cuda.is_available() else "cpu")
    texto.vae.enable_tiling()
    _pipes["texto"] = texto
    _pipes["imagem"] = LTXImageToVideoPipeline(**texto.components)
    return _pipes


def _quadros(segundos: float) -> int:
    # O LTX exige número de quadros no formato 8k + 1.
    return int(round(segundos * FPS / 8)) * 8 + 1


@usar_gpu
def gerar(prompt, preset, imagem, formato, segundos, passos, semente):
    from diffusers.utils import export_to_video

    if not prompt and imagem is None:
        raise gr.Error("Escreva um prompt ou envie uma imagem.")
    pipes = _carregar()
    largura, altura = FORMATOS.get(formato, FORMATOS["16:9"])
    semente = int(semente) if semente and int(semente) >= 0 else random.randint(0, 2**31 - 1)
    gerador = torch.Generator(device="cpu").manual_seed(semente)

    args = dict(
        prompt=montar_prompt(prompt or "", preset),
        negative_prompt=NEGATIVO,
        width=largura,
        height=altura,
        num_frames=_quadros(float(segundos)),
        num_inference_steps=int(passos),
        generator=gerador,
    )
    if imagem is not None:
        from PIL import Image

        img = Image.open(imagem).convert("RGB") if isinstance(imagem, str) else imagem.convert("RGB")
        quadros = pipes["imagem"](image=img.resize((largura, altura)), **args).frames[0]
    else:
        quadros = pipes["texto"](**args).frames[0]

    saida = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    export_to_video(quadros, saida, fps=FPS)
    return saida, f"semente {semente} · {largura}x{altura} · {len(quadros)} quadros"


with gr.Blocks(title="Estúdio") as demo:
    gr.Markdown("# 🎬 Estúdio\nTexto ou imagem → vídeo, com movimentos de câmera prontos.")
    with gr.Row():
        with gr.Column():
            prompt = gr.Textbox(label="Prompt", lines=3, placeholder="uma astronauta caminhando num deserto ao pôr do sol")
            imagem = gr.Image(label="Imagem inicial (opcional)", type="filepath")
            preset = gr.Radio(list(PRESETS), value="Dolly In", label="Movimento de câmera")
            with gr.Row():
                formato = gr.Radio(list(FORMATOS), value="16:9", label="Formato")
                segundos = gr.Slider(1, 5, value=3, step=0.5, label="Duração (s)")
            with gr.Accordion("Avançado", open=False):
                passos = gr.Slider(10, 50, value=30, step=1, label="Passos")
                semente = gr.Number(value=-1, label="Semente (-1 = aleatória)", precision=0)
            botao = gr.Button("Gerar", variant="primary")
        with gr.Column():
            video = gr.Video(label="Resultado", autoplay=True)
            info = gr.Markdown()

    botao.click(
        gerar,
        [prompt, preset, imagem, formato, segundos, passos, semente],
        [video, info],
        api_name="gerar",
    )

if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        share=os.environ.get("ESTUDIO_SHARE") == "1",
    )
