"""Controle do PC: captura de tela, mouse e teclado.

Todas as coordenadas recebidas pelos modelos estão no espaço da imagem
redimensionada que eles viram; aqui convertemos para pixels reais.
"""
from __future__ import annotations

import base64
import io
import platform
import threading
import time

import mss
import pyautogui
import pyperclip
from PIL import Image, ImageChops

IS_WIN = platform.system() == "Windows"

if IS_WIN:  # captura e cliques em pixels físicos (evita erro com escala 125%/150%)
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

pyautogui.FAILSAFE = True  # jogue o mouse num canto da tela para abortar na hora
pyautogui.PAUSE = 0.05

_lock = threading.Lock()


def grab() -> Image.Image:
    """Captura o monitor principal em resolução real."""
    with _lock, mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def fit(img: Image.Image, max_side: int) -> tuple[Image.Image, float]:
    """Redimensiona mantendo proporção. Retorna (imagem, escala real/imagem)."""
    w, h = img.size
    s = min(1.0, max_side / max(w, h))
    if s < 1.0:
        img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
    return img, (1 / s)


def to_b64(img: Image.Image, quality: int = 70) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def change_ratio(a: Image.Image | None, b: Image.Image) -> float:
    """Fração aproximada (0..1) de pixels que mudaram entre duas capturas."""
    if a is None:
        return 1.0
    sa = a.convert("L").resize((160, 90))
    sb = b.convert("L").resize((160, 90))
    diff = ImageChops.difference(sa, sb).point(lambda p: 255 if p > 25 else 0)
    return sum(1 for p in diff.getdata() if p) / (160 * 90)


class Screen:
    """Mantém a escala da última captura enviada a um modelo."""

    def __init__(self, max_side: int = 1280):
        self.max_side = max_side
        self.scale = 1.0
        self.last_full: Image.Image | None = None

    def shot_b64(self) -> str:
        full = grab()
        self.last_full = full
        img, self.scale = fit(full, self.max_side)
        return to_b64(img, 75)

    def zoom_b64(self, region) -> str:
        full = self.last_full or grab()
        x0, y0, x1, y1 = [int(v * self.scale) for v in region]
        crop = full.crop((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        crop, _ = fit(crop, self.max_side)
        return to_b64(crop, 85)

    def real(self, coord) -> tuple[int, int]:
        x, y = coord
        return int(x * self.scale), int(y * self.scale)


# ---------------- teclado ----------------
_KEYMAP = {
    "return": "enter", "enter": "enter", "kp_enter": "enter", "escape": "esc", "esc": "esc",
    "backspace": "backspace", "tab": "tab", "space": "space", "delete": "delete", "del": "delete",
    "super": "win", "win": "win", "meta": "win", "cmd": "win", "command": "win",
    "control": "ctrl", "ctrl": "ctrl", "control_l": "ctrl", "control_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "page_up": "pageup", "pageup": "pageup", "prior": "pageup", "page_down": "pagedown", "pagedown": "pagedown",
    "next": "pagedown", "home": "home", "end": "end", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "print": "printscreen", "caps_lock": "capslock", "menu": "apps",
    "xf86audioplay": "playpause", "xf86audionext": "nexttrack", "xf86audioprev": "prevtrack",
    "xf86audiomute": "volumemute", "xf86audioraisevolume": "volumeup", "xf86audiolowervolume": "volumedown",
}


def _keys(combo: str) -> list[str]:
    out = []
    for k in combo.replace(" ", "").split("+"):
        if not k:
            continue
        kl = k.lower()
        out.append(_KEYMAP.get(kl, kl))
    return out


def key(combo: str, repeat: int = 1):
    ks = _keys(combo)
    for _ in range(max(1, min(int(repeat or 1), 100))):
        pyautogui.hotkey(*ks) if len(ks) > 1 else pyautogui.press(ks[0])


def hold_key(combo: str, duration: float):
    ks = _keys(combo)
    for k in ks:
        pyautogui.keyDown(k)
    time.sleep(min(float(duration), 300))
    for k in reversed(ks):
        pyautogui.keyUp(k)


def type_text(text: str):
    """Digita texto. Acentos (ç, ã, é...) vão pela área de transferência."""
    if text.isascii():
        pyautogui.write(text, interval=0.01)
        return
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    pyautogui.hotkey("command" if platform.system() == "Darwin" else "ctrl", "v")
    time.sleep(0.15)
    if old is not None:
        try:
            pyperclip.copy(old)
        except Exception:
            pass


# ---------------- mouse ----------------
class _Mods:
    def __init__(self, text: str | None):
        self.ks = _keys(text) if text else []

    def __enter__(self):
        for k in self.ks:
            pyautogui.keyDown(k)

    def __exit__(self, *a):
        for k in reversed(self.ks):
            pyautogui.keyUp(k)


def click(x=None, y=None, button="left", clicks=1, mods=None):
    with _Mods(mods):
        if x is None:
            pyautogui.click(button=button, clicks=clicks, interval=0.08)
        else:
            pyautogui.click(x, y, button=button, clicks=clicks, interval=0.08)


def move(x, y):
    pyautogui.moveTo(x, y, duration=0.15)


def drag(x0, y0, x1, y1, mods=None):
    with _Mods(mods):
        pyautogui.moveTo(x0, y0, duration=0.1)
        pyautogui.dragTo(x1, y1, duration=0.4, button="left")


def scroll(direction: str, amount: int, x=None, y=None, mods=None):
    if x is not None:
        pyautogui.moveTo(x, y, duration=0.1)
    unit = 120 if IS_WIN else 1
    n = int(amount or 3) * unit
    with _Mods(mods):
        if direction == "up":
            pyautogui.scroll(n)
        elif direction == "down":
            pyautogui.scroll(-n)
        elif direction in ("left", "right"):
            try:
                pyautogui.hscroll(n if direction == "right" else -n)
            except Exception:
                with _Mods("shift"):
                    pyautogui.scroll(-n if direction == "right" else n)


def mouse_down():
    pyautogui.mouseDown()


def mouse_up():
    pyautogui.mouseUp()


def cursor() -> tuple[int, int]:
    p = pyautogui.position()
    return int(p[0]), int(p[1])
