import json
from types import SimpleNamespace

from automacao.instagram_auto import analisar_perfil_contato
from core import instagram_profiles


def test_salva_e_recupera_perfil_por_usuario_e_contato():
    perfil = {"tom": "leve", "tamanho": "curto", "emojis": "poucos"}

    salvo = instagram_profiles.save("angelo", "Contato", perfil, 12)

    assert salvo["sample_count"] == 12
    assert salvo["profile"] == perfil
    assert instagram_profiles.get("outro", "Contato") is None


def test_prompt_do_contato_nao_inclui_conversa_bruta():
    instagram_profiles.save(
        "angelo",
        "Contato",
        {
            "tom": "brincalhão",
            "tamanho": "uma frase",
            "vocabulario": "informal",
            "emojis": "raros",
            "dinamica": "amizade",
            "evitar": "formalidade",
        },
        20,
    )

    prompt = instagram_profiles.prompt_for("angelo", "Contato")

    assert "brincalhão" in prompt
    assert "formalidade" in prompt
    assert "profile_json" not in prompt


def test_analise_filtra_campos_e_limita_texto():
    resposta = json.dumps({
        "tom": "casual",
        "tamanho": "curto",
        "vocabulario": "simples",
        "emojis": "nenhum",
        "dinamica": "amigos",
        "assuntos": ["jogos"],
        "evitar": "respostas formais",
        "campo_injetado": "não deve ser salvo",
    })

    class FakeIA:
        def chat(self, *_args, **_kwargs):
            return "fake", resposta

    jarvis = SimpleNamespace(user_id="angelo", ia_manager=FakeIA())
    mensagens = [
        {"autor": "eu", "texto": "e aí"},
        {"autor": "contato", "texto": "beleza"},
    ]

    salvo = analisar_perfil_contato(jarvis, "Contato", mensagens)

    assert salvo["sample_count"] == 2
    assert "campo_injetado" not in salvo["profile"]
    assert salvo["profile"]["tom"] == "casual"

