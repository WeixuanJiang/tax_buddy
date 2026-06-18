"""Derive structured metadata (income year, doc type, breadcrumb) from an ATO URL."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_YEAR_RE = re.compile(r"/((?:19|20)\d{2})(?:/|$)")
_ROOT = "individuals-and-families"


def url_path_segments(url: str) -> list[str]:
    segs = urlparse(url).path.strip("/").split("/")
    if segs and segs[0] == _ROOT:
        segs = segs[1:]
    return [s for s in segs if s]


def income_year(url: str) -> int | None:
    """Year folder in the URL (= income year ending 30 June). None = evergreen."""
    m = _YEAR_RE.search(urlparse(url).path)
    return int(m.group(1)) if m else None


def doc_type(url: str) -> str:
    u = url.lower()
    if "mytax-instructions" in u:
        return "mytax-instruction"
    if "paper-tax-return-instructions" in u:
        return "paper-instruction"
    if "guides-for-occupations-and-industries" in u:
        return "occupation-guide"
    return "topic"


def breadcrumb(url: str) -> str:
    """Human-readable trail from URL segments, e.g.
    'Income deductions offsets and records > Deductions you can claim > ...'."""
    segs = url_path_segments(url)
    # drop the trailing slug (it's the page itself, captured as title)
    parts = segs[:-1] if len(segs) > 1 else segs
    pretty = [s.replace("-", " ").strip().capitalize() for s in parts]
    return " > ".join(pretty)


def is_evergreen(url: str) -> bool:
    return income_year(url) is None
