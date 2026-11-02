"""Executa Spaces Gradio do Hugging Face dentro deste Studio e deixa chamá-los por API.

Para cada Space: baixa o código (snapshot), cria um ambiente isolado (venv que enxerga os pacotes da imagem,
então o torch e a GPU são os do Studio), instala só o que falta, sobe o app numa porta interna e repassa as
chamadas com o gradio_client. Só um Space fica ativo por vez (RUNNER_MAX_ATIVOS) para caber na memória da GPU.
"""

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

DADOS = Path(os.environ.get("RUNNER_DADOS", "dados")).resolve()
LOCAIS = Path(os.environ.get("RUNNER_LOCAIS", "locais")).resolve()  # Spaces/modelos de teste: "local:nome"
SHIM = Path(__file__).resolve().parent / "shim"
MAX_ATIVOS = int(os.environ.get("RUNNER_MAX_ATIVOS", "1"))
TIMEOUT_INICIO = int(os.environ.get("RUNNER_TIMEOUT_INICIO", "3600"))  # baixar modelos pode demorar
TIMEOUT_PIP = int(os.environ.get("RUNNER_TIMEOUT_PIP", "3600"))

ID_HF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
ID_LOCAL = re.compile(r"^local:[A-Za-z0-9][A-Za-z0-9._-]*$")
# O torch/CUDA e o gradio da imagem do Studio são mantidos; "spaces" é o substituto de shim/.
IGNORAR_PACOTES = {"torch", "torchvision", "torchaudio", "triton", "spaces", "gradio", "gradio_client"}
COMPONENTES_ARQUIVO = {"Image", "Video", "Audio", "File", "UploadButton", "ImageEditor", "Model3D", "Gallery",
                       "ImageMask", "Sketchpad", "Paint", "AnnotatedImage", "DownloadButton"}
ESTADOS_VIVOS = {"baixando", "instalando", "iniciando", "pronto"}


class ErroRunner(Exception):
    """Erro esperado, com mensagem pensada para quem usa a API."""


class _Cancelado(Exception):
    pass


@dataclass
class Espaco:
    id: str
    slug: str
    dir: Path
    estado: str = "novo"
    mensagem: str = ""
    porta: int | None = None
    proc: subprocess.Popen | None = None
    proc_aux: subprocess.Popen | None = None
    cliente: object = None
    api: dict | None = None
    cancelar: bool = False
    criado: float = field(default_factory=time.time)
    ultimo_uso: float = field(default_factory=time.time)

    @property
    def log(self) -> Path:
        return DADOS / "logs" / f"{self.slug}.log"

    def resumo(self) -> dict:
        return {"id": self.id, "estado": self.estado, "mensagem": self.mensagem,
                "ultimo_uso": int(self.ultimo_uso), "log": ultimas_linhas(self.log, 3)}


REGISTRO: dict[str, Espaco] = {}
TRAVA = threading.RLock()


# ---------- identificação ----------
def validar_id(alvo: str) -> tuple[str, str]:
    """Devolve ("hf", "dono/nome") ou ("local", "nome"). Rejeita qualquer outra forma."""
    alvo = (alvo or "").strip()
    if ID_LOCAL.match(alvo):
        return "local", alvo.split(":", 1)[1]
    if ID_HF.match(alvo):
        return "hf", alvo
    raise ErroRunner("Informe o Space como dono/nome (ex.: Lightricks/ltx-video-distilled).")


def caminho_local(nome: str) -> Path:
    origem = (LOCAIS / nome).resolve()
    if LOCAIS not in origem.parents or not origem.exists():
        raise ErroRunner(f"Não existe '{nome}' na pasta de testes locais.")
    return origem


def ultimas_linhas(arquivo: Path, n: int = 30) -> str:
    try:
        return "\n".join(arquivo.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# ---------- requisitos ----------
def filtrar_requisitos(texto: str) -> list[str]:
    """Tira do requirements.txt do Space o que o Studio já fornece (torch, gradio, spaces)."""
    saida = []
    for linha in texto.splitlines():
        crua = linha.split("#", 1)[0].strip()
        if not crua:
            continue
        if crua.startswith("-"):  # -r outro.txt, --extra-index-url ...
            saida.append(crua)
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)", crua)
        nome = re.sub(r"[-_.]+", "_", m.group(1)).lower() if m else ""
        if nome in IGNORAR_PACOTES or nome.startswith("nvidia_"):
            continue
        saida.append(crua)
    return saida


