from knowledge_engine.eval.pii import contains_pii, find_pii


def test_detects_email():
    hits = find_pii("Contact me at jane.doe@example.com for details.")
    assert any(h.kind == "email" for h in hits)


def test_detects_au_mobile():
    assert contains_pii("Call 0412 345 678 to confirm.")


def test_detects_grouped_tfn():
    hits = find_pii("My TFN is 123 456 789.")
    assert any(h.kind in {"tfn", "abn", "medicare"} for h in hits)


def test_detects_credit_card_via_luhn():
    # 4111 1111 1111 1111 is a well-known Luhn-valid test number.
    hits = find_pii("Card 4111 1111 1111 1111 on file.")
    assert any(h.kind == "credit_card" for h in hits)


def test_random_16_digits_without_luhn_not_flagged_as_card():
    hits = find_pii("Reference 1234 5678 9012 3456 here.")
    assert not any(h.kind == "credit_card" for h in hits)


def test_dollar_amounts_and_years_are_not_pii():
    text = ("The tax-free threshold is $18,200 for the 2025 income year and the "
            "Medicare levy is 2%. Assets costing $300 or less are immediately "
            "deductible.")
    assert not contains_pii(text), find_pii(text)


def test_clean_tax_prose_has_no_pii():
    text = ("You can claim 50% CGT discount on assets held at least 12 months. "
            "See ato.gov.au for the working-from-home fixed rate method.")
    assert find_pii(text) == []
