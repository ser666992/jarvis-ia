"""
core/diagnostico.py
======================
Diagnóstico completo: testa CADA sub-recurso (não só o pacote
top-level) numa passada só, pensado especificamente pra pegar o tipo
de quebra que `core/module_manager.py` (`/modulos`) não pega -- aquele
só confirma que o PACOTE importa; uma dependência cruzada quebrada (ex.:
Instagram automático sem nenhuma fonte de notificação, depois que o app
do celular que a alimentava foi removido) continua reportando "ok" lá,
porque o pacote em si segue importável. Aqui cada checagem testa a
disponibilidade REAL do recurso, item por item.

Exposto via "diagnóstico completo" em plugins/consciencia.py (que já
tinha o comando "diagnóstico" pro estado do PROCESSO -- memória,
uptime, plugins -- e essa parte apenas ACRESCENTA um checklist de
sub-recursos ali, em vez de virar um segundo comando concorrendo pela
mesma palavra).

Voz também reporta o estado da calibração do microfone
(`voz.microfone_calibrado`, ver voz/loop.py:_calibrar_se_necessario() e
plugins/calibracao_voz.py) -- não calibrado ainda conta como "não
pronto" (mesma convenção de qualquer outro sub-recurso aqui: falta
alguma coisa pra funcionar do jeito ideal), com o valor calibrado nos
detalhes quando já feito.

Todas as checagens são LOCAIS e RÁPIDAS (leitura de config, import,
verificação de binário/arquivo, no máximo um teste de socket local de
~300ms para o provedor de IA local) -- nenhuma chamada de rede de
verdade, então isto é seguro de rodar a qualquer momento sem gastar
tempo/limite de API.
"""

import os


def _item(area: str, nome: str, ok: bool, detalhe: str = "") -> dict:
    return {"area": area, "nome": nome, "ok": bool(ok), "detalhe": detalhe}


def _checar_ia() -> list:
    from ia.manager import AIManager
    resultado = []
    try:
        manager = AIManager()
        disponiveis = manager.available_providers()
        if disponiveis:
            nomes = ", ".join(p.name for p in disponiveis)
            resultado.append(_item("IA", "provedor de IA", True, f"pronto(s): {nomes}"))
        else:
            resultado.append(_item(
                "IA", "provedor de IA", False,
                "nenhum provedor configurado nem modelo local disponível -- veja /configurarapi",
            ))
    except Exception as e:
        resultado.append(_item("IA", "provedor de IA", False, f"erro ao checar: {e}"))
    return resultado


def _checar_voz() -> list:
    resultado = []
    try:
        from voz.stt import SpeechToText
        backend = SpeechToText().backend_disponivel()
        if backend:
            resultado.append(_item("Voz", "reconhecimento de fala (STT)", True, f"motor: {backend}"))
        else:
            resultado.append(_item(
                "Voz", "reconhecimento de fala (STT)", False,
                "sem motor de STT + microfone disponíveis (ver requirements-voz.txt)",
            ))
    except Exception as e:
        resultado.append(_item("Voz", "reconhecimento de fala (STT)", False, f"erro ao checar: {e}"))

    try:
        from voz.tts import TextToSpeech
        ok = TextToSpeech().available()
        resultado.append(_item("Voz", "síntese de fala (TTS)", ok, "" if ok else "instale 'pyttsx3'"))
    except Exception as e:
        resultado.append(_item("Voz", "síntese de fala (TTS)", False, f"erro ao checar: {e}"))

    try:
        from config.settings import get_settings
        settings = get_settings()
        calibrado = bool(settings.get("voz.microfone_calibrado", False))
        if calibrado:
            silencio = settings.get("voz.silencio_para_parar_segundos", 0.6)
            sensibilidade = settings.get("voz.sensibilidade_barge_in", 2.8)
            detalhe = f"silêncio pra parar: {silencio}s, sensibilidade do barge-in: {sensibilidade}"
        else:
            detalhe = (
                'ainda não calibrado -- diga "calibra o microfone", ou será pedido '
                "automaticamente na primeira vez do modo de voz (python main.py --voz)"
            )
        resultado.append(_item("Voz", "calibração do microfone", calibrado, detalhe))
    except Exception as e:
        resultado.append(_item("Voz", "calibração do microfone", False, f"erro ao checar: {e}"))
    return resultado


