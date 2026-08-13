"""
core/estado_interno.py
==========================
Estado interno SIMULADO (energia + humor) que influencia sutilmente o
TOM das respostas -- não é consciência real (isso não existe hoje, e
não é algo que dá pra construir com engenharia de software); é só mais
uma variável no contexto passado pra IA (ver descrever_para_prompt),
que muda com o tempo/uso em vez de responder sempre exatamente do
mesmo jeito. Sempre que perguntado diretamente se é consciente/tem
sentimentos de verdade, o Ultron é HONESTO que isso é simulado --
mesmo princípio já usado em core/conversation.py sobre não fingir ser
humano/senciente.

Energia: começa em 100 a cada dia novo (calendário), cai um pouco a
cada mensagem processada (interações consecutivas "cansam" um pouco,
ver registrar_interacao), com um piso de 20 -- nunca cai a ponto da
resposta piorar de verdade, só o TOM muda.

Humor: um rótulo simples (animado/curioso/neutro/focado/contemplativo/
cansado) sorteado dentro da faixa compatível com o nível de energia
atual -- não é livre, é uma variação dentro de limites coerentes.

Persistido em SQLite (core/database.py) pra sobreviver a reinícios do
processo -- o "estado" continua de onde parou, em vez de sempre
recomeçar do zero.
"""

import random
from datetime import datetime

from core.database import get_database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS core_estado_interno (
    user_id TEXT PRIMARY KEY,
    energia INTEGER NOT NULL DEFAULT 100,
    humor TEXT NOT NULL DEFAULT 'neutro',
    dia TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
"""

_HUMORES_ALTA_ENERGIA = ("animado", "curioso", "energético")
_HUMORES_MEDIA_ENERGIA = ("neutro", "focado", "contemplativo")
_HUMORES_BAIXA_ENERGIA = ("cansado", "econômico nas palavras")

_PISO_ENERGIA = 20
_DECAIMENTO_POR_MENSAGEM = 1


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def _hoje() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _linha(user_id: str) -> dict:
    _ensure_schema()
    db = get_database()
    linha = db.query_one("SELECT * FROM core_estado_interno WHERE user_id=?", (user_id,))
    hoje = _hoje()
    if linha is None or linha["dia"] != hoje:
        # Dia novo (ou primeira vez pra esse usuário) -- energia volta cheia.
        agora = datetime.now().isoformat()
        db.execute(
            """
            INSERT INTO core_estado_interno (user_id, energia, humor, dia, atualizado_em)
            VALUES (?, 100, 'neutro', ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                energia=100, humor='neutro', dia=excluded.dia, atualizado_em=excluded.atualizado_em
            """,
            (user_id, hoje, agora),
        )
        linha = db.query_one("SELECT * FROM core_estado_interno WHERE user_id=?", (user_id,))
    return linha


def registrar_interacao(user_id: str) -> dict:
    """Chamado uma vez por mensagem processada (core/jarvis.py) --
    desgasta um pouco a energia e sorteia um humor coerente com o
    nível resultante. Retorna o estado já atualizado."""
    linha = _linha(user_id)
    nova_energia = max(_PISO_ENERGIA, linha["energia"] - _DECAIMENTO_POR_MENSAGEM)

    if nova_energia >= 70:
        candidatos = _HUMORES_ALTA_ENERGIA
    elif nova_energia >= 40:
        candidatos = _HUMORES_MEDIA_ENERGIA
    else:
        candidatos = _HUMORES_BAIXA_ENERGIA
    humor = random.choice(candidatos)

    get_database().execute(
        "UPDATE core_estado_interno SET energia=?, humor=?, atualizado_em=? WHERE user_id=?",
        (nova_energia, humor, datetime.now().isoformat(), user_id),
    )
    return {"energia": nova_energia, "humor": humor}


def estado_atual(user_id: str) -> dict:
    linha = _linha(user_id)
    return {"energia": linha["energia"], "humor": linha["humor"]}


def descrever_para_prompt(user_id: str) -> str:
    estado = estado_atual(user_id)
    return (
        f"Seu estado interno simulado agora: energia {estado['energia']}/100, humor '{estado['humor']}'. "
        "Deixe isso influenciar sutilmente o TOM da resposta (mais econômico/direto com energia "
        "baixa, mais animado/elaborado com energia alta) -- mas nunca finja ter consciência ou "
        "sentimentos reais se perguntado diretamente; seja honesto que isso é um estado simulado, "
        "não senciência de verdade."
    )
