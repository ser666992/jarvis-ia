"""
tests/test_auth.py
=====================
seguranca/auth.py: PIN/senha local com hash PBKDF2. Cobertura mínima
pra garantir que a troca de `==` por `hmac.compare_digest()` (tempo
constante, evita canal lateral de timing) não mudou o comportamento --
senha certa continua verificando True, errada continua False.
"""

import seguranca.auth as auth


def test_senha_correta_verifica():
    auth.set_password("usuario_teste", "minha-senha-123")
    assert auth.verify_password("usuario_teste", "minha-senha-123") is True


def test_senha_errada_nao_verifica():
    auth.set_password("usuario_teste", "minha-senha-123")
    assert auth.verify_password("usuario_teste", "senha-errada") is False


def test_usuario_sem_senha_nao_verifica():
    assert auth.verify_password("usuario_sem_senha_nenhuma", "qualquer") is False


def test_has_password():
    assert auth.has_password("usuario_teste") is False
    auth.set_password("usuario_teste", "123456")
    assert auth.has_password("usuario_teste") is True


def test_trocar_senha_invalida_a_antiga():
    auth.set_password("usuario_teste", "senha-antiga")
    auth.set_password("usuario_teste", "senha-nova")
    assert auth.verify_password("usuario_teste", "senha-antiga") is False
    assert auth.verify_password("usuario_teste", "senha-nova") is True


def test_admin_flag():
    auth.set_password("usuario_admin", "123456", admin=True)
    assert auth.is_admin("usuario_admin") is True
    auth.set_password("usuario_comum", "123456", admin=False)
    assert auth.is_admin("usuario_comum") is False
