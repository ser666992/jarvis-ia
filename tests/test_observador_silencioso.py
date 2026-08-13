def test_periodic_dependency_updates_are_silent_by_default(monkeypatch):
    from automacao import notify
    from sistema import observador_internet

    monkeypatch.setattr(
        observador_internet, "verificar_agora",
        lambda jarvis: [{"pacote": "demo", "versao_antiga": "1", "versao_nova": "2"}])
    sent = []
    monkeypatch.setattr(notify, "notify", lambda *args: sent.append(args))

    class Settings:
        @staticmethod
        def get(key, default=None):
            return default

    class Jarvis:
        settings = Settings()

    observador_internet._tick(Jarvis())
    assert sent == []


def test_dependency_notifications_can_be_enabled(monkeypatch):
    from automacao import notify
    from sistema import observador_internet

    monkeypatch.setattr(
        observador_internet, "verificar_agora",
        lambda jarvis: [{"pacote": "demo", "versao_antiga": "1", "versao_nova": "2"}])
    monkeypatch.setattr(observador_internet, "resumir", lambda *args: "resumo")
    sent = []
    monkeypatch.setattr(notify, "notify", lambda *args: sent.append(args))

    class Settings:
        @staticmethod
        def get(key, default=None):
            return True if key == "sistema.observador_internet_notificar" else default

    class Jarvis:
        settings = Settings()

    observador_internet._tick(Jarvis())
    assert sent and sent[0][0].startswith("Neutron")
