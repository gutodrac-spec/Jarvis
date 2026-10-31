"""Utilitário de linha de comando para o Claude Code ver a tela e mexer no PC.

Coordenadas são sempre no espaço da última screenshot (redimensionada para 1280px).
"""
import json
import sys
import tempfile
import time
from pathlib import Path

import pc

STATE = Path(tempfile.gettempdir()) / "jarvis_screen.json"
SHOT = Path(tempfile.gettempdir()) / "jarvis_screen.png"


def scale() -> float:
    try:
        return json.loads(STATE.read_text())["scale"]
    except Exception:
        return 1.0


def real(x, y):
    s = scale()
    return int(float(x) * s), int(float(y) * s)


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, a = argv[0], argv[1:]
    if cmd == "screenshot":
        img, s = pc.fit(pc.grab(), 1280)
        img.save(SHOT)
        STATE.write_text(json.dumps({"scale": s}))
        print(f"{SHOT}  ({img.width}x{img.height})")
        return
    if cmd == "click":
        btn = a[2] if len(a) > 2 else "left"
        x, y = real(a[0], a[1])
        if btn == "double":
            pc.click(x, y, clicks=2)
        else:
            pc.click(x, y, button=btn)
    elif cmd == "move":
        pc.move(*real(a[0], a[1]))
    elif cmd == "drag":
        pc.drag(*real(a[0], a[1]), *real(a[2], a[3]))
    elif cmd == "type":
        pc.type_text(" ".join(a))
    elif cmd == "key":
        pc.key(a[0], int(a[1]) if len(a) > 1 else 1)
    elif cmd == "scroll":
        xy = real(a[2], a[3]) if len(a) > 3 else (None, None)
        pc.scroll(a[0], int(a[1]) if len(a) > 1 else 3, *xy)
    else:
        print(f"comando desconhecido: {cmd}")
        sys.exit(1)
    time.sleep(0.3)
    print("OK")


if __name__ == "__main__":
    main(sys.argv[1:])
