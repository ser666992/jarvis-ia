"""
tests/conftest.py
====================
Isolamento de todo teste em relação ao ambiente REAL do usuário --
nenhum teste deve escrever em data/jarvis.db, config/config.json, no
cofre de credenciais do Windows (keyring) ou abrir um navegador de
verdade. As três primeiras linhas (ANTES de qualquer import de módulo
do projeto) são as que importam de verdade:

`JARVIS_DB_PATH` precisa estar definida ANTES do primeiro
`import core.database` / `import core.memory` de todo o processo --
ambos calculam `DB_PATH` uma vez só, na hora do import (valor padrão de
parâmetro é avaliado uma única vez), então mudar a variável de ambiente
DEPOIS não teria efeito nenhum. Setar aqui, no topo do conftest.py
(carregado pelo pytest antes de qualquer teste), garante que isso
aconteça cedo o suficiente.
"""

import os
import sys
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="jarvis_test_")
os.environ["JARVIS_DB_PATH"] = os.path.join(_TEST_DB_DIR, "jarvis_test.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import config.settings as settings_module  # noqa: E402
from core.database import DB_PATH  # noqa: E402


@pytest.fixture(autouse=True)
def banco_de_teste_limpo():
    """Cada teste começa com um banco vazio -- os módulos que usam
    core.database/core.memory sempre criam suas tabelas com
    'CREATE TABLE IF NOT EXISTS', então apagar o arquivo entre testes e
    deixar recriar sozinho é suficiente (mais simples e menos frágil que
    truncar tabela por tabela manualmente, e não precisa ser atualizado
    toda vez que um módulo novo ganha uma tabela)."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest.fixture(autouse=True)
def config_isolado(tmp_path, monkeypatch):
    """Redireciona config.settings pra um config.json TEMPORÁRIO --
    sem isso, qualquer teste que chame `settings.set(...)` +
    `settings.save()` (ex.: ligar/desligar modo autônomo) escreveria de
    verdade no config/config.json do usuário. `_settings_instance` é um
    singleton do módulo (`get_settings()` sempre devolve o mesmo objeto)
    -- resetar pra None força recriar na próxima chamada, lendo do
    caminho temporário já trocado."""
    config_json = tmp_path / "config.json"
    monkeypatch.setattr(settings_module, "JSON_PATH", str(config_json))
    settings_module._settings_instance = None
    yield
    settings_module._settings_instance = None


@pytest.fixture(autouse=True)
def inbox_de_notificacao_limpo():
    """automacao/notification_inbox.py guarda estado em memória, em
    nível de MÓDULO (não por instância) -- sem limpar entre testes, uma
    mensagem "enviada" por um teste vazaria pro próximo."""
    from automacao import notification_inbox
    notification_inbox.limpar()
    yield
    notification_inbox.limpar()


@pytest.fixture
def contexto(monkeypatch):
    """Contexto mínimo que os plugins esperam receber em handle() --
    ver core/plugin_manager.py. `jarvis=None` é seguro pra testar
    plugins que não dependem dele (a maioria); testes que precisam de
    um jarvis/ia_manager de verdade constroem o próprio fake."""
    return {"user_id": "usuario_teste", "jarvis": None, "ia_manager": None, "memory": None}
