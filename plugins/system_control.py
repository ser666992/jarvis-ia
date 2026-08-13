"""
plugins/system_control.py
==========================
Plugin de controle do computador.

Comandos de leitura (sempre seguros): hora, data, uso de CPU/RAM,
espaço em disco, processos, status do sistema.

Comandos de ação: abrir site/programa (reversível -- fechar depois
resolve), fechar programa (destrutivo -- exige confirmação explícita
na mesma frase ou na frase seguinte), volume, brilho, print da tela.
Propositalmente NÃO inclui: apagar arquivos, formatar, executar
comandos arbitrários do usuário, ou qualquer coisa irreversível de
verdade.

Nível de confiança: tudo aqui vem direto de leituras do sistema
operacional (relógio, psutil, disco) — não é informação buscada ou
inferida, é lida diretamente da fonte. Por isso usamos CONFIRMED (100).
Ações (abrir/fechar/volume/brilho/print) usam GUESS por convenção de
formato quando falham ou pedem confirmação, CONFIRMED quando executam.
"""

import datetime
import os
import platform
import re
import shutil
import sys
import webbrowser

from automacao import apps, janelas, media_keys
from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from seguranca.permissions import confirmado_pela_frase_ou_config
from sistema import display
from voz.tts import _RATE_PADRAO as _RATE_PADRAO_FALA

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Verbo "abrir" em várias conjugações ("abra", "abre", "abrir"), com
# tudo que vier depois capturado como alvo -- em vez de exigir a forma
# imperativa exata, porque "abre o youtube pra mim" é tão comum quanto
# "abra o youtube".
_OPEN_VERB_RE = re.compile(r"\b(?:abr[ae]|abrir)\b\s*(.*)", re.IGNORECASE)
_CLOSE_VERB_RE = re.compile(r"\b(?:feche|fecha|fechar|encerre|encerra|encerrar|mate|mata|matar)\b\s*(.*)", re.IGNORECASE)
_CONFIRM_WORD_RE = re.compile(
    r"\bconfirmo\b|\bconfirmar\b|\btenho certeza\b|\bpode fechar\b|\bpode mesmo\b|\bsim,? confirmo\b",
    re.IGNORECASE,
)
# Frases de preenchimento no fim do pedido ("...pra mim", "...por
# favor") que não fazem parte do nome do site/programa.
_FILLER_RE = re.compile(
    r"\b(pra mim|para mim|por favor|pfv|por gentileza|agora|a[íi])\b", re.IGNORECASE
)
_LEADING_ARTICLE_RE = re.compile(r"^(o|a|um|uma|meu|minha)\s+", re.IGNORECASE)

_VOLUME_UP_RE = re.compile(r"(aumenta|aumente|sobe|suba)\w*\s+.*\bvolume\b|\bvolume\b.*(mais alto|maior)", re.IGNORECASE)
_VOLUME_DOWN_RE = re.compile(r"(diminui|diminua|abaixa|abaixe|baixa|baixe)\w*\s+.*\bvolume\b|\bvolume\b.*(mais baixo|menor)", re.IGNORECASE)
_MUTE_RE = re.compile(r"\b(?:des)?mut[ae]\b|\bsilenci\w*\b.*\bsom\b|\btir\w*\s+o\s+som\b", re.IGNORECASE)

_BRIGHT_SET_RE = re.compile(r"\bbrilho\b.*?(\d{1,3})\s*%?", re.IGNORECASE)
_BRIGHT_UP_RE = re.compile(r"(aumenta|aumente|sobe|suba)\w*\s+.*\bbrilho\b", re.IGNORECASE)
_BRIGHT_DOWN_RE = re.compile(r"(diminui|diminua|abaixa|abaixe|baixa|baixe)\w*\s+.*\bbrilho\b", re.IGNORECASE)

_SCREENSHOT_RE = re.compile(
    r"\b(print|screenshot|captura[r]?)\b.*\btela\b|\btela\b.*\b(print|screenshot|captura)\b",
    re.IGNORECASE,
)

