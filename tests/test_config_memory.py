from knowledge_engine.config import Settings


def test_memory_defaults_off_and_local():
    s = Settings(_env_file=None)
    assert s.memory_enabled is False
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"


def test_memory_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    s = Settings(_env_file=None)
    assert s.memory_enabled is True


def test_google_places_defaults_disabled():
    s = Settings(_env_file=None)
    assert s.google_maps_api_key == ""
    assert s.tax_agent_max_results == 5
