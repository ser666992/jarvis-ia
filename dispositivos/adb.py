"""
dispositivos/adb.py
======================
Controle de dispositivos Android via `adb` (Android Debug Bridge) --
binário externo, não uma lib pip. Precisa estar instalado e no PATH
(faz parte do Android SDK Platform Tools).

Conexão sem fio (mesma rede Wi-Fi, sem cabo e sem expor nada na
internet): `connect()`/`pair()`/`disconnect()` usam o mesmo protocolo
ADB, só que por TCP/IP na rede local em vez de USB -- nunca abre porta
nenhuma para fora da rede local, então não tem o risco de segurança de
expor ADB na internet (que é real e conhecido: portas ADB abertas pra
internet são alvo comum de botnets).

Dois jeitos de conectar pela primeira vez:
  1. **Android 11+ ("Depuração sem fio")**: `pair()` com o código de 6
     dígitos que aparece em Opções do desenvolvedor > Depuração sem
     fio > Parear dispositivo com código -- depois `connect()` no
     IP:porta principal (porta diferente da de pareamento).
  2. **Qualquer versão, com USB uma única vez**: conecta o cabo, chama
     `enable_tcpip()` pra mudar o aparelho pro modo TCP/IP, desconecta
     o cabo, e a partir daí só `connect()` no IP Wi-Fi do aparelho
     (`device_ip()` ajuda a descobrir esse IP).
"""

import os
import re
import shutil
import subprocess

from config.settings import get_settings

_DEFAULT_ADB_PATH = "adb"
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUNDLED_ADB = os.path.join(
    _BASE_DIR, "tools", "platform-tools", "adb.exe" if os.name == "nt" else "adb"
)


def _adb_path() -> str:
    """Usa o caminho configurado em config.json se ele tiver sido
    customizado; caso contrário, prefere uma cópia baixada em
    tools/platform-tools/ (ver README) antes de cair para 'adb' via
    PATH do sistema -- assim quem já tem o Android SDK Platform Tools
    instalado globalmente continua funcionando sem mudar nada."""
    configurado = get_settings().get("dispositivos.adb_path", _DEFAULT_ADB_PATH)
    if configurado != _DEFAULT_ADB_PATH:
        return configurado
    if os.path.isfile(_BUNDLED_ADB):
        return _BUNDLED_ADB
    return _DEFAULT_ADB_PATH


def available() -> bool:
    return shutil.which(_adb_path()) is not None


def _run(args: list, timeout: int = 15):
    if not available():
        raise RuntimeError(f"'{_adb_path()}' não encontrado no PATH. Instale o Android SDK Platform Tools.")
    return subprocess.run([_adb_path()] + args, capture_output=True, text=True, timeout=timeout)


def list_devices() -> list:
    result = _run(["devices"])
    lines = result.stdout.strip().splitlines()[1:]
    return [line.split("\t")[0] for line in lines if line.strip() and "\t" in line]


def shell(command: str, device: str = None) -> str:
    args = (["-s", device] if device else []) + ["shell", command]
    return _run(args).stdout


def install_apk(apk_path: str, device: str = None) -> str:
    args = (["-s", device] if device else []) + ["install", apk_path]
    return _run(args, timeout=120).stdout


def push_file(local_path: str, remote_path: str, device: str = None) -> str:
    args = (["-s", device] if device else []) + ["push", local_path, remote_path]
    return _run(args, timeout=60).stdout


def pull_file(remote_path: str, local_path: str, device: str = None) -> str:
    args = (["-s", device] if device else []) + ["pull", remote_path, local_path]
    return _run(args, timeout=60).stdout


def screenshot(local_path: str, device: str = None) -> str:
    """Captura a tela do celular (`screencap`) e puxa pro PC em
    `local_path`. Usa um arquivo temporário no próprio celular como
    intermediário -- é como o `adb shell screencap` sempre funcionou,
    não tem atalho mais direto sem isso."""
    remote_tmp = "/sdcard/jarvis_screenshot.png"
    args = (["-s", device] if device else []) + ["shell", "screencap", "-p", remote_tmp]
    _run(args, timeout=20)
    pull_file(remote_tmp, local_path, device=device)
    return local_path


def battery_level(device: str = None) -> dict:
    """Nível de bateria do celular via `dumpsys battery` (presente em
    todo Android). Retorna nivel_percentual (int ou None se não
    conseguiu ler) e carregando (bool)."""
    saida = shell("dumpsys battery", device=device)
    info = {}
    for linha in saida.splitlines():
        linha = linha.strip()
        if ":" not in linha:
            continue
        chave, _, valor = linha.partition(":")
        info[chave.strip().lower()] = valor.strip()

    nivel = info.get("level")
    return {
        "nivel_percentual": int(nivel) if nivel and nivel.isdigit() else None,
        "carregando": info.get("ac powered") == "true" or info.get("usb powered") == "true",
        "bruto": info,
    }


def pair(ip: str, port: int, pairing_code: str) -> str:
    """Pareamento sem fio (Android 11+): ip/porta/código vêm da tela
    Opções do desenvolvedor > Depuração sem fio > Parear dispositivo
    com código, no próprio celular."""
    result = _run(["pair", f"{ip}:{port}", pairing_code])
    return (result.stdout or result.stderr).strip()