_PERSONALITY_ULTRON_RE = re.compile(
    r"(ativ[ae]|lig[ae]|ligue)\w*\s+.*\bpersonalidade\b.*\bultron\b|\bmodo ultron\b|\bpersonalidade ultron\b",
    re.IGNORECASE,
)
_PERSONALITY_PADRAO_RE = re.compile(
    r"\bpersonalidade\b.*\bpadr[aã]o\b|\bmodo (normal|padr[aã]o)\b|desativ\w*\s+.*\bultron\b",
    re.IGNORECASE,
)
_SHOW_CONFIDENCE_RE = re.compile(
    r"(mostr[ae]|exib[ae]|ativ[ae])\w*\s+.*\bconfian[çc]a\b", re.IGNORECASE
)
_HIDE_CONFIDENCE_RE = re.compile(
    r"(esconde\w*|oculta\w*|tira\w*|desativ\w*)\s+.*\bconfian[çc]a\b", re.IGNORECASE
)
_SHOW_PROVIDER_RE = re.compile(
    r"(mostr[ae]|exib[ae]|ativ[ae])\w*\s+.*\b(provedor|fonte)\b.*\b(ia|intelig[êe]ncia)\b", re.IGNORECASE
)
_HIDE_PROVIDER_RE = re.compile(
    r"(esconde\w*|oculta\w*|tira\w*|desativ\w*)\s+.*\b(provedor|fonte)\b.*\b(ia|intelig[êe]ncia)\b", re.IGNORECASE
)
_NO_CONFIRM_RE = re.compile(
    r"\b(n[ãa]o\s+pe[çc]a\s+confirma[çc][ãa]o|executa\s+sem\s+confirmar|"
    r"desativ[ae]\w*\s+.*\bconfirma[çc][ãa]o\b)", re.IGNORECASE
)
_YES_CONFIRM_RE = re.compile(
    r"\b(pe[çc]a\s+confirma[çc][ãa]o|confirma\s+antes\s+de\s+executar|"
    r"ativ[ae]\w*\s+.*\bconfirma[çc][ãa]o\b)", re.IGNORECASE
)
_FALA_RAPIDO_RE = re.compile(r"\bfal[ae]\w*\s+mais\s+r[áa]pid[oa]\b", re.IGNORECASE)
_FALA_DEVAGAR_RE = re.compile(r"\bfal[ae]\w*\s+mais\s+devagar\b|\bfal[ae]\w*\s+mais\s+lent[oa]\b", re.IGNORECASE)
_FALA_NORMAL_RE = re.compile(r"\bvelocidade\s+normal\s+d[ae]\s+fala\b|\bfal[ae]\w*\s+n[ao]\s+velocidade\s+normal\b", re.IGNORECASE)

# Controle de JANELA (minimizar/maximizar/restaurar/focar) -- diferente
# de _CLOSE_VERB_RE acima, que mata o processo inteiro. Aqui a janela
# continua existindo, só muda de estado visual -- ver automacao/janelas.py.
_MINIMIZE_RE = re.compile(r"\bminimiz\w+\b\s*(.*)", re.IGNORECASE)
_MAXIMIZE_RE = re.compile(r"\bmaximiz\w+\b\s*(.*)", re.IGNORECASE)
_RESTORE_WINDOW_RE = re.compile(r"\brestaur\w+\b\s*(?:a\s+janela\s+d[oa]\s+)?(.*)", re.IGNORECASE)
_FOCUS_RE = re.compile(
    r"\bfoc[ae]\w*\s+(?:n[oa]\s+)?(.+)|"
    r"\btra[gz]\w*\s+(?:o|a)\s+(.+?)\s+(?:pra|para)\s+(?:frente|o primeiro plano|primeiro plano)",
    re.IGNORECASE,
)

_DEFAULT_SITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
}


