"""Presets de movimento de câmera.

Cada preset é um trecho de prompt que descreve o movimento em inglês
(o modelo entende melhor assim). Para criar um novo, basta adicionar uma linha.
"""

PRESETS = {
    "Livre (sem preset)": "",
    "Dolly In": "slow dolly in toward the subject, smooth forward camera push",
    "Dolly Out": "slow dolly out away from the subject, camera pulling back revealing the scene",
    "Crash Zoom": "sudden fast crash zoom into the subject's face, dramatic snap zoom",
    "Órbita 360": "camera orbits 360 degrees around the subject, smooth circular tracking shot",
    "Drone FPV": "fast FPV drone shot flying through the scene, dynamic banking and diving",
    "Grua para cima": "crane shot rising up and tilting down, revealing the landscape from above",
    "Pan esquerda": "smooth camera pan from right to left",
    "Pan direita": "smooth camera pan from left to right",
    "Tilt para cima": "camera tilts up slowly from the ground to the sky",
    "Câmera na mão": "handheld camera, natural shake, documentary style",
    "Bullet Time": "bullet time effect, frozen moment while the camera arcs around the subject",
    "Snorricam": "snorricam shot, camera rigidly attached to the subject's body, background moving",
    "Dolly Zoom": "dolly zoom vertigo effect, background warps while the subject stays the same size",
    "Super Dolly": "fast push in through the scene, epic cinematic super dolly move",
    "Estático": "static locked-off camera, tripod shot, no camera movement",
}

ESTILO_BASE = "cinematic, high quality, detailed, smooth motion"

NEGATIVO = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, "
    "watermark, text, low resolution, deformed"
)


def montar_prompt(prompt: str, preset: str) -> str:
    """Junta o texto do usuário com o movimento do preset e o estilo base."""
    partes = [prompt.strip(), PRESETS.get(preset, ""), ESTILO_BASE]
    return ", ".join(p for p in partes if p)