def ler_readme(codigo: Path) -> dict:
    """Lê o cabeçalho YAML do README.md do Space (sdk, sdk_version, app_file)."""
    arquivo = codigo / "README.md"
    if not arquivo.exists():
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---", arquivo.read_text(errors="replace"), re.S)
    if not m:
        return {}
    import yaml

    try:
        dados = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return dados if isinstance(dados, dict) else {}


# ---------- ciclo de vida ----------
def _definir(esp: Espaco, estado: str, mensagem: str = ""):
    esp.estado, esp.mensagem = estado, mensagem
    esp.log.parent.mkdir(parents=True, exist_ok=True)
    with esp.log.open("a") as f:
        f.write(f"[runner] {estado}: {mensagem}\n")


def _checar(esp: Espaco):
    if esp.cancelar:
        raise _Cancelado()


def _matar(proc: subprocess.Popen | None):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def parar(esp: Espaco):
    esp.cancelar = True
    _matar(esp.proc)
    _matar(esp.proc_aux)
    esp.cliente = None
    if esp.estado != "erro":
        esp.estado, esp.mensagem = "parado", "parado"


def parar_todos():
    with TRAVA:
        for esp in list(REGISTRO.values()):
            if esp.estado in ESTADOS_VIVOS:
                parar(esp)


def _liberar_vaga(excluir: str):
    vivos = [e for e in REGISTRO.values() if e.id != excluir and e.estado in ESTADOS_VIVOS]
    vivos.sort(key=lambda e: e.ultimo_uso)
    while len(vivos) >= MAX_ATIVOS and vivos:
        parar(vivos.pop(0))


def iniciar(alvo: str) -> Espaco:
    """Começa a carregar o Space em segundo plano (se ainda não estiver) e devolve o estado."""
    tipo, nome = validar_id(alvo)
    alvo = nome if tipo == "hf" else f"local:{nome}"
    with TRAVA:
        esp = REGISTRO.get(alvo)
        if esp and esp.estado in ESTADOS_VIVOS and (esp.proc is None or esp.proc.poll() is None):
            esp.ultimo_uso = time.time()
            return esp
        slug = alvo.replace("/", "__").replace(":", "_")
        esp = Espaco(id=alvo, slug=slug, dir=DADOS / "espacos" / slug)
        REGISTRO[alvo] = esp
        _liberar_vaga(alvo)
        _definir(esp, "baixando", "começando")
        threading.Thread(target=_trabalho, args=(esp,), daemon=True, name=f"espaco-{slug}").start()
    return esp


def obter(alvo: str) -> Espaco | None:
    tipo, nome = validar_id(alvo)
    return REGISTRO.get(nome if tipo == "hf" else f"local:{nome}")


def _trabalho(esp: Espaco):
    try:
        codigo = _baixar(esp)
        _checar(esp)
        python, entrada = _instalar(esp, codigo)
        _checar(esp)
        _subir(esp, codigo, python, entrada)
    except _Cancelado:
        _definir(esp, "parado", "cancelado")
    except Exception as erro:  # noqa: BLE001
        _matar(esp.proc)
        _definir(esp, "erro", str(erro)[:600])


def _baixar(esp: Espaco) -> Path:
    _definir(esp, "baixando", "baixando o código do Space")
    codigo = esp.dir / "codigo"
    codigo.mkdir(parents=True, exist_ok=True)
    tipo, nome = validar_id(esp.id)
    if tipo == "local":
        shutil.copytree(caminho_local(nome), codigo, dirs_exist_ok=True)
    else:
        from huggingface_hub import snapshot_download

        try:
            snapshot_download(repo_id=nome, repo_type="space", local_dir=codigo,
                              token=os.environ.get("HF_TOKEN") or None)
        except Exception as erro:  # noqa: BLE001
            raise ErroRunner(f"Não consegui baixar o Space '{nome}': {str(erro)[:300]}") from erro
    return codigo


