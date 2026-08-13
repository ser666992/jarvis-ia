"""
jogos/armazenamento.py
=========================
Caminhos de arquivo compartilhados por gravador.py/treino.py/jogador.py
-- módulo folha (não importa nada do resto de jogos/) de propósito,
pra `jogos/__init__.py` poder importar dos submódulos sem risco de
import circular.

Convenção de pasta (mesmo padrão de core/skill_forge.py:PROGRAMS_DIR
e outras pastas em data/, ver .gitignore): `data/jogos/<slug_do_jogo>/`,
com `demonstracoes/` (gravações guiadas pelo usuário),
`sessoes/` (auto-jogo) e `politica.pt` (modelo treinado) dentro.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS_DIR = os.path.join(BASE_DIR, "data", "jogos")


def slug_jogo(nome_jogo: str) -> str:
    """Nome livre digitado pelo usuário ("Fórmula 1 24") -> nome de
    pasta seguro ("formula_1_24"). Nunca vazio (cai em "jogo")."""
    slug = re.sub(r"[^a-z0-9]+", "_", nome_jogo.strip().lower()).strip("_")
    return slug or "jogo"


def pasta_jogo(nome_jogo: str) -> str:
    return os.path.join(DADOS_DIR, slug_jogo(nome_jogo))


def pasta_demonstracoes(nome_jogo: str) -> str:
    return os.path.join(pasta_jogo(nome_jogo), "demonstracoes")


def pasta_sessoes(nome_jogo: str) -> str:
    return os.path.join(pasta_jogo(nome_jogo), "sessoes")


def caminho_politica(nome_jogo: str) -> str:
    return os.path.join(pasta_jogo(nome_jogo), "politica.pt")


def tem_politica_treinada(nome_jogo: str) -> bool:
    return os.path.isfile(caminho_politica(nome_jogo))


def listar_demonstracoes(nome_jogo: str) -> list:
    pasta = pasta_demonstracoes(nome_jogo)
    if not os.path.isdir(pasta):
        return []
    return sorted(os.path.join(pasta, f) for f in os.listdir(pasta) if f.endswith(".npz"))


def listar_sessoes(nome_jogo: str) -> list:
    pasta = pasta_sessoes(nome_jogo)
    if not os.path.isdir(pasta):
        return []
    return sorted(os.path.join(pasta, f) for f in os.listdir(pasta) if f.endswith(".npz"))


def apagar_jogo(nome_jogo: str) -> bool:
    """Remove toda a pasta de dados (demonstrações, sessões, política)
    de `nome_jogo` -- destrutivo e IRREVERSÍVEL. Quem chama
    (plugins/jogos.py) é responsável por confirmar antes
    (seguranca.permissions.check_destructive_action), esta função só
    executa. Retorna False se não havia nada pra apagar."""
    import shutil
    pasta = pasta_jogo(nome_jogo)
    if not os.path.isdir(pasta):
        return False
    shutil.rmtree(pasta)
    return True


def jogos_conhecidos() -> list:
    """Nomes (slug) de todo jogo com pelo menos uma demonstração ou
    sessão gravada -- usado por diagnóstico/status."""
    if not os.path.isdir(DADOS_DIR):
        return []
    return sorted(
        d for d in os.listdir(DADOS_DIR)
        if os.path.isdir(os.path.join(DADOS_DIR, d))
    )
