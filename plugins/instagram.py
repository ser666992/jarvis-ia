"""
plugins/instagram.py
=======================
Por padrão, Jarvis SUGERE respostas pras suas mensagens do Instagram,
no seu estilo -- nunca envia nada sozinho.

Por quê só sugestão, por padrão, e não envio automático: não existe
API pública pra automatizar mensagens numa conta PESSOAL do Instagram.
A API oficial (Graph API/Messaging) só atende contas Business/Creator
conectadas a uma Página do Facebook, com aprovação prévia do Meta.
Automação não-oficial (bibliotecas tipo instagrapi, automação de
navegador) viola os Termos de Uso do Instagram e arrisca banir a
conta -- e responder como se fosse você, sem a pessoa do outro lado
saber, é enganoso independente da API.

**Envio automático é opcional e desligado por padrão** (config
`instagram.envio_automatico`) -- só liga com o comando explícito
"ativa o envio automático do instagram" abaixo, depois de confirmado
que o usuário entende e aceita o risco de banimento. Ver
automacao/instagram_auto.py pros redutores de risco (sessão
persistente, atraso humano, limite diário, log de auditoria na
timeline) e pro polling que efetivamente lê e responde sozinho.

Fonte das notificações -- **só ADB sem fio agora**
(`dispositivos/adb.py:list_notifications()`, via `dumpsys
notification` -- melhor-esforço, formato não é uma API garantida): o
app companion Android que alimentava `automacao/notification_inbox.py`
via `POST /notify` foi removido do projeto. `_mensagens_instagram()`
ainda checa o inbox em memória primeiro (por segurança/compat -- nunca
é populado sozinho, então cai direto pro ADB na prática).

A sugestão de resposta é gerada com um prompt de sistema PRÓPRIO (não
o do Jarvis -- ver ia/manager.py:chat(system_prompt=...)), pra não
herdar a persona configurada do Jarvis (inclusive o estilo "ultron"):
o texto sugerido precisa soar como VOCÊ escrevendo, não como o Jarvis.

"conecta minha conta do instagram" abre a página de login DE VERDADE
do Instagram numa aba -- você digita sua senha/2FA direto com o
Instagram, o Jarvis nunca vê nem guarda essa senha (mesmo princípio do
login com o Google, ver automacao/logins_web.py). A sessão fica salva
(perfil de navegador próprio, data/instagram_browser_profile/) pras
próximas vezes -- ler mensagens, e responder sozinho se o envio
automático estiver ligado.

Comandos:
    "minhas mensagens do instagram" / "tem mensagem nova no instagram"
    "sugere uma resposta pro instagram" / "responde a mensagem do instagram"
    "conecta minha conta do instagram" / "loga no instagram" / "entra no
    instagram" / "acessa o instagram" / "faz login no instagram" (todas
    abrem a mesma página de login de verdade, numa aba)
    "ativa o envio automático do instagram" / "desativa o envio automático do instagram"
"""

import re

from automacao.notification_inbox import mensagens_de as inbox_mensagens_de
from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.personality import NOME
from core.plugin_manager import BasePlugin
from dispositivos import adb

_INSTAGRAM_PKG = "com.instagram.android"

