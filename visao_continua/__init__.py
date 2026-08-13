"""
visao_continua/
==================
Módulo novo (não altera nada do que já existia): visão CONTÍNUA da
tela, rodando em segundo plano -- diferente de `visao/observe.py`
(um retrato pontual, sob demanda) e de `plugins/observation.py` (o
usuário pede um comentário falado, de vez em quando). Este módulo
mantém um ESTADO estruturado sempre atualizado, que qualquer outra
parte do Ultron pode consultar, e alimenta o "cérebro" (a IA) com um
resumo do que está acontecendo na tela, silenciosamente.

Ver monitor.py para a implementação e o README deste módulo para
detalhes de design (por que desligado por padrão, como a detecção de
mudança funciona, limitações honestas).
"""

from visao_continua.monitor import (
    ativo,
    descrever_para_prompt,
    disponivel,
    estado_atual,
    historico,
    iniciar,
    ligar,
    parar,
)

__all__ = [
    "iniciar", "ligar", "parar", "ativo", "estado_atual", "historico",
    "descrever_para_prompt", "disponivel",
]
