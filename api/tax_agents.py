"""Google Places-backed tax agent recommendations."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from knowledge_engine.config import settings

logger = logging.getLogger(__name__)

_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
])


def _place_name(place: dict[str, Any]) -> str:
    display = place.get("displayName") or {}
    return str(display.get("text") or "").strip()


def rank_places(places: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Normalize and rank places by Google rating, then review count."""
    normalized = []
    for place in places:
        name = _place_name(place)
        if not name:
            continue
        normalized.append({
            "name": name,
            "address": place.get("formattedAddress") or "",
            "phone": place.get("nationalPhoneNumber")
            or place.get("internationalPhoneNumber")
            or "",
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount") or 0,
        })
    normalized.sort(
        key=lambda p: (p.get("rating") or 0, p.get("user_rating_count") or 0),
        reverse=True,
    )
    return normalized[: max(0, min(limit, 5))]


def search_tax_agents(postcode: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Return up to five tax agents near an Australian postcode; fail closed."""
    postcode = (postcode or "").strip()
    api_key = settings.google_maps_api_key
    if not api_key or not postcode:
        return []
    max_results = max(1, min(limit or settings.tax_agent_max_results, 5))
    try:
        res = httpx.post(
            _TEXT_SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": _FIELD_MASK,
            },
            json={
                "textQuery": f"tax agent near {postcode}",
                "regionCode": "AU",
                "languageCode": "en",
                "maxResultCount": max_results,
                "includePureServiceAreaBusinesses": True,
            },
            timeout=8.0,
        )
        res.raise_for_status()
        return rank_places((res.json() or {}).get("places") or [], limit=max_results)
    except Exception:
        logger.warning("tax agent search failed", exc_info=True)
        return []
