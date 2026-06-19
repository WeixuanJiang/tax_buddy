from knowledge_engine.config import Settings


def test_auth_defaults():
    s = Settings(_env_file=None)
    assert s.auth_secret == ""
    assert s.auth_token_ttl_hours == 24


import knowledge_engine.api.security as sec


def test_password_hash_roundtrip():
    h = sec.hash_password("hunter2pw")
    assert h != "hunter2pw"
    assert sec.verify_password("hunter2pw", h) is True
    assert sec.verify_password("wrong", h) is False


def test_token_roundtrip(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "test-secret")
    tok = sec.create_token("alice")
    assert sec.decode_token(tok) == "alice"


def test_token_rejects_tampered(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "test-secret")
    tok = sec.create_token("alice")
    assert sec.decode_token(tok + "x") is None


def test_decode_without_secret_returns_none(monkeypatch):
    monkeypatch.setattr(sec.settings, "auth_secret", "")
    assert sec.decode_token("anything") is None