def _instalar(esp: Espaco, codigo: Path) -> tuple[Path, str]:
    meta = ler_readme(codigo)
    if meta.get("sdk", "gradio") != "gradio":
        raise ErroRunner(f"Este Space usa sdk '{meta.get('sdk')}'; só Spaces Gradio são suportados.")
    entrada = str(meta.get("app_file", "app.py"))
    if not (codigo / entrada).is_file():
        raise ErroRunner(f"Não achei o arquivo principal '{entrada}' no Space.")

    _definir(esp, "instalando", "preparando o ambiente do Space")
    venv = esp.dir / "venv"
    python = venv / "bin" / "python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True,
                       capture_output=True, timeout=300)

    _ligar_ao_pai(python)

    linhas = []
    requisitos = codigo / "requirements.txt"
    if requisitos.exists():
        linhas = filtrar_requisitos(requisitos.read_text(errors="replace"))
    versao = str(meta.get("sdk_version") or "")
    if versao and versao != importlib.metadata.version("gradio"):
        linhas.append(f"gradio=={versao}")  # o Space foi feito para essa versão do Gradio
    if (codigo / "packages.txt").exists():
        with esp.log.open("a") as log:
            log.write("[runner] aviso: packages.txt (apt) é ignorado.\n")

    if linhas:
        marca = hashlib.sha256("\n".join(linhas).encode()).hexdigest()
        arquivo_marca = esp.dir / ".requisitos"
        if not arquivo_marca.exists() or arquivo_marca.read_text() != marca:
            filtrado = esp.dir / "requisitos.filtrado.txt"
            filtrado.write_text("\n".join(linhas) + "\n")
            _definir(esp, "instalando", f"instalando {len(linhas)} pacotes (pip)")
            with esp.log.open("a") as log:
                esp.proc_aux = subprocess.Popen(
                    [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(filtrado)],
                    cwd=codigo, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    codigo_saida = esp.proc_aux.wait(timeout=TIMEOUT_PIP)
                except subprocess.TimeoutExpired:
                    _matar(esp.proc_aux)
                    raise ErroRunner("A instalação dos pacotes passou do tempo limite.")
            _checar(esp)
            if codigo_saida != 0:
                raise ErroRunner("A instalação dos pacotes falhou:\n" + ultimas_linhas(esp.log, 8))
            arquivo_marca.write_text(marca)
    return python, entrada


def _ligar_ao_pai(python: Path):
    """Se o executor roda dentro de um venv, o venv do Space não enxerga os pacotes dele (só os do Python base).
    Um arquivo .pth acrescenta os pacotes do pai ao FIM do caminho: o que o Space instalar tem prioridade."""
    import site

    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        return
    pais = [p for p in site.getsitepackages() if Path(p).is_dir()]
    destino = subprocess.run([str(python), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                             capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    (Path(destino) / "_executor_pai.pth").write_text("\n".join(pais) + "\n")


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _subir(esp: Espaco, codigo: Path, python: Path, entrada: str):
    from gradio_client import Client

    esp.porta = _porta_livre()
    tipo, nome = validar_id(esp.id)
    ambiente = dict(os.environ)
    ambiente.update({
        "GRADIO_SERVER_NAME": "127.0.0.1", "GRADIO_SERVER_PORT": str(esp.porta),
        "GRADIO_ANALYTICS_ENABLED": "False", "PYTHONUNBUFFERED": "1", "SYSTEM": "spaces",
        "SPACE_ID": nome, "GRADIO_TEMP_DIR": str(esp.dir / "tmp"),
        "PYTHONPATH": os.pathsep.join([str(SHIM), str(codigo)] + ([ambiente["PYTHONPATH"]] if ambiente.get("PYTHONPATH") else [])),
    })
    ambiente.pop("SPACES_ZERO_GPU", None)
    _definir(esp, "iniciando", "iniciando o app (baixa os modelos na primeira vez; pode demorar)")
    with esp.log.open("a") as log:
        esp.proc = subprocess.Popen([str(python), entrada], cwd=codigo, env=ambiente, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
    fim = time.time() + TIMEOUT_INICIO
    while time.time() < fim:
        _checar(esp)
        if esp.proc.poll() is not None:
            raise ErroRunner("O Space encerrou ao iniciar:\n" + ultimas_linhas(esp.log, 10))
        try:
            esp.cliente = Client(f"http://127.0.0.1:{esp.porta}", verbose=False,
                                 download_files=str(esp.dir / "saidas"))
            break
        except Exception:  # noqa: BLE001  (o servidor ainda não abriu)
            time.sleep(3)
    else:
        raise ErroRunner("O Space não ficou pronto a tempo.")
    esp.api = esp.cliente.view_api(return_format="dict", print_info=False)
    _definir(esp, "pronto", f"{len(esp.api.get('named_endpoints', {}))} endpoints disponíveis")


# ---------- API ----------
def apis_simples(esp: Espaco) -> list[dict]:
    """Resumo dos endpoints do Space, na forma que o site usa para montar o formulário."""
    saida = []
    for nome, ep in (esp.api or {}).get("named_endpoints", {}).items():
        parametros = []
        for p in ep.get("parameters", []):
            tipo = p.get("type") or {}
            descricao = str(tipo.get("description", ""))
            faixa = re.search(r"between ([-\d.]+) and ([-\d.]+)", descricao)
            parametros.append({
                "nome": p.get("parameter_name"), "rotulo": p.get("label") or p.get("parameter_name"),
                "componente": p.get("component"), "tipo": (p.get("python_type") or {}).get("type", ""),
                "obrigatorio": not p.get("parameter_has_default", False), "padrao": p.get("parameter_default"),
                "opcoes": tipo.get("enum"), "minimo": float(faixa.group(1)) if faixa else None,
                "maximo": float(faixa.group(2)) if faixa else None, "arquivo": _eh_arquivo(p),
            })
        saida.append({"api_name": nome, "parametros": parametros,
                      "retornos": [{"rotulo": r.get("label"), "componente": r.get("component")}
                                   for r in ep.get("returns", [])]})
    return saida


def _eh_arquivo(parametro: dict) -> bool:
    return (parametro.get("component") in COMPONENTES_ARQUIVO
            or (parametro.get("python_type") or {}).get("type") in ("filepath", "List[filepath]")
            or "FileData" in json.dumps(parametro.get("type") or {})[:3000])


def _como_arquivo(valor, enviados: list[str]):
    from gradio_client import handle_file

    if isinstance(valor, str):
        m = re.fullmatch(r"@arquivo:(\d+)", valor)
        if m:
            indice = int(m.group(1))
            if indice >= len(enviados):
                raise ErroRunner(f"O argumento cita o arquivo {indice}, mas só {len(enviados)} foram enviados.")
            return handle_file(enviados[indice])
        if valor.startswith(("http://", "https://")):
            return handle_file(valor)
        return valor
    if isinstance(valor, dict) and (valor.get("url") or valor.get("path")):
        return handle_file(valor.get("url") or valor["path"])
    if isinstance(valor, list):
        return [_como_arquivo(v, enviados) for v in valor]
    return valor


def chamar(alvo: str, api_name: str, entradas, enviados: list[str]):
    """Chama um endpoint do Space. `entradas` é uma lista (posicional) ou um dict (por nome do parâmetro)."""
    esp = obter(alvo)
    if esp is None:
        raise ErroRunner("Esse Space ainda não foi carregado. Use /carregar primeiro.")
    if esp.estado != "pronto" or esp.proc is None or esp.proc.poll() is not None:
        raise ErroRunner(f"O Space está '{esp.estado}'. {esp.mensagem}")
    api_name = api_name if api_name.startswith("/") else "/" + api_name
    endpoint = esp.api["named_endpoints"].get(api_name)
    if endpoint is None:
        raise ErroRunner(f"O Space não tem o endpoint {api_name}. Disponíveis: {', '.join(esp.api['named_endpoints'])}")
    parametros = endpoint["parameters"]
    esp.ultimo_uso = time.time()

    if isinstance(entradas, dict):
        por_nome = {p["parameter_name"]: p for p in parametros}
        desconhecidos = set(entradas) - set(por_nome)
        if desconhecidos:
            raise ErroRunner(f"Parâmetros desconhecidos: {', '.join(sorted(desconhecidos))}")
        argumentos = {k: (_como_arquivo(v, enviados) if _eh_arquivo(por_nome[k]) else v) for k, v in entradas.items()}
        for p in parametros:  # o que ficou de fora: usa o padrão do Space; sem padrão, vai vazio (null)
            if p["parameter_name"] not in argumentos and not p.get("parameter_has_default"):
                argumentos[p["parameter_name"]] = None
        resultado = esp.cliente.predict(api_name=api_name, **argumentos)
    elif isinstance(entradas, list):
        if len(entradas) > len(parametros):
            raise ErroRunner(f"{api_name} aceita {len(parametros)} parâmetros e recebeu {len(entradas)}.")
        argumentos = [_como_arquivo(v, enviados) if _eh_arquivo(p) else v for v, p in zip(entradas, parametros)]
        for p in parametros[len(argumentos):]:  # parâmetros finais omitidos: padrão do Space ou vazio
            argumentos.append(p.get("parameter_default") if p.get("parameter_has_default") else None)
        resultado = esp.cliente.predict(*argumentos, api_name=api_name)
    else:
        raise ErroRunner("Os argumentos devem ser uma lista ou um objeto JSON.")
    esp.ultimo_uso = time.time()
    return normalizar(resultado, esp)


def normalizar(valor, esp: Espaco | None, arquivos: list[str] | None = None):
    """Troca os caminhos de arquivos gerados por {"__arquivo__": i} e junta os arquivos numa lista."""
    arquivos = [] if arquivos is None else arquivos

    def volta(v):
        if isinstance(v, (list, tuple)):
            return [volta(x) for x in v]
        if isinstance(v, dict):
            return {k: volta(x) for k, x in v.items()}
        if isinstance(v, str):
            if len(v) < 4096 and os.path.isfile(v) and (esp is None or esp.dir in Path(v).resolve().parents):
                arquivos.append(v)
                return {"__arquivo__": len(arquivos) - 1}
            return v
        if v is None or isinstance(v, (bool, int, float)):
            return v
        return str(v)

    return volta(valor), arquivos


_CODIGO_GPU = ("import json,torch;d=torch.cuda.is_available();"
               "print(json.dumps({'cuda':d,'nome':torch.cuda.get_device_name(0) if d else None,'torch':torch.__version__}))")


def diagnostico_gpu() -> dict:
    """A GPU como um processo FILHO a enxerga. É assim que os Spaces rodam aqui: se o xGPU só liga a GPU dentro do
    processo principal, o resultado é cuda=false e os Spaces ficariam na CPU."""
    try:
        r = subprocess.run([sys.executable, "-c", _CODIGO_GPU], capture_output=True, text=True, timeout=180)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as erro:  # noqa: BLE001
        return {"erro": str(erro)[:300]}


def limpar_antigos(idade: int = 7200) -> int:
    """Apaga saídas e caches com mais de `idade` segundos (o disco do Studio é pequeno). Devolve quantos arquivos saíram."""
    limite = time.time() - idade
    pastas = [DADOS / "saidas", *(DADOS / "espacos").glob("*/saidas"), *(DADOS / "espacos").glob("*/tmp")]
    apagados = 0
    for pasta in pastas:
        for arquivo in pasta.rglob("*"):
            try:
                if arquivo.is_file() and arquivo.stat().st_mtime < limite:
                    arquivo.unlink()
                    apagados += 1
            except OSError:
                pass
    return apagados


def iniciar_limpeza(idade: int = 7200, intervalo: int = 600):
    def laco():
        while True:
            time.sleep(intervalo)
            limpar_antigos(idade)

    threading.Thread(target=laco, daemon=True, name="limpeza").start()


def estado_geral() -> list[dict]:
    with TRAVA:
        return [e.resumo() for e in REGISTRO.values()]
