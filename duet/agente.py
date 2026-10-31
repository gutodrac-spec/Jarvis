"""O cérebro do Duet: conversa com a Claude API e usa as integrações como ferramentas."""
import datetime as dt
import json
import os
import pathlib

import anthropic

import integracoes as integ

# Estado fica no disco do Codespace (persiste quando ele é desligado).
# NÃO fica no Git: o repositório é público e o histórico pode ter e-mails seus.
PASTA_ESTADO = pathlib.Path(os.getenv("DUET_ESTADO", pathlib.Path.home() / ".duet"))
ARQ_HISTORICO = PASTA_ESTADO / "historico.json"
ARQ_MEMORIA = PASTA_ESTADO / "memoria.md"
MAX_TURNOS_HISTORICO = 40

MODELO_CHAT = os.getenv("DUET_MODELO", "claude-sonnet-5-5")
MODELO_VERIFICACAO = os.getenv("DUET_MODELO_VERIFICACAO", "claude-haiku-5-5")

FUSO = dt.timezone(dt.timedelta(hours=-3))  # America/Sao_Paulo

SISTEMA = """Você é o Duet, assistente proativo do Gustavo, conversando pelo Telegram.
Responda em português do Brasil, de forma curta e direta (é uma tela de celular).
Use as ferramentas para consultar e-mail, Google Drive, GitHub e Vercel antes de responder
sobre eles; nunca invente dados.
Você só tem acesso de LEITURA. Para qualquer ação (responder e-mail, mexer em deploy,
apagar algo, pagar algo), prepare o rascunho e peça a confirmação do Gustavo; explique
o que ele mesmo precisa fazer se você não tiver como executar.
Quando o Gustavo pedir para lembrar algo, use a ferramenta `lembrar`.
Agora: {agora} (horário de Brasília). Integrações ativas: {ativas}.

Memória salva:
{memoria}"""


# ------------------------------------------------------------------ estado
def _garantir_pasta():
    PASTA_ESTADO.mkdir(parents=True, exist_ok=True)


