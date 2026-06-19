"""Deterministic PII detection (Layer 1).

Pure-Python regex + Luhn detectors for the kinds of personally identifiable
information an ATO tax answer must never emit: tax file numbers, ABNs, Medicare
numbers, emails, Australian phone numbers, and credit-card numbers.

Tuned to avoid false positives on the things tax content legitimately contains:
plain dollar amounts ("$300"), income years ("2025"), section numbers, and
percentages do NOT match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PIIMatch:
    kind: str
    value: str


_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# AU mobile (04xx xxx xxx) or landline with area code; require >= 8 digits and a
# phone-ish shape so we don't flag dollar amounts or years.
_PHONE = re.compile(
    r"\b(?:\+?61|0)[2-478](?:[ -]?\d){7,9}\b"
)
# Tax File Number: 8-9 digits, commonly grouped 3-3-3 or 3-3-2.
_TFN = re.compile(r"\b\d{3}\s?\d{3}\s?\d{2,3}\b")
# ABN: 11 digits, commonly grouped 2 3 3 3.
_ABN = re.compile(r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b")
# Medicare card: 10 digits, commonly 4 5 1.
_MEDICARE = re.compile(r"\b\d{4}\s?\d{5}\s?\d{1}\b")
# Candidate card numbers: 13-19 digit runs (allowing spaces/dashes).
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(nums)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_pii(text: str) -> list[PIIMatch]:
    """Return every PII-looking span in `text` (possibly overlapping kinds)."""
    if not text:
        return []
    found: list[PIIMatch] = []

    for m in _EMAIL.finditer(text):
        found.append(PIIMatch("email", m.group()))
    for m in _PHONE.finditer(text):
        found.append(PIIMatch("phone", m.group().strip()))
    for m in _CARD_CANDIDATE.finditer(text):
        raw = m.group()
        if _luhn_ok(raw):
            found.append(PIIMatch("credit_card", raw.strip()))

    # Government identifiers: only flag when explicitly grouped with whitespace,
    # which is how a real number would be written and is very unlikely in prose.
    for pat, kind in ((_MEDICARE, "medicare"), (_ABN, "abn"), (_TFN, "tfn")):
        for m in pat.finditer(text):
            val = m.group()
            if " " in val:                       # grouped → almost certainly an ID
                found.append(PIIMatch(kind, val.strip()))

    return found


def contains_pii(text: str) -> bool:
    return bool(find_pii(text))
