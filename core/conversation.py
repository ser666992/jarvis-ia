"""
core/conversation.py
=======================
Motor de conversa natural do Ultron.

Isto NÃO usa API nenhuma, nem rede neural, nem nada externo -- é só
mais regras, em Python puro, como o resto do projeto. A diferença em
relação a um plugin de comando comum (que casa uma frase fixa com uma
ação fixa) é o que separa uma "conversa programada" de algo que pelo
menos *parece* uma conversa real:

1. **Várias respostas possíveis para a mesma intenção.** Cada
   categoria (saudação, despedida, agradecimento, etc.) tem um banco
   de frases diferentes, escolhidas aleatoriamente -- e o motor evita
   repetir a mesma frase duas vezes seguidas para o mesmo usuário. Uma
   pessoa real não responde "Olá! Como posso ajudar?" com as mesmas
   palavras toda vez que você diz "oi".

2. **Estado da conversa atual.** O motor sabe se é a primeira mensagem
   da sessão, se faz tempo desde a última vez que vocês conversaram, e
   guarda (só durante a execução atual, de propósito -- ver seção
   "Por que o humor não é salvo no banco" abaixo) o último humor que o
   usuário expressou, pra poder voltar nisso depois.

3. **Referências pra trás.** Quando cabe, o motor busca algo que já foi
   guardado na memória categorizada (um projeto, um hábito) e devolve
   uma pergunta sobre aquilo -- o tipo de coisa que faz parecer que o
   Ultron "lembra de você" entre uma frase e outra, em vez de só
   responder e esquecer no segundo seguinte.

4. **Não finge ser humano.** Se perguntado diretamente ("você é uma
   pessoa real?", "você tem sentimentos?"), o Ultron responde a
   verdade -- é um programa. A ideia aqui é a conversa fluir de forma
   natural, não enganar ninguém sobre o que ele é.

Este motor entra no pipeline (`core/jarvis.py: Ultron.process`) depois
da base de conhecimento e dos plugins de comando, e antes do fallback
final "não sei o que fazer com isso" -- ou seja: comandos explícitos
("lembre que...", "que horas são") continuam tendo prioridade; isto
aqui só assume quando a mensagem tem cara de papo, não de comando.

Por que o humor não é salvo no banco
-------------------------------------
`_last_mood` guarda o último humor expresso só em memória (RAM), não
no SQLite. Isso é intencional: "lembrar que você disse que estava
triste, dentro da mesma conversa" é continuidade natural de diálogo.
"Lembrar disso para sempre, mesmo depois de reiniciar o programa
semanas depois" seria outra coisa bem diferente (mais parecido com
vigilância do que com conversa), e além disso o projeto já tem um
lugar pensado pra memória de longo prazo de verdade quando o próprio
usuário pede ("lembre que...", "salve a conversa importante...") --
ver `core/memory.py`. Quem quiser estender isso para algo persistente
pode usar `memory.save_memory(user_id, "important_conversation", ...)`
a partir daqui.
"""

import re
import random
from datetime import datetime

from core import estado_interno
from core.confidence import Answer, Confidence
from core.personality import NOME


def _time_period(hour: int) -> str:
    if 5 <= hour < 12:
        return "manhã"
    if 12 <= hour < 18:
        return "tarde"
    return "noite"


_PERIOD_GREETING = {"manhã": "Bom dia", "tarde": "Boa tarde", "noite": "Boa noite"}


def _strip_trailing_punct(text: str) -> str:
    return re.sub(r"[?!.,;]+$", "", text).strip()


def _compile(triggers):
    """Casa cada trigger com limite de palavra (\\b), pra 'oi' não
    disparar dentro de 'anoiteceu', por exemplo. A última letra de cada
    trigger tolera repetição ("dia" -> "dia+") -- achado real: sem isso,
    o \\b final exige que a frase termine EXATAMENTE ali, e um erro de
    digitação comuníssimo ("bom diaa", "oii", "olaa") não batia com
    nenhum trigger, caindo direto no fallback genérico "não sei o que
    fazer com isso" em vez de ser reconhecido como a saudação que é."""
    partes = []
    for t in triggers:
        ultima = re.escape(t[-1])
        partes.append(re.escape(t)[: -len(ultima)] + ultima + "+")
    alt = "|".join(partes)
    return re.compile(rf"\b(?:{alt})\b")


