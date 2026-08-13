"""
core/consciencia_codigo.py
=============================
"Consciência de código": monta um mapa de dependências do PRÓPRIO
código do Ultron, analisando os imports de cada arquivo .py (via `ast`,
sem rodar nada). Responde perguntas como "o que depende do módulo X?"
e "o que quebra se eu mexer em Y?" -- útil pra entender o impacto de
uma mudança antes de fazer.

Honestidade sobre o escopo: é análise ESTÁTICA no nível de MÓDULO/IMPORT
(quem importa quem), não no nível de método/linha. "Esse método conversa
com esse método" exigiria montar um call graph completo (bem mais caro e
frágil); o nível de import já cobre 80% do "se eu apagar isso, o que
quebra" na prática, e é confiável (lê o código, não adivinha). Só
considera módulos INTERNOS do projeto -- imports de bibliotecas externas
(os, re, numpy...) são ignorados de propósito.
"""

import ast
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pastas de topo que são código INTERNO do Jarvis. Um import que começa
# com uma destas é uma dependência interna; qualquer outra coisa (os,
# re, numpy, requests...) é externa e ignorada.
_PACOTES_INTERNOS = {
    "core", "automacao", "plugins", "ia", "voz", "visao", "visao_continua",
    "controle_pc", "sistema", "dispositivos", "seguranca", "logs",
    "atualizacoes", "config", "linguagem", "investigador", "jogos",
}

_IGNORAR_DIRS = {"__pycache__", "venv", ".venv", ".git", "node_modules", "tools"}

_cache = None  # resultado da análise, calculado sob demanda e reusado


def _caminho_para_modulo(caminho: str) -> str:
    rel = os.path.relpath(caminho, BASE_DIR).replace(os.sep, ".")
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith(".__init__"):
        rel = rel[: -len(".__init__")]
    return rel


def _eh_interno(nome_modulo: str) -> bool:
    topo = nome_modulo.split(".", 1)[0]
    return topo in _PACOTES_INTERNOS


def _imports_do_arquivo(caminho: str) -> set:
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            arvore = ast.parse(f.read(), filename=caminho)
    except Exception:
        return set()
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                if _eh_interno(alias.name):
                    modulos.add(alias.name)
        elif isinstance(no, ast.ImportFrom):
            if no.module and no.level == 0 and _eh_interno(no.module):
                modulos.add(no.module)
                # "from automacao import tasks" registra module='automacao'
                # e name='tasks' -- ou seja, a dependência REAL é
                # automacao.tasks (um submódulo), não só 'automacao'.
                # Registra module.name também pra pegar esse caso (que é
                # o padrão dominante neste projeto). Se 'name' for uma
                # função/classe em vez de submódulo (ex.: core.confidence.Answer),
                # o nome extra simplesmente não bate com nenhum módulo
                # procurado -- sem dano.
                for alias in no.names:
                    if alias.name != "*":
                        modulos.add(f"{no.module}.{alias.name}")
    return modulos


def analisar_projeto(forcar: bool = False) -> dict:
    """{modulo: {"importa": set(modulos internos), "arquivo": caminho}}.
    Cacheado -- passe forcar=True pra reanalisar (ex.: depois de aprovar
    uma habilidade nova)."""
    global _cache
    if _cache is not None and not forcar:
        return _cache

    grafo = {}
    for raiz, dirs, arquivos in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in _IGNORAR_DIRS]
        for arq in arquivos:
            if not arq.endswith(".py"):
                continue
            caminho = os.path.join(raiz, arq)
            modulo = _caminho_para_modulo(caminho)
            if not _eh_interno(modulo):
                continue
            grafo[modulo] = {"importa": _imports_do_arquivo(caminho), "arquivo": caminho}
    _cache = grafo
    return grafo


def _casa(alvo: str, modulo: str) -> bool:
    """`alvo` bate com `modulo` se for igual, um prefixo de pacote
    (ex.: 'automacao' bate 'automacao.tasks'), ou o nome curto final
    (ex.: 'tasks' bate 'automacao.tasks')."""
    alvo = alvo.strip().strip(".").lower()
    m = modulo.lower()
    return m == alvo or m.startswith(alvo + ".") or m.split(".")[-1] == alvo


def dependentes_de(alvo: str) -> list:
    """Módulos que IMPORTAM `alvo` (direta ou por pacote) -- ou seja, o
    que pode QUEBRAR se você mexer/apagar `alvo`. Ordenado por nome."""
    grafo = analisar_projeto()
    resultado = []
    for modulo, info in grafo.items():
        if any(_casa(alvo, imp) for imp in info["importa"]):
            resultado.append(modulo)
    return sorted(resultado)


def dependencias_de(alvo: str) -> list:
    """Módulos internos que `alvo` importa (do que ele depende)."""
    grafo = analisar_projeto()
    alvos = [m for m in grafo if _casa(alvo, m)]
    deps = set()
    for m in alvos:
        deps.update(grafo[m]["importa"])
    return sorted(deps)


def resumo() -> dict:
    """Números gerais + os módulos mais "centrais" (mais importados por
    outros), que são os mais arriscados de mexer."""
    grafo = analisar_projeto()
    total_modulos = len(grafo)
    total_arestas = sum(len(info["importa"]) for info in grafo.values())

    contagem = {}
    for info in grafo.values():
        for imp in info["importa"]:
            # normaliza pro módulo real quando existir, senão usa o import cru
            chave = imp
            contagem[chave] = contagem.get(chave, 0) + 1
    mais_importados = sorted(contagem.items(), key=lambda kv: -kv[1])[:10]

    return {
        "total_modulos": total_modulos,
        "total_dependencias": total_arestas,
        "mais_importados": mais_importados,
    }
