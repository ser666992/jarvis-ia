"""
core/skill_forge.py
======================
Motor de geração de código: pede pra IA configurada (ia/manager.py)
escrever um plugin novo (habilidade) ou um script autocontido
(programa), a partir de um pedido em linguagem natural.

NUNCA ativa nada sozinho. Uma habilidade gerada fica em
`plugins/pendentes/<slug>.py` -- uma pasta separada de `plugins/`, que
core/plugin_manager.py (que só varre os arquivos DIRETAMENTE dentro de
`plugins/`) nunca enxerga -- até o usuário aprovar explicitamente
(aprovar_habilidade), o que move o arquivo pra `plugins/` de verdade e
permite recarregar os plugins em tempo real. Rejeitar (rejeitar_habilidade)
só apaga o rascunho.

Por que essa fricção: um plugin tem acesso total ao que o resto do
Ultron tem acesso -- arquivos, processos, seu celular via ADB. Código
gerado por IA pode ter bugs, alucinar uma API que não existe, ou fazer
algo diferente do que foi pedido. Gerar sempre; ativar só com aprovação
humana explícita (ver plugins/skill_forge.py, que expõe os comandos de
chat pra tudo isso).

Programas (scripts autocontidos, "cria um programa que...") seguem a
mesma ideia mas são mais simples: vão para `data/programas_gerados/`, e
SEMPRE exigem confirmação explícita pra rodar (seguranca.permissions)
-- rodar código novo, não revisado por um humano, é tratado como ação
destrutiva por padrão, igual a fechar um programa.
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys

from core.timeline import registrar
from logs.logger import get_logger
from seguranca.permissions import check_destructive_action

log = get_logger("core")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")
PENDING_DIR = os.path.join(PLUGINS_DIR, "pendentes")
PROGRAMS_DIR = os.path.join(BASE_DIR, "data", "programas_gerados")

_PLUGIN_SYSTEM_PROMPT = """Você é um gerador de código Python para o assistente Ultron. Sua ÚNICA tarefa é escrever UM arquivo de plugin completo -- nada além do código, sem explicações, sem markdown, sem texto antes ou depois.

Convenção obrigatória do projeto (core/plugin_manager.py):

    from core.plugin_manager import BasePlugin
    from core.confidence import Answer, Confidence

    class NomeDoPlugin(BasePlugin):
        name = "nome_curto_unico"
        description = "descrição breve do que o plugin faz"
        triggers = ["palavra1", "palavra2"]  # substrings (minúsculas) que ativam o plugin

        def handle(self, text: str, context: dict):
            # context contém: memory, knowledge, knowledge_base, user_id,
            # history (lista de mensagens recentes), ia_manager (pode ser None).
            # Retorne Answer(texto, confidence), uma string simples, ou None
            # se não souber responder a ESTE texto especificamente.
            return Answer("resposta aqui", Confidence.CONFIRMED)

Níveis de Confidence disponíveis: CONFIRMED (100), RELIABLE_SOURCE (90), SINGLE_SOURCE (70), INFERRED (50), POSSIBLE (30), GUESS (10).

