"""
core/intencao.py
===================
Classificação interna e silenciosa de intenção -- "isso tem mais cara
de pergunta/conversa, ou de comando?" -- usada só para ORIENTAR
core/jarvis.py:process(), NUNCA aparece na resposta que o usuário vê
(nem como texto, nem como debug). Não é IA nem machine learning: é
heurística determinística (marcadores de pergunta + lista de verbos de
ação), rápida e fácil de auditar/ajustar.

Por que existe: o modo de comando direto ("/", ver core/jarvis.py)
resolve o problema de "o comando caiu na IA em vez de executar" só
quando o usuário lembra de digitar a barra. Esta classificação estende
a mesma garantia pra frases naturais SEM a barra -- se o texto começa
com um verbo de ação inequívoco (ex.: "abre", "fecha", "muta") e NENHUM
plugin soube executar, o Ultron avisa que não conhece o comando em vez
de deixar a conversa/IA inventarem uma resposta em texto que parece ter
feito algo, mas não executou nada de verdade.

Design deliberadamente conservador: a lista de verbos só inclui casos
INEQUÍVOCOS de comando de sistema (abrir/fechar programa, mutar,
minimizar janela, instalar, conectar, etc.) -- verbos ambíguos que
também são pedidos criativos/informacionais comuns (ex.: "cria"/"faz"
podem significar "cria uma história"/"faz um resumo", que devem ir
pra IA normalmente) ficam de FORA de propósito. Um falso negativo aqui
(um comando real que não foi reconhecido como tal) só mantém o
comportamento de hoje, sem regressão -- um falso positivo (bloquear um
pedido criativo/de conversa legítimo) seria uma regressão de verdade,
então o critério é sempre pecar por cautela.
"""

import re

_MARCADORES_PERGUNTA = (
    "o que é", "o que e ", "o que são", "o que sao",
    "quem foi", "quem é", "quem e ", "quem são", "quem sao",
    "qual é", "qual e ", "qual o", "qual a", "quais são", "quais sao",
    "como funciona", "como funcionam", "por que", "porque",
    "quando foi", "quando ocorreu", "onde fica", "onde está", "onde esta",
    "explique", "defina", "definição de", "definicao de",
    "você sabe", "voce sabe", "me diga", "me fale", "me explica",
)

# Só verbos de ação de sistema, SEM uso criativo/informacional comum --
# ver docstring do módulo pro porquê de "cria"/"faz"/"escreve"/"mostra"
# ficarem de fora mesmo sendo verbos de comando em outros contextos.
_VERBOS_COMANDO_RE = re.compile(
    r"^\s*(abr[ae]|abrir|fech[ae]|fechar|mat[ae]|matar|encerr[ae]|encerrar|"
    r"lig[ae]|ligar|deslig[ae]|desligar|mut[ae]|desmut[ae]|"
    r"minimiz[ae]|maximiz[ae]|restaur[ae]|foc[ae]|"
    r"instal[ae]|instalar|conect[ae]|desconect[ae]|"
    r"agend[ae]|agendar|rod[ae]|execut[ae])\w*\b",
    re.IGNORECASE,
)


def classificar(texto: str) -> str:
    """Retorna "pergunta", "comando" ou "conversa". Marcadores de
    pergunta têm prioridade sobre verbo de comando -- "como eu abro um
    arquivo zip" começa com um verbo de comando (abro), mas "como"
    logo no início já entrega que é uma pergunta sobre o assunto, não
    uma ordem pra executar algo agora."""
    t = texto.strip().lower()
    if not t:
        return "conversa"
    if t.endswith("?") or any(m in t for m in _MARCADORES_PERGUNTA):
        return "pergunta"
    if _VERBOS_COMANDO_RE.match(t):
        return "comando"
    return "conversa"
