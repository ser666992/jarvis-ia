"""
controle_pc/
===============
Módulo novo (não altera nada do que já existia): API interna pro
"cérebro" do Ultron pedir ações no computador -- mouse/teclado, abrir/
fechar/alternar programas, localizar e interagir com elementos de
interface, organizar janelas, ler/escrever arquivos, rodar comandos do
sistema, monitorar e encerrar processos, trocar o plano de energia
(controle_pc/energia.py, via `powercfg`).

Onde possível, isto REAPROVEITA o que já existe em vez de duplicar:
`automacao.apps` (abrir/fechar programa), `automacao.janelas`
(minimizar/maximizar/restaurar/focar), `sistema.processes` (listar
processos) -- este pacote só ACRESCENTA o que faltava (mouse/teclado,
localizar elemento, organizar em grade, ler/escrever arquivo, rodar
comando) atrás de uma API única e documentada.

Regra de permissão (igual ao resto do projeto, nada novo): ações
REVERSÍVEIS (mover mouse, clicar, digitar, focar janela) não exigem
confirmação -- são só entrada simulada, o mesmo que você mexendo no
seu próprio mouse/teclado. Ações DESTRUTIVAS/IRREVERSÍVEIS (rodar
comando do sistema, escrever arquivo, fechar programa, encerrar
processo) exigem `confirmed=True` via `seguranca.permissions`, com o
MESMO toggle global "não peça confirmação" que já existe pro resto do
Ultron -- ver seguranca/permissions.py:confirmado_pela_frase_ou_config.
"""

from controle_pc.entrada import (
    clicar,
    digitar_texto,
    mover_mouse,
    mover_mouse_relativo,
    pressionar_tecla,
    segurar_tecla,
    soltar_tecla,
)
from controle_pc.elementos import clicar_elemento, localizar_elemento
from controle_pc.janelas import alternar_para, organizar_janelas
from controle_pc.arquivos import escrever_arquivo, ler_arquivo, listar_pasta
from controle_pc.processos import (
    abrir_programa,
    encerrar_processo_travado,
    executar_comando,
    fechar_programa,
    listar_processos,
)
from controle_pc.energia import ativar_plano, listar_planos, plano_ativo

__all__ = [
    "mover_mouse", "mover_mouse_relativo", "clicar", "digitar_texto", "pressionar_tecla",
    "segurar_tecla", "soltar_tecla",
    "localizar_elemento", "clicar_elemento",
    "alternar_para", "organizar_janelas",
    "ler_arquivo", "escrever_arquivo", "listar_pasta",
    "abrir_programa", "fechar_programa", "executar_comando",
    "listar_processos", "encerrar_processo_travado",
    "listar_planos", "plano_ativo", "ativar_plano",
]
