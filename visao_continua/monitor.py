"""
visao_continua/monitor.py
============================
Implementação do Módulo 1 (visão contínua da tela). Roda em segundo
plano via `automacao.tasks.schedule_recurring` -- mesmo mecanismo já
usado por auto_melhoria/aprendizado_autonomo/habitos/sonhos/instagram_auto,
nada novo na arquitetura.

Design pensado pra "alta eficiência" (pedido explícito):
  1. A cada tick, primeiro faz só as checagens BARATAS: um novo
     screenshot reduzido (poucos KB, via slicing puro em numpy, sem
     redimensionamento de biblioteca) comparado ao anterior, e a lista
     de processos rodando (psutil, já rápido por natureza).
  2. Só roda a parte CARA (OCR + enumeração de elementos de UI via
     UI Automation) quando a checagem barata indica que a tela mudou
     de verdade, ou quando processos abriram/fecharam -- do contrário,
     um monitor "contínuo" reprocessaria a mesma tela parada dezenas de
     vezes por minuto à toa.

Desligado por padrão (`visao_continua.ativa`, `false`) -- diferente da
maioria dos outros módulos automáticos deste projeto, que assumem
"provavelmente inofensivo, ligado por padrão". Vigiar a tela o tempo
todo é sensível por natureza (pode conter senhas sendo digitadas,
conversas privadas, dados financeiros) mesmo sendo só a SUA própria
tela, no seu próprio computador -- por isso exige ativação explícita
("liga a visão contínua"), mesmo padrão de risco->opt-in já usado para
`instagram.envio_automatico`.
"""

import collections
import sys
import time

from logs.logger import get_logger

log = get_logger("visao_continua")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# IMPORTANTE: pywinauto NÃO é importado aqui em cima, de propósito.
# Importar pywinauto executa código de inicialização de COM (apartment
# threading) na hora do import -- fazer isso durante
# core/jarvis.py:_startup_diagnostics() (thread principal, junto de
# outras libs que também mexem em COM, como win32com/Playwright)
# causava `[WinError -2147417850] Não é possível alterar o modo de
# thread depois de o mesmo estar definido` (RPC_E_CHANGED_MODE) --
# erro real, reproduzido e visto no log. A importação fica dentro de
# _elementos_janela_foco(), que só roda de dentro do tick em segundo
# plano (thread própria, criada por automacao.tasks.schedule_recurring),
# nunca na thread principal -- resolve o conflito na raiz.
HAS_PYWINAUTO = sys.platform == "win32"

_ROTINA_NOME = "visao_continua"

# Tipos de controle (UI Automation) que correspondem ao pedido
# ("botões, menus, caixas de diálogo") -- outros tipos (Pane, Group,
# Separator, texto estático genérico) são ruído pra esse propósito e
# só inflariam a lista sem ajudar a entender o que está na tela.
# Ordem importa (por isso é tupla, não mais um set): Dialog/Window
# primeiro (o sinal mais importante -- uma caixa de diálogo aparecendo
# -- e tipicamente poucos itens, então quase não consome o teto),
# ListItem/TabItem por último (podem existir aos milhares numa lista
# grande, e são o tipo menos crítico pra "o que está acontecendo").
_TIPOS_RELEVANTES = ("Dialog", "Window", "Button", "MenuItem", "Menu", "TabItem", "ListItem")
_MAX_ELEMENTOS = 40

