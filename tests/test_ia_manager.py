"""
tests/test_ia_manager.py
===========================
Bug real encontrado em auditoria: `AIManager.providers` é construído
uma vez e cacheado (`self._providers`) -- necessário pra não reler
config/reconstruir os provedores a cada mensagem, mas isso significa
que configurar/trocar a API key EM UMA SESSÃO JÁ EM ANDAMENTO
("/configurarapi" no modo texto, com o Jarvis já rodando) salvava a
chave certinho em config.json, mas o AIManager já construído
continuava respondendo com a lista antiga (ex.: sem nenhum provedor
disponível, se a primeira mensagem foi processada antes de configurar
a chave) até o processo ser reiniciado. `AIManager.refresh()` resolve
isso -- main.py:_run_ia_setup_wizard() chama depois de salvar com
sucesso, quando um ia_manager já existente foi passado.
"""

from config.settings import get_settings
from ia.manager import AIManager


def test_providers_e_cacheado_ate_o_primeiro_acesso():
    manager = AIManager()
    assert manager._providers is None

    primeira_leitura = manager.providers
    segunda_leitura = manager.providers

    assert primeira_leitura is segunda_leitura  # mesma lista -- não reconstruiu


def test_refresh_forca_reconstruir_na_proxima_leitura():
    manager = AIManager()
    primeira_leitura = manager.providers
    assert manager._providers is not None

    manager.refresh()

    assert manager._providers is None
    segunda_leitura = manager.providers
    assert segunda_leitura is not primeira_leitura  # reconstruiu de verdade


def test_refresh_pega_config_nova_apos_configurar_provedor_em_sessao_ja_ativa():
    """Simula o cenário real do bug: settings muda DEPOIS do primeiro
    acesso a .providers (equivalente a rodar /configurarapi no meio de
    uma sessão) -- sem refresh(), a chave nova nunca aparece; com
    refresh(), aparece na primeira leitura seguinte."""
    settings = get_settings()
    manager = AIManager()

    settings.set("ia.provedores.anthropic.api_key", "")
    manager.providers  # força construir a lista com a chave ainda vazia

    settings.set("ia.provedores.anthropic.api_key", "sk-ant-nova-chave-configurada-agora")
    settings.save()

    # SEM refresh(): a lista continua sendo a mesma construída antes da chave existir.
    anthropic_antes = next(p for p in manager.providers if p.name == "anthropic")
    assert anthropic_antes.api_key == ""

    manager.refresh()

    anthropic_depois = next(p for p in manager.providers if p.name == "anthropic")
    assert anthropic_depois.api_key == "sk-ant-nova-chave-configurada-agora"