class SystemControlPlugin(BasePlugin):
    name = "system_control"
    description = "Controle do computador: abrir/fechar apps, volume, brilho, print da tela, status"
    triggers = [
        "abra", "abre", "abrir", "feche", "fecha", "fechar", "encerre", "encerra", "mate", "mata",
        "que horas", "hora atual", "data de hoje",
        "uso de cpu", "uso de memoria", "uso de memória", "espaço em disco",
        "espaco em disco", "listar processos", "processos rodando",
        "status do sistema", "informações do sistema", "informacoes do sistema",
        "volume", "mute", "muta", "desmuta", "silenci",
        "brilho", "print", "screenshot", "captura",
        "personalidade", "modo ultron", "modo normal", "modo padrão", "modo padrao",
        "confiança", "confianca", "provedor", "confirmação", "confirmacao",
        "minimiza", "minimize", "maximiza", "maximize", "restaura", "restaure",
        "foca", "foque", "focar", "traz", "traga", "primeiro plano",
        "fala mais rápido", "fala mais rapido", "fala mais devagar",
        "fala mais lento", "velocidade normal da fala",
    ]

    # Nome comum -> alvo que o Windows sabe resolver (executável
    # registrado em App Paths, ou no PATH). Programas fora desta lista
    # ainda são tentados diretamente pelo nome dito -- muitos apps se
    # registram no Windows com o próprio nome do executável.
    # Nomes mais LONGOS/específicos primeiro (ex.: "google chrome" antes de
    # qualquer coisa) -- _abrir() escolhe o primeiro alias cujo nome bate
    # como palavra, então navegadores conhecidos vencem o site homônimo
    # ("abre o google chrome" abre o navegador, não o google.com).
    APP_ALIASES = {
        "google chrome": "chrome.exe",
        "microsoft edge": "msedge.exe",
        "visual studio code": "code",
        "explorador de arquivos": "explorer.exe",
        "bloco de notas": "notepad.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "firefox": "firefox.exe",
        "brave": "brave.exe",
        "opera": "opera.exe",
        "steam": "steam.exe",
        "discord": "discord.exe",
        "spotify": "spotify.exe",
        "navegador": "chrome.exe",
        "notepad": "notepad.exe",
        "calculadora": "calc.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "vscode": "code",
    }

    def _sites(self) -> dict:
        configurados = get_settings().get("automacao.sites", {}) or {}
        return {**_DEFAULT_SITES, **configurados}

    def matches(self, text: str) -> bool:
        # Este plugin tem MUITOS comandos, e vários regexes em handle()
        # aceitam frases cujas palavras não estão todas na lista
        # `triggers` (que só serve de UI/documentação). Sem este
        # override, o default do BasePlugin (substring contra
        # `triggers`) bloqueava silenciosamente frases reais como
        # "executa sem confirmar", "confirma antes de executar" e
        # "tira o som" antes mesmo de handle() rodar -- por isso aqui
        # replicamos exatamente as mesmas checagens de handle().
        t = text.lower()
        if (
            "que horas" in t or "hora atual" in t or "data de hoje" in t
            or "que dia é hoje" in t or "que dia e hoje" in t or "qual a data" in t
            or "uso de cpu" in t or "uso de memoria" in t or "uso de memória" in t
            or ("bateria" in t and "celular" not in t)
            or "espaço em disco" in t or "espaco em disco" in t
            or "listar processos" in t or "processos rodando" in t
            or "status do sistema" in t or "informações do sistema" in t or "informacoes do sistema" in t
        ):
            return True
        return bool(
            _PERSONALITY_ULTRON_RE.search(t) or _PERSONALITY_PADRAO_RE.search(t)
            or _SHOW_CONFIDENCE_RE.search(t) or _HIDE_CONFIDENCE_RE.search(t)
            or _SHOW_PROVIDER_RE.search(t) or _HIDE_PROVIDER_RE.search(t)
            or _NO_CONFIRM_RE.search(t) or _YES_CONFIRM_RE.search(t)
            or _FALA_RAPIDO_RE.search(t) or _FALA_DEVAGAR_RE.search(t) or _FALA_NORMAL_RE.search(t)
            or _MINIMIZE_RE.search(t) or _MAXIMIZE_RE.search(t)
            or _RESTORE_WINDOW_RE.search(t) or _FOCUS_RE.search(t)
            or _CLOSE_VERB_RE.search(t) or _OPEN_VERB_RE.search(t)
            or _MUTE_RE.search(t) or _VOLUME_UP_RE.search(t) or _VOLUME_DOWN_RE.search(t)
            or _BRIGHT_SET_RE.search(t) or _BRIGHT_UP_RE.search(t) or _BRIGHT_DOWN_RE.search(t)
            or _SCREENSHOT_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.lower()

        if "que horas" in t or "hora atual" in t:
            return Answer(f"Agora são {datetime.datetime.now().strftime('%H:%M:%S')}.",
                          Confidence.CONFIRMED)

        if "data de hoje" in t or "que dia é hoje" in t or "que dia e hoje" in t or "qual a data" in t:
            # %A/%B viriam em inglês (locale C padrão do Python) -- monta
            # o dia da semana/mês em português na mão.
            agora = datetime.datetime.now()
            dias = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                    "sexta-feira", "sábado", "domingo")
            return Answer(
                f"Hoje é {dias[agora.weekday()]}, {agora.strftime('%d/%m/%Y')}.",
                Confidence.CONFIRMED,
            )

        if "bateria" in t and "celular" not in t:
            # Bateria do PC (a do celular é o device_control, que exige
            # a palavra "celular" e roda antes deste plugin no dispatch).
            bat = None
            if HAS_PSUTIL:
                try:
                    bat = psutil.sensors_battery()
                except Exception:
                    bat = None
            if bat is None:
                return Answer(
                    "Este computador não tem bateria (ou o Windows não a expõe) -- "
                    'é um desktop na tomada. Pra ver a do celular, diga "bateria do celular".',
                    Confidence.CONFIRMED,
                )
            estado = "carregando" if bat.power_plugged else "na bateria"
            return Answer(f"Bateria do PC: {bat.percent:.0f}% ({estado}).", Confidence.CONFIRMED)

        if _PERSONALITY_ULTRON_RE.search(t):
            return self._set_personalidade("ultron")
        if _PERSONALITY_PADRAO_RE.search(t):
            return self._set_personalidade("padrao")

        if _SHOW_CONFIDENCE_RE.search(t):
            return self._set_mostrar_confianca(True)
        if _HIDE_CONFIDENCE_RE.search(t):
            return self._set_mostrar_confianca(False)

        if _SHOW_PROVIDER_RE.search(t):
            return self._set_mostrar_provedor_ia(True)
        if _HIDE_PROVIDER_RE.search(t):
            return self._set_mostrar_provedor_ia(False)

        if _NO_CONFIRM_RE.search(t):
            return self._set_exigir_confirmacao(False)
        if _YES_CONFIRM_RE.search(t):
            return self._set_exigir_confirmacao(True)

        if _FALA_RAPIDO_RE.search(t):
            return self._ajustar_velocidade_fala(25)
        if _FALA_DEVAGAR_RE.search(t):
            return self._ajustar_velocidade_fala(-25)
        if _FALA_NORMAL_RE.search(t):
            return self._ajustar_velocidade_fala(None)

        m = _MINIMIZE_RE.search(t)
        if m:
            return self._janela("minimizar", m.group(1))
        m = _MAXIMIZE_RE.search(t)
        if m:
            return self._janela("maximizar", m.group(1))
        m = _RESTORE_WINDOW_RE.search(t)
        if m:
            return self._janela("restaurar", m.group(1))
        m = _FOCUS_RE.search(t)
        if m:
            return self._janela("focar", m.group(1) or m.group(2))

        m = _CLOSE_VERB_RE.search(t)
        if m:
            return self._fechar(m.group(1))

        m = _OPEN_VERB_RE.search(t)
        if m:
            return self._abrir(m.group(1))

        if _MUTE_RE.search(t):
            return self._mute()
        if _VOLUME_UP_RE.search(t):
            return self._volume(media_keys.volume_up, "aumentado")
        if _VOLUME_DOWN_RE.search(t):
            return self._volume(media_keys.volume_down, "diminuído")

        m = _BRIGHT_SET_RE.search(t)
        if m:
            return self._brilho_definir(int(m.group(1)))
        if _BRIGHT_UP_RE.search(t):
            return self._brilho_ajustar(10)
        if _BRIGHT_DOWN_RE.search(t):
            return self._brilho_ajustar(-10)

        if _SCREENSHOT_RE.search(t):
            return self._print_tela()

        if "uso de cpu" in t:
            if HAS_PSUTIL:
                return Answer(f"Uso de CPU: {psutil.cpu_percent(interval=0.5)}%",
                              Confidence.CONFIRMED)
            return Answer("Instale 'psutil' (pip install psutil) para eu conseguir ler o uso de CPU.",
                          Confidence.GUESS)

        if "uso de memoria" in t or "uso de memória" in t:
            if HAS_PSUTIL:
                mem = psutil.virtual_memory()
                return Answer(
                    f"Memória usada: {mem.percent}% ({mem.used // (1024**2)}MB de {mem.total // (1024**2)}MB)",
                    Confidence.CONFIRMED
                )
            return Answer("Instale 'psutil' (pip install psutil) para eu conseguir ler a memória.",
                          Confidence.GUESS)

        if "espaço em disco" in t or "espaco em disco" in t:
            total, used, free = shutil.disk_usage("/")
            return Answer(
                f"Disco: {used // (1024**3)}GB usados de {total // (1024**3)}GB "
                f"({free // (1024**3)}GB livres).",
                Confidence.CONFIRMED
            )

        if "listar processos" in t or "processos rodando" in t:
            if HAS_PSUTIL:
                procs = sorted(psutil.process_iter(["pid", "name"]),
                                key=lambda p: p.info["name"] or "")[:15]
                lines = [f"{p.info['pid']}: {p.info['name']}" for p in procs]
                return Answer("Alguns processos em execução:\n" + "\n".join(lines),
                              Confidence.CONFIRMED)
            return Answer("Instale 'psutil' (pip install psutil) para eu listar processos.",
                          Confidence.GUESS)

        if "status do sistema" in t or "informações do sistema" in t or "informacoes do sistema" in t:
            info = (
                f"Sistema: {platform.system()} {platform.release()}\n"
                f"Versão Python: {sys.version.split()[0]}\n"
                f"Máquina: {platform.machine()}"
            )
            return Answer(info, Confidence.CONFIRMED)

        return None

    def _abrir(self, resto: str):
        alvo = _FILLER_RE.sub("", resto).strip(" ,.!?")
        alvo = _LEADING_ARTICLE_RE.sub("", alvo).strip()
        alvo_low = alvo.lower()
        # Você não precisa dizer ".exe"/".apk" -- se disser, tiro o sufixo.
        alvo_low = re.sub(r"\.(exe|apk|app|lnk|com\b)$", "", alvo_low).strip()

        if not alvo_low:
            return Answer("Abrir o quê? Diga o nome do site ou programa.", Confidence.GUESS)

        # 1) URL/domínio explícito ("abre github.com", "abre https://...") -> site.
        if alvo_low.startswith("http") or re.search(r"\b[\w-]+\.(com|net|org|br|io|gov|edu|dev|me)\b", alvo_low):
            url = alvo if alvo.lower().startswith("http") else "https://" + alvo_low
            webbrowser.open(url)
            return Answer(f"Abrindo {alvo_low}...", Confidence.CONFIRMED)

        # 2) PROGRAMA conhecido tem prioridade sobre site quando o nome dele
        #    aparece como palavra -- é o que conserta "abre o google chrome"
        #    (que abria o site google.com em vez do navegador, por causa do
        #    'google' dentro da frase). Nome específico de app = quer o app.
        for nome_app, exe in self.APP_ALIASES.items():
            if re.search(r"\b" + re.escape(nome_app) + r"\b", alvo_low):
                try:
                    apps.open_program(exe)
                    return Answer(f"Abrindo {nome_app}...", Confidence.CONFIRMED)
                except Exception:
                    break  # não conseguiu abrir esse -- segue pros próximos caminhos

        # 3) SITE conhecido por palavra inteira (não substring solta).
        for site_name, url in self._sites().items():
            if re.search(r"\b" + re.escape(site_name) + r"\b", alvo_low):
                webbrowser.open(url)
                return Answer(f"Abrindo {site_name}...", Confidence.CONFIRMED)

        # 4) Tenta abrir como programa pelo nome dito (com ou sem alias).
        programa = self.APP_ALIASES.get(alvo_low, alvo_low)
        try:
            apps.open_program(programa)
            return Answer(f"Abrindo {alvo_low}...", Confidence.CONFIRMED)
        except Exception:
            # 5) Não é programa conhecido -- oferece abrir como busca na web,
            #    em vez de só dar erro.
            import urllib.parse
            busca = "https://www.google.com/search?q=" + urllib.parse.quote(alvo_low)
            webbrowser.open(busca)
            return Answer(
                f'Não achei um programa chamado "{alvo_low}" instalado, então pesquisei ele na '
                f'web. Se for um programa, me diga o nome do executável (ex.: "steam.exe"), ou '
                f'"instala o {alvo_low}" pra eu instalar via winget.',
                Confidence.GUESS,
            )

    def _fechar(self, resto: str):
        confirmado = confirmado_pela_frase_ou_config(bool(_CONFIRM_WORD_RE.search(resto)))
        alvo = _CONFIRM_WORD_RE.sub("", resto)
        alvo = _FILLER_RE.sub("", alvo).strip(" ,.!?")
        alvo = _LEADING_ARTICLE_RE.sub("", alvo).strip()

        if not alvo:
            return Answer("Fechar o quê?", Confidence.GUESS)

        if not confirmado:
            return Answer(
                f'Tem certeza que quer fechar "{alvo}"? Isso encerra o programa sem salvar '
                f'nada em aberto. Diga "feche {alvo}, confirmo" pra eu fazer de verdade.',
                Confidence.GUESS,
            )

        try:
            n = apps.close_program(alvo, confirmed=True)
        except Exception as e:
            return Answer(f'Não consegui fechar "{alvo}": {e}', Confidence.GUESS)
        if n == 0:
            return Answer(f'Não encontrei nenhum programa rodando parecido com "{alvo}".', Confidence.CONFIRMED)
        return Answer(f'Encerrei {n} processo(s) de "{alvo}".', Confidence.CONFIRMED)

    def _janela(self, acao: str, resto: str):
        alvo = _FILLER_RE.sub("", resto or "").strip(" ,.!?")
        alvo = _LEADING_ARTICLE_RE.sub("", alvo).strip()
        if not alvo:
            return Answer(f"{acao.capitalize()} o quê? Diga o nome da janela/programa.", Confidence.GUESS)
        if not janelas.available():
            return Answer(
                "Instale 'pygetwindow' (requirements-automacao.txt) para eu controlar janelas.",
                Confidence.GUESS,
            )
        try:
            encontrada = getattr(janelas, acao)(alvo)
        except Exception as e:
            return Answer(f'Não consegui {acao} "{alvo}": {e}', Confidence.GUESS)
        if not encontrada:
            return Answer(f'Não encontrei nenhuma janela aberta parecida com "{alvo}".', Confidence.CONFIRMED)
        verbo_passado = {
            "minimizar": "Minimizei", "maximizar": "Maximizei",
            "restaurar": "Restaurei", "focar": "Trouxe pra frente",
        }[acao]
        return Answer(f'{verbo_passado} a janela de "{alvo}".', Confidence.CONFIRMED)

    def _volume(self, acao, particípio: str):
        if not media_keys.available():
            return Answer("Controle de volume só está implementado no Windows.", Confidence.GUESS)
        try:
            acao()
        except Exception as e:
            return Answer(f"Não consegui ajustar o volume: {e}", Confidence.GUESS)
        return Answer(f"Volume {particípio}.", Confidence.CONFIRMED)

    def _mute(self):
        if not media_keys.available():
            return Answer("Controle de volume só está implementado no Windows.", Confidence.GUESS)
        try:
            media_keys.mute_toggle()
        except Exception as e:
            return Answer(f"Não consegui mutar/desmutar: {e}", Confidence.GUESS)
        return Answer("Som mutado/desmutado.", Confidence.CONFIRMED)

    def _brilho_definir(self, percent: int):
        if not display.available():
            return Answer("Controle de brilho requer Windows.", Confidence.GUESS)
        try:
            novo = display.set_brightness(percent)
        except Exception as e:
            return Answer(
                f"Não consegui ajustar o brilho ({e}). Isso geralmente acontece em "
                "monitores externos, que só têm brilho controlado pelos botões físicos.",
                Confidence.GUESS,
            )
        return Answer(f"Brilho ajustado para {novo}%.", Confidence.CONFIRMED)

    def _brilho_ajustar(self, delta: int):
        if not display.available():
            return Answer("Controle de brilho requer Windows.", Confidence.GUESS)
        try:
            novo = display.adjust_brightness(delta)
        except Exception as e:
            return Answer(
                f"Não consegui ajustar o brilho ({e}). Isso geralmente acontece em "
                "monitores externos, que só têm brilho controlado pelos botões físicos.",
                Confidence.GUESS,
            )
        return Answer(f"Brilho ajustado para {novo}%.", Confidence.CONFIRMED)

    def _print_tela(self):
        try:
            from visao.screen import save_screenshot
        except Exception as e:
            return Answer(f"Módulo de captura de tela indisponível: {e}", Confidence.GUESS)

        pasta = os.path.join("data", "screenshots")
        os.makedirs(pasta, exist_ok=True)
        nome = f"tela_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        caminho = os.path.join(pasta, nome)
        try:
            save_screenshot(caminho)
        except Exception as e:
            return Answer(f"Não consegui capturar a tela: {e}", Confidence.GUESS)
        return Answer(f"Print salvo em {caminho}.", Confidence.CONFIRMED)

    def _set_personalidade(self, estilo: str):
        settings = get_settings()
        settings.set("personalidade.estilo", estilo)
        settings.save()
        if estilo == "ultron":
            return Answer(
                "Personalidade ultron ativada. Prossiga -- se conseguir acompanhar.",
                Confidence.CONFIRMED,
            )
        return Answer("Personalidade padrão restaurada.", Confidence.CONFIRMED)

    def _set_mostrar_confianca(self, mostrar: bool):
        settings = get_settings()
        settings.set("personalidade.mostrar_confianca", mostrar)
        settings.save()
        if mostrar:
            return Answer(
                "Ok, volto a mostrar o bloco de confiança nas respostas.", Confidence.CONFIRMED,
            )
        return Answer(
            "Ok, não vou mais mostrar o bloco de confiança -- só o texto da resposta.",
            Confidence.CONFIRMED,
        )

    def _set_mostrar_provedor_ia(self, mostrar: bool):
        settings = get_settings()
        settings.set("personalidade.mostrar_provedor_ia", mostrar)
        settings.save()
        if mostrar:
            return Answer(
                "Ok, volto a mostrar qual provedor de IA gerou cada resposta.", Confidence.CONFIRMED,
            )
        return Answer(
            "Ok, não vou mais mostrar qual provedor de IA gerou a resposta -- só o texto.",
            Confidence.CONFIRMED,
        )

    def _set_exigir_confirmacao(self, exigir: bool):
        settings = get_settings()
        settings.set("seguranca.exigir_confirmacao_acoes_destrutivas", exigir)
        settings.save()
        if exigir:
            return Answer(
                "Ok, volto a pedir confirmação antes de ações como fechar programa, instalar "
                "algo, rodar código gerado, etc.",
                Confidence.CONFIRMED,
            )
        return Answer(
            "Ok, vou executar essas ações direto, sem pedir confirmação (fechar programa, "
            "instalar algo, rodar código gerado, etc.) -- diga \"peça confirmação\" a qualquer "
            "momento pra voltar a ter essa segurança.",
            Confidence.CONFIRMED,
        )

    def _ajustar_velocidade_fala(self, delta: int):
        """delta=None reseta pro padrão; +/-N ajusta a partir do valor
        atual, com teto/piso pra nunca virar ruído ininteligível (muito
        rápido) nem arrastado (muito devagar). Vale pra próxima fala --
        não interrompe uma fala já em andamento."""
        settings = get_settings()
        if delta is None:
            nova = _RATE_PADRAO_FALA
        else:
            atual = int(settings.get("voz.velocidade_fala", _RATE_PADRAO_FALA))
            nova = max(120, min(350, atual + delta))
        settings.set("voz.velocidade_fala", nova)
        settings.save()
        if delta is None:
            return Answer(f"Velocidade da fala de volta ao normal ({nova}).", Confidence.CONFIRMED)
        return Answer(
            f"Velocidade da fala ajustada pra {nova}"
            + (" -- diga de novo pra acelerar ainda mais." if delta > 0 else " -- diga de novo pra desacelerar ainda mais.")
            + ' Diga "velocidade normal da fala" pra voltar ao padrão.',
            Confidence.CONFIRMED,
        )