# Palavras-chave (heurística, não é NLP de verdade) pra classificar
# eventos a partir do texto/nome de elementos vistos na tela -- ver
# docstring de _detectar_eventos_por_texto() pra limitação honesta.
# Lista propositalmente ampla (várias variantes pt/en de cada evento):
# uma lista curta demais é a causa mais comum de "não percebeu que
# tinha um erro na tela" -- essa detecção é casamento de substring, só
# funciona pra variantes que estão explicitamente aqui.
_PALAVRAS_ERRO = (
    "erro", "error", "falhou", "falha ao", "failed", "failure", "exception",
    "não responde", "nao responde", "not responding", "travou", "crashed",
    "problema ao", "não foi possível", "nao foi possivel", "unable to",
    "invalid", "inválido", "invalido", "not found", "não encontrado", "nao encontrado",
)
_PALAVRAS_ATUALIZACAO = (
    "atualização disponível", "atualizacao disponivel", "update available",
    "nova versão", "nova versao", "new version", "atualização necessária",
    "atualizacao necessaria", "update required", "reiniciar para atualizar",
    "restart to update",
)
_PALAVRAS_DOWNLOAD = (
    "download conclu", "concluído", "concluido", "transferência concluída",
    "transferencia concluida", "download complete", "download finished",
    "instalação concluída", "instalacao concluida", "installation complete",
)

_estado = {
    "ativo": False,
    "ultima_obs": None,
    "ultimo_frame_pequeno": None,
    "processos_conhecidos": None,
    "historico": None,  # deque, criado em _garantir_estado() (precisa do maxlen do config)
    "ultimo_erro_avisado": None,  # assinatura do último erro já notificado -- evita avisar de novo a cada tick pro MESMO erro parado na tela
}


def disponivel() -> bool:
    from visao.screen import available as screen_available
    return screen_available()


def _garantir_estado():
    if _estado["historico"] is None:
        from config.settings import get_settings
        maxlen = int(get_settings().get("visao_continua.manter_historico", 20))
        _estado["historico"] = collections.deque(maxlen=maxlen)
    if _estado["processos_conhecidos"] is None:
        _estado["processos_conhecidos"] = _processos_rodando()


def _processos_rodando() -> set:
    if not HAS_PSUTIL:
        return set()
    try:
        return {p.info.get("name") for p in psutil.process_iter(["name"]) if p.info.get("name")}
    except Exception:
        return set()