def _checar_visao() -> list:
    resultado = []
    checagens = [
        ("OCR (leitura de texto em tela/imagem)", "visao.ocr", "available"),
        ("captura de tela", "visao.screen", "available"),
        ("detecção de objetos (YOLO)", "visao.objects", "available"),
        ("detecção de gestos/mãos", "visao.gestures", "available"),
    ]
    for nome, modulo, fn in checagens:
        try:
            import importlib
            mod = importlib.import_module(modulo)
            ok = getattr(mod, fn)()
            resultado.append(_item("Visão", nome, ok, "" if ok else "dependência não instalada"))
        except Exception as e:
            resultado.append(_item("Visão", nome, False, f"erro ao checar: {e}"))

    try:
        from visao.camera import Camera
        ok = Camera().available()
        resultado.append(_item("Visão", "câmera", ok, "" if ok else "instale 'opencv-python'"))
    except Exception as e:
        resultado.append(_item("Visão", "câmera", False, f"erro ao checar: {e}"))

    try:
        import visao_continua
        ok = visao_continua.disponivel()
        resultado.append(_item("Visão", "visão contínua da tela", ok, "" if ok else "instale 'mss'"))
    except Exception as e:
        resultado.append(_item("Visão", "visão contínua da tela", False, f"erro ao checar: {e}"))
    return resultado


def _checar_automacao() -> list:
    resultado = []
    try:
        from automacao import logins_web
        ok = logins_web.available()
        resultado.append(_item(
            "Automação", "login automático em sites", ok,
            "" if ok else "instale 'keyring' + 'playwright' (e rode playwright install chromium)",
        ))
    except Exception as e:
        resultado.append(_item("Automação", "login automático em sites", False, f"erro ao checar: {e}"))

    try:
        from automacao import instagram_auto
        ok = instagram_auto.available()
        resultado.append(_item(
            "Automação", "Instagram (sugerir/enviar resposta)", ok,
            "" if ok else "instale 'playwright' (e rode playwright install chromium)",
        ))
    except Exception as e:
        resultado.append(_item("Automação", "Instagram (sugerir/enviar resposta)", False, f"erro ao checar: {e}"))

    # Checagem CRUZADA (o tipo que pegou o bug real do Instagram): mesmo
    # com o playwright disponível, a LEITURA de mensagens do Instagram
    # (e o ciclo automático) depende de uma fonte de notificação de
    # verdade -- inbox do app do celular (removido) OU ADB sem fio com
    # um aparelho pareado. Sem nenhum dos dois, "sugere resposta" e o
    # envio automático não têm o que ler, mesmo com tudo "disponível".
    try:
        from automacao.notification_inbox import todas as inbox_todas
        from dispositivos import adb
        tem_inbox = bool(inbox_todas())
        tem_adb = adb.available() and bool(adb.list_devices())
        ok = tem_inbox or tem_adb
        if ok:
            fonte = "inbox em memória" if tem_inbox else "ADB sem fio (celular pareado)"
            detalhe = f"fonte ativa: {fonte}"
        else:
            detalhe = (
                "sem nenhuma fonte de notificação do celular -- pareie por ADB "
                '("pareia o celular <ip>:<porta> <código>") pra habilitar leitura '
                "de notificações (Instagram etc.)"
            )
        resultado.append(_item("Automação", "fonte de notificações do celular", ok, detalhe))
    except Exception as e:
        resultado.append(_item("Automação", "fonte de notificações do celular", False, f"erro ao checar: {e}"))

    try:
        from automacao import watcher
        resultado.append(_item(
            "Automação", "observador de pastas", True,
            "backend: watchdog" if watcher.HAS_WATCHDOG else "backend: polling (fallback sem dependência)",
        ))
    except Exception as e:
        resultado.append(_item("Automação", "observador de pastas", False, f"erro ao checar: {e}"))
    return resultado


