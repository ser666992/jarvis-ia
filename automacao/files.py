"""
automacao/files.py
=====================
Organização, busca e backup de arquivos -- tudo com `shutil`/`zipfile`
da stdlib, zero dependência. Mover/renomear são ações destrutivas e
exigem confirmação explícita (ver `seguranca.permissions`).
"""

import fnmatch
import os
import shutil
import zipfile
from datetime import datetime

from seguranca.permissions import check_destructive_action

DEFAULT_CATEGORY_MAP = {
    "imagens": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"),
    "documentos": (".pdf", ".doc", ".docx", ".txt", ".odt", ".xlsx", ".csv"),
    "videos": (".mp4", ".mkv", ".avi", ".mov"),
    "audio": (".mp3", ".wav", ".flac", ".ogg"),
    "compactados": (".zip", ".rar", ".7z", ".tar", ".gz"),
    "instaladores": (".exe", ".msi"),
}


def search_files(root: str, pattern: str, max_results: int = 50) -> list:
    """Busca arquivos por padrão de nome (glob, ex.: '*.pdf') a partir
    de `root`, recursivamente."""
    matches = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                matches.append(os.path.join(dirpath, filename))
                if len(matches) >= max_results:
                    return matches
    return matches


def organize_by_type(folder: str, category_map: dict = None, confirmed: bool = False) -> dict:
    """Move arquivos soltos em `folder` para subpastas por categoria
    (imagens/, documentos/, ...). Ação destrutiva (move arquivos)."""
    check_destructive_action(f"organizar arquivos em '{folder}' por tipo", confirmed=confirmed)
    category_map = category_map or DEFAULT_CATEGORY_MAP

    moved = {}
    for filename in os.listdir(folder):
        full_path = os.path.join(folder, filename)
        if not os.path.isfile(full_path):
            continue
        ext = os.path.splitext(filename)[1].lower()
        category = next((cat for cat, exts in category_map.items() if ext in exts), None)
        if not category:
            continue
        dest_dir = os.path.join(folder, category)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(full_path, os.path.join(dest_dir, filename))
        moved.setdefault(category, []).append(filename)
    return moved


def rename_file(path: str, new_name: str, confirmed: bool = False) -> str:
    check_destructive_action(f"renomear '{path}' para '{new_name}'", confirmed=confirmed)
    # os.path.basename descarta qualquer componente de caminho em
    # new_name -- sem isso, um new_name absoluto (ex.: "C:\Windows\x")
    # faz os.path.join IGNORAR o diretório de origem (join com um
    # caminho absoluto descarta o primeiro argumento) e o arquivo seria
    # movido pra um lugar arbitrário do sistema em vez de só renomeado.
    new_path = os.path.join(os.path.dirname(path), os.path.basename(new_name))
    os.rename(path, new_path)
    return new_path


def backup_folder(folder: str, dest_dir: str = None) -> str:
    """Compacta `folder` inteiro em um .zip com timestamp -- ação NÃO
    destrutiva (não apaga o original), então não exige confirmação."""
    dest_dir = dest_dir or os.path.dirname(folder.rstrip(os.sep)) or "."
    os.makedirs(dest_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(folder.rstrip(os.sep))
    zip_path = os.path.join(dest_dir, f"{base_name}_{timestamp}.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, filenames in os.walk(folder):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                arcname = os.path.relpath(full_path, folder)
                zf.write(full_path, arcname)
    return zip_path