_LIST_RE = re.compile(
    r"\b(mensage(?:m|ns)|dm)\b.*\binstagram\b|\binstagram\b.*\b(mensage(?:m|ns)|dm)\b",
    re.IGNORECASE,
)
_SUGGEST_RE = re.compile(
    r"\b(sugir[ae]|sugest[aã]o|responde|resposta)\b.*\binstagram\b|"
    r"\binstagram\b.*\b(sugir[ae]|sugest[aã]o|resposta|responde)\b",
    re.IGNORECASE,
)
_ENABLE_AUTO_RE = re.compile(
    r"\b(ativ[ae]|lig[ae])\w*\s+.*\benvio\s+autom[aá]tico\b.*\binstagram\b|"
    r"\binstagram\b.*\benvio\s+autom[aá]tico\b.*\b(ativ[ae]|lig[ae])\w*\b",
    re.IGNORECASE,
)
_DISABLE_AUTO_RE = re.compile(
    r"\b(desativ[ae]|deslig[ae])\w*\s+.*\benvio\s+autom[aá]tico\b.*\binstagram\b",
    re.IGNORECASE,
)
# Aceita várias formas naturais de pedir pra entrar no Instagram --
# não só "conecta" -- porque "loga no instagram"/"entra no instagram"
# são frases comuns que, sem isso, cairiam no plugin genérico de login
# (logins_web.py), que tenta achar uma senha salva no keyring pra
# "instagram" (não existe, o Instagram usa sessão de navegador
# persistente, não keyring) e devolve um erro confuso em vez de abrir
# a página de login de verdade. Como instagram.py carrega ANTES de
# logins_web.py (ordem alfabética, ver core/plugin_manager.py), esse
# regex mais amplo garante que essas frases sejam resolvidas aqui.
_CONNECT_RE = re.compile(
    r"\b(conecta|acess[ae])\w*\s+.*\binstagram\b|"
    r"\blog[ae]\w*\s+(?:no|na|em)\s+.*\binstagram\b|"
    r"\bfa[çcz]\w*\s+login\s+(?:no|na|em)\s+.*\binstagram\b|"
    r"\bentr[ae]\w*\s+(?:no|na)\s+.*\binstagram\b|"
    r"\binstagram\b.*\b(conecta|acess[ae])\w*\b",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(
    r"\b(?:verific[ae]|confir[ae]|status)\w*\s+.*\b(?:conex[aã]o|conta|login)\b.*\binstagram\b|"
    r"\binstagram\b.*\b(?:conectad[oa]|logad[oa])\b",
    re.IGNORECASE,
)
_ANALISAR_ESTILO_RE = re.compile(
    r"\b(?:analis[ae]|aprend[ae])\w*\s+.*\b(?:conversas?|mensagens?|jeito\s+de\s+falar)\b"
    r".*\binstagram\b|\binstagram\b.*\b(?:perfil|estilo|personalidade)\b",
    re.IGNORECASE,
)


def _system_prompt_sugestao(contexto_extra: str) -> str:
    from config.settings import get_settings
    perfil = get_settings().get("instagram.perfil_resposta", "casual")
    estilos = {
        "casual": "casual, natural e breve",
        "profissional": "profissional, claro e cordial",
        "atendimento": "acolhedor, objetivo e focado em resolver",
        "vendas": "consultivo, útil e sem pressão",
        "amigos": "próximo, descontraído e espontâneo",
    }
    base = (
        f"Você está ajudando a redigir uma resposta de Instagram Direct em nome "
        f"do usuário -- você NÃO é o {NOME} respondendo aqui, é uma sugestão de "
        f"texto pra ELE mandar como se fosse a própria voz dele. Tom "
        f"{estilos.get(perfil, estilos['casual'])}, como uma mensagem de verdade "
        "entre pessoas -- nunca se "
        "identifique como assistente ou IA no texto sugerido, e não adicione "
        "nada além da resposta em si (sem 'aqui está uma sugestão:' ou aspas)."
    )
    if contexto_extra:
        base += f"\n\nContexto sobre o usuário (pra imitar melhor o estilo dele):\n{contexto_extra}"
    return base


class InstagramPlugin(BasePlugin):
    name = "instagram"
    description = "Sugere respostas pras mensagens do Instagram no seu estilo (você revisa e envia manualmente)"

    def matches(self, text: str) -> bool:
        return bool(
            _LIST_RE.search(text) or _SUGGEST_RE.search(text) or _CONNECT_RE.search(text)
            or _STATUS_RE.search(text) or _ENABLE_AUTO_RE.search(text)
            or _DISABLE_AUTO_RE.search(text) or _ANALISAR_ESTILO_RE.search(text)
        )

    def handle(self, text: str, context: dict):
        if _STATUS_RE.search(text):
            return self._status_instagram()
        if _ANALISAR_ESTILO_RE.search(text):
            return self._analisar_estilos(context)
        if _CONNECT_RE.search(text):
            return self._conectar_instagram()
        if _ENABLE_AUTO_RE.search(text):
            return self._ativar_envio_automatico(context)
        if _DISABLE_AUTO_RE.search(text):
            return self._desativar_envio_automatico()
        if _SUGGEST_RE.search(text):
            return self._sugerir_resposta(context)
        return self._listar_mensagens()

    def _analisar_estilos(self, context):
        jarvis = context.get("jarvis")
        if jarvis is None:
            return Answer("Não consigo analisar conversas neste contexto.", Confidence.GUESS)
        from automacao.instagram_auto import analisar_conversas_visiveis
        try:
            results = analisar_conversas_visiveis(jarvis)
        except Exception as e:
            return Answer(f"Não consegui analisar as conversas: {e}", Confidence.GUESS)
        success = [r for r in results if r["sucesso"]]
        failed = [r for r in results if not r["sucesso"]]
        lines = [
            f"- {r['contato']}: perfil criado com {r['mensagens']} mensagem(ns)"
            for r in success]
        if failed:
            lines.append(f"{len(failed)} conversa(s) sem texto suficiente ou com falha.")
        return Answer(
            f"Criei {len(success)} perfil(is) de comunicação.\n" + "\n".join(lines),
            Confidence.CONFIRMED if success else Confidence.GUESS)

    def _conectar_instagram(self):
        from automacao import instagram_auto

        if not instagram_auto.available():
            return Answer(
                "Instale 'playwright' (requirements-automacao.txt) e rode "
                "'python -m playwright install chromium' pra eu conseguir conectar sua conta do Instagram.",
                Confidence.GUESS,
            )
        try:
            mensagem = instagram_auto.conectar_instagram()
        except Exception as e:
            return Answer(f"Não consegui abrir o login do Instagram: {e}", Confidence.GUESS)
        return Answer(mensagem, Confidence.CONFIRMED)

    def _status_instagram(self):
        from automacao import instagram_auto

        if not instagram_auto.available():
            return Answer(
                "Não consigo verificar a conexão sem o Playwright instalado.",
                Confidence.GUESS,
            )
        if instagram_auto.instagram_conectado():
            try:
                from core.timeline import registrar
                registrar("instagram_conectado", "")
            except Exception:
                pass
            return Answer(
                "Conta do Instagram conectada e sessão confirmada.",
                Confidence.CONFIRMED,
            )
        return Answer(
            'A conta ainda não está conectada. Diga "conecta minha conta do instagram", '
            "conclua o login e a verificação em duas etapas na aba aberta, e depois peça "
            "para verificar novamente.",
            Confidence.CONFIRMED,
        )

    def _ativar_envio_automatico(self, context: dict):
        from automacao import instagram_auto

        if not instagram_auto.available():
            return Answer(
                "Instale 'playwright' e 'keyring' (requirements-automacao.txt), e rode "
                "'python -m playwright install chromium', antes de ligar o envio automático.",
                Confidence.GUESS,
            )
        settings = get_settings()
        settings.set("instagram.envio_automatico", True)
        settings.save()
        jarvis = context.get("jarvis")
        sessao_pronta = False
        try:
            from automacao import tasks
            if jarvis is None:
                raise RuntimeError("contexto do Neutron indisponível")
            sessao_pronta = instagram_auto._garantir_sessao_automatica(jarvis)
            tasks.schedule_recurring(
                "instagram_auto", instagram_auto._INTERVALO_POLL,
                instagram_auto._tick, jarvis)
        except Exception as e:
            return Answer(
                "Ativei a opção, mas não consegui iniciar a rotina automática agora: "
                f"{e}. Reinicie o Neutron e confira o status do Instagram.",
                Confidence.GUESS,
            )
        aviso_sessao = (
            ""
            if sessao_pronta
            else " A janela do Instagram foi aberta; confirme o login para a leitura começar."
        )
        return Answer(
            "Envio automático do Instagram LIGADO -- a partir de agora eu leio e respondo "
            "sozinho, sem te mostrar antes. Lembrete: isso viola os Termos de Uso do "
            "Instagram e pode banir a conta, e quem te manda mensagem não vai saber que "
            "está falando com um bot. Limite de segurança: até "
            f'{get_settings().get("instagram.limite_envios_por_dia", 15)} respostas automáticas '
            'por dia. Diga "desativa o envio automático do instagram" a qualquer momento pra voltar '
            "ao modo só-sugestão." + aviso_sessao,
            Confidence.CONFIRMED,
        )

    def _desativar_envio_automatico(self):
        settings = get_settings()
        settings.set("instagram.envio_automatico", False)
        settings.save()
        try:
            from automacao import tasks
            tasks.cancel_routine("instagram_auto")
        except Exception:
            pass
        return Answer(
            "Envio automático do Instagram DESLIGADO. Voltei ao modo só-sugestão -- "
            "você revisa e manda manualmente.",
            Confidence.CONFIRMED,
        )

    def _mensagens_instagram(self) -> list:
        """Checa o inbox em memória primeiro (automacao/notification_inbox.py)
        -- hoje sempre vazio, já que o app companion que o alimentava foi
        removido do projeto; mantido por segurança/compatibilidade. Na
        prática, sempre cai pro ADB sem fio abaixo."""
        from automacao.instagram_auto import mensagens_web
        da_web = mensagens_web()
        if da_web:
            return da_web
        do_app = inbox_mensagens_de(_INSTAGRAM_PKG)
        if do_app:
            return do_app

        if not adb.available() or not adb.list_devices():
            return []
        try:
            notifs = adb.list_notifications(package=_INSTAGRAM_PKG)
        except Exception as e:
            raise RuntimeError(f"Falha ao ler notificações do celular via ADB: {e}")
        return [n for n in notifs if n.get("texto")]

    def _listar_mensagens(self):
        try:
            mensagens = self._mensagens_instagram()
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        if not mensagens:
            return Answer(
                "Não vejo nenhuma mensagem do Instagram agora. Isso pode ser porque: "
                "(1) a sessão web expirou, (2) o Direct ainda está carregando, ou "
                "(3) não há notificações disponíveis no celular como fallback.",
                Confidence.CONFIRMED,
            )
        linhas = [f'- {m.get("titulo") or "alguém"}: "{m["texto"]}"' for m in mensagens]
        return Answer(
            "Conversas recentes do Instagram:\n" + "\n".join(linhas),
            Confidence.CONFIRMED,
        )

    def _sugerir_resposta(self, context: dict):
        try:
            mensagens = self._mensagens_instagram()
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        if not mensagens:
            return Answer(
                "Não achei nenhuma mensagem do Instagram pra sugerir resposta. "
                "Peça 'minhas mensagens do instagram' pra eu checar de novo.",
                Confidence.CONFIRMED,
            )

        ia_manager = context.get("ia_manager")
        if ia_manager is None:
            return Answer(
                "Preciso de um provedor de IA configurado pra sugerir uma resposta "
                "(veja /configurarapi). Sem isso, só consigo mostrar a mensagem em si.",
                Confidence.GUESS,
            )

        ultima = mensagens[-1]
        memory = context["memory"]
        contexto_extra = memory.get_context_summary(context["user_id"])
        try:
            from core.instagram_profiles import prompt_for
            perfil = prompt_for(context["user_id"], ultima.get("titulo") or "")
            if perfil:
                contexto_extra += f"\n\nEstilo específico desta conversa:\n{perfil}"
        except Exception:
            pass
        prompt = f'Mensagem recebida no Instagram de "{ultima.get("titulo") or "alguém"}": "{ultima["texto"]}"'

        try:
            _, sugestao = ia_manager.chat(
                prompt, history=[], system_prompt=_system_prompt_sugestao(contexto_extra),
            )
        except Exception as e:
            return Answer(f"Falha ao gerar sugestão: {e}", Confidence.GUESS)
        if not sugestao:
            return Answer("Não consegui gerar uma sugestão agora.", Confidence.GUESS)

        return Answer(
            f'Mensagem de "{ultima.get("titulo") or "alguém"}": "{ultima["texto"]}"\n\n'
            f'Sugestão de resposta (revise antes de mandar):\n"{sugestao.strip()}"',
            Confidence.RELIABLE_SOURCE,
        )