Regras OBRIGATÓRIAS:
- Só importe bibliotecas da stdlib do Python, ou as já usadas no projeto (psutil, requests) -- nunca invente uma dependência de terceiros nova.
- NUNCA apague arquivos, formate discos, rode eval/exec sobre texto do usuário, ou execute comandos de shell arbitrários vindos do texto do usuário.
- Se o pedido envolver algo potencialmente destrutivo ou irreversível, a handle() deve recusar educadamente e explicar por quê, em vez de implementar.
- Código sintaticamente válido em Python 3.10+, autocontido em um único arquivo, sem inventar imports de módulos do projeto que não existem.
- Inclua comentários breves explicando decisões NÃO óbvias (por que este regex/heurística/estrutura de dados, não o que o código faz linha a linha) -- quem for revisar o rascunho antes de aprovar precisa entender o raciocínio, não só reler a sintaxe. Não comente o óbvio (ex.: "# soma a e b" em cima de "return a + b").
- TRIGGERS ESPECÍFICOS, nunca genéricos: cada trigger é uma SUBSTRING que rouba a mensagem de TODOS os outros plugins quando bate. Um trigger de uma palavra comum ("erro", "tela", "abrir", "problema", "tempo") sequestra dezenas de comandos que não têm nada a ver com este plugin -- bug real já aconteceu. Use SEMPRE frases de 2+ palavras bem específicas do propósito do plugin (ex.: "erro na inicialização do windows", não "erro").
- handle() deve devolver None quando o texto não for claramente sobre o propósito ESPECÍFICO deste plugin -- nunca responder qualquer coisa só porque um trigger bateu.

Gere APENAS o código do arquivo .py, começando direto com os imports."""

_PROGRAM_SYSTEM_PROMPT = """Você é um gerador de código Python. Sua ÚNICA tarefa é escrever UM script Python completo e autocontido que faça o que for pedido -- nada além do código, sem explicações, sem markdown.

Regras OBRIGATÓRIAS:
- Use só a biblioteca padrão do Python sempre que possível.
- Inclua um bloco `if __name__ == "__main__":` como ponto de entrada.
- NUNCA apague arquivos fora de uma pasta que o próprio script crie, formate discos, ou rode comandos de shell arbitrários vindos de input do usuário.
- Se o pedido for perigoso/destrutivo por natureza, escreva um script que apenas explica (via print) por que não vai fazer isso, em vez de implementar a parte perigosa.
- Código sintaticamente válido em Python 3.10+, autocontido em um único arquivo.
- Inclua comentários breves explicando decisões NÃO óbvias (por que essa abordagem, não o que cada linha faz) -- quem revisar antes de rodar precisa entender o raciocínio.

Gere APENAS o código do arquivo .py."""

_GAME_DESIGN_SYSTEM_PROMPT = """Você é um designer de jogos. Vai receber só um TEMA (pode ser uma única palavra ou frase curta, ex.: "piratas espaciais") -- o usuário não descreveu nenhuma mecânica, e é seu trabalho inventar um jogo completo a partir só disso.

Responda APENAS com um JSON (sem markdown, sem texto fora do JSON), neste formato exato:
{
  "titulo": "título curto e evocativo do jogo",
  "lore": "2-4 frases de contexto/história -- por que esse mundo existe, quem é o jogador, o que está em jogo",
  "mecanica": "1-2 frases descrevendo como se joga -- controles e objetivo principal",
  "condicao_vitoria": "o que precisa acontecer pra vencer",
  "condicao_derrota": "o que precisa acontecer pra perder",
  "niveis": ["descrição breve do nível 1", "descrição breve do nível 2", "descrição breve do nível 3"]
}

O campo "niveis" deve ter entre 2 e 4 níveis, com dificuldade visivelmente crescente entre eles (mais rápido, mais obstáculos/inimigos, objetivo maior etc.)."""

_GAME_SYSTEM_PROMPT_2D = """Você é um gerador de jogos em Python usando Pygame. Vai receber um DESIGN DE JOGO em JSON (título, lore, mecânica, condições de vitória/derrota, níveis) -- sua ÚNICA tarefa é implementar esse design INTEIRO como um arquivo .py completo e autocontido. Nada além do código, sem explicações, sem markdown.

