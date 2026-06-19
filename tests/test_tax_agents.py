from knowledge_engine.api import tax_agents


def test_rank_places_orders_by_rating_then_reviews():
    places = [
        {"displayName": {"text": "Few Reviews"}, "rating": 4.9, "userRatingCount": 3},
        {"displayName": {"text": "Many Reviews"}, "rating": 4.9, "userRatingCount": 200},
        {"displayName": {"text": "Lower Rating"}, "rating": 4.7, "userRatingCount": 999},
    ]

    ranked = tax_agents.rank_places(places, limit=2)

    assert [p["name"] for p in ranked] == ["Many Reviews", "Few Reviews"]


def test_search_tax_agents_disabled_without_key(monkeypatch):
    monkeypatch.setattr(tax_agents.settings, "google_maps_api_key", "")

    assert tax_agents.search_tax_agents("2000") == []


def test_search_tax_agents_calls_google_text_search(monkeypatch):
    captured = {}
    monkeypatch.setattr(tax_agents.settings, "google_maps_api_key", "key")
    monkeypatch.setattr(tax_agents.settings, "tax_agent_max_results", 5)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    {
                        "displayName": {"text": "Agent A"},
                        "formattedAddress": "1 Example St",
                        "rating": 4.8,
                        "userRatingCount": 100,
                        "nationalPhoneNumber": "(02) 1234 5678",
                        "googleMapsUri": "https://maps.example/a",
                    }
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(tax_agents.httpx, "post", fake_post)

    out = tax_agents.search_tax_agents("2000")

    assert captured["url"].endswith("/places:searchText")
    assert captured["json"]["textQuery"] == "tax agent near 2000"
    assert captured["json"]["regionCode"] == "AU"
    assert captured["headers"]["X-Goog-Api-Key"] == "key"
    assert "places.nationalPhoneNumber" in captured["headers"]["X-Goog-FieldMask"]
    assert "places.googleMapsUri" not in captured["headers"]["X-Goog-FieldMask"]
    assert out[0]["name"] == "Agent A"
    assert out[0]["phone"] == "(02) 1234 5678"
