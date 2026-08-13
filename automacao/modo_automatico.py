"""
automacao/modo_automatico.py
================================
"Modo automático": em vez de dar um comando de cada vez, você diz um
OBJETIVO ("ativa auto: abre o spotify e toca lofi, depois diminui o
volume") e o Ultron quebra isso numa sequência de comandos que ELE JÁ
SABE EXECUTAR (a mesma lista de plugins/comandos disponível pro chat
normal) e executa cada um, em ordem, sozinho -- sem perguntar passo a
passo.

Diferença honesta em relação a automacao/intencoes.py: intencoes.py
PLANEJA e quem executa depois é você (ou um comando específico); aqui o
Ultron EXECUTA de verdade, mas só dentro do que ele já sabe fazer com
segurança -- cada passo passa pelo MESMO PluginManager.dispatch() do
chat normal, então:
  - Ações destrutivas/irreversíveis continuam exigindo confirmação
    (seguranca/permissions.py) -- o modo automático NÃO contorna isso;
    se um passo esbarrar nisso, a sequência PARA ali e avisa, em vez de
    confirmar sozinho por você.
  - Se a IA sugerir um passo que nenhum plugin reconhece, a sequência
    PARA nesse passo e reporta "não executado" -- nunca inventa uma
    ação que não existe de verdade.
  - Teto de MAX_PASSOS evita uma sequência gigante/fora de controle.
  - Se o objetivo pedir algo claramente destrutivo/fora do que Ultron
    pode fazer com segurança, a IA é instruída a recusar o PLANO
    INTEIRO (campo "recusa") em vez de arriscar um passo perigoso.

Isso NÃO é "controle irrestrito" -- é orquestração de vários comandos
JÁ seguros, decidida pela IA, dentro da MESMA política de permissões
que já vale pra qualquer comando manual.
"""

import json
import re

from core.confidence import Confidence
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

MAX_PASSOS = 8

_SYSTEM_PROMPT_PLANO = (
    "Você decompõe um OBJETIVO numa sequência curta de COMANDOS DE CHAT que um assistente "
    "chamado Ultron já sabe executar de verdade. Aqui está a lista de capacidades REAIS "
    "disponíveis (nome: descrição):\n{capacidades}\n\n"
    "Responda APENAS com um JSON (sem markdown, sem texto fora do JSON) neste formato:\n"
    '{{"passos": ["comando 1", "comando 2", "..."], "recusa": null}}\n\n'
    "Regras estritas:\n"
    f"- No máximo {MAX_PASSOS} passos.\n"
    "- Cada passo deve ser uma frase de comando em português que uma dessas capacidades "
    'reconheceria de verdade (ex.: "abre o spotify", "diminui o volume", "tira um '
    'screenshot") -- NUNCA invente um comando fora dessas capacidades.\n'
    "- Se o objetivo pedir algo destrutivo/irreversível (apagar, formatar, desinstalar, "
    "fechar programas sem salvar) ou algo que claramente não está nessas capacidades, "
    'responda com "passos": [] e preencha "recusa" com um motivo curto -- nunca arrisque '
    "um passo perigoso ou inventado só pra ter algo pra fazer."
)


def _extrair_plano_json(resposta: str) -> dict:
    texto = (resposta or "").strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", texto, re.DOTALL)
    if m:
        texto = m.group(1).strip()
    try:
        dados = json.loads(texto)
    except Exception:
        return {"passos": [], "recusa": None}
    if not isinstance(dados, dict):
        return {"passos": [], "recusa": None}
    passos = dados.get("passos") or []
    recusa = dados.get("recusa")
    if not isinstance(passos, list):
        passos = []
    return {
        "passos": [str(p).strip() for p in passos if str(p).strip()][:MAX_PASSOS],
        "recusa": str(recusa).strip() if recusa else None,
    }


