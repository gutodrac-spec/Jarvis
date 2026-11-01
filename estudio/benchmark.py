"""Mede o tempo real de geração com e sem CUDA Graphs (e com e sem Turbo).

Uso (numa máquina com GPU, ex.: Colab):  python benchmark.py
Cada configuração roda num processo separado, para uma medir sem interferir na outra.
"""

import os
import statistics
import subprocess
import sys
import time

PROMPT = "uma astronauta caminhando num deserto ao pôr do sol"
REPETICOES = 3


def medir(turbo: bool):
    import app

    app._carregar()
    args = (PROMPT, "Dolly In", None, "16:9", 3, "Rápido", turbo, 42)
    t = time.perf_counter()
    app.gerar(*args)  # aquecimento: na versão compilada, é aqui que ela compila
    aquecimento = time.perf_counter() - t
    tempos = []
    for _ in range(REPETICOES):
        t = time.perf_counter()
        app.gerar(*args)
        tempos.append(time.perf_counter() - t)
    print(f"RESULTADO {aquecimento:.2f} {statistics.median(tempos):.2f}", flush=True)


def main():
    linhas = []
    for compilar in ("0", "1"):
        for turbo in ("0", "1"):
            nome = f"{'CUDA Graphs' if compilar == '1' else 'normal':11s} | turbo {'sim' if turbo == '1' else 'não'}"
            print(f"\n=== {nome} ===", flush=True)
            env = {**os.environ, "ESTUDIO_COMPILAR": compilar}
            saida = subprocess.run([sys.executable, __file__, "--medir", turbo], env=env,
                                   capture_output=True, text=True)
            resultado = [l for l in saida.stdout.splitlines() if l.startswith("RESULTADO")]
            if not resultado:
                print(saida.stdout[-2000:], saida.stderr[-3000:])
                linhas.append((nome, None, None))
                continue
            _, aquec, med = resultado[0].split()
            linhas.append((nome, float(aquec), float(med)))
            print(f"1ª geração {aquec} s · mediana {med} s")

    base = linhas[0][2]
    print("\nConfiguração                | 1ª geração | mediana | vs. normal")
    print("----------------------------|------------|---------|-----------")
    for nome, aquec, med in linhas:
        if med is None:
            print(f"{nome} |     falhou |         |")
        else:
            print(f"{nome} | {aquec:8.1f} s | {med:5.1f} s | {base / med:5.2f}x")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--medir":
        medir(sys.argv[2] == "1")
    else:
        main()
