"""
main.py
========
Ponto de entrada do Neutron: interface de chat via terminal (ou voz).

Uso:
    python main.py           -> interface gráfica (fundo preto, orbe
                                 "molécula", chat) -- ver gui/app.py.
                                 Requer requirements-gui.txt; sem isso
                                 instalado, cai sozinho para o modo
                                 texto no terminal.
    python main.py --texto   -> força o modo texto no terminal
    python main.py --voz     -> inicia em modo de conversa por voz (ver voz/)

Comandos especiais dentro do chat:
    /sair              -> encerra o Neutron
    /historico         -> mostra as últimas mensagens
    /plugins           -> lista plugins carregados
    /recarregar        -> recarrega plugins (hot-reload)
    /aprendizado       -> mostra o resumo do que o Neutron aprendeu
    /consolidar        -> força a consolidação de assuntos frequentes em conhecimento
    /baseconhecimento  -> mostra estatísticas da base de conhecimento curada
    /modulos           -> status de cada módulo (ia, voz, visao, automacao, ...)
    /sistema           -> hardware detectado (CPU/GPU) e uso atual de recursos
    /backup            -> força um backup manual do banco de dados
    /atualizacoes      -> checa se há atualizações disponíveis (via git)
    /logs              -> mostra as últimas linhas do log
    /configurarapi     -> configura (ou troca) um provedor de IA, com validação real

No primeiro início sem nenhum provedor de IA configurado, o Neutron
pergunta se você quer configurar um agora (qualquer provedor,
incluindo NVIDIA) -- ver ia/setup.py. Responder "não" não pergunta de
novo nas próximas execuções; use /configurarapi quando quiser.

Variáveis de ambiente:
    JARVIS_SEM_DELAY=1  -> desliga a simulação de "digitando..." e
                           imprime a resposta na hora (útil para
                           testes automatizados ou quem prefere
                           respostas instantâneas).
"""

import argparse
import os
import random
import sys
import time

# Em alguns terminais Windows, `sys.stdout`/`sys.stderr` chegam
# configurados no codepage ANSI do sistema (ex.: cp1252) mesmo quando o
# console em si já está em UTF-8 -- e cp1252 não tem os caracteres de
# desenho de caixa do BANNER abaixo, o que derruba o programa com
# UnicodeEncodeError antes de imprimir qualquer coisa (a "interface"
# nunca chega a aparecer, seja a gráfica ou a de texto). Força UTF-8
# aqui, o mais cedo possível.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

from config.settings import get_settings
from core.jarvis import Jarvis
from core.personality import NOME

BANNER = f"""
███╗   ██╗███████╗██╗   ██╗████████╗██████╗  ██████╗ ███╗   ██╗
████╗  ██║██╔════╝██║   ██║╚══██╔══╝██╔══██╗██╔═══██╗████╗  ██║
██╔██╗ ██║█████╗  ██║   ██║   ██║   ██████╔╝██║   ██║██╔██╗ ██║
██║╚██╗██║██╔══╝  ██║   ██║   ██║   ██╔══██╗██║   ██║██║╚██╗██║
██║ ╚████║███████╗╚██████╔╝   ██║   ██║  ██║╚██████╔╝██║ ╚████║
╚═╝  ╚═══╝╚══════╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
                 {NOME} — digite /sair para encerrar
"""

_LEGACY_BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
        Assistente pessoal — digite /sair para encerrar
