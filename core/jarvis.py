"""
core/jarvis.py
================
Núcleo do Ultron: une memória, conhecimento aprendido, plugins,
motor de conversa natural, confiança e lógica de resposta.

"Evolução constante" aqui significa, de forma honesta:
- Cada interação é salva permanentemente (histórico completo).
- Fatos novos ditos pelo usuário são incorporados à memória e
  passam a influenciar respostas futuras.
- Toda mensagem alimenta passivamente o sistema de aprendizado
  (core/knowledge.py): assuntos frequentes são detectados, e podem
  ser consolidados em conhecimento próprio sob comando ou via
  /consolidar.
- Novos plugins podem ser adicionados sem alterar o núcleo,
  então as capacidades do Ultron crescem com o tempo.

Isso NÃO é um modelo de linguagem treinando pesos em tempo real —
é um sistema de regras + memória persistente + base de conhecimento
relacional + busca externa, com um estágio opcional de IA (externa ou
local, ver `ia/`) plugado antes do fallback final.

Ordem de prioridade em `process()`:
1. Base de conhecimento curada (pergunta factual) → core/knowledge_base.py
2. Plugins de comando (ex.: "lembre que...", "que horas são") → /plugins
3. Motor de conversa natural (saudação, humor, piada, etc.) → core/conversation.py
4. IA (externa configurada, ou modelo local) → ia/manager.py -- só entra
   em ação se o módulo `ia` estiver ligado E algum provedor/modelo
   estiver disponível; nunca é obrigatório.
5. Fallback final (ajuda, ou "não sei o que fazer com isso")

Respostas factuais (1, 2, 4 e 5) saem formatadas com o bloco explícito
de confiança (ver core/confidence.py):

    Resposta:
    <texto>

    Confiança:
    <nível>%

Respostas de conversa natural (3) saem como texto puro, sem esse
bloco — o motivo está documentado em `core/conversation.py` e em
`Answer.formal` (core/confidence.py).
"""

import os

from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.conversation import ConversationEngine
from core.knowledge import Knowledge
from core.knowledge_base import KB_CATEGORY_LABELS, KnowledgeBase
from core.memory import Memory
from core.module_manager import ModuleManager
from core.plugin_manager import PluginManager

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")


