"""Teste ponta a ponta do executor, sem internet: sobe o app.py de verdade e usa só a API do Gradio.

Uso (a partir de estudio/runner):
    python testes/criar_modelo_tiny.py testes/locais/tiny
    python testes/teste_local.py
Usa os "Spaces" locais de testes/locais (local:demo) e o modelo local:tiny.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from gradio_client import Client, handle_file

RAIZ = Path(__file__).resolve().parent.parent
PORTA = 7871
CHAVE = "segredo-de-teste"
falhas = []


def confere(nome, condicao, detalhe=""):
    print(("  ok   " if condicao else "  FALHOU ") + nome + (f"  [{detalhe}]" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(nome)


def deve_falhar(nome, funcao, trecho):
    try:
        funcao()
        confere(nome, False, "não deu erro")
    except Exception as erro:  # noqa: BLE001
        confere(nome, trecho.lower() in str(erro).lower(), str(erro)[:150])


dados = Path(tempfile.mkdtemp(prefix="runner-dados-"))
ambiente = {**os.environ, "RUNNER_DADOS": str(dados), "RUNNER_LOCAIS": str(RAIZ / "testes" / "locais"),
            "RUNNER_CHAVE": CHAVE, "RUNNER_PUBLICOS": "local:demo,local:segundo", "RUNNER_SEM_PROBE": "1",
            "GRADIO_SERVER_PORT": str(PORTA), "GRADIO_ANALYTICS_ENABLED": "False"}
servidor = subprocess.Popen([sys.executable, "app.py"], cwd=RAIZ, env=ambiente,
                            stdout=open(dados / "servidor.log", "w"), stderr=subprocess.STDOUT)
try:
    api = None
    for _ in range(60):
        try:
            api = Client(f"http://127.0.0.1:{PORTA}", verbose=False)
            break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    assert api, "o executor não subiu:\n" + (dados / "servidor.log").read_text()

    print("status e segurança")
    st = api.predict(api_name="/status")
    confere("status responde", st["versao"] and st["chave_configurada"] is True and st["publicos"] == ["local:demo", "local:segundo"])
    dg = api.predict(api_name="/diagnostico")
    confere("diagnóstico da GPU (principal e subprocesso)", "principal" in dg and "torch" in dg["subprocesso"], str(dg))
    deve_falhar("carregar não público sem chave", lambda: api.predict("", "local:outro", api_name="/carregar"), "chave")
    deve_falhar("carregar com chave errada", lambda: api.predict("errada", "local:outro", api_name="/carregar"), "chave inválida")
    deve_falhar("id malformado", lambda: api.predict(CHAVE, "../../etc/passwd", api_name="/carregar"), "dono/nome")
    deve_falhar("local fora da pasta", lambda: api.predict(CHAVE, "local:..", api_name="/carregar"), "dono/nome")
    deve_falhar("local inexistente vira erro claro", lambda: (api.predict(CHAVE, "local:nao_existe", api_name="/carregar"),
                time.sleep(3), api.predict(CHAVE, "local:nao_existe", "/x", "[]", None, api_name="/chamar")), "")

    print("carregar o Space público (sem chave)")
    r = api.predict("", "local:demo", api_name="/carregar")
    confere("carregar começa em segundo plano", r["estado"] in ("baixando", "instalando", "iniciando", "pronto"), str(r))
    estado = None
    for _ in range(90):
        st = api.predict(api_name="/status")
        estado = next((e for e in st["espacos"] if e["id"] == "local:demo"), {}).get("estado")
        if estado in ("pronto", "erro"):
            break
        time.sleep(1)
    confere("Space chegou a 'pronto'", estado == "pronto", f"estado={estado} log={api.predict('', 'local:demo', api_name='/log')['log'][-600:]}")
    log = api.predict("", "local:demo", api_name="/log")["log"]
    confere("shim do spaces foi usado", "shim do spaces em uso: True" in log)
    filtrado = (dados / "espacos" / "local_demo" / "requisitos.filtrado.txt").read_text()
    confere("requisitos filtrados (sem torch/spaces/gradio)", filtrado.split() == ["pillow"], filtrado)

    print("descobrir a API")
    apis = api.predict("", "local:demo", api_name="/apis")
    gerar = next(a for a in apis if a["api_name"] == "/gerar")
    nomes = [p["nome"] for p in gerar["parametros"]]
    confere("endpoint /gerar descrito", nomes == ["texto", "vezes", "maiuscula", "modo", "arquivo"], str(nomes))
    modo = next(p for p in gerar["parametros"] if p["nome"] == "modo")
    vezes = next(p for p in gerar["parametros"] if p["nome"] == "vezes")
    confere("opções do dropdown", modo["opcoes"] == ["a", "b"])
    confere("faixa do slider", (vezes["minimo"], vezes["maximo"]) == (1.0, 5.0), str((vezes["minimo"], vezes["maximo"])))
    confere("parâmetro de arquivo marcado", next(p for p in gerar["parametros"] if p["nome"] == "arquivo")["arquivo"] is True)

    print("chamar")
    enviado = dados / "entrada.txt"
    enviado.write_text("12345")
    res, arquivos = api.predict("", "local:demo", "/gerar", json.dumps(["ab", 3, True, "b", "@arquivo:0"]),
                                [handle_file(str(enviado))], api_name="/chamar")
    saida = res["resultado"]
    confere("texto calculado pelo Space", saida[0] == "b:ABABAB:5", str(saida))
    confere("número calculado", saida[2] == 6)
    confere("arquivo gerado referenciado", saida[1] == {"__arquivo__": 0}, str(saida[1]))
    confere("arquivo gerado devolvido", len(arquivos) == 1 and Path(arquivos[0]).suffix == ".png" and Path(arquivos[0]).stat().st_size > 50,
            str(arquivos))
    res2, _ = api.predict("", "local:demo", "/gerar", json.dumps({"texto": "x", "vezes": 2, "maiuscula": False, "modo": "a"}),
                          None, api_name="/chamar")
    confere("chamada por nome de parâmetro", res2["resultado"][0] == "a:xx:0", str(res2))
    deve_falhar("endpoint inexistente", lambda: api.predict("", "local:demo", "/nada", "[]", None, api_name="/chamar"), "não tem o endpoint")
    deve_falhar("parâmetro desconhecido", lambda: api.predict("", "local:demo", "/gerar", '{"zzz": 1}', None, api_name="/chamar"), "desconhecidos")
    deve_falhar("JSON inválido", lambda: api.predict("", "local:demo", "/gerar", "{oi", None, api_name="/chamar"), "json inválido")
    deve_falhar("arquivo citado e não enviado", lambda: api.predict("", "local:demo", "/gerar", '["a", 1, false, "a", "@arquivo:3"]', None, api_name="/chamar"), "arquivo 3")

    print("um Space ativo por vez")
    api.predict("", "local:segundo", api_name="/carregar")
    for _ in range(90):
        st = {e["id"]: e["estado"] for e in api.predict(api_name="/status")["espacos"]}
        if st.get("local:segundo") in ("pronto", "erro"):
            break
        time.sleep(1)
    confere("segundo Space ficou pronto", st.get("local:segundo") == "pronto", str(st))
    confere("o primeiro foi parado para liberar a GPU", st.get("local:demo") == "parado", str(st))
    deve_falhar("chamar o parado pede para carregar de novo", lambda: api.predict("", "local:demo", "/gerar", "[]", None, api_name="/chamar"), "'parado'")
    res3, _ = api.predict("", "local:segundo", "/gerar", '["z", 1, false, "a"]', None, api_name="/chamar")
    confere("o segundo responde", res3["resultado"][0] == "a:z:0", str(res3))

    print("modelo solto (transformers, local:tiny)")
    deve_falhar("modelo exige chave", lambda: api.predict("", "local:tiny", "classificacao-de-texto", '{"entrada": "o filme é bom"}', None, api_name="/modelo"), "chave")
    if (RAIZ / "testes" / "locais" / "tiny").exists():
        r, a = api.predict(CHAVE, "local:tiny", "classificacao-de-texto", '{"entrada": "o filme é bom"}', None, api_name="/modelo")
        res = r["resultado"]
        confere("classificação devolve rótulo e nota", isinstance(res, list) and res[0]["label"] in ("NEGATIVO", "POSITIVO")
                and 0 <= res[0]["score"] <= 1, str(res))
        deve_falhar("tarefa vazia", lambda: api.predict(CHAVE, "local:tiny", "", "{}", None, api_name="/modelo"), "tarefa")

    print("parar")
    deve_falhar("parar exige chave", lambda: api.predict("", api_name="/parar"), "chave")
    api.predict(CHAVE, api_name="/parar")
    st = api.predict(api_name="/status")
    confere("tudo parado", all(e["estado"] != "pronto" for e in st["espacos"]), str(st["espacos"]))
    deve_falhar("chamar depois de parar", lambda: api.predict("", "local:demo", "/gerar", "[]", None, api_name="/chamar"), "")
finally:
    servidor.terminate()
    try:
        servidor.wait(15)
    except subprocess.TimeoutExpired:
        servidor.kill()
    for pid_log in (dados / "espacos").glob("*"):
        pass
    shutil.rmtree(dados, ignore_errors=True)

print("\n" + ("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): " + "; ".join(falhas)))
sys.exit(1 if falhas else 0)
