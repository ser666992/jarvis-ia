"""
automacao/musica.py
======================
Tocar música por comando, direto no Spotify ou no YouTube.

Honestidade sobre o que dá pra fazer sem a API paga de cada serviço:
- **YouTube**: com Playwright instalado, o Ultron abre o YouTube, busca
  a música e clica no primeiro resultado -> TOCA de verdade (o vídeo dá
  autoplay). Sem Playwright, abre a página de busca no navegador padrão
  (aí você clica). O navegador fica aberto tocando.
- **Spotify**: abre o app do Spotify (ou o Spotify web) já na busca pela
  música. Tocar automaticamente a faixa certa exigiria a Web API do
  Spotify + conta Premium + autenticação (bem mais pesado) -- então aqui
  ele te deixa na busca e você dá o play. É o "direto" possível sem isso.

O navegador do YouTube (Playwright) fica guardado num global pra NÃO ser
fechado quando a função retorna (senão a música pararia na hora).
"""

import os
import urllib.parse
import webbrowser

from logs.logger import get_logger

log = get_logger("automacao")

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

_sessao_yt = {}  # mantém o navegador do YouTube vivo tocando entre chamadas


def _perfil_youtube() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(base, "data", "youtube_music_profile")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def tocar_youtube(query: str) -> str:
    query = query.strip()
    if not query:
        return "Tocar o quê no YouTube?"
    busca = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"

    if not HAS_PLAYWRIGHT:
        webbrowser.open(busca)
        return f'Abri a busca de "{query}" no YouTube -- clica no primeiro vídeo pra tocar.'

    pw = None
    contexto = None
    try:
        from automacao.browser_engine import kwargs_launch
        # Fecha uma sessão anterior antes de abrir outra (evita várias
        # músicas tocando ao mesmo tempo).
        _fechar_youtube()
        pw = sync_playwright().start()
        contexto = pw.chromium.launch_persistent_context(_perfil_youtube(), headless=False, **kwargs_launch())
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        pagina.goto(busca, wait_until="domcontentloaded", timeout=20000)
        # Dá tempo da página assentar antes de procurar qualquer coisa --
        # sem isso, o clique no consentimento de cookies (se aparecer) e a
        # busca pelo primeiro vídeo competem com o carregamento ainda em
        # andamento (achado real: causava timeout intermitente esperando
        # o link do vídeo aparecer, mesmo ele existindo segundos depois).
        pagina.wait_for_timeout(1500)
        # Consentimento de cookies (aparece em algumas regiões) -- clica se houver.
        for txt in ("Aceitar tudo", "Accept all", "Concordo", "I agree", "Reject all", "Rejeitar tudo"):
            try:
                botao = pagina.get_by_role("button", name=txt)
                if botao.count() > 0:
                    botao.first.click(timeout=2000)
                    pagina.wait_for_timeout(1000)
                    break
            except Exception:
                pass
        # Primeiro vídeo do resultado -> clicar abre a página e dá autoplay.
        alvo = pagina.locator("a#video-title, ytd-video-renderer a#video-title").first
        alvo.wait_for(timeout=15000)
        alvo.click(timeout=10000)
        pagina.wait_for_timeout(800)
        _sessao_yt["pw"] = pw
        _sessao_yt["contexto"] = contexto
        _sessao_yt["page"] = pagina
        try:
            from automacao import janelas
            titulo = pagina.title() or "YouTube"
            janelas.forcar_foco(titulo[:30] if titulo != "YouTube" else "YouTube")
        except Exception:
            pass
        return f'Tocando "{query}" no YouTube. Diga "pausa a música" ou "próxima música" pra controlar.'
    except Exception as e:
        log.warning("musica: falha no autoplay do YouTube (%s) -- abrindo a busca no navegador", e)
        # Sem isso, o navegador aberto pela tentativa acima ficava
        # órfão (aberto, mas fora de _sessao_yt) -- achado real: um
        # processo de Chromium/Brave a mais rodando pra sempre em
        # segundo plano a cada autoplay que falhasse.
        for fechar in (lambda: contexto and contexto.close(), lambda: pw and pw.stop()):
            try:
                fechar()
            except Exception:
                pass
        webbrowser.open(busca)
        return (
            f'Não consegui tocar "{query}" automaticamente no YouTube (abri só a busca) -- '
            "clica no primeiro vídeo pra tocar."
        )


def _fechar_youtube():
    ctx = _sessao_yt.pop("contexto", None)
    pw = _sessao_yt.pop("pw", None)
    _sessao_yt.pop("page", None)
    for fechar in (lambda: ctx and ctx.close(), lambda: pw and pw.stop()):
        try:
            fechar()
        except Exception:
            pass


def parar_youtube() -> bool:
    if "contexto" not in _sessao_yt:
        return False
    _fechar_youtube()
    return True


def tocar_spotify(query: str) -> str:
    query = query.strip()
    if not query:
        return "Tocar o quê no Spotify?"
    uri = f"spotify:search:{urllib.parse.quote(query)}"
    web = f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
    # Tenta o app do Spotify (deep link) primeiro; se não houver app
    # registrado pro esquema spotify:, cai pro Spotify web.
    try:
        if os.name == "nt":
            os.startfile(uri)
        else:
            webbrowser.open(uri)
        # Se o Spotify já estiver aberto (comum -- ele fica rodando em
        # segundo plano/bandeja), o deep link só atualiza a busca dentro
        # do processo existente e a janela pode continuar escondida --
        # achado real: o usuário via a resposta de sucesso mas nada
        # aparecia na tela, porque a janela nunca vinha pra frente.
        try:
            from automacao import janelas
            janelas.forcar_foco("spotify")
        except Exception:
            pass
        return (
            f'Abri o Spotify na busca por "{query}" -- é só dar play na faixa. '
            "(Tocar a faixa exata sozinho precisaria da API do Spotify + Premium.)"
        )
    except Exception:
        webbrowser.open(web)
        return f'Abri o Spotify web na busca por "{query}" -- dá o play na faixa.'


def tocar(query: str, servico: str = None) -> str:
    """Toca `query` no serviço pedido. Sem serviço explícito, usa o
    YouTube (o que mais confiavelmente TOCA sozinho)."""
    servico = (servico or "").lower()
    if "spotify" in servico:
        return tocar_spotify(query)
    return tocar_youtube(query)
