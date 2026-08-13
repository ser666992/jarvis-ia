"""
controle_pc/arquivos.py
===========================
Ler/escrever conteúdo de arquivo e listar pasta -- automacao/files.py
já cobre busca/organização/renomeação/backup, mas não tinha leitura/
escrita genérica de conteúdo. Ler é seguro (não muda nada); escrever é
destrutivo (pode sobrescrever um arquivo existente) e exige
`confirmed=True`, mesmo padrão de automacao/files.py:rename_file.
"""

import os

from seguranca.permissions import check_destructive_action

_MAX_CHARS_PADRAO = 5000  # teto de segurança -- não despeja um arquivo de GBs no contexto da IA sem querer


def ler_arquivo(caminho: str, max_chars: int = _MAX_CHARS_PADRAO) -> str:
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: '{caminho}'.")
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        conteudo = f.read(max_chars + 1)
    if len(conteudo) > max_chars:
        conteudo = conteudo[:max_chars] + "\n... (arquivo truncado, só os primeiros "
        conteudo += f"{max_chars} caracteres foram lidos)"
    return conteudo


def escrever_arquivo(caminho: str, conteudo: str, confirmed: bool = False, sobrescrever: bool = True) -> str:
    """Cria (ou sobrescreve, se `sobrescrever=True` e o arquivo já
    existir) um arquivo de texto. Ação destrutiva -- exige
    `confirmed=True`."""
    ja_existe = os.path.isfile(caminho)
    if ja_existe and not sobrescrever:
        raise FileExistsError(f"'{caminho}' já existe e sobrescrever=False.")
    descricao = f"{'sobrescrever' if ja_existe else 'criar'} o arquivo '{caminho}'"
    check_destructive_action(descricao, confirmed=confirmed)
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


def listar_pasta(caminho: str) -> list:
    """Lista o conteúdo de uma pasta (não recursivo) -- leitura,
    sem confirmação. Ver automacao.files.search_files para busca
    recursiva por padrão de nome."""
    if not os.path.isdir(caminho):
        raise NotADirectoryError(f"Pasta não encontrada: '{caminho}'.")
    itens = []
    for nome in sorted(os.listdir(caminho)):
        full = os.path.join(caminho, nome)
        itens.append({"nome": nome, "e_pasta": os.path.isdir(full), "tamanho": os.path.getsize(full) if os.path.isfile(full) else None})
    return itens