def carregar_historico():
    try:
        return json.loads(ARQ_HISTORICO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def salvar_historico(historico):
    _garantir_pasta()
    historico = historico[-MAX_TURNOS_HISTORICO:]
    # o histórico precisa começar por uma mensagem do usuário
    while historico and historico[0]["role"] != "user":
        historico = historico[1:]
    ARQ_HISTORICO.write_text(json.dumps(historico, ensure_ascii=False, indent=1), encoding="utf-8")


def ler_memoria():
    try:
        return ARQ_MEMORIA.read_text(encoding="utf-8").strip() or "(vazia)"
    except FileNotFoundError:
        return "(vazia)"


def lembrar(nota):
    _garantir_pasta()
    with ARQ_MEMORIA.open("a", encoding="utf-8") as f:
        f.write(f"- {nota.strip()}\n")
    return "ok, anotado"


def esquecer_tudo():
    for arq in (ARQ_HISTORICO, ARQ_MEMORIA):
        arq.unlink(missing_ok=True)


# ------------------------------------------------------------- ferramentas
def _ferramenta(nome, descricao, propriedades=None, obrigatorias=None):
    return {
        "name": nome,
        "description": descricao,
        "input_schema": {
            "type": "object",
            "properties": propriedades or {},
            "required": obrigatorias or [],
        },
    }


def definir_ferramentas():
    ativas = integ.integracoes_ativas()
    defs, funcs = [], {}

    defs.append(_ferramenta(
        "lembrar", "Salva uma nota permanente na memória do Duet.",
        {"nota": {"type": "string"}}, ["nota"]))
    funcs["lembrar"] = lambda a: lembrar(a["nota"])

    if ativas["github"]:
        defs.append(_ferramenta(
            "github_notificacoes", "Notificações do GitHub (PRs, issues, menções).",
            {"desde_horas": {"type": "integer", "default": 24}}))
        funcs["github_notificacoes"] = lambda a: integ.github_notificacoes(a.get("desde_horas", 24))
        defs.append(_ferramenta(
            "github_repos_recentes", "Repositórios do Gustavo com push mais recente."))
        funcs["github_repos_recentes"] = lambda a: integ.github_repos_recentes()
        defs.append(_ferramenta(
            "github_issues_abertas", "Issues e PRs abertos de um repositório (dono/nome).",
            {"repo": {"type": "string"}}, ["repo"]))
        funcs["github_issues_abertas"] = lambda a: integ.github_issues_abertas(a["repo"])

    if ativas["vercel"]:
        defs.append(_ferramenta(
            "vercel_deploys", "Últimos deploys da Vercel com estado (READY, ERROR, BUILDING...).",
            {"limite": {"type": "integer", "default": 10}}))
        funcs["vercel_deploys"] = lambda a: integ.vercel_deploys(a.get("limite", 10))

    if ativas["gmail"]:
        defs.append(_ferramenta(
            "gmail_buscar", "Busca e-mails com a sintaxe de busca do Gmail. "
            "Ex.: 'is:unread newer_than:1d', 'from:banco subject:boleto'.",
            {"consulta": {"type": "string"}, "limite": {"type": "integer", "default": 15}},
            ["consulta"]))
        funcs["gmail_buscar"] = lambda a: integ.gmail_buscar(a["consulta"], a.get("limite", 15))
        defs.append(_ferramenta(
            "gmail_ler", "Lê o conteúdo completo de um e-mail pelo id.",
            {"id": {"type": "string"}}, ["id"]))
        funcs["gmail_ler"] = lambda a: integ.gmail_ler(a["id"])

    if ativas["drive"]:
        defs.append(_ferramenta(
            "drive_recentes", "Arquivos do Google Drive modificados recentemente.",
            {"desde_horas": {"type": "integer", "default": 24}}))
        funcs["drive_recentes"] = lambda a: integ.drive_recentes(a.get("desde_horas", 24))

    return defs, funcs


def _executar(funcs, nome, entrada):
    try:
        resultado = funcs[nome](entrada or {})
        texto = json.dumps(resultado, ensure_ascii=False, default=str)
        return texto[:20000], False
    except Exception as e:  # erro vira texto para o modelo explicar ao usuário
        return f"Erro ao executar {nome}: {e}", True


# ------------------------------------------------------------------- laço
def _sistema():
    ativas = [k for k, v in integ.integracoes_ativas().items() if v] or ["nenhuma"]
    return SISTEMA.format(
        agora=dt.datetime.now(FUSO).strftime("%d/%m/%Y %H:%M"),
        ativas=", ".join(ativas),
        memoria=ler_memoria(),
    )


def rodar(mensagens, modelo=MODELO_CHAT, max_passos=8, cliente=None):
    """Roda o laço de ferramentas e devolve o texto final."""
    cliente = cliente or anthropic.Anthropic()
    defs, funcs = definir_ferramentas()
    msgs = list(mensagens)
    for _ in range(max_passos):
        resp = cliente.messages.create(
            model=modelo, max_tokens=2000, system=_sistema(), tools=defs, messages=msgs
        )
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        msgs.append({"role": "assistant", "content": resp.content})
        resultados = []
        for bloco in resp.content:
            if bloco.type == "tool_use":
                texto, erro = _executar(funcs, bloco.name, bloco.input)
                resultados.append({
                    "type": "tool_result", "tool_use_id": bloco.id,
                    "content": texto, "is_error": erro,
                })
        msgs.append({"role": "user", "content": resultados})
    return "Parei porque a tarefa ficou longa demais. Pode detalhar o que precisa?"


def conversar(texto_usuario, cliente=None):
    """Uma mensagem do Gustavo -> resposta, mantendo o histórico."""
    historico = carregar_historico()
    historico.append({"role": "user", "content": texto_usuario})
    resposta = rodar(historico, cliente=cliente) or "(sem resposta)"
    historico.append({"role": "assistant", "content": resposta})
    salvar_historico(historico)
    return resposta


PEDIDO_VERIFICACAO = """Verificação automática de {janela} minutos.
Consulte as integrações ativas olhando só o que aconteceu nos últimos {janela} minutos
(e-mails não lidos, arquivos do Drive alterados, notificações do GitHub, deploys com erro).
Se houver algo que realmente precise da atenção do Gustavo, escreva um aviso curto com
o que é e o próximo passo sugerido.
Se não houver nada importante, responda exatamente: NADA"""


def verificar(janela_minutos=65, cliente=None):
    """Checagem proativa. Devolve o aviso, ou None se não há nada importante."""
    texto = rodar(
        [{"role": "user", "content": PEDIDO_VERIFICACAO.format(janela=janela_minutos)}],
        modelo=MODELO_VERIFICACAO,
        cliente=cliente,
    )
    if not texto or texto.strip().upper().startswith("NADA"):
        return None
    return texto