class Jarvis:
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self.settings = get_settings()
        self.memory = Memory()
        self.knowledge = Knowledge()
        self.knowledge_base = KnowledgeBase()
        self.plugins = PluginManager(PLUGINS_DIR)
        self.conversation = ConversationEngine()
        self.module_manager = ModuleManager()
        self.memory.log_event("startup", "Ultron iniciado")

        if not self.memory.get_profile(user_id):
            self.memory.create_or_update_profile(user_id, name=None)

        self.log = None
        self.ia_manager = self._init_ia()
        self._startup_diagnostics()

    def _init_ia(self):
        """Estágio de IA (externa ou local) é opcional -- só é
        instanciado se o módulo `ia` estiver ligado em config.json.
        Nunca é obrigatório: sem provedor/modelo disponível, este
        método retorna None e `process()` simplesmente pula a etapa 4."""
        if not self.settings.is_module_enabled("ia"):
            return None
        try:
            import ia
            return ia.manager()
        except Exception as e:
            self.memory.log_event("modulo_ia_indisponivel", str(e))
            return None

    def _startup_diagnostics(self):
        """Roda uma vez por sessão: registra um resumo de hardware nos
        logs (útil para saber depois se o Ultron rodou com GPU ou CPU)
        e dispara o backup automático do banco de dados, se configurado.
        Ambos são melhor-esforço -- uma falha aqui nunca impede o
        Ultron de iniciar."""
        try:
            from logs.logger import get_logger
            self.log = get_logger("core")
        except Exception:
            self.log = None

        if self.settings.is_module_enabled("sistema"):
            try:
                import sistema
                gpu = sistema.detect_gpu()
                msg = f"GPU: {gpu['nome']}" if gpu["disponivel"] else "GPU: nenhuma NVIDIA detectada (usando CPU)"
                if self.log:
                    self.log.info(msg)
            except Exception:
                pass

        if self.settings.is_module_enabled("seguranca"):
            try:
                import seguranca
                backup_path = seguranca.maybe_auto_backup()
                if backup_path and self.log:
                    self.log.info("backup automático criado: %s", backup_path)
            except Exception as e:
                if self.log:
                    self.log.warning("falha no backup automático: %s", e)
            try:
                import seguranca
                seguranca.iniciar_backup_diario(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao agendar backup diário: %s", e)

        if self.settings.is_module_enabled("automacao"):
            try:
                from automacao import reminders
                reminders.reschedule_pending()
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao reagendar lembretes: %s", e)
            try:
                from automacao import auto_melhoria
                auto_melhoria.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar auto-melhoria: %s", e)
            try:
                from automacao import aprendizado_autonomo
                aprendizado_autonomo.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar aprendizado autônomo: %s", e)
            try:
                from automacao import auto_consolidacao
                auto_consolidacao.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar auto-consolidação de conhecimento: %s", e)
            try:
                from automacao import modo_autonomo
                modo_autonomo.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar modo autônomo: %s", e)
            try:
                from automacao import missoes
                missoes.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar motor de missões: %s", e)
            try:
                from automacao import instagram_auto
                instagram_auto.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar envio automático do instagram: %s", e)
            try:
                from automacao import habitos
                habitos.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar análise de hábitos: %s", e)
            try:
                from automacao import sonhos
                sonhos.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar sistema de sonhos: %s", e)
            try:
                from automacao import macros
                macros.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao retomar agendamentos de macros: %s", e)

        if self.settings.is_module_enabled("atualizacoes"):
            try:
                import atualizacoes
                atualizacoes.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar checagem automática de atualizações: %s", e)

        if self.settings.is_module_enabled("sistema"):
            try:
                from sistema import curiosidade
                curiosidade.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar sistema de curiosidade: %s", e)
            try:
                from sistema import observador_internet
                observador_internet.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar observador da internet: %s", e)

        if self.settings.is_module_enabled("visao_continua"):
            try:
                import visao_continua
                visao_continua.iniciar(self)
            except Exception as e:
                if self.log:
                    self.log.warning("falha ao iniciar visão contínua: %s", e)

    def _context(self) -> dict:
        return {
            "memory": self.memory,
            "knowledge": self.knowledge,
            "knowledge_base": self.knowledge_base,
            "user_id": self.user_id,
            "history": self.memory.get_history(self.user_id, limit=10),
            "ia_manager": self.ia_manager,
            "reload_plugins": self.reload_plugins,
            "jarvis": self,
        }

    def _query_ia(self, text: str, context: dict):
        """Consulta o AIManager (ia/manager.py): tenta os provedores
        configurados, em ordem, e cai para modelo local se nenhum
        provedor remoto estiver disponível. Retorna None (nunca
        levanta exceção) se a IA não conseguiu responder -- nesse caso
        `process()` segue normalmente para `_fallback_response`."""
        try:
            context_summary = self.memory.get_context_summary(self.user_id)
            try:
                from core import estado_interno
                context_summary += "\n\n" + estado_interno.descrever_para_prompt(self.user_id)
            except Exception:
                pass  # estado interno é só tempero -- nunca impede a IA de responder
            try:
                import visao_continua
                resumo_tela = visao_continua.descrever_para_prompt()
                if resumo_tela:
                    context_summary += "\n\n" + resumo_tela
            except Exception:
                pass  # visão contínua é só contexto extra -- nunca impede a IA de responder
            perfil_uso = self.settings.get("geral.perfil_uso", "pessoal")
            context_summary += (
                f"\n\nPerfil de uso atual: {perfil_uso}. "
                "Adapte exemplos, prioridades e nível de detalhe a esse contexto."
            )
            try:
                from core.advanced import active_temp_memory, list_projects
                temporarias = active_temp_memory(self.user_id)
                projetos = list_projects(self.user_id)
                if temporarias:
                    context_summary += "\n\nMemória temporária:\n" + "\n".join(
                        f"- {item['content']} (expira {item['expires_at'][:16]})"
                        for item in temporarias[:10])
                if projetos:
                    context_summary += "\n\nProjetos ativos:\n" + "\n".join(
                        f"- {item['name']}: {item['description'] or 'sem descrição'}"
                        for item in projetos[:10] if item["status"] == "ativo")
            except Exception:
                pass
            provider_name, ia_text = self.ia_manager.chat(
                text, history=context["history"], extra_context=context_summary,
                timeout=int(self.settings.get("ia.timeout_segundos", 60)),
            )
        except Exception as e:
            if self.log:
                self.log.warning("erro ao consultar IA: %s", e)
            return None

        if not ia_text:
            return None
        texto_final = ia_text
        if self.settings.get("personalidade.mostrar_provedor_ia", False):
            texto_final += f"\n({provider_name} | resposta gerada por IA)"
        return Answer(texto_final, Confidence.RELIABLE_SOURCE)

    def _query_internet(self, text: str):
        """Última tentativa para perguntas de conhecimento.

        Só roda depois da base, plugins, conversa e provedores de IA
        (incluindo NVIDIA) falharem. A navegação é somente leitura e
        devolve None silenciosamente quando o recurso não está instalado
        ou a rede não respondeu, preservando o fallback normal.
        """
        t = text.lower().strip()
        settings = getattr(self, "settings", None)
        if settings is not None and not settings.get("permissoes.internet", True):
            return None
        marcadores = (
            "o que ", "quem ", "qual ", "quais ", "como ", "por que",
            "porque ", "quando ", "onde ", "explique", "defina",
            "pesquise", "procure", "descubra", "fale sobre",
            "me fale", "conte sobre",
        )
        if not (t.endswith("?") or any(t.startswith(m) for m in marcadores)):
            return None

        try:
            from automacao import navegador
            if not navegador.available():
                return None
            # A IA já foi tentada imediatamente antes e falhou. Não a
            # chame de novo com o conteúdo web: devolva os trechos/fontes
            # diretamente para que a pesquisa continue útil mesmo com a
            # NVIDIA (ou outro provedor) temporariamente indisponível.
            resposta = navegador.pesquisar_e_resumir(None, text)
        except Exception as e:
            if self.log:
                self.log.warning("erro na pesquisa automática da internet: %s", e)
            return None

        if not resposta or resposta.startswith("Não consegui"):
            return None
        try:
            from core.timeline import registrar
            registrar("navegacao_web", text[:200])
        except Exception:
            pass
        return Answer(resposta, Confidence.SINGLE_SOURCE)

    def _fallback_response(self, text: str) -> Answer:
        """
        Último ponto de extensão: quando nem a base de conhecimento,
        nem um plugin de comando, nem o motor de conversa natural
        (core/conversation.py), nem o estágio de IA (ia/manager.py,
        `_query_ia` acima) souberam responder.

        Saudações, despedidas, humor, etc. já são tratados antes desta
        função, pelo ConversationEngine -- o que sobra aqui é só o
        pedido de ajuda (lista de plugins) e o "realmente não sei o
        que fazer com isso" -> GUESS.
        """
        if "ajuda" in text.lower() or "help" in text.lower() or "o que você faz" in text.lower():
            plugin_list = "\n".join(f"- {n}: {d}" for n, d in self.plugins.list_plugins())
            nome = self.settings.get("geral.nome_assistente", "Ultron") or "Ultron"
            return Answer(
                f"Eu sou o {nome}. Alguns exemplos do que posso fazer:\n"
                f"{plugin_list}\n\n"
                "Diga coisas como 'que horas são', 'o que é fotossíntese', "
                "'lembre que minha cor favorita é azul', 'meu nome é ...'.",
                Confidence.CONFIRMED
            )

        return Answer(
            "Ainda não tenho um plugin para lidar com isso, mas guardei sua "
            "mensagem na memória. Você pode me ensinar uma resposta com "
            "'lembre que ...'.",
            Confidence.GUESS
        )

    def _query_knowledge_base_first(self, text: str):
        """
        Pesquisa a base de conhecimento curada (core/knowledge_base.py)
        ANTES de qualquer outra coisa -- esta é a regra central pedida:
        "a IA deve pesquisar nessa base antes de responder".

        Só intervém quando o texto parece ser uma PERGUNTA/consulta de
        conhecimento (e não um comando de memória, sistema, ou um
        comando explícito de gestão da própria base, que o plugin
        knowledge_base.py já trata). Isso evita que "meu nome é Pedro"
        ou "/sair" sejam interceptados aqui.

        Retorna uma Answer se encontrou algo relevante na base, ou
        None se a base não tem nada e o fluxo normal (dispatch de
        plugins, depois fallback) deve continuar.
        """
        t = text.lower().strip()

        # Não intercepta comandos de gestão da própria base (o plugin
        # knowledge_base.py é quem trata esses, com mais contexto).
        management_markers = (
            "adicione na base", "adicionar na base", "adicione à base",
            "remova da base", "remover da base", "liste a base",
            "listar a base", "liste a categoria", "busque na base",
            "buscar na base", "pesquise na base", "estatísticas da base",
            "estatisticas da base", "resumo da base", "categorias da base",
        )
        if any(marker in t for marker in management_markers):
            return None

        # Só pesquisa de forma proativa quando a frase tem cara de
        # pergunta/consulta de conhecimento geral.
        question_markers = (
            "o que é", "o que e ", "o que são", "o que sao",
            "quem foi", "quem é", "quem e ", "quem são", "quem sao",
            "qual é", "qual e ", "qual o", "qual a", "quais são", "quais sao",
            "como funciona", "como funcionam", "por que", "porque",
            "quando foi", "quando ocorreu", "onde fica", "onde está",
            "explique", "defina", "definição de", "definicao de",
        )
        matched_marker = next((m for m in question_markers if m in t), None)
        if not matched_marker and not t.endswith("?"):
            return None

        # Busca tanto pelo texto completo quanto pelo "tópico" (texto
        # sem o marcador de pergunta, ex.: "o que é um NPC" -> "um NPC"),
        # já que itens da base costumam ter títulos curtos e diretos
        # ("O que é um NPC") que não necessariamente contêm a frase
        # inteira do usuário como substring.
        candidates = [text]
        topic = t
        if matched_marker:
            topic = t.split(matched_marker, 1)[1].strip(" ?.!")
        else:
            topic = t.strip(" ?.!")
        if topic:
            candidates.append(topic)

        result = None
        for candidate in candidates:
            result = self.knowledge_base.best_match(candidate)
            if result:
                break
        if not result:
            return None

        category_label = KB_CATEGORY_LABELS.get(result["category"], result["category"])
        return Answer(
            f"{result['content']}\n(Categoria: {category_label} | Base de conhecimento interna)",
            result["confidence"]
        )

    def process(self, text: str) -> str:
        text = text.strip()
        if not text:
            return Answer("Pode repetir? Não recebi nenhum texto.", Confidence.GUESS).format()

        # Modo de comando direto: texto que começa com "/" -- usado
        # pelo campo de texto do app/GUI quando o usuário DIGITA um
        # comando (fala nunca produz uma barra, então voz continua
        # indo pelo fluxo normal abaixo). Nesse modo a IA e a conversa
        # natural são puladas por completo: ou um plugin executa o
        # comando, ou o Jarvis avisa explicitamente que não reconhece
        # -- nunca "escapa" pra IA responder no lugar de executar.
        comando_direto = text.startswith("/")
        if comando_direto:
            text = text[1:].strip()
            if not text:
                return Answer('Comando vazio depois da "/".', Confidence.GUESS).format()

        modo_privado = bool(self.settings.get("privacidade.modo_privado", False))
        if not modo_privado:
            self.memory.add_message(self.user_id, "user", text)

        # Aprendizado passivo: toda mensagem do usuário alimenta a
        # detecção de assuntos frequentes, mesmo sem nenhum comando
        # explícito de "aprenda que ...". É assim que o Jarvis nota
        # quais temas voltam sempre nas conversas.
        if not modo_privado:
            self.knowledge.observe_text(self.user_id, text)

        # Estado interno simulado (energia/humor, ver core/estado_interno.py)
        # -- desgasta um pouco a cada mensagem processada. Melhor-esforço:
        # nunca deve impedir o resto do processamento se falhar.
        if not modo_privado:
            try:
                from core import estado_interno
                estado_interno.registrar_interacao(self.user_id)
            except Exception:
                pass

        context = self._context()

        if comando_direto:
            # Só plugins de comando participam -- sem base de
            # conhecimento (é pra perguntas, não comandos), sem
            # conversa natural, sem IA.
            plugin_name, answer = self.plugins.dispatch(text, context)
            if answer is None:
                plugin_name = "comando_nao_reconhecido"
                answer = Answer(
                    f'Não conheço o comando "/{text}". Diga "ajuda" (sem a barra) pra ver o '
                    "que eu sei fazer, ou mande a mensagem sem a barra pra eu tentar entender "
                    "e conversar/pesquisar normalmente.",
                    Confidence.GUESS,
                )
        else:
            # PRIORIDADE MÁXIMA: consulta a base de conhecimento curada
            # antes de qualquer outra coisa. Se ela tiver uma resposta
            # relevante, usamos -- sem precisar buscar na Wikipedia ou
            # cair no fallback.
            plugin_name, answer = "knowledge_base", self._query_knowledge_base_first(text)

            if answer is None:
                plugin_name, answer = self.plugins.dispatch(text, context)

            # Raciocínio interno, NUNCA mostrado ao usuário (ver
            # core/intencao.py): se nenhum plugin soube executar e a
            # frase tem cara inequívoca de comando de sistema ("abre",
            # "fecha", "muta" etc.), evita deixar a conversa/IA
            # inventarem uma resposta em texto que parece ter feito
            # algo mas não executou nada -- mesma garantia do modo "/",
            # só que automática, sem precisar da barra. Só se aplica a
            # verbos inequívocos (ver docstring do módulo) -- qualquer
            # coisa ambígua (inclusive pedidos criativos como "cria uma
            # história") continua caindo na conversa/IA normalmente.
            if answer is None:
                from core import intencao
                if intencao.classificar(text) == "comando":
                    plugin_name = "comando_nao_reconhecido"
                    answer = Answer(
                        f'Não sei executar isso -- nenhum comando que eu conheço bate com "{text}". '
                        'Diga "ajuda" pra ver o que eu sei fazer, ou comece a mensagem com "/" pra eu '
                        "sempre tratar como comando direto.",
                        Confidence.GUESS,
                    )

            # Antes do fallback genérico, dá a chance da conversa natural
            # (saudação, despedida, humor, piada, etc.) responder -- é o
            # que faz "oi" ou "estou triste" terem uma resposta de verdade
            # em vez de cair direto no "não sei o que fazer com isso".
            if answer is None:
                conversational_answer = self.conversation.respond(text, context)
                if conversational_answer is not None:
                    plugin_name, answer = "conversa", conversational_answer

            # Estágio opcional de IA (externa configurada, ou modelo local)
            # -- só roda se nada dos estágios anteriores soube responder, e
            # só existe (self.ia_manager != None) se o módulo `ia` estiver
            # ligado em config.json. Ver ia/manager.py.
            if answer is None and self.ia_manager is not None:
                ia_answer = self._query_ia(text, context)
                if ia_answer is not None:
                    plugin_name, answer = "ia", ia_answer

            # Se nem a IA (incluindo NVIDIA, conforme a ordem configurada)
            # respondeu, tenta pesquisar a pergunta na internet antes de
            # admitir que não sabe.
            if answer is None:
                internet_answer = self._query_internet(text)
                if internet_answer is not None:
                    plugin_name, answer = "internet_auto", internet_answer

            if answer is None:
                answer = self._fallback_response(text)
                plugin_name = "fallback"

        # Conhecimento vindo de fontes externas (ex.: busca na Wikipedia,
        # via knowledge_search) é absorvido automaticamente na base de
        # conhecimento própria, já com fonte, categoria e confiança
        # corretas -- sem precisar de um comando "aprenda que ...".
        if plugin_name == "knowledge_search" and answer.confidence >= Confidence.SINGLE_SOURCE:
            self.knowledge.learn(
                self.user_id, answer.text,
                source="wikipedia", category="definition",
                confidence=answer.confidence,
            )

        # Salva no histórico só o texto puro da resposta (sem o
        # formato "Resposta:/Confiança:"), mantendo o log limpo.
        if not modo_privado:
            self.memory.add_message(self.user_id, "jarvis", answer.text)

        # Quando cai no fallback (nenhum plugin/base/conversa/IA soube
        # responder), grava também um trecho do texto original no
        # evento -- é isso que automacao/auto_melhoria.py lê depois
        # pra detectar pedidos que se repetem sem resposta e sugerir
        # uma habilidade nova pra eles.
        detalhe = f"plugin={plugin_name} confidence={answer.confidence}"
        if plugin_name == "fallback":
            detalhe += f" texto={text[:200]!r}"
        if not modo_privado:
            self.memory.log_event("message_processed", detalhe)

        mostrar_confianca = self.settings.get("personalidade.mostrar_confianca", False)
        return answer.format(mostrar_confianca=mostrar_confianca)

    def reload_plugins(self):
        self.plugins.load_plugins()  # usado por plugins/skill_forge.py após aprovar uma habilidade
        return [n for n, _ in self.plugins.list_plugins()]
