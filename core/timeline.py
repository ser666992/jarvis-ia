"""
core/timeline.py
===================
"Linha do tempo de tudo que aconteceu no PC": junta os eventos
estruturados que os módulos de automação registram (abrir/fechar
programa, lembretes, habilidades criadas/aprovadas, janelas
controladas, logins usados, correções automáticas, etc.) numa lista
cronológica com descrições em português.

`registrar(tipo, descricao)` é um atalho fino sobre
`core/memory.py:Memory.log_event()` -- os módulos de automação chamam
isso nos pontos-chave (ver automacao/apps.py, automacao/reminders.py,
core/skill_forge.py, automacao/janelas.py, automacao/logins_web.py).
Eventos de rotina barulhentos (cada mensagem de chat, cada ajuste de
volume) ficam de propósito FORA da timeline, pra não afogar o que
importa -- só os pontos que os módulos decidiram valer a pena registrar.
"""

from datetime import datetime

_ROTULOS = {
    "startup": "Ultron foi iniciado",
    "modulo_ia_indisponivel": "Módulo de IA ficou indisponível",
    "auto_melhoria_sugestao": "Ultron sugeriu uma habilidade nova sozinho",
    "app_aberto": "Programa/site aberto",
    "app_fechado": "Programa encerrado",
    "lembrete_criado": "Lembrete criado",
    "lembrete_disparado": "Lembrete disparou",
    "habilidade_criada": "Habilidade nova gerada (rascunho)",
    "habilidade_aprovada": "Habilidade aprovada e ativada",
    "habilidade_rejeitada": "Rascunho de habilidade descartado",
    "programa_gerado": "Programa novo gerado",
    "programa_executado": "Programa executado",
    "correcao_gerada": "Ultron corrigiu um erro sozinho",
    "janela_controlada": "Janela de outro programa controlada",
    "login_salvo": "Login de site salvo",
    "login_usado": "Login automático usado",
    "comentario_tela": "Ultron comentou sobre sua tela",
    "tecnologia_aprendida": "Ultron pesquisou e aprendeu sobre uma tecnologia nova",
    "bateria_celular_baixa": "Bateria do celular ficou baixa (aviso automático)",
    "instagram_enviado": "Ultron respondeu sozinho no Instagram",
    "video_gravado": "Vídeo da tela gravado",
    "video_editado": "Vídeo editado (corte/aceleração)",
    "navegacao_web": "Ultron pesquisou e leu páginas na internet",
    "google_conectado": "Conta do Google conectada no navegador",
    "instagram_conectado": "Conta do Instagram conectada no navegador",
    "programa_aprendido": "Ultron aprendeu a usar um programa observando você",
    "app_instalado": "Programa instalado via winget",
    "gemeo_digital_testado": "Ultron testou uma alteração num gêmeo digital antes de aplicar de verdade",
    "sonho_apresentado": "Ultron inventou e testou uma ideia sozinho (\"sonho\")",
    "macro_criada": "Macro criada",
    "macro_executada": "Macro executada",
    "macro_agendada": "Macro agendada pra rodar sozinha",
    "visao_continua_evento": "Visão contínua detectou um evento na tela",
    "comando_executado": "Comando de sistema executado (controle_pc)",
    "processo_encerrado": "Processo travado encerrado (controle_pc)",
    "missao_criada": "Missão autônoma criada",
    "missao_passo": "Passo de missão executado ou verificado",
}


def registrar(event_type: str, descricao: str = ""):
    """Atalho pra registrar um evento na timeline sem cada módulo
    precisar instanciar Memory() e importar core.memory diretamente."""
    try:
        from config.settings import get_settings
        if get_settings().get("privacidade.modo_privado", False):
            return
    except Exception:
        pass
    from core.memory import Memory
    try:
        Memory().log_event(event_type, descricao)
    except Exception:
        pass  # nunca deixa o registro de timeline quebrar a ação em si


def _rotulo(event_type: str) -> str:
    return _ROTULOS.get(event_type, event_type)


def eventos_do_periodo(memory, desde: datetime, limite: int = 1000) -> list:
    eventos = memory.recent_events(limit=limite)
    resultado = []
    for ev in eventos:
        try:
            quando = datetime.fromisoformat(ev["timestamp"])
        except (KeyError, ValueError, TypeError):
            continue
        if quando < desde:
            continue
        if ev.get("event_type") not in _ROTULOS:
            continue  # evento de rotina não pensado pra aparecer na timeline
        resultado.append({
            "quando": quando,
            "tipo": ev["event_type"],
            "rotulo": _rotulo(ev["event_type"]),
            "descricao": ev.get("description") or "",
        })
    resultado.sort(key=lambda e: e["quando"])
    return resultado


def formatar_linha_do_tempo(memory, desde: datetime) -> str:
    eventos = eventos_do_periodo(memory, desde)
    if not eventos:
        return "Não encontrei nada registrado nesse período."
    linhas = []
    for ev in eventos:
        hora = ev["quando"].strftime("%d/%m %H:%M")
        desc = ev["descricao"]
        if desc:
            linhas.append(f"{hora} -- {ev['rotulo']}: {desc}")
        else:
            linhas.append(f"{hora} -- {ev['rotulo']}")
    return "\n".join(linhas)