def _checar_dispositivos() -> list:
    resultado = []
    try:
        from dispositivos import adb
        ok = adb.available()
        if ok:
            try:
                pareados = adb.list_devices()
            except Exception:
                pareados = []
            detalhe = f"{len(pareados)} dispositivo(s) conectado(s)" if pareados else "nenhum celular pareado ainda"
        else:
            detalhe = "binário 'adb' não encontrado (nem em tools/platform-tools/, nem no PATH)"
        resultado.append(_item("Dispositivos", "ADB (celular Android)", ok, detalhe))
    except Exception as e:
        resultado.append(_item("Dispositivos", "ADB (celular Android)", False, f"erro ao checar: {e}"))

    for nome, modulo in (
        ("Bluetooth LE", "dispositivos.bluetooth_ble"),
        ("Serial (Arduino/ESP32)", "dispositivos.serial_device"),
        ("MQTT (IoT)", "dispositivos.mqtt"),
        ("SSH", "dispositivos.ssh_client"),
    ):
        try:
            import importlib
            mod = importlib.import_module(modulo)
            ok = mod.available()
            resultado.append(_item("Dispositivos", nome, ok, "" if ok else "dependência não instalada"))
        except Exception as e:
            resultado.append(_item("Dispositivos", nome, False, f"erro ao checar: {e}"))
    return resultado


def _checar_controle_pc() -> list:
    resultado = []
    try:
        from controle_pc import entrada
        ok = entrada.available()
        resultado.append(_item("Controle do PC", "mouse/teclado simulados", ok, "" if ok else "instale 'pyautogui'"))
    except Exception as e:
        resultado.append(_item("Controle do PC", "mouse/teclado simulados", False, f"erro ao checar: {e}"))

    try:
        from controle_pc import janelas
        ok = janelas.available()
        resultado.append(_item("Controle do PC", "organizar janelas", ok, "" if ok else "instale 'pygetwindow'"))
    except Exception as e:
        resultado.append(_item("Controle do PC", "organizar janelas", False, f"erro ao checar: {e}"))

    try:
        from controle_pc import elementos
        ok = elementos.HAS_PYWINAUTO
        resultado.append(_item(
            "Controle do PC", "localizar/clicar elemento por nome", ok,
            "" if ok else "só funciona no Windows",
        ))
    except Exception as e:
        resultado.append(_item("Controle do PC", "localizar/clicar elemento por nome", False, f"erro ao checar: {e}"))

    try:
        from controle_pc import energia
        ok = energia.available()
        resultado.append(_item("Controle do PC", "plano de energia (powercfg)", ok, "" if ok else "só funciona no Windows"))
    except Exception as e:
        resultado.append(_item("Controle do PC", "plano de energia (powercfg)", False, f"erro ao checar: {e}"))
    return resultado


def _checar_sistema() -> list:
    resultado = []
    try:
        from sistema import hardware
        gpu = hardware.detect_gpu()
        if gpu.get("disponivel"):
            resultado.append(_item("Sistema", "GPU", True, f'{gpu.get("nome", "?")} (via {gpu.get("backend", "?")})'))
        else:
            resultado.append(_item("Sistema", "GPU", False, "nenhuma GPU utilizável detectada (CPU só)"))
    except Exception as e:
        resultado.append(_item("Sistema", "GPU", False, f"erro ao checar: {e}"))

    try:
        import psutil  # noqa: F401
        resultado.append(_item("Sistema", "monitoramento de processos/recursos", True))
    except ImportError:
        resultado.append(_item("Sistema", "monitoramento de processos/recursos", False, "instale 'psutil'"))
    return resultado


def _checar_seguranca() -> list:
    resultado = []
    try:
        from seguranca.crypto import is_real_encryption
        ok = is_real_encryption()
        resultado.append(_item(
            "Segurança", "criptografia de segredos", ok,
            "" if ok else "sem 'cryptography' instalado -- caindo pra ofuscação, não criptografia real",
        ))
    except Exception as e:
        resultado.append(_item("Segurança", "criptografia de segredos", False, f"erro ao checar: {e}"))
    return resultado