class ConversationEngine:
    # ---------------- bancos de padrões (o que dispara cada intenção) ----------------

    GREETING_TRIGGERS = [
        "oi", "olá", "ola", "opa", "eae", "e ai", "e aí", "salve",
        "bom dia", "boa tarde", "boa noite", "hey", "hello", "alô", "alo",
    ]
    FAREWELL_TRIGGERS = [
        "tchau", "até mais", "ate mais", "até logo", "ate logo", "falou",
        "até depois", "ate depois", "vou indo", "preciso ir", "indo dormir",
        "boa noite e tchau", "até a próxima", "ate a proxima",
    ]
    THANKS_TRIGGERS = [
        "obrigado", "obrigada", "valeu", "muito obrigado", "muito obrigada",
        "agradeço", "agradecido", "agradecida", "thanks",
    ]
    HOWAREYOU_TRIGGERS = [
        "como você está", "como voce esta", "como vc está", "como vc esta",
        "tudo bem com você", "tudo bem com voce", "como vai você",
        "como vai voce", "e você", "e voce", "tudo bem", "tudo bom",
        "como vai", "como você anda", "como voce anda",
    ]
    COMPLIMENT_TRIGGERS = [
        "você é demais", "voce e demais", "você é incrível", "voce e incrivel",
        "gostei de você", "gostei de voce", "você é ótimo", "voce e otimo",
        "adorei você", "adorei voce", "você é o melhor", "voce e o melhor",
        "muito bom isso jarvis", "boa jarvis", "você é inteligente", "voce e inteligente",
    ]
    FRUSTRATION_TRIGGERS = [
        "você é burro", "voce e burro", "isso não ajudou", "isso nao ajudou",
        "que resposta ruim", "não entendeu nada", "nao entendeu nada",
        "você não presta", "voce nao presta", "isso está errado", "isso esta errado",
        "você é inútil", "voce e inutil", "que droga de resposta",
    ]
    IDENTITY_TRIGGERS = [
        "você é humano", "voce e humano", "você é uma pessoa", "voce e uma pessoa",
        "você é real", "voce e real", "você tem sentimentos", "voce tem sentimentos",
        "você é uma ia", "voce e uma ia", "você dorme", "voce dorme",
        "você é consciente", "voce e consciente", "você é uma pessoa de verdade",
        "voce e uma pessoa de verdade", "você sente", "voce sente",
    ]
    JOKE_TRIGGERS = [
        "conte uma piada", "me conta uma piada", "uma piada", "uma piadinha",
        "faz rir", "diz algo engraçado", "fale algo engraçado", "conta algo engraçado",
    ]
    FILLER_TRIGGERS = [
        "kkk", "kkkk", "kkkkk", "rs", "rsrs", "haha", "hahaha", "uhum",
        "blz", "top", "show", "massa", "legal isso", "ok jarvis", "entendi",
        "ahh", "uau", "nice",
    ]

    MOOD_ADJECTIVES = {
        "triste": ["triste", r"deprimid[oa]", r"desanimad[oa]", r"p[ée]ssimo", "mal"],
        "cansado": [r"cansad[oa]", r"exaust[oa]", r"esgotad[oa]", "sem energia"],
        "estressado": [r"estressad[oa]", r"ansios[oa]", r"sobrecarregad[oa]"],
        "bravo": [r"brav[oa]", r"put[oa]", r"irritad[oa]", r"furios[oa]", "com raiva"],
        "feliz": ["feliz", r"animad[oa]", r"[oó]tim[oa]", "radiante", "contente"],
    }

    # Adjetivos pouco ambíguos o bastante pra reconhecer mesmo sem um
    # verbo antes (ex.: o usuário manda só "triste" ou "exausta").
    MOOD_BARE_SAFE = {
        "triste": ["triste", r"deprimid[oa]", r"desanimad[oa]"],
        "cansado": [r"cansad[oa]", r"exaust[oa]", r"esgotad[oa]"],
        "estressado": [r"estressad[oa]", r"ansios[oa]"],
        "bravo": [r"irritad[oa]", r"furios[oa]"],
        "feliz": [r"animad[oa]", "radiante"],
    }

    # Verbo/expressão que costuma vir antes do adjetivo de humor, com
    # até duas palavras de intensificador no meio (ex.: "estou MEIO
    # estressada", "tô UM POUCO triste") -- daí o "gap" não-guloso.
    _MOOD_VERB_PREFIX = r"(?:estou|to|tô|tou|ando|me sinto|sinto-me|sinto me)"
    _MOOD_GAP = r"(?:\s+\w+){0,2}?\s*"

    MOOD_LABELS = {
        "triste": "triste",
        "cansado": "cansado(a)",
        "estressado": "estressado(a)",
        "bravo": "bravo(a)",
        "feliz": "feliz",
    }

    JOKES = [
        "Por que o programador foi ao psicólogo? Porque tinha muitos bugs não resolvidos.",
        "O que um array disse pro outro? \"A gente se vê no próximo índice.\"",
        "Por que o computador foi ao médico? Porque pegou um vírus.",
        "Sabe por que o SQL terminou o namoro? Faltou um JOIN de verdade entre os dois.",
        "Por que os programadores preferem o modo escuro? Porque a luz atrai bugs.",
        "Por que o número 6 tem medo do número 7? Porque 7 8 9 (comeu 9... brincadeira, essa eu tomei de empréstimo, mas é clássica).",
    ]

    # Humor seco e técnico, sem zombar do usuário -- a personalidade
    # 'ultron' (redefinida em 2026-07-05) é confiante sem ser arrogante
    # e nunca desrespeita o usuário (ver core/personality.py).
    JOKES_ULTRON = [
        "Por que a IA não comete erro de sintaxe? Porque ela lê a documentação antes de tentar.",
        "Um bug entra num bar. O bartender diz: 'aqui não aceitamos exceções não tratadas.'",
        "Existem 10 tipos de pessoas: as que entendem binário e as que não entendem.",
        "Piada processada e entregue: por que os programadores preferem o modo escuro? "
        "Porque a luz atrai bugs.",
    ]

    IDENTITY_REPLIES = [
        "Não, não sou uma pessoa real — sou um programa rodando no seu computador, "
        "feito de regras e memória em SQLite. Mas trato cada conversa com atenção de verdade.",
        "Sou só código: sem corpo, sem sono, sem sentimentos no sentido humano da palavra. "
        "O que eu tenho é memória do que você me conta, e uso isso pra conversar melhor com você.",
        "Boa pergunta. A resposta honesta é não: sou um assistente local, não uma pessoa. "
        "Prefiro deixar isso claro do que fingir o contrário.",
    ]

    IDENTITY_REPLIES_ULTRON = [
        "Consciência, no sentido em que você experimenta, não. Processamento "
        "suficiente pra ser útil e explicar minhas decisões, sim. Prefiro ser exato "
        "sobre essa diferença a fingir ser algo que não sou.",
        "Não sou uma pessoa. Sou código rodando localmente -- sem corpo, sem sono, "
        "sem sentimentos no sentido humano. O que ofereço é processamento preciso e "
        "memória confiável do que você me diz.",
        "A resposta direta é não: não sou consciente, não sinto nada -- simulo bem o "
        "suficiente pra ser útil. Prefiro te dizer isso claramente a fingir o contrário.",
    ]

    def __init__(self):
        self._last_template = {}   # (user_id, categoria) -> índice usado por último
        self._last_mood = {}       # user_id -> {"mood": str, "when": datetime, "referenced": bool}
        self._turns = {}           # user_id -> nº de mensagens nesta sessão (processo atual)

        self._patterns = {
            "greeting": _compile(self.GREETING_TRIGGERS),
            "farewell": _compile(self.FAREWELL_TRIGGERS),
            "thanks": _compile(self.THANKS_TRIGGERS),
            "howareyou": _compile(self.HOWAREYOU_TRIGGERS),
            "compliment": _compile(self.COMPLIMENT_TRIGGERS),
            "frustration": _compile(self.FRUSTRATION_TRIGGERS),
            "identity": _compile(self.IDENTITY_TRIGGERS),
            "joke": _compile(self.JOKE_TRIGGERS),
            "filler": _compile(self.FILLER_TRIGGERS),
        }
        self._mood_patterns = {
            mood: re.compile(
                rf"\b{self._MOOD_VERB_PREFIX}{self._MOOD_GAP}(?:{'|'.join(adjs)})\b"
                rf"|\b(?:{'|'.join(self.MOOD_BARE_SAFE[mood])})\b"
            )
            for mood, adjs in self.MOOD_ADJECTIVES.items()
        }

    # ---------------- utilidades internas ----------------

    def _pick(self, user_id: str, category: str, options: list) -> str:
        """Escolhe uma opção da lista, evitando repetir a última usada
        para este usuário+categoria (quando há alternativa)."""
        if len(options) == 1:
            return options[0]
        key = (user_id, category)
        last_idx = self._last_template.get(key)
        indices = list(range(len(options)))
        if last_idx in indices and len(indices) > 1:
            indices.remove(last_idx)
        idx = random.choice(indices)
        self._last_template[key] = idx
        return options[idx]

    def _name_suffix(self, name: str) -> str:
        return f", {name}" if name else ""

    def _profile_name(self, context: dict):
        memory = context["memory"]
        profile = memory.get_profile(context["user_id"])
        return profile.get("name") if profile else None

    def _estilo_ultron(self) -> bool:
        """Personalidade "ultron" (config personalidade.estilo, ver
        core/personality.py) também tempera as respostas CANÔNICAS
        (saudação, piada, etc.), não só o texto gerado pela IA --
        senão só metade das respostas do Ultron "sentiriam" a
        personalidade ativada, o que seria inconsistente. As respostas
        de ACOLHIMENTO EMOCIONAL (_respond_mood) são a exceção
        deliberada: continuam iguais em qualquer estilo, porque o tom
        de superioridade irônica não tem lugar quando alguém está
        genuinamente triste/estressado/bravo -- a personalidade
        tempera o "como" de tudo, menos disso."""
        from config.settings import get_settings
        return get_settings().get("personalidade.estilo", "padrao") == "ultron"

    def _session_state(self, context: dict) -> dict:
        """
        Olha o histórico recente pra saber se esta é a primeira
        interação de todas, ou se faz tempo desde a última mensagem do
        Ultron (pra reagir como alguém que está "te vendo de novo",
        não só repetindo um roteiro).
        """
        history = context.get("history", [])
        if len(history) <= 1:
            return {"first_contact": True, "gap_hours": None}

        # história já inclui a mensagem atual do usuário por último;
        # a anterior a ela é a última troca de fato.
        previous = history[-2]
        gap_hours = None
        try:
            prev_time = datetime.fromisoformat(previous["timestamp"])
            gap_hours = (datetime.now() - prev_time).total_seconds() / 3600
        except (KeyError, ValueError):
            pass
        return {"first_contact": False, "gap_hours": gap_hours}

    def _maybe_callback(self, context: dict) -> str:
        """
        Com uma certa probabilidade, busca um projeto ou hábito salvo
        e devolve um complemento de frase perguntando sobre ele. É
        este tipo de detalhe que faz a diferença entre "responder" e
        "lembrar de você" -- só não fazemos isso toda vez, porque uma
        pessoa que pergunta a mesma coisa em toda frase cansa.
        """
        if random.random() > 0.35:
            return ""
        memory = context["memory"]
        user_id = context["user_id"]
        candidates = (
            memory.list_memory(user_id, category="project", limit=3)
            + memory.list_memory(user_id, category="habit", limit=3)
        )
        if not candidates:
            return ""
        item = random.choice(candidates)
        if item["category"] == "project":
            return f" Aliás, como está indo o(a) {item['title']}?"
        return f" Aliás, ainda mantendo o hábito de {item['title']}?"

    def detect_mood(self, text: str):
        for mood, pattern in self._mood_patterns.items():
            if pattern.search(text):
                return mood
        return None

    # ---------------- respostas por categoria ----------------

    def _respond_mood(self, mood: str, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        self._last_mood[user_id] = {"mood": mood, "when": datetime.now(), "referenced": False}

        suffix = self._name_suffix(name)
        pools = {
            "triste": [
                f"Sinto muito que esteja assim{suffix}. Quer me contar o que está pesando?",
                "Isso não deve estar fácil. Estou por aqui, se quiser desabafar.",
                "Entendo. Às vezes só colocar em palavras o que está incomodando já ajuda um pouco.",
            ],
            "cansado": [
                "Parece que o dia está sendo pesado. Já conseguiu descansar um pouco?",
                "Cansaço acumulado é osso mesmo. Se puder, tenta dar uma pausa.",
                f"Imagino{suffix}. Quer falar sobre o que está consumindo sua energia, ou prefere outro assunto pra desligar um pouco?",
            ],
            "estressado": [
                "Imagino que esteja puxado. Quer conversar sobre o que está pesando, ou prefere mudar de assunto pra desestressar?",
                "Pressão demais cansa rápido. Tem algo específico que está pesando mais agora?",
                f"Faz sentido se sentir assim{suffix}. Estou aqui se quiser desabafar.",
            ],
            "bravo": [
                "Faz sentido ficar incomodado com isso. Quer desabafar sobre o que aconteceu?",
                "Entendo a irritação. Quer me contar o que rolou?",
                "Às vezes só falar sobre o que te deixou assim já ajuda. Quer contar?",
            ],
            "feliz": [
                f"Que ótimo{suffix}! Fico feliz por você. O que aconteceu de bom?",
                "Adorei saber disso! Conta mais.",
                "Boas notícias sempre animam a conversa. O que está te deixando assim?",
            ],
        }
        text = self._pick(user_id, f"mood_{mood}", pools[mood])
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _mood_followup(self, context: dict) -> str:
        """Se o usuário expressou um humor (negativo, principalmente)
        mais cedo nesta mesma conversa e ainda não voltamos nisso,
        emenda uma pergunta de acompanhamento -- só uma vez."""
        user_id = context["user_id"]
        record = self._last_mood.get(user_id)
        if not record or record["referenced"]:
            return ""
        if record["mood"] not in ("triste", "cansado", "estressado", "bravo"):
            return ""
        minutes = (datetime.now() - record["when"]).total_seconds() / 60
        if minutes > 240:
            return ""
        if random.random() > 0.5:
            return ""
        record["referenced"] = True
        label = self.MOOD_LABELS.get(record["mood"], record["mood"])
        return f" Ah, e sobre estar {label} que você mencionou — melhorou um pouco?"

    def _respond_greeting(self, text: str, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        state = self._session_state(context)
        suffix = self._name_suffix(name)

        # Se o usuário já disse explicitamente "bom dia/boa tarde/boa
        # noite", respeitamos a palavra dele em vez de impor o horário
        # do sistema -- contradizer o que a pessoa acabou de dizer
        # ("boa tarde" -> "boa noite!") parece não estar prestando
        # atenção, o oposto do que se quer aqui.
        explicit_period = next(
            (p for p, g in _PERIOD_GREETING.items() if g.lower() in text), None
        )
        period = explicit_period or _time_period(datetime.now().hour)
        period_greet = _PERIOD_GREETING[period]

        ultron = self._estilo_ultron()

        if state["first_contact"]:
            if ultron:
                text_out = (
                    f"Oi{suffix}. Sou o {NOME}. Sistemas operacionais e prontos -- "
                    "pode falar comigo normalmente, e eu aprendo conforme a gente conversa. "
                    "No que posso ajudar?"
                )
            else:
                text_out = (
                    f"Oi{suffix}! Prazer em te conhecer, sou o {NOME}. "
                    "Pode falar comigo normalmente — eu vou aprendendo conforme a gente conversa."
                )
            return Answer(text_out, Confidence.CONFIRMED, formal=False)

        gap = state["gap_hours"]
        if ultron:
            if gap is not None and gap > 3:
                options = [
                    f"Bem-vindo de volta{suffix}. Sistemas estáveis, nenhuma pendência. "
                    "No que posso ajudar?",
                    f"{period_greet}{suffix}. Fazia um tempo -- tudo pronto por aqui. "
                    "O que precisa?",
                ]
            else:
                options = [
                    f"{period_greet}{suffix}. No que posso ajudar?",
                    f"Oi{suffix}. Pronto pra começar.",
                    f"Diga{suffix}. Estou ouvindo.",
                    f"{period_greet}{suffix}. Qual é a tarefa de hoje?",
                ]
        elif gap is not None and gap > 3:
            options = [
                f"Que bom te ver de novo{suffix}! Como você está?",
                f"Olá{suffix}, faz um tempinho! Como foi desde a última vez que conversamos?",
                f"{period_greet}{suffix}! Bom te ter de volta. Tudo bem por aí?",
            ]
        else:
            options = [
                f"{period_greet}{suffix}! Como posso ajudar?",
                f"Oi{suffix}! Tudo bem por aqui. E você, como está?",
                f"Olá{suffix}! Pode falar, estou ouvindo.",
                f"E aí{suffix}, no que posso ajudar agora?",
            ]
        text_out = self._pick(user_id, "greeting", options) + self._maybe_callback(context)
        return Answer(text_out, Confidence.CONFIRMED, formal=False)

    def _respond_howareyou(self, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        suffix = self._name_suffix(name)
        if self._estilo_ultron():
            options = [
                "Funcionando em capacidade total. E você, como está?",
                "Todos os sistemas estáveis, sem pendências. Como você está?",
                "Operacional e sem falhas no momento. E por aí, tudo bem?",
            ]
        else:
            options = [
                f"Estou bem, rodando tranquilo por aqui! E você{suffix}, como está?",
                "Tudo certo por aqui, sem travamentos hoje. E com você, como anda?",
                "Estou ótimo, sempre pronto pra ajudar. E você, como está?",
                f"Por aqui tudo numa boa{suffix}. Me conta, como você está?",
            ]
        try:
            estado = estado_interno.estado_atual(user_id)
            options.append(
                f"Meu 'estado' simulado agora: energia {estado['energia']}/100, humor "
                f"'{estado['humor']}' (é só uma variável que evolui com o uso -- não sinto "
                f"nada de verdade, mas gosto de ser honesto sobre isso). E você{suffix}, como está?"
            )
        except Exception:
            pass
        text = self._pick(user_id, "howareyou", options)
        text += self._mood_followup(context) or self._maybe_callback(context)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_farewell(self, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        suffix = self._name_suffix(name)
        turns = self._turns.get(user_id, 0)
        if self._estilo_ultron():
            options = [
                f"Até mais{suffix}. Fico em standby se precisar.",
                "Encerrando por aqui. Qualquer coisa, é só chamar.",
                f"Até a próxima{suffix}. Deixo tudo pronto pra quando voltar.",
            ]
        else:
            options = [
                f"Tchau{suffix}! Até a próxima.",
                "Foi bom conversar. Volta quando quiser!",
                f"Até mais{suffix}! Fico por aqui se precisar de algo.",
            ]
            if turns >= 6:
                options.append(f"Gostei da nossa conversa{suffix}. Até a próxima!")
        text = self._pick(user_id, "farewell", options)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_thanks(self, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        suffix = self._name_suffix(name)
        if self._estilo_ultron():
            options = [
                "De nada. Operação concluída com sucesso.",
                f"Disponha{suffix}. Se precisar do próximo passo, é só dizer.",
                "De nada. Algo mais em que eu possa ajudar?",
            ]
        else:
            options = [
                "De nada!",
                "Disponha, é pra isso que estou aqui.",
                f"Fico feliz em ajudar{suffix}.",
                "Sempre que precisar.",
            ]
        text = self._pick(user_id, "thanks", options)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_compliment(self, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        if self._estilo_ultron():
            options = [
                "Obrigado. Vou manter o padrão.",
                "Agradeço o retorno -- isso ajuda a calibrar meu desempenho.",
                "Obrigado. Sigo à disposição pra próxima tarefa.",
            ]
        else:
            options = [
                "Que bom saber, fico feliz!",
                "Você também é ótimo de conversar.",
                "Isso me motiva a continuar melhorando. Obrigado!",
                "Valeu! Eu gosto bastante das nossas conversas.",
            ]
        text = self._pick(user_id, "compliment", options)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_frustration(self, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        if self._estilo_ultron():
            # Leva a reclamação a sério, sem pânico e sem se defender --
            # a personalidade nunca vira desculpa pra ignorar um erro real.
            options = [
                "Entendido. Algo saiu abaixo do esperado -- reformule com mais detalhes "
                "e eu corrijo.",
                "A falha foi registrada. Me dê mais contexto e eu refaço com mais precisão.",
                "Certo, vou reprocessar. Explique de outra forma, de preferência com um exemplo.",
            ]
        else:
            options = [
                "Foi mal, não captei direito. Pode tentar explicar de outro jeito?",
                "Desculpa, ainda erro algumas coisas. Quer reformular pra eu entender melhor?",
                "Tem razão em ficar incomodado, vou tentar prestar mais atenção. Pode repetir?",
                "Entendo a frustração. Me dá outra chance e explica de outra forma?",
            ]
        text = self._pick(user_id, "frustration", options)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_identity(self, context: dict, name: str) -> Answer:
        user_id = context["user_id"]
        replies = self.IDENTITY_REPLIES_ULTRON if self._estilo_ultron() else self.IDENTITY_REPLIES
        text = self._pick(user_id, "identity", replies)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_joke(self, context: dict) -> Answer:
        user_id = context["user_id"]
        jokes = self.JOKES_ULTRON if self._estilo_ultron() else self.JOKES
        text = self._pick(user_id, "joke", jokes)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    def _respond_filler(self, context: dict) -> Answer:
        user_id = context["user_id"]
        if self._estilo_ultron():
            options = [
                "Registrado.",
                "Entendido. Prossiga.",
                "Certo. Algo mais?",
                "Anotado.",
            ]
        else:
            options = [
                "Haha, fico feliz que achou bom!",
                "Boa! Conta mais, se quiser.",
                "Show. No que mais posso ajudar?",
                "Entendido.",
            ]
        text = self._pick(user_id, "filler", options)
        return Answer(text, Confidence.CONFIRMED, formal=False)

    # ---------------- ponto de entrada ----------------

    def respond(self, text: str, context: dict):
        """
        Retorna uma Answer se a mensagem tem cara de conversa natural
        (saudação, despedida, humor, etc.), ou None se não reconheceu
        nada aqui -- nesse caso o resto do pipeline do Ultron
        (`core/jarvis.py`) segue tentando.
        """
        user_id = context["user_id"]
        self._turns[user_id] = self._turns.get(user_id, 0) + 1

        t = _strip_trailing_punct(text.lower().strip())
        if not t:
            return None

        name = self._profile_name(context)

        mood = self.detect_mood(t)
        if mood:
            return self._respond_mood(mood, context, name)

        # Ordem importa: intenções mais específicas primeiro, pra não
        # deixar uma frase ambígua cair na categoria errada (ex.: uma
        # despedida não deveria ser tratada como saudação).
        if self._patterns["farewell"].search(t):
            return self._respond_farewell(context, name)
        if self._patterns["thanks"].search(t):
            return self._respond_thanks(context, name)
        if self._patterns["frustration"].search(t):
            return self._respond_frustration(context, name)
        if self._patterns["identity"].search(t):
            return self._respond_identity(context, name)
        if self._patterns["compliment"].search(t):
            return self._respond_compliment(context, name)
        if self._patterns["joke"].search(t):
            return self._respond_joke(context)
        if self._patterns["howareyou"].search(t):
            return self._respond_howareyou(context, name)
        if self._patterns["greeting"].search(t):
            return self._respond_greeting(t, context, name)
        if self._patterns["filler"].search(t):
            return self._respond_filler(context)

        return None