"""

# Simulação de "digitando...": pequena pausa antes de mostrar a
# resposta, proporcional ao tamanho do texto (com piso e teto), só
# para a resposta não aparecer instantânea como um questionário
# automático -- uma conversa real tem esse compasso. Desligue com
# JARVIS_SEM_DELAY=1 se preferir respostas imediatas.
_TYPING_DISABLED = os.environ.get("JARVIS_SEM_DELAY", "").strip() in ("1", "true", "True")


def _typing_delay(text: str) -> float:
    base = min(0.25 + len(text) * 0.01, 1.6)
    return base + random.uniform(0, 0.35)


def _print_resposta(texto: str, elapsed: float = 0.0):
    if _TYPING_DISABLED:
        print(f"{NOME}>\n{texto}\n")
        return

    # Se o processamento real (ex.: uma chamada de IA externa) já levou
    # mais tempo que o piso do "digitando...", não espera de novo --
    # esse tempo real já cumpriu o papel do delay simulado.
    restante = _typing_delay(texto) - elapsed
    if restante > 0:
        time.sleep(restante)
    sys.stdout.write("\r" + " " * 30 + "\r")
    sys.stdout.flush()
    print(f"{NOME}>\n{texto}\n")


def _process_and_print(jarvis: Jarvis, text: str):
    """Mostra o indicador de 'digitando...' ANTES de processar (não
    depois) -- uma resposta que depende de IA externa pode levar vários
    segundos de verdade, e sem isso a tela fica parada, sem feedback
    nenhum, dando a impressão de que travou."""
    if not _TYPING_DISABLED:
        sys.stdout.write(f"{NOME} está digitando...")
        sys.stdout.flush()

    inicio = time.time()
    resposta = jarvis.process(text)
    decorrido = time.time() - inicio

    _print_resposta(resposta, decorrido)


def _cmd_modulos(jarvis: Jarvis):
    print(jarvis.module_manager.report_text())


def _cmd_sistema():
    try:
        import sistema
    except Exception as e:
        print(f"Módulo 'sistema' indisponível: {e}")
        return
    report = sistema.full_report()
    print(f"CPU: {report['cpu']}")
    print(f"GPU: {report['gpu']}")
    snap = sistema.snapshot()
    print(
        f"Agora -> CPU: {snap.get('cpu_percent')}% | RAM: {snap.get('ram_percent')}% | "
        f"Disco: {snap.get('disco_percent')}%"
    )


def _cmd_backup():
    try:
        import seguranca
    except Exception as e:
        print(f"Módulo 'seguranca' indisponível: {e}")
        return
    try:
        path = seguranca.create_backup()
        print(f"Backup criado em: {path}")
    except Exception as e:
        print(f"Falha ao criar backup: {e}")


def _cmd_atualizacoes():
    try:
        import atualizacoes
    except Exception as e:
        print(f"Módulo 'atualizacoes' indisponível: {e}")
        return
    report = atualizacoes.check_for_updates()
    print(f"Versão local: {report['versao_local']}")
    print(report["motivo"])


def _cmd_logs():
    try:
        from logs.logger import tail
    except Exception as e:
        print(f"Módulo 'logs' indisponível: {e}")
        return
    lines = tail(20)
    print("\n".join(lines) if lines else "Nenhum log registrado ainda.")


def _run_ia_setup_wizard(ia_manager=None):
    """Assistente interativo: escolher provedor, informar chave/URL,
    validar de verdade com uma chamada mínima real e só então salvar
    em config/config.json. Aceita qualquer provedor suportado --
    incluindo NVIDIA (NIM / API Catalog), Ollama, LM Studio e um
    servidor OpenAI-compatível qualquer.

    `ia_manager` (opcional): quando chamado com o Jarvis JÁ em
    execução (comando "/configurarapi" no meio de uma sessão, ver
    run_text_mode), passa o `jarvis.ia_manager` pra invalidar o cache
    de provedores dele depois de salvar -- sem isso, a chave nova era
    salva certinho mas só passava a valer depois de reiniciar (bug
    real encontrado em auditoria, ver AIManager.refresh()). Quando
    chamado ANTES do Jarvis existir (primeira execução), não há
    ia_manager nenhum ainda -- None é seguro."""
    try:
        import ia.setup as ia_setup
    except Exception as e:
        print(f"Módulo 'ia' indisponível: {e}")
        return

    providers = ia_setup.list_providers()
    print("\nProvedores de IA suportados:")
    for i, (name, label, needs_key, default_url) in enumerate(providers, start=1):
        tag = "requer API key" if needs_key else "servidor local, sem API key"
        print(f"  {i:2}. {label} ({tag})")

    escolha = input("\nEscolha o número do provedor (ou ENTER para cancelar): ").strip()
    if not escolha:
        print("Configuração de IA cancelada.\n")
        return
    try:
        idx = int(escolha) - 1
        if idx < 0:
            raise ValueError
        name, label, needs_key, default_url = providers[idx]
    except (ValueError, IndexError):
        print("Opção inválida.\n")
        return

    api_key = ""
    if needs_key:
        api_key = input(f"Cole a API key de {label} (não é salva em texto puro no console): ").strip()
        if not api_key:
            print("Nenhuma chave informada. Configuração cancelada.\n")
            return

    base_url = ""
    if name not in ("anthropic", "gemini"):
        rotulo_url = default_url or "obrigatório informar"
        base_url = input(f"URL base da API (ENTER para usar {rotulo_url}): ").strip()

    model = input("Nome do modelo (ENTER para usar o padrão): ").strip()

    print("Validando conexão com uma chamada de teste...")
    ok, mensagem = ia_setup.test_provider(name, api_key=api_key, base_url=base_url, model=model)
    if ok:
        ia_setup.save_provider(name, api_key=api_key, base_url=base_url, model=model)
        if ia_manager is not None:
            ia_manager.refresh()
        print(f"{label} configurado com sucesso -- {mensagem}\n")
    else:
        print(f"Não consegui validar {label}: {mensagem}")
        retry = input("Tentar de novo (outro provedor, chave ou URL)? (s/N): ").strip().lower()
        if retry in ("s", "sim", "y", "yes"):
            _run_ia_setup_wizard(ia_manager)
        else:
            print("Configuração de IA cancelada. Rode /configurarapi quando quiser tentar de novo.\n")


def _maybe_prompt_ia_setup():
    """Roda uma vez por início do programa: se nenhum provedor de IA
    estiver configurado ainda E o usuário não tiver recusado antes,
    pergunta se quer configurar um agora. Nunca obrigatório -- o
    Neutron continua funcionando 100% local se a resposta for não."""
    try:
        import ia.setup as ia_setup
        from config.settings import get_settings
    except Exception:
        return

    settings = get_settings()
    if not settings.is_module_enabled("ia"):
        return
    if not settings.get("ia.perguntar_no_inicio", True):
        return
    if ia_setup.any_remote_provider_configured():
        return

    resp = input(
        f"\nNenhuma API de IA configurada ainda (isso é opcional -- o {NOME} já "
        "funciona sem ela). Quer configurar uma agora? (s/N): "
    ).strip().lower()

    if resp not in ("s", "sim", "y", "yes"):
        settings.set("ia.perguntar_no_inicio", False)
        settings.save()
        print("Sem problema. Quando quiser, use /configurarapi para configurar depois.\n")
        return

    _run_ia_setup_wizard()


def run_text_mode(jarvis: Jarvis, user_id: str):
    print(f"\n{NOME} pronto. Sessão de: {user_id}\n")

    while True:
        try:
            text = input("Você> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando. Até logo!")
            break

        if not text:
            continue

        cmd = text.lower()

        if cmd in ("/sair", "/exit", "/quit"):
            print(f"{NOME}> Até logo!")
            break

        if cmd == "/historico":
            hist = jarvis.memory.get_history(user_id, limit=20)
            for h in hist:
                print(f"  [{h['timestamp']}] {h['role']}: {h['content']}")
            continue

        if cmd == "/plugins":
            for name, desc in jarvis.plugins.list_plugins():
                print(f"  - {name}: {desc}")
            continue

        if cmd == "/recarregar":
            names = jarvis.reload_plugins()
            print(f"Plugins recarregados: {', '.join(names)}")
            continue

        if cmd == "/aprendizado":
            print(jarvis.knowledge.learning_summary(user_id))
            continue

        if cmd == "/consolidar":
            criados = jarvis.knowledge.consolidate(user_id, min_mentions=3)
            if criados:
                print(f"Consolidei {len(criados)} item(ns) de conhecimento a partir de assuntos frequentes:")
                for i in criados:
                    print(f"  #{i['id']} [{i['category']}] {i['content']} (confiança {i['confidence']}%)")
            else:
                print("Nenhum assunto com menções suficientes (3+) para consolidar ainda.")
            continue

        if cmd == "/baseconhecimento":
            stats = jarvis.knowledge_base.stats()
            from core.knowledge_base import KB_CATEGORY_LABELS
            for cat, n in stats.items():
                print(f"  {KB_CATEGORY_LABELS[cat]}: {n} entrada(s)")
            continue

        if cmd == "/modulos":
            _cmd_modulos(jarvis)
            continue

        if cmd == "/sistema":
            _cmd_sistema()
            continue

        if cmd == "/backup":
            _cmd_backup()
            continue

        if cmd == "/atualizacoes":
            _cmd_atualizacoes()
            continue

        if cmd == "/logs":
            _cmd_logs()
            continue

        if cmd == "/configurarapi":
            _run_ia_setup_wizard(jarvis.ia_manager)
            continue

        _process_and_print(jarvis, text)


def _pedir_user_id() -> str:
    """Pergunta o nome de usuário, sugerindo o último usado (persistido
    em config.json -> geral.usuario_padrao) em vez de sempre cair de
    volta pro literal "default_user". Sem isso, digitar o nome numa
    sessão e só apertar ENTER na próxima criava um perfil/memória
    SEPARADO ("default_user") a cada vez -- o Neutron parecia "esquecer"
    tudo porque, na prática, estava conversando com um usuário
    diferente. Ver gui/app.py:_ask_username() para o equivalente na GUI."""
    settings = get_settings()
    padrao = settings.get("geral.usuario_padrao", "default_user")
    digitado = input(f"Digite seu nome de usuário (ENTER para continuar como '{padrao}'): ").strip()
    if not digitado:
        return padrao
    if digitado != padrao:
        settings.set("geral.usuario_padrao", digitado)
        settings.save()
    return digitado


def main():
    parser = argparse.ArgumentParser(description=f"{NOME} - assistente pessoal")
    parser.add_argument("--voz", action="store_true", help="inicia em modo de conversa por voz")
    parser.add_argument(
        "--texto", action="store_true",
        help="força o modo texto no terminal (sem interface gráfica)",
    )
    args = parser.parse_args()

    if not args.voz and not args.texto:
        try:
            from gui.app import run_gui
        except Exception as e:
            print(BANNER)
            print(
                f"Interface gráfica indisponível ({e}).\n"
                "Instale as dependências com: pip install -r requirements-gui.txt\n"
                "Continuando em modo texto no terminal...\n"
            )
        else:
            run_gui()
            return

    print(BANNER)
    user_id = _pedir_user_id()

    _maybe_prompt_ia_setup()

    jarvis = Jarvis(user_id=user_id)

    if args.voz:
        try:
            from voz.loop import VoiceLoop
        except Exception as e:
            print(f"Módulo de voz indisponível: {e}")
            return
        loop = VoiceLoop(jarvis)
        if not loop.available():
            print(
                "Voz indisponível: instale as dependências em requirements-voz.txt "
                "(reconhecimento + síntese de voz) e verifique o microfone."
            )
            return
        loop.run()
        return

    run_text_mode(jarvis, user_id)


if __name__ == "__main__":
    main()
