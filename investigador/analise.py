"""
investigador/analise.py
==========================
"Investigador Universal": dado um arquivo (EXE, APK, PDF, imagem,
vídeo, script, documento Office, .zip) ou uma URL, tenta identificar
tecnologias/arquitetura/bibliotecas usadas e sinaliza pontos de
atenção.

Todo arquivo local também ganha um hash SHA-256 (`detalhes.sha256`) e
uma checagem de "dupla extensão" (`_checar_dupla_extensao`, ex.:
"fatura.pdf.exe" -- disfarce clássico de malware), além da análise
específica do tipo. Scripts (.ps1/.bat/.vbs/.js/.wsf/.hta) são varridos
por padrões de texto associados a ofuscação/execução remota
(-EncodedCommand, Invoke-Expression, DownloadString, LOLBins como
certutil/mshta/regsvr32...) -- heurística, não análise de fluxo real.
Documentos Office (.docx/.xlsx/.pptx e as variantes *m com macro) são
checados por macro VBA embutida (vbaProject.bin) e link externo.

Análise ESTÁTICA e PASSIVA por design:
  - Arquivos locais: só LÊ bytes/metadados -- nunca executa o arquivo
    analisado (rodar um .exe/.apk desconhecido pra "ver o que faz"
    seria perigoso de verdade, e não é isso que este módulo faz).
  - Sites: UM request HTTP de leitura (cabeçalhos + HTML da página
    pedida) -- nunca varredura ativa (sem fuzzing de parâmetro, sem
    tentar SQLi/XSS, sem varrer portas). Varredura ativa contra um site
    que não é seu, sem autorização, é o tipo de coisa que este projeto
    recusa por padrão (ver plugins/security_scan.py se existir um
    equivalente autorizado de pentest -- aqui é só reconhecimento
    passivo de tecnologia, não teste de invasão).

Limitação honesta: isso é reconhecimento por assinatura/heurística
(extensão, magic bytes, strings legíveis, imports, cabeçalhos HTTP) --
NÃO é engenharia reversa de verdade (sem desmontagem/decompilação) e
NÃO é um scanner de vulnerabilidades real (sem consulta a base de CVE,
sem fuzzing, sem exploração). Serve pra um retrato rápido de "o que é
isso e com o que foi feito", não um laudo de segurança completo --
todo resultado inclui os "indicios" encontrados, nunca uma alegação
de certeza absoluta.
"""

import hashlib
import os
import re
import zipfile

from logs.logger import get_logger

log = get_logger("investigador")

try:
    import pefile
    HAS_PEFILE = True
except ImportError:
    HAS_PEFILE = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from PIL import Image, ExifTags
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
_EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
_EXT_SCRIPT = {".ps1", ".bat", ".cmd", ".vbs", ".js", ".wsf", ".hta"}
_EXT_OFFICE = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm"}
_EXT_OFFICE_MACRO = {".docm", ".xlsm", ".pptm"}  # extensão já denuncia macro habilitada, mesmo sem abrir o zip
# extensões "de disfarce" -- o tipo que malware usa como penúltimo sufixo
# pra parecer documento inofensivo (ex.: "fatura.pdf.exe") antes da
# extensão de execução de verdade.
_EXT_DOCUMENTO_DISFARCE = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".txt", ".zip"}
_EXT_EXECUTAVEL = {".exe", ".scr", ".com", ".bat", ".cmd", ".vbs", ".js", ".ps1", ".msi", ".jar", ".hta"}

# Strings legíveis dentro de um EXE que costumam denunciar a tecnologia
# usada -- heurística simples (equivalente ao comando `strings` + grep
# por marcador conhecido), não é análise binária de verdade.
_MARCADORES_EXE = {
    "pyinstaller": "PyInstaller (aplicativo Python empacotado)",
    "python3": "Python (runtime embutido)",
    "electron.exe": "Electron (app desktop com Chromium+Node.js)",
    "node.exe": "Node.js embutido",
    "mscoree.dll": ".NET (CLR da Microsoft)",
    "qt5core.dll": "Qt5 (framework de UI C++)",
    "qt6core.dll": "Qt6 (framework de UI C++)",
    "unityplayer.dll": "Unity (engine de jogos)",
    "unreal": "Unreal Engine",
    "chromiumembedded": "CEF -- Chromium Embedded Framework",
    "libcef.dll": "CEF -- Chromium Embedded Framework",
    "java.exe": "Java (runtime embutido/launcher)",
    "vcruntime": "Visual C++ Runtime (compilado em C/C++)",
    "golang": "Go (build id presente)",
}


