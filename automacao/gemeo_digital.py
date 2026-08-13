"""
automacao/gemeo_digital.py
==============================
"Gêmeo digital": antes de aplicar uma organização de arquivos de
verdade, cria uma cópia temporária (o "gêmeo") da pasta em
data/gemeo_digital/, aplica a MESMA operação nessa cópia, e devolve um
relatório do que teria acontecido (quantos arquivos, pra onde) -- só
depois disso você decide aplicar de verdade na pasta real (mesma ação,
automacao/files.py:organize_by_type, com a confirmação normal).

Isto é a versão honesta de "criar um gêmeo digital do computador/
celular e testar alterações nele antes de aplicar no sistema real":
simular o COMPUTADOR INTEIRO não é possível (seria um projeto de
virtualização completo, fora de escopo) -- o que dá pra fazer bem, de
verdade, é simular o efeito de UMA operação específica (organizar uma
pasta) numa cópia real dos arquivos, sem nenhum risco pro original.
"""

import os
import shutil
from datetime import datetime

from automacao import files
from logs.logger import get_logger

log = get_logger("automacao")

_GEMEOS_DIR = os.path.join("data", "gemeo_digital")


def testar_organizacao(folder: str) -> dict:
    """Copia `folder` pra uma pasta temporária, aplica organize_by_type
    nela (sem tocar no original), e devolve um relatório do que teria
    mudado + o caminho da cópia (pra você poder olhar antes de decidir)."""
    if not os.path.isdir(folder):
        raise ValueError(f"Pasta não encontrada: {folder}")

    os.makedirs(_GEMEOS_DIR, exist_ok=True)
    nome_pasta = os.path.basename(folder.rstrip(os.sep)) or "pasta"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_gemeo = os.path.join(_GEMEOS_DIR, f"{nome_pasta}_{timestamp}")

    shutil.copytree(folder, caminho_gemeo)
    try:
        movidos = files.organize_by_type(caminho_gemeo, confirmed=True)
    except Exception:
        shutil.rmtree(caminho_gemeo, ignore_errors=True)
        raise

    total = sum(len(v) for v in movidos.values())
    log.info("gêmeo digital testado: %s (%d arquivo(s) moveriam)", caminho_gemeo, total)
    return {"caminho_gemeo": caminho_gemeo, "movidos": movidos, "total": total}


def limpar_gemeo(caminho_gemeo: str) -> bool:
    """Remove uma cópia de gêmeo digital -- só aceita caminhos DENTRO
    de data/gemeo_digital/, nunca um caminho arbitrário (defesa extra
    contra apagar a pasta errada por engano)."""
    caminho_absoluto = os.path.abspath(caminho_gemeo)
    base_absoluta = os.path.abspath(_GEMEOS_DIR)
    if not caminho_absoluto.startswith(base_absoluta):
        return False
    if not os.path.isdir(caminho_absoluto):
        return False
    shutil.rmtree(caminho_absoluto, ignore_errors=True)
    return True
