"""
sistema/observador_internet.py
==================================
"Observador da Internet": acompanha novas versões de bibliotecas/
frameworks relevantes aos SEUS projetos, e resume só o que é novo desde
a última checagem -- em vez de te fazer procurar changelog por
changelog.

O que conta como "relevante aos seus projetos" (honesto, nada arbitrário):
1. As dependências REAIS do próprio Ultron (requirements*.txt na raiz
   do projeto) -- são bibliotecas que você genuinamente usa agora.
2. Os "projetos" que você registrou na memória categorizada (ver
   plugins/categorized_memory.py) -- best-effort: cada um é testado
   contra o PyPI, e o que não existir como pacote é simplesmente
   ignorado (nenhum erro, nenhuma alucinação de projeto inexistente).

Fonte: API pública do PyPI (https://pypi.org/pypi/<pacote>/json), sem
chave de API. Nunca instala nada sozinho -- só CONSULTA a versão mais
recente publicada e compara com a última que já foi vista.

Evita ruído de duas formas:
- Só reporta como "novidade" uma versão DIFERENTE da última vista.
- Na PRIMEIRA vez que um pacote é checado (sem histórico ainda), só
  conta como novidade se o lançamento foi HÁ POUCO TEMPO (30 dias) --
  senão a primeira rodada "descobriria" a stack inteira de uma vez,
  a maioria delas sem nada de novo de verdade.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta

from core.database import get_database
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("sistema")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sistema_pacotes_observados (
    pacote TEXT PRIMARY KEY,
    ultima_versao_vista TEXT,
    verificado_em TEXT
);
"""