def connect(ip: str, port: int = 5555) -> str:
    """Conecta por Wi-Fi a um aparelho já pareado (ou já em modo
    tcpip -- ver enable_tcpip())."""
    result = _run(["connect", f"{ip}:{port}"])
    return (result.stdout or result.stderr).strip()


def disconnect(ip: str = None, port: int = 5555) -> str:
    args = ["disconnect"] + ([f"{ip}:{port}"] if ip else [])
    result = _run(args)
    return (result.stdout or result.stderr).strip()


def enable_tcpip(port: int = 5555, device: str = None) -> str:
    """Muda um aparelho já conectado por USB para modo TCP/IP -- só
    precisa ser feito uma vez; depois dá pra desconectar o cabo e usar
    connect() por Wi-Fi enquanto o aparelho ficar na mesma rede."""
    args = (["-s", device] if device else []) + ["tcpip", str(port)]
    return _run(args).stdout.strip()


def device_ip(device: str = None) -> str:
    """Tenta descobrir o IP Wi-Fi do aparelho, lendo a tabela de rotas
    de dentro do próprio Android -- útil pra saber pra qual IP usar em
    connect() depois de enable_tcpip()."""
    saida = shell("ip route", device=device)
    for linha in saida.splitlines():
        partes = linha.split()
        if "src" in partes:
            return partes[partes.index("src") + 1]
    return ""


def list_packages(device: str = None) -> list:
    saida = shell("pm list packages", device=device)
    return [l.split(":", 1)[1].strip() for l in saida.splitlines() if l.startswith("package:")]


_APP_ALIASES = {
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome",
    "spotify": "com.spotify.music",
    "gmail": "com.google.android.gm",
    "play store": "com.android.vending",
    "playstore": "com.android.vending",
    "telegram": "org.telegram.messenger",
    "facebook": "com.facebook.katana",
    "tiktok": "com.zhiliaoapp.musically",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
}


def open_app(nome_ou_pacote: str, device: str = None) -> str:
    """Abre um app no celular por nome comum (ver _APP_ALIASES) ou
    nome de pacote exato; sem alias conhecido, procura nos pacotes
    instalados um que contenha o nome pedido. Retorna o pacote aberto,
    ou levanta RuntimeError se não achar nada parecido."""
    alvo = nome_ou_pacote.strip().lower()
    pacote = _APP_ALIASES.get(alvo)
    if not pacote:
        if "." in alvo:  # já parece um nome de pacote
            pacote = alvo
        else:
            instalados = list_packages(device=device)
            candidatos = [p for p in instalados if alvo.replace(" ", "") in p.lower()]
            if not candidatos:
                raise RuntimeError(f"Não encontrei nenhum app instalado no celular parecido com '{nome_ou_pacote}'.")
            pacote = candidatos[0]
    args = (["-s", device] if device else []) + [
        "shell", "monkey", "-p", pacote, "-c", "android.intent.category.LAUNCHER", "1",
    ]
    _run(args)
    return pacote


_NOTIF_PKG_RE = re.compile(r"NotificationRecord\(.*?pkg=(\S+)")
_NOTIF_EXTRA_RE = re.compile(r"android\.(title|text|bigText)=(?:String)?\s*\((.*)\)\s*$")


def list_notifications(package: str = None, device: str = None) -> list:
    """Lista notificações ativas no celular (leitura só -- não toca em
    nenhum app), via `dumpsys notification --noredact`. Retorna uma
    lista de dicts `{"pacote", "titulo", "texto"}`.

    Melhor-esforço: o formato de saída do `dumpsys` varia por versão
    do Android/fabricante e não é uma API garantida (ao contrário dos
    outros comandos deste módulo, que usam o protocolo ADB
    documentado). Funciona na maioria dos aparelhos modernos; se o
    Android estiver ocultando conteúdo por privacidade (notificações
    sensíveis na tela de bloqueio), título/texto podem vir vazios.

    `package`: filtra só notificações desse pacote (ex.:
    "com.instagram.android"). Sem isso, retorna de todos os apps.
    """
    saida = shell("dumpsys notification --noredact", device=device)
    resultado = []
    pacote_atual = None
    titulo = texto = None

    def _fechar_bloco():
        if pacote_atual and (titulo or texto) and (package is None or pacote_atual == package):
            resultado.append({"pacote": pacote_atual, "titulo": titulo, "texto": texto})

    for linha in saida.splitlines():
        m_pkg = _NOTIF_PKG_RE.search(linha)
        if m_pkg:
            _fechar_bloco()
            pacote_atual = m_pkg.group(1)
            titulo = texto = None
            continue
        m_extra = _NOTIF_EXTRA_RE.search(linha.strip())
        if m_extra:
            campo, valor = m_extra.group(1), m_extra.group(2)
            if campo == "title":
                titulo = valor
            elif campo in ("text", "bigText"):
                texto = valor
    _fechar_bloco()
    return resultado