def planejar(jarvis, objetivo: str) -> dict:
    """Usa a IA pra decompor `objetivo` numa lista de comandos que o
    Ultron já sabe executar. Retorna {"passos": [...], "recusa": str|None}
    -- "recusa" preenchido (e passos vazio) quando a IA julgou o pedido
    destrutivo/impossível/fora das capacidades reais."""
    if jarvis.ia_manager is None:
        return {"passos": [], "recusa": "IA não está disponível pra planejar o modo automático."}
    capacidades = "\n".join(f"- {n}: {d}" for n, d in jarvis.plugins.list_plugins())
    system_prompt = _SYSTEM_PROMPT_PLANO.format(capacidades=capacidades)
    try:
        _, resposta = jarvis.ia_manager.chat(
            f"Objetivo: {objetivo}", history=[], system_prompt=system_prompt, max_tokens=500,
        )
    except Exception as e:
        log.warning("modo_automatico: falha ao planejar '%s': %s", objetivo, e)
        return {"passos": [], "recusa": "não consegui planejar (falha ao consultar a IA)."}
    plano = _extrair_plano_json(resposta)
    if not plano["passos"] and not plano["recusa"]:
        plano["recusa"] = "não consegui gerar um plano válido pra esse objetivo."
    return plano


def executar(jarvis, objetivo: str, context: dict) -> dict:
    """Planeja E executa um objetivo, passo a passo, através do MESMO
    PluginManager.dispatch() do chat normal -- nenhum atalho/bypass de
    segurança. Retorna um relatório:
        {"objetivo", "recusa", "passos": [{"comando", "executado", "resposta"}]}
    Para na primeira falha (passo não reconhecido, bloqueado por exigir
    confirmação, ou erro) -- não empurra o resto do plano depois de um
    passo que não deu certo."""
    objetivo = objetivo.strip()
    plano = planejar(jarvis, objetivo)
    relatorio = {"objetivo": objetivo, "recusa": plano.get("recusa"), "passos": []}
    if relatorio["recusa"] or not plano["passos"]:
        registrar("modo_automatico_recusado", f"{objetivo[:100]} -- {relatorio['recusa']}")
        return relatorio

    for comando in plano["passos"]:
        # Nunca deixa um passo re-entrar no próprio modo automático --
        # evita recursão/loop (mesmo tipo de guarda que macros.py já usa
        # pra não deixar uma macro chamar a si mesma).
        if re.search(r"\bativa\s+auto\b|\bmodo\s+autom[áa]tico\b", comando, re.IGNORECASE):
            relatorio["passos"].append({
                "comando": comando, "executado": False,
                "resposta": "passo recusado (chamaria o modo automático de novo -- não permitido)",
            })
            break
        try:
            _, answer = jarvis.plugins.dispatch(comando, context)
        except Exception as e:
            relatorio["passos"].append({"comando": comando, "executado": False, "resposta": f"erro: {e}"})
            break
        if answer is None:
            relatorio["passos"].append({
                "comando": comando, "executado": False,
                "resposta": "nenhum comando reconhecido pra isso -- parei aqui.",
            })
            break
        # Confiança GUESS geralmente significa "não fiz o que foi pedido de
        # verdade" (pergunta de esclarecimento, ação bloqueada por exigir
        # confirmação, recusa) -- ver seguranca/permissions.py: um passo
        # destrutivo sem a palavra "confirmo" no texto cai exatamente
        # nesse caso. Trata como PAROU em vez de "executado com sucesso",
        # em vez de assumir otimisticamente que qualquer resposta não-nula
        # significa que a ação realmente aconteceu.
        if answer.confidence <= Confidence.GUESS:
            relatorio["passos"].append({"comando": comando, "executado": False, "resposta": answer.text})
            break
        relatorio["passos"].append({"comando": comando, "executado": True, "resposta": answer.text})

    feitos = sum(1 for p in relatorio["passos"] if p["executado"])
    registrar("modo_automatico_executado", f"{objetivo[:100]} ({feitos}/{len(plano['passos'])} passos)")
    return relatorio
