"""
automacao/aprendizado_programa.py
=====================================
"Observa como eu uso um programa e aprende a utilizá-lo": tira
capturas periódicas (janela em foco + texto visível via OCR, ver
visao/observe.py) enquanto você usa um programa, e ao final pede pra
IA resumir o que viu num "como usar" -- salvo na base de conhecimento
orgânico (core/knowledge.py) pra você poder perguntar "como eu uso o
X" depois.

Isto NÃO é automação/replay -- Ultron não aprende a clicar sozinho nos
mesmos lugares (seria muito mais frágil e arriscado); ele aprende a
DESCREVER o fluxo que observou, como escrever um tutorial de leitura.

Teto de MAX_CAPTURAS (~20 minutos a 15s por captura) pra não ficar
observando pra sempre se o usuário esquecer de dizer "para".
"""

from datetime import datetime

from automacao import tasks
from core.timeline import registrar
from logs.logger import get_logger
from visao.observe import describe_activity

log = get_logger("automacao")

_INTERVALO_CAPTURA = 15  # segundos
_MAX_CAPTURAS = 80

_sessoes = {}  # nome_programa -> lista de capturas


def _routine_name(nome_programa: str) -> str:
    return f"aprendizado_programa_{nome_programa}"


def iniciar_observacao(nome_programa: str) -> None:
    chave = nome_programa.strip().lower()
    _sessoes[chave] = []
    routine_name = _routine_name(chave)

    def _tick():
        capturas = _sessoes.get(chave)
        if capturas is None:
            return
        info = describe_activity()
        capturas.append({
            "quando": datetime.now().isoformat(),
            "janela": info.get("janela"),
            "processo": info.get("processo"),
            "texto_tela": info.get("texto_tela"),
        })
        if len(capturas) >= _MAX_CAPTURAS:
            tasks.cancel_routine(routine_name)

    tasks.schedule_recurring(routine_name, _INTERVALO_CAPTURA, _tick)


def em_observacao(nome_programa: str) -> bool:
    return nome_programa.strip().lower() in _sessoes


def parar_e_aprender(nome_programa: str, ia_manager, knowledge, user_id: str) -> str:
    chave = nome_programa.strip().lower()
    tasks.cancel_routine(_routine_name(chave))
    capturas = _sessoes.pop(chave, [])
    if not capturas:
        return f'Não tenho nenhuma observação de "{nome_programa}" pra aprender ainda.'

    if ia_manager is None:
        return (
            f'Observei {len(capturas)} momento(s) usando "{nome_programa}", mas preciso de um '
            "provedor de IA configurado pra resumir isso num tutorial (veja /configurarapi)."
        )

    linhas = []
    for c in capturas:
        pedaco = f"- Janela: {c['janela'] or '?'}"
        if c.get("texto_tela"):
            pedaco += f" | Texto na tela: {c['texto_tela'][:200]}"
        linhas.append(pedaco)
    resumo_bruto = "\n".join(linhas)

    prompt = (
        f'Estas são capturas periódicas (janela em foco + texto visível na tela) enquanto o '
        f'usuário usava o programa "{nome_programa}":\n\n{resumo_bruto}\n\n'
        "Com base nisso, escreva um resumo curto (\"como usar esse programa\") descrevendo o "
        "fluxo/passos que parecem ter sido seguidos. Se não der pra inferir nada útil, diga "
        "isso honestamente em vez de inventar."
    )
    try:
        _, tutorial = ia_manager.chat(prompt, history=[], max_tokens=500)
    except Exception as e:
        return f"Observei {len(capturas)} momento(s), mas falhei ao gerar o resumo: {e}"

    if not tutorial:
        return "Não consegui gerar um resumo útil dessa observação."

    knowledge.learn(
        user_id, f'Como usar "{nome_programa}": {tutorial}',
        source="observacao_de_uso", category="concept",
    )
    registrar("programa_aprendido", nome_programa)
    return (
        f'Aprendi um pouco sobre como usar "{nome_programa}" observando você. Salvei na minha '
        f'base de conhecimento -- pergunte "o que você aprendeu sobre {nome_programa}" quando quiser ver.'
    )
