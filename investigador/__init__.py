"""
investigador/
================
"Investigador Universal": dado um arquivo (EXE, APK, PDF, imagem,
vídeo) ou uma URL, identifica tecnologias/arquitetura/bibliotecas por
heurística de assinatura -- análise estática e passiva, nunca executa
o arquivo nem varre um site ativamente. Ver analise.py e README.md
deste módulo para detalhes e limitações honestas.
"""

from investigador.analise import analisar, formatar_relatorio

__all__ = ["analisar", "formatar_relatorio"]
