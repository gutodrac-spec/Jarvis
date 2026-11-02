import os

import gradio as gr
import spaces
from PIL import Image

print("shim do spaces em uso:", "shim" in spaces.__file__, flush=True)


@spaces.GPU(duration=60, size="xlarge")
def gerar(texto, vezes, maiuscula, modo, arquivo):
    tamanho = os.path.getsize(arquivo) if arquivo else 0
    s = texto * int(vezes)
    s = s.upper() if maiuscula else s
    Image.new("RGB", (64, 48), (200, 50, 50)).save("saida.png")
    return f"{modo}:{s}:{tamanho}", "saida.png", int(vezes) * 2


with gr.Blocks() as demo:
    t = gr.Textbox(label="Texto")
    n = gr.Slider(1, 5, value=2, step=1, label="Vezes")
    c = gr.Checkbox(label="Maiúscula", value=False)
    m = gr.Dropdown(["a", "b"], value="a", label="Modo")
    f = gr.File(label="Arquivo", type="filepath")
    o1, o2, o3 = gr.Textbox(label="Saída"), gr.Image(label="Imagem", type="filepath"), gr.Number(label="Dobro")
    gr.Button("ok").click(gerar, [t, n, c, m, f], [o1, o2, o3], api_name="gerar")

if __name__ == "__main__":
    demo.launch()