def _extensao(caminho: str) -> str:
    return os.path.splitext(caminho)[1].lower()


def _eh_url(alvo: str) -> bool:
    return alvo.lower().startswith("http://") or alvo.lower().startswith("https://")


def _tamanho_legivel(bytes_: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f}{unidade}"
        bytes_ /= 1024
    return f"{bytes_:.1f}TB"


def _strings_legiveis(dados: bytes, tamanho_minimo: int = 5) -> list:
    """Extrai substrings ASCII imprimíveis -- equivalente simples ao
    utilitário `strings` do Unix, usado só pra procurar marcadores de
    tecnologia conhecidos, não pra dump completo (dump completo de um
    binário grande não cabe numa resposta de chat)."""
    padrao = re.compile(rb"[\x20-\x7e]{%d,}" % tamanho_minimo)
    return [m.decode("ascii", errors="ignore") for m in padrao.findall(dados)]


def _sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _checar_dupla_extensao(caminho: str) -> str:
    """Sinaliza o disfarce clássico de malware: um nome de arquivo com
    DOIS sufixos, onde o penúltimo parece um documento/imagem inofensiva
    e o ÚLTIMO é o que o Windows realmente usa pra decidir como abrir
    (ex.: "fatura.pdf.exe" -- o Windows executa, não abre no leitor de
    PDF, mesmo a pessoa vendo ".pdf" no meio do nome). Retorna uma
    string de aviso, ou None se o nome não bater o padrão."""
    nome = os.path.basename(caminho)
    partes = nome.split(".")
    if len(partes) < 3:
        return None
    penultima, ultima = f".{partes[-2].lower()}", f".{partes[-1].lower()}"
    if penultima in _EXT_DOCUMENTO_DISFARCE and ultima in _EXT_EXECUTAVEL:
        return (
            f'nome de arquivo suspeito: "{nome}" parece um documento ("{penultima}") mas a extensão '
            f'real é "{ultima}" -- disfarce clássico usado por malware pra enganar quem só olha o começo do nome'
        )
    return None


_PADROES_SUSPEITOS_SCRIPT = {
    re.compile(r"-enc(odedcommand)?\b", re.IGNORECASE):
        "comando PowerShell codificado em base64 (-EncodedCommand) -- esconde o comando real de uma leitura rápida",
    re.compile(r"\biex\b|invoke-expression", re.IGNORECASE):
        "Invoke-Expression/IEX -- executa texto como código, comum em scripts que baixam e rodam algo em seguida",
    re.compile(r"downloadstring|downloadfile|net\.webclient", re.IGNORECASE):
        "baixa conteúdo da internet (WebClient/DownloadString/DownloadFile)",
    re.compile(r"bypass\s*-?\s*(execution)?\s*policy|-ep\s+bypass", re.IGNORECASE):
        "tenta contornar a política de execução do PowerShell",
    re.compile(r"certutil.{0,20}-decode", re.IGNORECASE):
        "usa certutil pra decodificar base64 -- técnica conhecida de contornar antivírus (LOLBin)",
    re.compile(r"frombase64string", re.IGNORECASE):
        "decodifica um bloco de base64 embutido no próprio script",
    re.compile(r"hidden\s+window|windowstyle\s+hidden|-w(indowstyle)?\s+hidden", re.IGNORECASE):
        "roda com a janela escondida do usuário",
    re.compile(r"\bmshta\b|\bregsvr32\b.{0,20}/i:", re.IGNORECASE):
        "usa mshta/regsvr32 pra rodar código -- técnica conhecida de contornar antivírus (LOLBin)",
    re.compile(r"wscript\.shell|createobject\([\"']wscript\.shell", re.IGNORECASE):
        "cria um objeto de shell pra rodar outros comandos a partir do script",
    re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"):
        "contém um bloco longo parecido com base64/dado codificado (ofuscação comum)",
}


