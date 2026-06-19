from knowledge_engine.config import Settings


def test_auth_defaults():
    s = Settings(_env_file=None)
    assert s.auth_secret == ""
    assert s.auth_token_ttl_hours == 24