_PYPI_JSON = "https://pypi.org/pypi/{pacote}/json"
_TIMEOUT_SEGUNDOS = 6
_DIAS_RECENTE = 30
_MAX_PACOTES_POR_RODADA = 40  # teto -- não fica minutos checando uma lista gigante


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def _pacotes_do_projeto() -> set:
    """Extrai nomes de pacotes dos requirements*.txt na raiz do Ultron."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pacotes = set()
    try:
        arquivos = os.listdir(base)
    except Exception:
        return pacotes
    for nome_arquivo in arquivos:
        if not nome_arquivo.startswith("requirements") or not nome_arquivo.endswith(".txt"):
            continue
        caminho = os.path.join(base, nome_arquivo)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    # Ignora vazias, comentários, e diretivas do pip
                    # (-r outro.txt, -e ., --find-links ...) -- achado
                    # real: "-r" estava sendo extraído como se fosse
                    # nome de pacote, gerando uma consulta inútil (e
                    # sempre "não encontrado") no PyPI a cada rodada.
                    if not linha or linha.startswith("#") or linha.startswith("-"):
                        continue
                    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)", linha)
                    if m:
                        pacotes.add(m.group(1).lower())
        except Exception:
            continue
    return pacotes


def _projetos_do_usuario(jarvis) -> set:
    """Nomes de 'projeto' registrados na memória categorizada --
    best-effort: a maioria não vai existir no PyPI, e isso é esperado
    (são projetos do usuário, não necessariamente pacotes Python)."""
    try:
        itens = jarvis.memory.list_memory(jarvis.user_id, category="project", limit=20)
    except Exception:
        return set()
    nomes = set()
    for i in itens:
        conteudo = (i.get("content") or "").strip()
        if not conteudo:
            continue
        primeira_palavra = re.split(r"[\s:]", conteudo)[0]
        limpo = re.sub(r"[^A-Za-z0-9_.-]", "", primeira_palavra).lower()
        if limpo:
            nomes.add(limpo)
    return nomes


def _consultar_pypi(pacote: str):
    """Retorna (versao_mais_recente, data_iso_do_upload) ou (None, None)
    se o pacote não existir/falhar -- nunca levanta."""
    try:
        req = urllib.request.Request(
            _PYPI_JSON.format(pacote=pacote),
            headers={"User-Agent": "Ultron/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEGUNDOS) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        versao = dados.get("info", {}).get("version")
        if not versao:
            return None, None
        releases = dados.get("releases", {}).get(versao) or []
        data_upload = releases[0]["upload_time"] if releases else None
        return versao, data_upload
    except Exception:
        return None, None


def _e_recente(data_iso: str) -> bool:
    if not data_iso:
        return False
    try:
        dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00")).replace(tzinfo=None)
        return (datetime.now() - dt) <= timedelta(days=_DIAS_RECENTE)
    except Exception:
        return False


def verificar_agora(jarvis) -> list:
    """Roda a checagem uma vez contra o PyPI. Retorna uma lista de
    {"pacote", "versao_antiga", "versao_nova"} só com o que É novidade
    de verdade (ver critérios no topo do arquivo) -- registra cada
    pacote checado pra não repetir aviso sobre a mesma versão depois."""
    _ensure_schema()
    pacotes = sorted(_pacotes_do_projeto() | _projetos_do_usuario(jarvis))[:_MAX_PACOTES_POR_RODADA]
    novidades = []
    agora_iso = datetime.now().isoformat()

    for pacote in pacotes:
        versao_nova, data_upload = _consultar_pypi(pacote)
        if not versao_nova:
            continue
        linha = get_database().query_one(
            "SELECT ultima_versao_vista FROM sistema_pacotes_observados WHERE pacote=?", (pacote,)
        )
        primeira_vez = linha is None
        versao_antiga = linha["ultima_versao_vista"] if linha else None
        mudou = versao_nova != versao_antiga

        if mudou and (not primeira_vez or _e_recente(data_upload)):
            novidades.append({
                "pacote": pacote, "versao_antiga": versao_antiga, "versao_nova": versao_nova,
            })

        get_database().execute(
            "INSERT INTO sistema_pacotes_observados (pacote, ultima_versao_vista, verificado_em) "
            "VALUES (?,?,?) ON CONFLICT(pacote) DO UPDATE SET "
            "ultima_versao_vista=excluded.ultima_versao_vista, verificado_em=excluded.verificado_em",
            (pacote, versao_nova, agora_iso),
        )

    if novidades:
        resumo_bruto = "; ".join(f"{n['pacote']} {n['versao_nova']}" for n in novidades[:10])
        registrar("observador_internet_novidades", resumo_bruto[:200])
    return novidades


def resumir(jarvis, novidades: list) -> str:
    """Texto pronto pra mostrar/notificar -- usa a IA (se disponível)
    pra dizer em 1-2 frases por item por que aquilo pode interessar,
    dado o contexto dos projetos do usuário; sem IA, cai numa lista
    simples de pacote+versão (sempre funciona, só menos explicativo)."""
    if not novidades:
        return "Nada de novo nas suas dependências desde a última checagem."

    linhas_simples = [
        f"- {n['pacote']}: {n['versao_antiga'] or '(nunca visto)'} -> {n['versao_nova']}"
        for n in novidades
    ]
    if jarvis.ia_manager is None:
        return "Novidades encontradas:\n" + "\n".join(linhas_simples)

    try:
        contexto = jarvis.memory.get_context_summary(jarvis.user_id)
        prompt = (
            "Aqui estão atualizações de bibliotecas/frameworks relevantes aos projetos do usuário:\n"
            + "\n".join(linhas_simples)
            + f"\n\nContexto do usuário:\n{contexto}\n\n"
            "Resuma em poucas frases, por item, só o que PODE interessar de verdade (nova feature "
            "relevante, correção importante, mudança que quebra compatibilidade) -- se não souber o "
            "motivo específico de uma atualização, diga só que houve atualização, sem inventar detalhes."
        )
        _, resposta = jarvis.ia_manager.chat(prompt, history=[], max_tokens=500)
        return resposta or ("Novidades encontradas:\n" + "\n".join(linhas_simples))
    except Exception as e:
        log.warning("observador_internet: falha ao resumir com IA (%s)", e)
        return "Novidades encontradas:\n" + "\n".join(linhas_simples)


def _tick(jarvis):
    try:
        novidades = verificar_agora(jarvis)
    except Exception as e:
        log.warning("observador_internet: falha no ciclo (%s)", e)
        return
    if not novidades:
        return
    # Atualizações comuns de dependências são manutenção interna e não
    # devem interromper a conversa. Continuam registradas no histórico
    # e aparecem quando o usuário pergunta explicitamente pelo plugin.
    if not jarvis.settings.get("sistema.observador_internet_notificar", False):
        log.info("observador_internet: %d novidade(s) registrada(s) silenciosamente", len(novidades))
        return
    from automacao.notify import notify
    notify(
        "Neutron encontrou atualizações (Observador da Internet)",
        resumir(jarvis, novidades),
    )


def iniciar(jarvis):
    """Agenda a checagem periódica. No-op se o módulo 'sistema' estiver
    desligado ou `sistema.observador_internet` for false. A consulta
    roda silenciosamente por padrão; notificações exigem
    `sistema.observador_internet_notificar=true`."""
    settings = jarvis.settings
    if not settings.is_module_enabled("sistema"):
        return
    if not settings.get("sistema.observador_internet", True):
        return
    try:
        horas = float(settings.get("sistema.observador_internet_intervalo_horas", 12))
    except (TypeError, ValueError):
        horas = 12
    intervalo = max(3600, horas * 3600)
    from automacao import tasks
    # Primeira checagem ~3 min depois de abrir -- rápido o bastante pra
    # ver funcionando numa sessão normal, sem atrapalhar o boot.
    tasks.schedule_recurring(
        "observador_internet", intervalo, _tick, jarvis, primeiro_delay_segundos=180
    )
