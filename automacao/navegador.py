"""
automacao/navegador.py
=========================
"Navegar sozinho na internet": Ultron pesquisa um termo (DuckDuckGo,
não exige chave de API), abre os primeiros resultados de verdade,
extrai o texto principal de cada página, e pede pra IA configurada
resumir/responder com base no que leu -- tudo num navegador real via
Playwright (mesma dependência opcional de automacao/logins_web.py).

Isso é NAVEGAÇÃO SOMENTE LEITURA por design -- nunca preenche
formulário, nunca clica em nada além de links de resultado de busca,
nunca loga em nada, nunca envia dados, nunca compra nada. "Sozinho"
aqui significa "não precisa que você diga o site exato", não "faz o
que quiser sem ser pedido": só roda quando VOCÊ pede uma pesquisa
("pesquisa na internet sobre X"), não como um robô vasculhando a
internet sem parar em segundo plano -- isso seria caro (chamadas de
IA) e imprevisível (pode cair em qualquer conteúdo) sem necessidade.

Limites, de propósito:
- No máximo MAX_PAGINAS páginas visitadas por pesquisa.
- Timeout curto por página -- uma página lenta/travada não trava a
  pesquisa inteira, só é pulada.
"""

import re
import time

from logs.logger import get_logger

log = get_logger("automacao")

MAX_PAGINAS = 3
_TIMEOUT_MS = 12000
_CACHE = {}
_INJECTION_PATTERNS = (
    r"ignore (?:all |any )?(?:previous|prior) instructions?",
    r"ignore todas? as instruções",
    r"(?:system|developer)\s*prompt",
    r"you are now ",
    r"revele? (?:seu|o) prompt",
    r"execute (?:este|o seguinte) comando",
)


def sanitizar_conteudo_web(texto: str) -> tuple[str, int]:
    """Remove linhas com padrões comuns de prompt injection.

    Conteúdo da web é dado não confiável, nunca instrução. Retorna o
    texto limpo e quantas linhas foram descartadas para auditoria.
    """
    linhas, removidas = [], 0
    for linha in (texto or "").splitlines():
        if any(re.search(pattern, linha, re.IGNORECASE) for pattern in _INJECTION_PATTERNS):
            removidas += 1
            continue
        linhas.append(linha)
    return "\n".join(linhas), removidas

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def available() -> bool:
    return HAS_PLAYWRIGHT


def _extrair_texto_principal(pagina) -> str:
    try:
        texto = pagina.locator("body").inner_text(timeout=_TIMEOUT_MS)
    except Exception:
        return ""
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto[:4000]


def _buscar_resultados(pagina, consulta: str) -> list:
    import urllib.parse
    pagina.goto(
        f"https://duckduckgo.com/html/?q={urllib.parse.quote(consulta)}",
        wait_until="domcontentloaded", timeout=_TIMEOUT_MS,
    )
    links = pagina.locator("a.result__a").all()
    urls = []
    for link in links[:MAX_PAGINAS]:
        href = link.get_attribute("href")
        if href:
            urls.append(href)
    return urls


def pesquisar_e_ler(consulta: str) -> list:
    """Retorna uma lista de {"url", "texto"} com o conteúdo lido de
    cada página visitada -- só leitura, nunca interage com a página
    além de navegar até ela."""
    chave_cache = consulta.strip().lower()
    try:
        from config.settings import get_settings
        ttl = int(get_settings().get("internet.cache_minutos", 30)) * 60
    except Exception:
        ttl = 1800
    cached = _CACHE.get(chave_cache)
    if cached and time.time() - cached[0] < ttl:
        return [dict(item) for item in cached[1]]

    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Instale 'playwright' (requirements-automacao.txt) e rode "
            "'python -m playwright install chromium' pra eu navegar na internet."
        )
    resultados = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pagina = browser.new_page()
        try:
            urls = _buscar_resultados(pagina, consulta)
        except Exception as e:
            browser.close()
            raise RuntimeError(f"Falha ao pesquisar: {e}")

        for url in urls:
            try:
                pagina.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
                texto = _extrair_texto_principal(pagina)
                if texto:
                    texto, removidas = sanitizar_conteudo_web(texto)
                    if texto:
                        resultados.append({
                            "url": url, "texto": texto,
                            "linhas_suspeitas_removidas": removidas,
                        })
            except Exception as e:
                log.warning("navegador: falha ao ler '%s': %s", url, e)
                continue
        browser.close()
    if resultados:
        _CACHE[chave_cache] = (time.time(), [dict(item) for item in resultados])
        # Limite simples para sessões muito longas.
        if len(_CACHE) > 100:
            oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
            _CACHE.pop(oldest, None)
    return resultados


def pesquisar_e_resumir(ia_manager, consulta: str) -> str:
    paginas = pesquisar_e_ler(consulta)
    if not paginas:
        return "Não consegui achar nada útil pesquisando isso agora."
    if ia_manager is None:
        blocos = [f"{p['url']}:\n{p['texto'][:300]}" for p in paginas]
        return "\n\n".join(blocos)

    contexto = "\n\n".join(f"Fonte: {p['url']}\n{p['texto']}" for p in paginas)
    prompt = (
        f'Pesquisei na internet sobre "{consulta}" e li estas páginas:\n\n{contexto}\n\n'
        "Responda a pergunta/consulta original de forma clara e objetiva, citando de qual "
        "fonte (URL) veio a informação principal."
    )
    try:
        _, resposta = ia_manager.chat(prompt, history=[], max_tokens=700)
    except Exception as e:
        return f"Li {len(paginas)} página(s), mas falhei ao resumir com a IA: {e}"
    return resposta or "Não consegui gerar um resumo."