def _checar_dados() -> list:
    """Checagens sobre o próprio estado de dados -- não são "recurso
    instalado ou não", mas ajudam a perceber se a memória/backup estão
    saudáveis."""
    resultado = []
    from core.memory import DB_PATH
    existe = os.path.isfile(DB_PATH)
    resultado.append(_item(
        "Dados", "banco de memória (data/jarvis.db)", existe,
        "será criado na primeira mensagem" if not existe else f"{os.path.getsize(DB_PATH) // 1024} KB",
    ))

    try:
        from seguranca.backup import list_backups
        backups = list_backups()
        resultado.append(_item(
            "Dados", "backups", bool(backups),
            f"{len(backups)} backup(s), o mais recente: {os.path.basename(backups[0])}" if backups
            else "nenhum backup ainda (roda automaticamente, ver seguranca.backup_horario)",
        ))
    except Exception as e:
        resultado.append(_item("Dados", "backups", False, f"erro ao checar: {e}"))
    return resultado


def _checar_jogos() -> list:
    """"Aprendiz de jogos" (jogos/) -- gravar demonstração só precisa
    de pynput/captura de tela; treinar/jogar sozinho também exigem
    `torch`, checado separadamente (uma máquina pode conseguir gravar
    mas não treinar, ainda). Também lista quantos jogos já têm alguma
    demonstração/sessão gravada."""
    resultado = []
    try:
        from jogos import gravador
        ok = gravador.available()
        resultado.append(_item(
            "Jogos", "gravar demonstração (pynput + captura de tela)", ok,
            "" if ok else "instale 'pynput' (requirements-automacao.txt) e 'mss' (requirements-visao.txt)",
        ))
    except Exception as e:
        resultado.append(_item("Jogos", "gravar demonstração (pynput + captura de tela)", False, f"erro ao checar: {e}"))

    try:
        from jogos.modelo import HAS_TORCH
        resultado.append(_item(
            "Jogos", "treinar/jogar sozinho (torch)", HAS_TORCH,
            "" if HAS_TORCH else "instale 'torch' (requirements-ia.txt)",
        ))
    except Exception as e:
        resultado.append(_item("Jogos", "treinar/jogar sozinho (torch)", False, f"erro ao checar: {e}"))

    try:
        from jogos import jogador
        ok = jogador.HAS_PYGETWINDOW if hasattr(jogador, "HAS_PYGETWINDOW") else False
        resultado.append(_item(
            "Jogos", "checagem de foco da janela (pygetwindow)", ok,
            "" if ok else "instale 'pygetwindow' (requirements-automacao.txt) -- sem isso, jogar sozinho fica indisponível por segurança",
        ))
    except Exception as e:
        resultado.append(_item("Jogos", "checagem de foco da janela (pygetwindow)", False, f"erro ao checar: {e}"))

    try:
        from jogos import armazenamento
        conhecidos = armazenamento.jogos_conhecidos()
        resultado.append(_item(
            "Jogos", "jogos com dados gravados", bool(conhecidos),
            ", ".join(conhecidos) if conhecidos else "nenhum ainda -- diga \"aprende a jogar <jogo>\"",
        ))
    except Exception as e:
        resultado.append(_item("Jogos", "jogos com dados gravados", False, f"erro ao checar: {e}"))
    return resultado


def rodar_diagnostico() -> list:
    """Roda todas as checagens e retorna uma lista de itens
    {"area", "nome", "ok", "detalhe"} -- quem chama decide como
    formatar (ver plugins/diagnostico.py:_formatar())."""
    itens = []
    for checagem in (
        _checar_ia, _checar_voz, _checar_visao, _checar_automacao,
        _checar_dispositivos, _checar_controle_pc, _checar_sistema,
        _checar_seguranca, _checar_dados, _checar_jogos,
    ):
        itens.extend(checagem())
    return itens