def _analisar_script(caminho: str) -> dict:
    resultado = {
        "tipo": "script",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [
            "Isso é busca por padrão de texto (heurística), não análise de fluxo de execução -- um "
            "script pode ser malicioso sem bater em nenhum desses padrões, e um script legítimo pode "
            "conter algum deles por razão inofensiva (ex.: um instalador que baixa uma atualização).",
        ],
    }
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            conteudo = f.read()
    except Exception as e:
        resultado["limitacoes"].append(f"Não consegui ler o arquivo como texto ({e}).")
        return resultado

    for padrao, explicacao in _PADROES_SUSPEITOS_SCRIPT.items():
        if padrao.search(conteudo):
            resultado["indicios_tecnologia"].append(explicacao)
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum padrão suspeito conhecido encontrado no texto do script")
    resultado["detalhes"]["linhas"] = conteudo.count("\n") + 1
    return resultado


def _analisar_office(caminho: str) -> dict:
    ext = _extensao(caminho)
    resultado = {
        "tipo": "documento Office (OOXML)",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [
            "Detecção de macro é por PRESENÇA do arquivo vbaProject.bin dentro do zip, não "
            "decompilação do código VBA -- não avalia SE a macro é maliciosa, só se ela existe.",
        ],
    }
    if ext in _EXT_OFFICE_MACRO:
        resultado["indicios_tecnologia"].append(
            f"extensão '{ext}' já indica macro habilitada (formato *m, não *x) -- cuidado ao habilitar conteúdo"
        )
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
    except zipfile.BadZipFile:
        resultado["limitacoes"].append("O arquivo não é um .docx/.xlsx/.pptx válido (ou está corrompido).")
        return resultado

    tem_macro = any("vbaproject.bin" in n.lower() for n in nomes)
    resultado["detalhes"]["contem_macro_vba"] = tem_macro
    if tem_macro:
        resultado["indicios_tecnologia"].append("contém macro VBA (vbaProject.bin) -- revise antes de habilitar conteúdo/macros")

    if any("externallink" in n.lower() for n in nomes):
        resultado["indicios_tecnologia"].append("contém referência a link/dado externo -- pode buscar conteúdo de fora ao abrir")

    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum indício de macro/link externo encontrado")
    return resultado


def _analisar_zip_generico(caminho: str) -> dict:
    resultado = {
        "tipo": "arquivo compactado (.zip)",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": ["Só lista a estrutura do zip -- não extrai nem inspeciona o conteúdo de cada arquivo interno."],
    }
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
    except zipfile.BadZipFile:
        resultado["limitacoes"].append("O arquivo não é um .zip válido (ou está corrompido).")
        return resultado

    resultado["detalhes"]["arquivos_dentro"] = len(nomes)
    resultado["detalhes"]["primeiros_arquivos"] = nomes[:15]

    executaveis_dentro = [n for n in nomes if os.path.splitext(n)[1].lower() in _EXT_EXECUTAVEL]
    if executaveis_dentro:
        resultado["indicios_tecnologia"].append(
            f"contém {len(executaveis_dentro)} arquivo(s) executável/script dentro: {', '.join(executaveis_dentro[:5])}"
        )
    for n in nomes:
        aviso = _checar_dupla_extensao(n)
        if aviso:
            resultado["indicios_tecnologia"].append(aviso)
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum executável/script nem nome de arquivo suspeito encontrado dentro")
    return resultado