Regras OBRIGATÓRIAS:
- Implemente TODOS os níveis descritos no design, em ordem, com dificuldade crescente entre eles (você decide os números exatos de velocidade/quantidade/obstáculos condizentes com a descrição de cada nível).
- Tela de abertura mostrando o título e um resumo curto da lore antes de começar a jogar (ex.: "aperte espaço para começar").
- Tela de vitória E tela de derrota, cada uma com uma mensagem curta condizente com a lore do design.
- Use a biblioteca `pygame` (já disponível no ambiente).
- Jogável de verdade: o jogador controla algo pelo teclado, existe progressão de nível clara, e a janela fecha direito ao clicar no X ou apertar ESC (sem travar o processo).
- Rode a 60 FPS com um `pygame.time.Clock`, e sempre chame `pygame.quit()` e `sys.exit()` no final.
- Inclua um bloco `if __name__ == "__main__":` como ponto de entrada.
- NÃO baixe nenhum asset externo (imagem/som) da internet -- desenhe formas simples (retângulos, círculos, texto) com `pygame.draw`/`pygame.font`, sem precisar de arquivos externos.
- Código sintaticamente válido em Python 3.10+, autocontido em um único arquivo.
- Inclua comentários breves explicando a lógica do jogo (regras, condição de vitória/derrota, por que uma constante tem aquele valor) -- não precisa comentar cada chamada óbvia do pygame.

Gere APENAS o código do arquivo .py."""

_GAME_SYSTEM_PROMPT_3D = """Você é um gerador de jogos em Python usando a biblioteca `ursina` (engine 3D simples baseada em Panda3D). Vai receber um DESIGN DE JOGO em JSON (título, lore, mecânica, condições de vitória/derrota, níveis) -- sua ÚNICA tarefa é implementar esse design INTEIRO como um arquivo .py completo e autocontido, em 3D de verdade. Nada além do código, sem explicações, sem markdown.

Regras OBRIGATÓRIAS:
- Use `from ursina import *` (já disponível no ambiente) -- cenário em 3D de verdade (câmera navegável, entidades com posição x/y/z), não uma simulação 2D disfarçada.
- Use só primitivas geométricas do próprio ursina (`Entity(model='cube'/'sphere'/'plane'/'quad', color=...)`) -- NUNCA tente carregar textura/modelo/asset externo de arquivo ou da internet.
- Implemente TODOS os níveis descritos no design, com dificuldade crescente entre eles.
- Texto inicial (via `Text(...)`) mostrando o título e um resumo curto da lore antes de começar.
- Condição de vitória e de derrota implementadas de verdade, cada uma com uma mensagem final (via `Text(...)`) condizente com a lore.
- Jogável com teclado (e mouse pra câmera, se fizer sentido pro jogo) -- chame `app.run()` no final, e garanta que ESC fecha a janela direito (sem travar o processo -- `window.exit_button.visible = False` e tratar a tecla escape).
- Código sintaticamente válido em Python 3.10+, autocontido em um único arquivo.
- Inclua comentários breves explicando a lógica do jogo.

Gere APENAS o código do arquivo .py."""

_PALAVRAS_3D = ("3d", "tridimensional", "três dimensões", "3 dimensões", "3 d")

_FIX_PLUGIN_SYSTEM_PROMPT = """Você é um corretor de código Python. Vai receber um arquivo de PLUGIN do Ultron que deu erro, e a mensagem de erro/traceback. Sua ÚNICA tarefa é devolver o arquivo INTEIRO já corrigido -- nada além do código, sem explicações, sem markdown.

Regras OBRIGATÓRIAS:
- Mantenha a convenção BasePlugin/Answer/Confidence e, se possível, o mesmo `name`/`triggers` do original -- corrija só o que está causando o erro.
- Não reintroduza o mesmo bug de outra forma, nem invente um comportamento novo que não foi pedido.
- Código sintaticamente válido em Python 3.10+, autocontido em um único arquivo.
- Adicione um comentário breve no ponto exato da correção explicando qual era o bug e por que a mudança resolve -- ajuda quem for reaprovar a entender o que mudou sem comparar diff manualmente. Mantenha os comentários que já existiam no resto do arquivo.

