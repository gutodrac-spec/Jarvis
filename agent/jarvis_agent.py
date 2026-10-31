"""J.A.R.V.I.S. - agente que roda no seu PC.

- Conecta no servidor Jarvis (WebSocket)
- Vigia a tela sozinho e te LIGA quando algo importante acontece
- Atende seus pedidos (voz/texto pelo app): Groq para o rápido, Claude para o complexo
- Mexe no mouse e teclado do PC
- Transmite a tela ao vivo para o app

Rode:  python jarvis_agent.py
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import psutil  # noqa: E402
import websockets  # noqa: E402

import brain  # noqa: E402
import claude_worker  # noqa: E402
import pc  # noqa: E402

SERVER = os.getenv("JARVIS_SERVER", "ws://localhost:8787/ws")
TOKEN = os.environ.get("JARVIS_TOKEN", "")
MONITOR_ENABLED = os.getenv("MONITOR_ENABLED", "1") == "1"
MONITOR_INTERVAL = float(os.getenv("MONITOR_INTERVAL", "20"))
MONITOR_FORCE_EVERY = float(os.getenv("MONITOR_FORCE_EVERY", "300"))
ALERT_COOLDOWN = float(os.getenv("ALERT_COOLDOWN", "900"))
WATCH_RULES = os.getenv("WATCH_RULES", "Me ligue se aparecer erro, travamento ou algo que precise da minha atenção.")
STREAM_FPS = float(os.getenv("STREAM_FPS", "1.5"))
STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", "1100"))
URGENCY = ["baixa", "normal", "alta", "critica"]
CALL_MIN = URGENCY.index(os.getenv("CALL_MIN_URGENCY", "normal")) if os.getenv("CALL_MIN_URGENCY", "normal") in URGENCY else 1


class Jarvis:
    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ws = None
        self.streaming = False
        self.history: list[dict] = []
        self.last_alert: dict | None = None
        self.alerted: dict[str, float] = {}
        self.task_thread: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.user_active_until = 0.0

    # ------------------------------------------------------------ envio
    def send(self, msg: dict):
        """Seguro para chamar de qualquer thread."""
        if self.loop and self.ws:
            asyncio.run_coroutine_threadsafe(self._send(msg), self.loop)

    async def _send(self, msg: dict):
        try:
            await self.ws.send(json.dumps(msg))
        except Exception:
            pass

    def say(self, text: str):
        if text:
            print(f"[Jarvis] {text}")
            self.send({"type": "say", "text": text})

    def call(self, reason: str, urgency: str = "normal"):
        print(f"[LIGANDO] ({urgency}) {reason}")
        self.send({"type": "call", "reason": reason, "urgency": urgency})

    def notify(self, title: str, body: str):
        self.send({"type": "notify", "title": title, "body": body})

    # ------------------------------------------------------------ conexão
    async def run(self):
        self.loop = asyncio.get_running_loop()
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        threading.Thread(target=self.stream_loop, daemon=True).start()
        threading.Thread(target=self.system_watch_loop, daemon=True).start()
        url = f"{SERVER}?role=agent&token={TOKEN}"
        while True:
            try:
                async with websockets.connect(url, max_size=8 * 1024 * 1024, ping_interval=20) as ws:
                    self.ws = ws
                    print(f"Conectado a {SERVER}")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        await self.on_message(msg)
            except Exception as e:
                print(f"Conexão perdida ({e}); tentando de novo em 3s…")
            self.ws = None
            await asyncio.sleep(3)

    async def on_message(self, m: dict):
        t = m.get("type")
        if t == "user_text":
            self.user_active_until = time.time() + 120
            threading.Thread(target=self.handle_user, args=(m.get("text", ""),), daemon=True).start()
        elif t == "user_call":
            self.user_active_until = time.time() + 120
        elif t == "call_accepted":
            self.user_active_until = time.time() + 120
            if self.last_alert:
                reason = self.last_alert["reason"]
                txt = f"{reason} Quer que eu cuide disso?"
                self.history.append({"role": "assistant", "content": txt})
                self.say(txt)
        elif t == "call_declined":
            print("Chamada recusada.")
        elif t == "stream":
            self.streaming = bool(m.get("on"))
        elif t == "stop":
            self.stop_task()

    # ------------------------------------------------------------ pedidos do usuário
    def context(self) -> str:
        parts = []
        if self.last_alert and time.time() - self.last_alert["ts"] < 1800:
            parts.append(f"último alerta que você deu: {self.last_alert['reason']} (tela: {self.last_alert.get('summary', '')})")
        if self.busy():
            parts.append("há uma tarefa avançada em andamento no PC")
        return "; ".join(parts)

    def handle_user(self, text: str):
        if not text.strip():
            return
        low = text.lower().strip()
        if low in ("para", "pare", "parar", "cancela", "cancelar", "stop"):
            self.stop_task()
            return
        t0 = time.time()
        d = brain.route(self.history, text, self.context())
        print(f"[groq {int((time.time() - t0) * 1000)}ms] {d}")
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": d.get("reply", "")}]
        self.history = self.history[-30:]
        self.say(d.get("reply", ""))

        for act in d.get("actions") or []:
            try:
                out = self.quick_action(act)
                if out:
                    self.say(out)
                    self.history.append({"role": "assistant", "content": out})
            except Exception as e:
                self.say(f"Não consegui executar {act.get('tool')}: {e}")

        task = d.get("delegate")
        if task:
            self.start_task(task)

    def quick_action(self, a: dict) -> str | None:
        tool = a.get("tool")
        if tool == "open_url":
            webbrowser.open(a["url"])
        elif tool == "open_app":
            open_app(a["name"])
        elif tool == "hotkey":
            pc.key(a["keys"])
        elif tool == "type_text":
            pc.type_text(a["text"])
        elif tool == "media":
            pc.key(a.get("key", "playpause"))
        elif tool == "lock_pc":
            lock_pc()
        elif tool == "look":
            img, _ = pc.fit(pc.grab(), 1280)
            return brain.look(pc.to_b64(img), a.get("question", "O que está na tela?"))
        return None

    # ------------------------------------------------------------ tarefas complexas (Claude)
    def busy(self) -> bool:
        return bool(self.task_thread and self.task_thread.is_alive())

    def start_task(self, task: str):
        if self.busy():
            self.say("Já estou executando outra tarefa, senhor. Diga 'parar' se quiser cancelar.")
            return
        self.stop_flag.clear()

        def work():
            print(f"[claude] tarefa: {task}")
            self.send({"type": "log", "text": f"🧠 Claude: {task}"})
            try:
                result = claude_worker.run(task, self.say, self.stop_flag)
            except Exception as e:
                result = f"Deu erro na tarefa: {e}"
            self.history.append({"role": "assistant", "content": f"[resultado da tarefa] {result}"})
            self.say(result)
            if time.time() > self.user_active_until:  # se você saiu do app, eu te ligo com o resultado
                self.call(f"Senhor, terminei: {result[:180]}", "normal")

        self.task_thread = threading.Thread(target=work, daemon=True)
        self.task_thread.start()

    def stop_task(self):
        self.stop_flag.set()
        claude_worker.kill()
        self.say("Parando, senhor.")

    # ------------------------------------------------------------ vigilância da tela
    def monitor_loop(self):
        if not MONITOR_ENABLED:
            return
        if not os.getenv("GROQ_API_KEY"):
            print("GROQ_API_KEY ausente: monitoramento desligado.")
            return
        prev = None
        last_check = 0.0
        while True:
            time.sleep(MONITOR_INTERVAL)
            if self.busy() or not self.ws:
                continue  # durante uma tarefa a tela muda de propósito
            try:
                full = pc.grab()
                changed = pc.change_ratio(prev, full)
                if changed < 0.02 and time.time() - last_check < MONITOR_FORCE_EVERY:
                    continue
                prev = full
                last_check = time.time()
                img, _ = pc.fit(full, 1024)
                r = brain.analyze_screen(pc.to_b64(img, 70), WATCH_RULES, self.context())
                if not r.get("alert"):
                    continue
                key = (r.get("key") or r.get("reason", ""))[:60].lower()
                if time.time() - self.alerted.get(key, 0) < ALERT_COOLDOWN:
                    continue
                self.alerted[key] = time.time()
                urg = r.get("urgency", "normal")
                reason = r.get("reason") or "Algo na tela precisa da sua atenção."
                self.last_alert = {"reason": reason, "summary": r.get("summary", ""), "ts": time.time()}
                level = URGENCY.index(urg) if urg in URGENCY else 1
                if level >= CALL_MIN:
                    self.call(reason, urg)
                else:
                    self.notify("Jarvis", reason)
            except Exception as e:
                print(f"[monitor] erro: {e}")

    def system_watch_loop(self):
        """Alertas que não precisam de IA: bateria, RAM, disco."""
        high_ram = 0
        while True:
            time.sleep(30)
            try:
                b = psutil.sensors_battery()
                if b and not b.power_plugged and b.percent <= 15:
                    self._sys_alert("bateria", f"Senhor, a bateria está em {int(b.percent)}% e fora da tomada.", "alta")
                ram = psutil.virtual_memory().percent
                high_ram = high_ram + 1 if ram > 95 else 0
                if high_ram >= 4:
                    self._sys_alert("ram", f"Senhor, a memória RAM está em {int(ram)}% há 2 minutos.", "normal")
                disk = psutil.disk_usage(str(Path.home().anchor or "/")).percent
                if disk > 97:
                    self._sys_alert("disco", f"Senhor, o disco principal está {int(disk)}% cheio.", "normal")
            except Exception:
                pass

    def _sys_alert(self, key, reason, urg):
        if time.time() - self.alerted.get(key, 0) < 3600:
            return
        self.alerted[key] = time.time()
        self.last_alert = {"reason": reason, "summary": "", "ts": time.time()}
        self.call(reason, urg)

    # ------------------------------------------------------------ tela ao vivo
    def stream_loop(self):
        while True:
            if not (self.streaming and self.ws):
                time.sleep(0.3)
                continue
            t0 = time.time()
            try:
                img, _ = pc.fit(pc.grab(), STREAM_WIDTH)
                self.send({"type": "frame", "jpeg": pc.to_b64(img, 55)})
            except Exception as e:
                print(f"[stream] {e}")
            time.sleep(max(0.05, 1 / STREAM_FPS - (time.time() - t0)))


# ---------------------------------------------------------------- utilidades do SO
def open_app(name: str):
    sysname = platform.system()
    if sysname == "Windows":
        # "start" encontra programas registrados (chrome, spotify, notepad, calc...)
        subprocess.Popen(f'start "" "{name}"', shell=True)
    elif sysname == "Darwin":
        subprocess.Popen(["open", "-a", name])
    else:
        subprocess.Popen([name])


def lock_pc():
    sysname = platform.system()
    if sysname == "Windows":
        import ctypes

        ctypes.windll.user32.LockWorkStation()
    elif sysname == "Darwin":
        subprocess.Popen(["pmset", "displaysleepnow"])
    else:
        subprocess.Popen(["loginctl", "lock-session"])


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina JARVIS_TOKEN no arquivo .env (copie de .env.example).")
    print("J.A.R.V.I.S. online. (Mova o mouse para um canto da tela para abortar qualquer ação.)")
    try:
        asyncio.run(Jarvis().run())
    except KeyboardInterrupt:
        pass