def _analisar_exe(caminho: str) -> dict:
    with open(caminho, "rb") as f:
        dados = f.read()

    resultado = {
        "tipo": "executável (PE)",
        "tamanho": _tamanho_legivel(len(dados)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }

    if dados[:2] != b"MZ":
        resultado["limitacoes"].append("O arquivo não começa com a assinatura MZ esperada de um PE do Windows.")

    strings = _strings_legiveis(dados)
    texto_busca = "\n".join(strings).lower()
    for marcador, explicacao in _MARCADORES_EXE.items():
        if marcador in texto_busca:
            resultado["indicios_tecnologia"].append(explicacao)

    if HAS_PEFILE:
        try:
            pe = pefile.PE(caminho, fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            resultado["detalhes"]["arquitetura"] = pefile.MACHINE_TYPE.get(pe.FILE_HEADER.Machine, str(pe.FILE_HEADER.Machine))
            dlls_importadas = []
            if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
                dlls_importadas = [entry.dll.decode(errors="ignore") for entry in pe.DIRECTORY_ENTRY_IMPORT]
            resultado["detalhes"]["dlls_importadas"] = dlls_importadas[:30]
            pe.close()
        except Exception as e:
            resultado["limitacoes"].append(f"pefile não conseguiu processar o cabeçalho PE ({e}).")
    else:
        resultado["limitacoes"].append(
            "Instale 'pefile' (requirements-investigador.txt) pra ver arquitetura/DLLs importadas."
        )

    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum marcador de tecnologia conhecido encontrado nas strings legíveis")

    resultado["limitacoes"].append(
        "Isso é reconhecimento por assinatura, não engenharia reversa -- não desmonta nem executa o binário."
    )
    return resultado


_MARCADORES_APK = {
    "libflutter.so": "Flutter",
    "flutter_assets/": "Flutter",
    "libreactnativejni.so": "React Native",
    "index.android.bundle": "React Native",
    "assets/www/cordova.js": "Cordova (WebView híbrido)",
    "assets/www/": "app híbrido baseado em WebView (Cordova/Capacitor ou similar)",
    "classes.dex": "Java/Kotlin nativo (Android SDK)",
    "kotlin/": "Kotlin",
}


def _analisar_apk(caminho: str) -> dict:
    resultado = {
        "tipo": "APK (Android)",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
    except zipfile.BadZipFile:
        resultado["limitacoes"].append("O arquivo não é um .zip/.apk válido (ou está corrompido).")
        return resultado

    arquiteturas = sorted({n.split("/")[1] for n in nomes if n.startswith("lib/") and "/" in n[4:]})
    if arquiteturas:
        resultado["detalhes"]["arquiteturas_nativas"] = arquiteturas

    assinado = any(n.startswith("META-INF/") and (n.endswith(".RSA") or n.endswith(".DSA") or n.endswith(".EC")) for n in nomes)
    resultado["detalhes"]["assinado"] = assinado

    for marcador, tecnologia in _MARCADORES_APK.items():
        if any(marcador in n for n in nomes) and tecnologia not in resultado["indicios_tecnologia"]:
            resultado["indicios_tecnologia"].append(tecnologia)

    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum marcador de framework conhecido encontrado na estrutura do APK")

    resultado["limitacoes"].append(
        "AndroidManifest.xml está em formato binário -- sem 'aapt'/androguard instalado, não lemos "
        "permissões declaradas nem versão/nome do pacote diretamente daqui."
    )
    return resultado


def _analisar_pdf(caminho: str) -> dict:
    resultado = {
        "tipo": "PDF",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    if HAS_PYPDF:
        try:
            leitor = PdfReader(caminho)
            metadados = leitor.metadata or {}
            if metadados.get("/Producer"):
                resultado["detalhes"]["producer"] = str(metadados["/Producer"])
            if metadados.get("/Creator"):
                resultado["detalhes"]["creator"] = str(metadados["/Creator"])
            resultado["detalhes"]["paginas"] = len(leitor.pages)
        except Exception as e:
            resultado["limitacoes"].append(f"pypdf não conseguiu ler os metadados ({e}).")
    else:
        resultado["limitacoes"].append("Instale 'pypdf' (requirements-investigador.txt) pra ler metadados/nº de páginas.")

    with open(caminho, "rb") as f:
        dados = f.read()
    if b"/JavaScript" in dados or b"/JS" in dados:
        resultado["indicios_tecnologia"].append("contém JavaScript embutido -- revise antes de abrir com JS habilitado")
    if b"/EmbeddedFile" in dados:
        resultado["indicios_tecnologia"].append("contém arquivo(s) embutido(s) dentro do PDF")
    if b"/OpenAction" in dados or b"/AA" in dados:
        resultado["indicios_tecnologia"].append("possui ação automática configurada para rodar ao abrir")
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum indício de conteúdo ativo (JS/ação automática/anexo) encontrado")

    resultado["limitacoes"].append("Detecção de JS/anexo é busca por assinatura nos bytes crus, não parsing completo do PDF.")
    return resultado


def _analisar_imagem(caminho: str) -> dict:
    resultado = {
        "tipo": "imagem",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    if not HAS_PIL:
        resultado["limitacoes"].append("Instale 'Pillow' (requirements-visao.txt) pra ler formato/resolução/EXIF.")
        return resultado
    try:
        with Image.open(caminho) as img:
            resultado["detalhes"]["formato"] = img.format
            resultado["detalhes"]["resolucao"] = f"{img.width}x{img.height}"
            exif_bruto = img._getexif() if hasattr(img, "_getexif") else None
            if exif_bruto:
                tags = {ExifTags.TAGS.get(k, k): v for k, v in exif_bruto.items()}
                if tags.get("Make") or tags.get("Model"):
                    resultado["detalhes"]["camera"] = f"{tags.get('Make', '')} {tags.get('Model', '')}".strip()
                if tags.get("Software"):
                    resultado["detalhes"]["software"] = str(tags["Software"])
                if tags.get("GPSInfo"):
                    resultado["indicios_tecnologia"].append(
                        "contém dados de localização GPS no EXIF -- cuidado antes de compartilhar"
                    )
    except Exception as e:
        resultado["limitacoes"].append(f"Pillow não conseguiu processar a imagem ({e}).")
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum dado sensível óbvio encontrado no EXIF")
    return resultado


def _analisar_video(caminho: str) -> dict:
    resultado = {
        "tipo": "vídeo",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    import subprocess
    import shutil as _shutil
    import json as _json

    if not _shutil.which("ffprobe"):
        resultado["limitacoes"].append(
            "Instale o 'ffprobe' (parte do ffmpeg, não é um pacote Python) pra ler codec/resolução/duração."
        )
        return resultado
    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", caminho],
            capture_output=True, text=True, timeout=15,
        )
        info = _json.loads(saida.stdout or "{}")
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                resultado["detalhes"]["codec_video"] = stream.get("codec_name")
                resultado["detalhes"]["resolucao"] = f"{stream.get('width')}x{stream.get('height')}"
            if stream.get("codec_type") == "audio":
                resultado["detalhes"]["codec_audio"] = stream.get("codec_name")
        if info.get("format", {}).get("duration"):
            resultado["detalhes"]["duracao_segundos"] = round(float(info["format"]["duration"]), 1)
    except Exception as e:
        resultado["limitacoes"].append(f"ffprobe falhou ao processar o vídeo ({e}).")
    return resultado


_FINGERPRINTS_SITE = {
    "wp-content/": "WordPress",
    "wp-json": "WordPress (REST API)",
    "cdn.shopify.com": "Shopify",
    "__next_data__": "Next.js (React)",
    "_nuxt/": "Nuxt.js (Vue)",
    "django": "Django (indício em cookie/erro)",
    "laravel_session": "Laravel (PHP)",
    "x-drupal-cache": "Drupal",
}
_HEADERS_SEGURANCA = ("content-security-policy", "x-frame-options", "strict-transport-security")


def _analisar_site(url: str) -> dict:
    import urllib.request

    resultado = {
        "tipo": "site",
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [
            "Análise passiva: um único GET nessa URL, sem varredura ativa de "
            "portas/parâmetros/injeção -- não é um teste de invasão.",
        ],
    }
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UltronInvestigador)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            corpo = resp.read(200_000).decode("utf-8", errors="ignore")
            headers = {k.lower(): v for k, v in resp.getheaders()}
    except Exception as e:
        resultado["limitacoes"].append(f"Não consegui acessar a URL ({e}).")
        return resultado

    if headers.get("server"):
        resultado["detalhes"]["servidor"] = headers["server"]
    if headers.get("x-powered-by"):
        resultado["detalhes"]["x_powered_by"] = headers["x-powered-by"]

    texto_busca = (corpo + " " + " ".join(headers.values())).lower()
    for marcador, tecnologia in _FINGERPRINTS_SITE.items():
        if marcador in texto_busca:
            resultado["indicios_tecnologia"].append(tecnologia)

    m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', corpo, re.IGNORECASE)
    if m:
        resultado["detalhes"]["meta_generator"] = m.group(1)

    faltando = [h for h in _HEADERS_SEGURANCA if h not in headers]
    if faltando:
        resultado["indicios_tecnologia"].append(
            f"cabeçalhos de segurança ausentes: {', '.join(faltando)} (possível ponto de atenção, não confirma vulnerabilidade)"
        )
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum framework/CMS conhecido identificado por fingerprint")

    return resultado


def analisar(alvo: str) -> dict:
    """Ponto de entrada único: recebe um caminho de arquivo local ou
    uma URL, detecta o tipo e despacha pra análise específica. Levanta
    FileNotFoundError se um caminho local não existir.

    Pra QUALQUER arquivo local (não URL), duas checagens rodam sempre,
    além da análise específica do tipo: hash SHA-256 (deixa a pessoa
    cross-checar manualmente em outro lugar se quiser, sem este módulo
    fazer nenhuma consulta de rede) e disfarce de dupla extensão (ver
    _checar_dupla_extensao)."""
    if _eh_url(alvo):
        return _analisar_site(alvo)

    if not os.path.isfile(alvo):
        raise FileNotFoundError(f"Não encontrei o arquivo '{alvo}'.")

    ext = _extensao(alvo)
    if ext in (".exe", ".dll"):
        resultado = _analisar_exe(alvo)
    elif ext == ".apk":
        resultado = _analisar_apk(alvo)
    elif ext == ".pdf":
        resultado = _analisar_pdf(alvo)
    elif ext in _EXT_IMAGEM:
        resultado = _analisar_imagem(alvo)
    elif ext in _EXT_VIDEO:
        resultado = _analisar_video(alvo)
    elif ext in _EXT_SCRIPT:
        resultado = _analisar_script(alvo)
    elif ext in _EXT_OFFICE:
        resultado = _analisar_office(alvo)
    elif ext == ".zip":
        resultado = _analisar_zip_generico(alvo)
    else:
        resultado = {
            "tipo": f"arquivo genérico ({ext or 'sem extensão'})",
            "tamanho": _tamanho_legivel(os.path.getsize(alvo)),
            "indicios_tecnologia": [],
            "detalhes": {},
            "limitacoes": [f"Extensão '{ext}' não tem um analisador específico -- só reportei o tamanho e o hash."],
        }

    try:
        resultado["detalhes"]["sha256"] = _sha256(alvo)
    except Exception as e:
        resultado["limitacoes"].append(f"Não consegui calcular o hash SHA-256 ({e}).")

    aviso_disfarce = _checar_dupla_extensao(alvo)
    if aviso_disfarce:
        resultado["indicios_tecnologia"].insert(0, aviso_disfarce)

    return resultado


def formatar_relatorio(alvo: str, resultado: dict) -> str:
    linhas = [f'Investigação de "{alvo}" -- tipo: {resultado["tipo"]}']
    if resultado.get("tamanho"):
        linhas.append(f"Tamanho: {resultado['tamanho']}")
    for chave, valor in resultado.get("detalhes", {}).items():
        linhas.append(f"{chave}: {valor}")
    if resultado.get("indicios_tecnologia"):
        linhas.append("Indícios de tecnologia:")
        linhas.extend(f"- {i}" for i in resultado["indicios_tecnologia"])
    if resultado.get("limitacoes"):
        linhas.append("Limitações desta análise:")
        linhas.extend(f"- {lim}" for lim in resultado["limitacoes"])
    return "\n".join(linhas)