def _frame_pequeno(frame):
    """Reduz o screenshot a uma miniatura (~64x36) só com slicing puro
    em numpy -- suficiente pra detectar SE algo mudou, sem o custo de
    uma biblioteca de redimensionamento de imagem pra uma checagem que
    roda a cada poucos segundos.

    Usa a MÉDIA dos 3 canais (aproximação barata de luminância), não
    mais só o canal azul (BGR[0]) sozinho -- um valor só perdia mudanças
    que mexem principalmente no vermelho/verde (ex.: um aviso/banner
    vermelho aparecendo sobre um fundo já predominantemente azul), o que
    contribuía pra "a visão contínua não percebeu que algo mudou". A
    média ainda é só slicing + uma operação vetorizada barata -- mesmo
    custo desprezível de antes."""
    if not HAS_NUMPY or frame is None:
        return None
    altura, largura = frame.shape[0], frame.shape[1]
    passo_y = max(1, altura // 36)
    passo_x = max(1, largura // 64)
    return frame[::passo_y, ::passo_x, :].astype("int16").mean(axis=2)


def _mudou_o_suficiente(atual, anterior, limiar: float) -> bool:
    if atual is None:
        return False
    if anterior is None:
        return True
    if anterior.shape != atual.shape:
        return True
    diff = np.abs(atual - anterior)
    return float(diff.mean()) >= limiar


def _hwnd_janela_foco():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def _janela_travada(hwnd) -> bool:
    """Usa a API do próprio Windows feita pra isso (IsHungAppWindow) --
    muito mais confiável que tentar inferir 'travou' comparando pixels
    (uma tela parada não significa travado; um vídeo tocando não
    significa que não travou)."""
    if not hwnd or sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsHungAppWindow(hwnd))
    except Exception:
        return False


def _elementos_janela_foco(hwnd) -> list:
    """Enumera botões/menus/diálogos da janela em foco via UI
    Automation (pywinauto) -- muito mais confiável e barato que tentar
    'ver' botões a partir de pixels (visão computacional de verdade
    pra isso exigiria um modelo de detecção de objetos, caro e ainda
    assim menos preciso que a árvore de acessibilidade que o próprio
    Windows já expõe).

    IMPORTANTE (correção de desempenho real): a versão anterior chamava
    `janela.descendants()` SEM filtro nenhum -- isso enumera e materializa
    TODOS os descendentes da janela (via UI Automation, uma chamada COM
    fora de processo por elemento pra ler `control_type`/`name`), e só
    DEPOIS filtrava por tipo em Python. Pra apps com árvore de UI grande
    (Chrome, VS Code, Electron em geral facilmente têm milhares de nós
    Pane/Group/Text) isso significa milhares de chamadas COM pagas
    inteiramente à toa antes do corte de `_MAX_ELEMENTOS` conseguir
    ajudar em qualquer coisa -- a causa real de "a visão contínua trava/
    demora" em janelas complexas (o README já admitia "1-2 segundos a
    mais", que na prática podia ser bem mais que isso). Agora cada tipo
    relevante é buscado com `descendants(control_type=tipo)`, que passa
    a condição pro UI Automation nativo (`FindAll` com
    `CreatePropertyCondition`) -- só os elementos que já batem o tipo
    voltam pra cá, então o custo de marshaling/COM cai proporcionalmente
    à fração de elementos relevantes (tipicamente pequena) em vez do
    total da árvore. Some-se a isso que o loop externo já para assim que
    `_MAX_ELEMENTOS` é atingido, então tipos "caros" (ex.: ListItem, que
    pode ter centenas numa lista grande) muitas vezes nem chegam a ser
    consultados."""
    if not HAS_PYWINAUTO or not hwnd:
        return []
    try:
        from pywinauto import Desktop as _PywinautoDesktop  # import atrasado -- ver comentário no topo do arquivo
        janela = _PywinautoDesktop(backend="uia").window(handle=hwnd)
        elementos = []
        for tipo in _TIPOS_RELEVANTES:
            if len(elementos) >= _MAX_ELEMENTOS:
                break
            try:
                achados = janela.descendants(control_type=tipo)
            except Exception:
                continue
            for c in achados:
                try:
                    nome = (c.element_info.name or "").strip()
                    if not nome:
                        continue
                    elementos.append({"tipo": tipo, "nome": nome[:120]})
                    if len(elementos) >= _MAX_ELEMENTOS:
                        break
                except Exception:
                    continue
        return elementos
    except Exception as e:
        log.warning("falha ao enumerar elementos de UI: %s", e)
        return []


def _texto_para_analise(obs: dict) -> str:
    partes = [obs.get("texto_tela") or ""]
    partes += [e["nome"] for e in obs.get("elementos", [])]
    return " \n".join(partes).lower()


def _detectar_eventos_por_texto(obs: dict) -> list:
    """Heurística por palavra-chave (pt/en) pra sinalizar erro/
    atualização/download concluído -- NÃO é compreensão de linguagem
    de verdade, é casamento de substring. Suficiente pra avisar "acho
    que vi um erro na tela", insuficiente pra confiar cegamente (podem
    existir falsos positivos/negativos). Documentado honestamente no
    README deste módulo."""
    texto = _texto_para_analise(obs)
    eventos = []
    if any(p in texto for p in _PALAVRAS_ERRO):
        eventos.append("possivel_erro_na_tela")
    if any(p in texto for p in _PALAVRAS_ATUALIZACAO):
        eventos.append("possivel_atualizacao_disponivel")
    if any(p in texto for p in _PALAVRAS_DOWNLOAD):
        eventos.append("possivel_download_concluido")
    if any(e.get("tipo") == "Dialog" for e in obs.get("elementos", [])):
        eventos.append("caixa_de_dialogo_na_tela")
    return eventos


def _detectar_eventos_processos(processos_antes: set, processos_agora: set) -> list:
    eventos = []
    for novo in processos_agora - processos_antes:
        eventos.append(f"programa_aberto:{novo}")
    for sumiu in processos_antes - processos_agora:
        eventos.append(f"programa_fechado:{sumiu}")
    return eventos


def _montar_observacao(ocr_ligado: bool) -> dict:
    from visao.observe import active_process_name, active_window_title, visible_screen_text

    hwnd = _hwnd_janela_foco()
    obs = {
        "timestamp": time.time(),
        "janela": active_window_title(),
        "processo": active_process_name(),
        "texto_tela": visible_screen_text() if ocr_ligado else None,
        "elementos": _elementos_janela_foco(hwnd),
        "travada": _janela_travada(hwnd),
        "eventos": [],
    }
    obs["eventos"] = _detectar_eventos_por_texto(obs)
    if obs["travada"] and obs.get("janela"):
        obs["eventos"].append(f"programa_travado:{obs['janela']}")
    return obs


def _registrar_eventos(eventos: list):
    if not eventos:
        return
    from core.timeline import registrar
    for evento in eventos:
        registrar("visao_continua_evento", evento)


def _assinatura_erro(obs: dict) -> str:
    return f"{obs.get('janela')}|{(obs.get('texto_tela') or '')[:200]}"


def _gerar_explicacao_erro(obs: dict, jarvis=None) -> str:
    """Pede pra IA configurada (mesma usada no resto do Ultron, via
    `jarvis.ia_manager`) uma explicação curta do possível erro visto na
    tela -- degrada pra uma mensagem genérica sem IA disponível (nunca
    trava, nunca fica sem avisar)."""
    ia_manager = getattr(jarvis, "ia_manager", None)
    texto_tela = (obs.get("texto_tela") or "")[:600]
    if ia_manager is not None:
        prompt = (
            "Percebi um possível erro na tela do usuário (detecção por palavra-chave, "
            "pode ser falso positivo).\n"
            f"Janela em foco: {obs.get('janela') or 'desconhecida'}.\n"
            f"Texto visível: {texto_tela or 'não disponível'}.\n\n"
            "Em 1-3 frases, explique o que esse erro provavelmente significa e sugira um "
            "próximo passo -- breve, direto, não alarmista. Se não der pra saber com esse "
            "texto, diga isso honestamente em vez de inventar."
        )
        try:
            _, resposta = ia_manager.chat(prompt, history=[])
            if resposta:
                return resposta
        except Exception as e:
            log.warning("falha ao gerar explicação de erro via IA: %s", e)
    alvo = obs.get("janela") or obs.get("processo") or "sua tela"
    return f'Notei algo que parece um erro em "{alvo}" -- dá uma olhada quando puder.'


def _avisar_proativamente(obs: dict, jarvis=None):
    """Assistência proativa opt-in (`personalidade.assistencia_proativa`,
    desligado por padrão): quando a visão contínua já detectou um
    possível erro na tela por conta própria, avisa com uma explicação
    gerada por IA em vez de exigir que o usuário pergunte. Só notifica
    UMA vez por erro (assinatura = janela + trecho do texto) -- sem
    isso, um erro parado na tela junto de qualquer outra mudança visual
    (cursor piscando, animação) reavisaria a cada tick."""
    if "possivel_erro_na_tela" not in obs.get("eventos", []):
        _estado["ultimo_erro_avisado"] = None
        return
    from config.settings import get_settings
    if not get_settings().get("personalidade.assistencia_proativa", False):
        return
    assinatura = _assinatura_erro(obs)
    if assinatura == _estado.get("ultimo_erro_avisado"):
        return
    _estado["ultimo_erro_avisado"] = assinatura
    explicacao = _gerar_explicacao_erro(obs, jarvis)
    from automacao.notify import notify
    notify("Assistência proativa", explicacao)
    from core.timeline import registrar
    registrar("assistencia_proativa_erro", explicacao[:150])


def _tick(jarvis=None):
    _garantir_estado()
    from config.settings import get_settings
    settings = get_settings()
    limiar = float(settings.get("visao_continua.limiar_mudanca", 12.0))

    from visao.screen import screenshot
    try:
        frame = screenshot()
    except Exception as e:
        log.warning("falha ao capturar tela pra visão contínua: %s", e)
        return

    # --- Checagem barata de processos (sempre roda, custo baixo) ---
    processos_agora = _processos_rodando()
    eventos_processos = _detectar_eventos_processos(_estado["processos_conhecidos"], processos_agora)
    _estado["processos_conhecidos"] = processos_agora

    # --- Checagem barata de mudança visual (decide se vale a pena a parte cara) ---
    pequeno = _frame_pequeno(frame)
    mudou = _mudou_o_suficiente(pequeno, _estado["ultimo_frame_pequeno"], limiar)
    _estado["ultimo_frame_pequeno"] = pequeno

    if not mudou and not eventos_processos:
        return  # nada relevante -- economiza OCR/enumeração de UI à toa

    from visao.ocr import available as ocr_available
    obs = _montar_observacao(ocr_ligado=ocr_available())
    obs["eventos"] = eventos_processos + obs["eventos"]

    _estado["ultima_obs"] = obs
    _estado["historico"].append(obs)
    _registrar_eventos(obs["eventos"])
    _avisar_proativamente(obs, jarvis)


def iniciar(jarvis=None):
    """Chamado no startup do Ultron (core/jarvis.py) -- só realmente
    ativa o loop em segundo plano se `visao_continua.ativa` estiver
    ligado no config (desligado por padrão, ver docstring do módulo)."""
    from config.settings import get_settings
    if not get_settings().get("visao_continua.ativa", False):
        return
    ligar(jarvis)


def ligar(jarvis=None):
    if not disponivel():
        raise RuntimeError("Instale 'mss' (requirements-visao.txt) para eu conseguir ver a tela.")
    _garantir_estado()
    _estado["ativo"] = True
    from automacao import tasks
    from config.settings import get_settings
    intervalo = float(get_settings().get("visao_continua.intervalo_segundos", 3.0))
    tasks.schedule_recurring(_ROTINA_NOME, intervalo, _tick, jarvis)


def parar():
    from automacao import tasks
    _estado["ativo"] = False
    return tasks.cancel_routine(_ROTINA_NOME)


def ativo() -> bool:
    return bool(_estado["ativo"])


def estado_atual() -> dict:
    """Retrato estruturado mais recente -- outros módulos/plugins
    consultam isto em vez de cada um fazer sua própria captura de
    tela. Retorna None se a visão contínua nunca rodou um tick ainda
    (ex.: acabou de ligar)."""
    _garantir_estado()
    return _estado["ultima_obs"]


def historico(n: int = 5) -> list:
    _garantir_estado()
    return list(_estado["historico"])[-n:]


def descrever_para_prompt(max_chars: int = 400) -> str:
    """Resumo curto pra injetar no contexto da IA (mesmo padrão de
    core/estado_interno.py:descrever_para_prompt) -- só retorna algo
    quando a visão contínua está ativa E já tem pelo menos uma
    observação; string vazia caso contrário, pra não poluir o prompt
    com "nada a reportar" toda hora."""
    if not ativo():
        return ""
    obs = estado_atual()
    if not obs:
        return ""
    partes = [f"[Visão contínua da tela] Janela em foco: {obs.get('janela') or 'desconhecida'}"]
    if obs.get("processo"):
        partes.append(f"Processo: {obs['processo']}")
    if obs.get("eventos"):
        partes.append("Eventos recentes: " + ", ".join(obs["eventos"]))
    texto = " | ".join(partes)
    return texto[:max_chars]