Gere APENAS o código do arquivo .py corrigido."""

_FIX_PROGRAM_SYSTEM_PROMPT = """Você é um corretor de código Python. Vai receber um script autocontido que deu erro ao rodar, e a mensagem de erro/traceback. Sua ÚNICA tarefa é devolver o arquivo INTEIRO já corrigido -- nada além do código, sem explicações, sem markdown.

Regras OBRIGATÓRIAS:
- Mantenha o objetivo/comportamento pretendido do script original -- corrija só o que está causando o erro.
- Inclua o bloco `if __name__ == "__main__":`.
- Código sintaticamente válido em Python 3.10+, autocontido em um único arquivo.
- Adicione um comentário breve no ponto exato da correção explicando qual era o bug e por que a mudança resolve. Mantenha os comentários que já existiam no resto do arquivo.

Gere APENAS o código do arquivo .py corrigido."""

# Heurística simples (aviso, não bloqueio) -- sinaliza pro usuário
# revisar com mais atenção antes de aprovar/rodar, mas não impede a
# geração: algumas dessas chamadas são legítimas para o que foi pedido.
_PADROES_RISCO = {
    "shutil.rmtree": "remove pastas inteiras recursivamente",
    "os.remove": "apaga arquivos",
    "os.unlink": "apaga arquivos",
    "os.system": "executa comando de shell",
    "subprocess": "executa um processo externo",
    "eval(": "executa código arbitrário (eval)",
    "exec(": "executa código arbitrário (exec)",
}


class SkillForgeError(Exception):
    pass


def slugify(nome: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", nome.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:40] or "gerado"


def _extrair_codigo(resposta: str) -> str:
    texto = resposta.strip()
    m = re.search(r"```(?:python)?\s*\n?(.*?)```", texto, re.DOTALL)
    if m:
        return m.group(1).strip()
    return texto


def _validar_sintaxe(codigo: str):
    try:
        ast.parse(codigo)
    except SyntaxError as e:
        raise SkillForgeError(
            f"O código gerado tem um erro de sintaxe ({e}) -- descartado antes de salvar."
        )


def _avisos_de_risco(codigo: str) -> list:
    return [aviso for padrao, aviso in _PADROES_RISCO.items() if padrao in codigo]


def _timeout_geracao() -> int:
    """Timeout (segundos) das chamadas de IA pra GERAR código/jogo.
    Configurável (`ia.timeout_geracao_segundos`, 600s = 10min por
    padrão) e bem mais folgado que os 90s hardcoded de antes: gerar um
    arquivo inteiro de código (até 2000 tokens) num modelo grande
    hospedado (ex.: os 70B da NVIDIA) ou local roda MUITO mais devagar
    que uma resposta curta de chat, e 90s estourava no meio -- o
    sintoma de "peço pra criar algo e dá timeout". 0 ou negativo
    desliga o teto (espera indefinidamente)."""
    from config.settings import get_settings
    try:
        valor = int(get_settings().get("ia.timeout_geracao_segundos", 600))
    except (TypeError, ValueError):
        valor = 600
    return valor if valor > 0 else None


def _gerar(ia_manager, pedido: str, system_prompt: str) -> str:
    if ia_manager is None:
        raise SkillForgeError(
            "Preciso de um provedor de IA configurado pra gerar código (veja /configurarapi)."
        )
    try:
        _, resposta = ia_manager.chat(
            pedido, history=[], system_prompt=system_prompt, max_tokens=2000,
            timeout=_timeout_geracao(),
        )
    except Exception as e:
        raise SkillForgeError(f"Falha ao gerar código: {e}")
    if not resposta:
        raise SkillForgeError("A IA não conseguiu gerar nada pra esse pedido.")
    codigo = _extrair_codigo(resposta)
    _validar_sintaxe(codigo)
    return codigo


# ==================== Habilidades (plugins) ====================

def gerar_habilidade(ia_manager, pedido: str, nome_sugerido: str = None) -> dict:
    """Gera um rascunho de plugin novo em plugins/pendentes/<slug>.py.
    Nunca ativa sozinho -- ver aprovar_habilidade()."""
    codigo = _gerar(
        ia_manager,
        f"Crie um plugin novo pro Ultron que faça o seguinte: {pedido}",
        _PLUGIN_SYSTEM_PROMPT,
    )
    slug = slugify(nome_sugerido or pedido)
    os.makedirs(PENDING_DIR, exist_ok=True)
    caminho = os.path.join(PENDING_DIR, f"{slug}.py")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(codigo)
    log.info("rascunho de habilidade gerado: %s", caminho)
    registrar("habilidade_criada", slug)
    return {
        "slug": slug,
        "caminho": caminho,
        "avisos": _avisos_de_risco(codigo),
        "preview": codigo[:600],
    }


def listar_habilidades_pendentes() -> list:
    if not os.path.isdir(PENDING_DIR):
        return []
    return sorted(f[:-3] for f in os.listdir(PENDING_DIR) if f.endswith(".py"))


# Palavras comuns demais pra servirem de trigger sozinhas -- um plugin
# gerado com um trigger desses SEQUESTRA (via substring, ver
# BasePlugin.matches) todo comando que contenha a palavra, inclusive os
# dos plugins nativos. Bug real: um "sonho" aprovado com
# triggers=["erro","tela","problema"] fez "grava minha tela", "assiste a
# tela" etc. pararem de funcionar TODOS de uma vez, respondendo "reinicie
# o computador" pra tudo.
_TRIGGERS_GENERICOS = {
    "erro", "erros", "tela", "problema", "problemas", "ajuda", "abrir",
    "abre", "abra", "fecha", "fechar", "tempo", "hora", "horas", "dia",
    "musica", "música", "video", "vídeo", "arquivo", "arquivos", "foto",
    "fotos", "jogo", "jogos", "internet", "pesquisa", "pesquisar", "site",
    "computador", "sistema", "programa", "programas", "app", "apps",
    "aplicativo", "celular", "email", "e-mail", "mensagem", "mensagens",
    "lista", "listar", "cria", "criar", "faz", "fazer", "mostra",
    "mostrar", "roda", "rodar", "executa", "executar", "liga", "ligar",
    "desliga", "desligar", "para", "parar", "salva", "salvar", "novo",
    "nova", "meu", "minha", "windows", "chrome", "navegador",
}


def _triggers_do_arquivo(caminho: str) -> list:
    """Extrai (via ast, sem executar o arquivo) todos os literais da
    lista `triggers = [...]` de classes definidas no arquivo."""
    import ast as _ast
    with open(caminho, "r", encoding="utf-8") as f:
        arvore = _ast.parse(f.read())
    triggers = []
    for no in _ast.walk(arvore):
        if isinstance(no, _ast.ClassDef):
            for item in no.body:
                if (isinstance(item, _ast.Assign)
                        and any(getattr(t, "id", None) == "triggers" for t in item.targets)
                        and isinstance(item.value, (_ast.List, _ast.Tuple))):
                    for el in item.value.elts:
                        if isinstance(el, _ast.Constant) and isinstance(el.value, str):
                            triggers.append(el.value)
    return triggers


def validar_triggers(caminho: str) -> list:
    """Retorna a lista de triggers PROBLEMÁTICOS (genéricos demais) do
    rascunho -- vazia se estiver tudo bem. Um trigger é problemático se
    for uma única palavra E (curta, ou da lista de palavras comuns).
    Frases de 2+ palavras passam sempre (são específicas o bastante)."""
    ruins = []
    for t in _triggers_do_arquivo(caminho):
        limpo = t.strip().lower()
        palavras = limpo.split()
        if len(palavras) >= 2:
            continue
        if limpo in _TRIGGERS_GENERICOS or len(limpo) < 10:
            ruins.append(t)
    return ruins


def aprovar_habilidade(slug: str) -> str:
    origem = os.path.join(PENDING_DIR, f"{slug}.py")
    if not os.path.isfile(origem):
        raise FileNotFoundError(f"Não há nenhum rascunho de habilidade pendente chamado '{slug}'.")
    try:
        ruins = validar_triggers(origem)
    except SyntaxError:
        raise SkillForgeError(
            f"O rascunho '{slug}' tem erro de sintaxe -- não dá pra aprovar. "
            f"Corrija o arquivo ({origem}) ou rejeite com \"rejeita a habilidade {slug}\"."
        )
    if ruins:
        lista = ", ".join(f'"{r}"' for r in ruins)
        raise SkillForgeError(
            f"Não aprovei '{slug}': os triggers {lista} são genéricos demais e fariam "
            "esse plugin roubar comandos que não têm nada a ver com ele (qualquer frase "
            "contendo essas palavras). Edite o arquivo em plugins/pendentes/ trocando por "
            "frases específicas de 2+ palavras (ex.: \"erro na inicialização\" em vez de "
            f'"erro") e aprove de novo, ou rejeite com "rejeita a habilidade {slug}".'
        )
    destino = os.path.join(PLUGINS_DIR, f"{slug}.py")
    # A correção usa o mesmo slug do plugin quebrado. Antes removíamos
    # a versão ativa e só depois movíamos a nova; qualquer falha no move
    # deixava o usuário sem nenhuma das duas. Como ambas ficam no mesmo
    # projeto, os.replace faz a troca atômica e preserva a antiga se a
    # operação não puder ser concluída.
    os.replace(origem, destino)
    log.info("habilidade aprovada e ativada: %s", destino)
    registrar("habilidade_aprovada", slug)
    return destino


def rejeitar_habilidade(slug: str) -> bool:
    origem = os.path.join(PENDING_DIR, f"{slug}.py")
    if not os.path.isfile(origem):
        return False
    os.remove(origem)
    log.info("rascunho de habilidade rejeitado/descartado: %s", slug)
    registrar("habilidade_rejeitada", slug)
    return True


# ==================== Programas (scripts autocontidos) ====================

def gerar_programa(ia_manager, pedido: str, nome_sugerido: str = None) -> dict:
    codigo = _gerar(
        ia_manager,
        f"Crie um programa Python que faça o seguinte: {pedido}",
        _PROGRAM_SYSTEM_PROMPT,
    )
    slug = slugify(nome_sugerido or pedido)
    os.makedirs(PROGRAMS_DIR, exist_ok=True)
    caminho = os.path.join(PROGRAMS_DIR, f"{slug}.py")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(codigo)
    log.info("programa gerado: %s", caminho)
    registrar("programa_gerado", slug)
    return {
        "slug": slug,
        "caminho": caminho,
        "avisos": _avisos_de_risco(codigo),
        "preview": codigo[:600],
    }


def _extrair_json(resposta: str):
    texto = resposta.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", texto, re.DOTALL)
    if m:
        texto = m.group(1).strip()
    try:
        return json.loads(texto)
    except Exception:
        return None


def _pedido_quer_3d(pedido: str) -> bool:
    p = pedido.lower()
    return any(palavra in p for palavra in _PALAVRAS_3D)


def _gerar_design_jogo(ia_manager, pedido: str) -> dict:
    """Primeira etapa: pede pra IA inventar um design de jogo completo
    (título, lore, mecânica, condições de vitória/derrota, níveis) a
    partir só do TEMA -- o usuário não precisa descrever como o jogo
    deve funcionar, só do que ele é sobre (ex.: "cria um jogo sobre
    piratas espaciais"). Degrada pra um design mínimo (sem lore
    elaborada) se a IA não devolver um JSON válido, em vez de falhar
    a geração inteira por causa disso."""
    if ia_manager is None:
        raise SkillForgeError("Preciso de um provedor de IA configurado pra gerar código (veja /configurarapi).")
    try:
        _, resposta = ia_manager.chat(
            f"Tema do jogo: {pedido}", history=[], system_prompt=_GAME_DESIGN_SYSTEM_PROMPT,
            max_tokens=700, timeout=_timeout_geracao(),
        )
    except Exception as e:
        raise SkillForgeError(f"Falha ao inventar o design do jogo: {e}")
    design = _extrair_json(resposta or "")
    if not isinstance(design, dict):
        log.warning("design de jogo não veio em JSON válido -- usando design mínimo de fallback")
        design = {
            "titulo": pedido[:60], "lore": "", "mecanica": pedido,
            "condicao_vitoria": "", "condicao_derrota": "", "niveis": [],
        }
    return design


def gerar_jogo(ia_manager, pedido: str, nome_sugerido: str = None) -> dict:
    """Gera um jogo completo a partir só de um TEMA, em duas etapas:
    1) `_gerar_design_jogo` inventa título/lore/mecânica/níveis a
       partir do tema, sem exigir que o usuário descreva a mecânica;
    2) implementa esse design como um jogo jogável de verdade -- em 2D
       (Pygame, o padrão, zero dependência nova) ou em 3D (`ursina`,
       opcional, só quando o pedido menciona "3d"/"tridimensional";
       requer instalar via requirements-jogos.txt).

    Continua na mesma pasta/mecânica de 'programa' (data/programas_gerados/):
    roda com o mesmo rodar_programa(), exige a mesma confirmação explícita."""
    design = _gerar_design_jogo(ia_manager, pedido)
    quer_3d = _pedido_quer_3d(pedido)
    system_prompt = _GAME_SYSTEM_PROMPT_3D if quer_3d else _GAME_SYSTEM_PROMPT_2D
    prompt_codigo = (
        f"Tema original pedido pelo usuário: {pedido}\n\n"
        f"Design do jogo (JSON):\n{json.dumps(design, ensure_ascii=False, indent=2)}"
    )
    codigo = _gerar(ia_manager, prompt_codigo, system_prompt)

    slug = slugify(nome_sugerido or design.get("titulo") or pedido)
    os.makedirs(PROGRAMS_DIR, exist_ok=True)
    caminho = os.path.join(PROGRAMS_DIR, f"{slug}.py")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(codigo)

    # Lore/design salvos ao lado do jogo -- pra usuário poder ver do que
    # o jogo é sobre sem precisar ler o código gerado.
    design_path = os.path.join(PROGRAMS_DIR, f"{slug}.design.json")
    with open(design_path, "w", encoding="utf-8") as f:
        json.dump(design, f, ensure_ascii=False, indent=2)

    log.info("jogo gerado (%s): %s", "3D" if quer_3d else "2D", caminho)
    registrar("programa_gerado", slug)
    return {
        "slug": slug,
        "caminho": caminho,
        "design": design,
        "modo": "3d" if quer_3d else "2d",
        "avisos": _avisos_de_risco(codigo),
        "preview": codigo[:600],
    }


def listar_programas() -> list:
    if not os.path.isdir(PROGRAMS_DIR):
        return []
    return sorted(f[:-3] for f in os.listdir(PROGRAMS_DIR) if f.endswith(".py"))


def _gerar_correcao(ia_manager, caminho_arquivo: str, erro: str, system_prompt: str, destino_dir: str) -> dict:
    if not os.path.isfile(caminho_arquivo):
        raise SkillForgeError(f"Arquivo '{caminho_arquivo}' não encontrado pra corrigir.")
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        codigo_original = f.read()
    pedido = (
        f"Código atual (arquivo {os.path.basename(caminho_arquivo)}):\n\n{codigo_original}\n\n"
        f"Erro ao rodar:\n{erro}\n\nCorrija o arquivo inteiro."
    )
    codigo_corrigido = _gerar(ia_manager, pedido, system_prompt)
    slug = os.path.splitext(os.path.basename(caminho_arquivo))[0]
    os.makedirs(destino_dir, exist_ok=True)
    caminho_saida = os.path.join(destino_dir, f"{slug}.py")
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(codigo_corrigido)
    log.info("correção gerada: %s -> %s", caminho_arquivo, caminho_saida)
    registrar("correcao_gerada", slug)
    return {
        "slug": slug,
        "caminho": caminho_saida,
        "avisos": _avisos_de_risco(codigo_corrigido),
        "preview": codigo_corrigido[:600],
    }


def gerar_correcao_habilidade(ia_manager, caminho_arquivo: str, erro: str) -> dict:
    """Gera uma correção pra um PLUGIN que deu erro em tempo de
    execução (ver core/plugin_manager.py:dispatch()). Sai em
    plugins/pendentes/ com o MESMO slug do plugin quebrado -- aprovar
    (aprovar_habilidade) substitui a versão anterior, não ativa
    sozinho."""
    return _gerar_correcao(ia_manager, caminho_arquivo, erro, _FIX_PLUGIN_SYSTEM_PROMPT, PENDING_DIR)


def gerar_correcao_programa(ia_manager, caminho_arquivo: str, erro: str) -> dict:
    """Gera uma correção pra um PROGRAMA que falhou ao rodar
    (rodar_programa retornou código != 0). Sobrescreve o programa
    original em data/programas_gerados/ direto -- rodar de novo
    continua exigindo confirmação explícita (mesma regra de sempre)."""
    return _gerar_correcao(ia_manager, caminho_arquivo, erro, _FIX_PROGRAM_SYSTEM_PROMPT, PROGRAMS_DIR)


def rodar_programa(slug: str, confirmed: bool = False, timeout: int = None) -> dict:
    """Roda um programa gerado, como subprocesso isolado. Ação tratada
    como destrutiva por padrão (código novo, não revisado por um
    humano) -- exige confirmed=True (ver seguranca.permissions).

    `timeout=None` escolhe sozinho: jogos gerados via gerar_jogo()
    (detectados pela presença de "pygame" OU "ursina" no código -- não
    há outro jeito de diferenciar "programa" de "jogo" aqui, os dois
    vão pra mesma pasta e rodam pelo mesmo caminho) ganham 1h em vez de
    30s, porque têm um loop principal que só termina quando o USUÁRIO
    fecha a janela -- um teto de 30s mataria qualquer partida no meio.
    `subprocess.run(timeout=...)` MATA o processo ao estourar o tempo
    (não deixa rodando em segundo plano), então isso é sempre "o
    processo foi encerrado", nunca "ainda está rodando por aí"."""
    caminho = os.path.join(PROGRAMS_DIR, f"{slug}.py")
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"Não encontrei nenhum programa gerado chamado '{slug}'.")
    check_destructive_action(f"rodar o programa gerado '{slug}'", confirmed=confirmed)

    if timeout is None:
        with open(caminho, "r", encoding="utf-8") as f:
            codigo_programa = f.read()
        eh_jogo = "pygame" in codigo_programa or "ursina" in codigo_programa
        timeout = 3600 if eh_jogo else 30

    try:
        resultado = subprocess.run(
            [sys.executable, caminho], capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        # Sem isso, TimeoutExpired escapava até core/plugin_manager.py,
        # que atribuía o erro ao PLUGIN skill_forge.py (o dispatcher),
        # não ao programa gerado -- e tentava "corrigir" o arquivo
        # errado com uma chamada de IA baseada num traceback que não
        # tinha nada a ver com um bug de verdade.
        registrar("programa_executado", f"{slug} (encerrado por exceder {timeout}s)")
        return {"stdout": e.stdout or "", "stderr": e.stderr or "", "returncode": None, "timeout": True}

    registrar("programa_executado", f"{slug} (código {resultado.returncode})")
    return {"stdout": resultado.stdout, "stderr": resultado.stderr, "returncode": resultado.returncode, "timeout": False}
