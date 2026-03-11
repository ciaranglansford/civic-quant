from app.services.canonicalization import canonicalize_extraction


def _base_payload() -> dict:
    return {
        "topic": "geopolitics",
        "entities": {
            "countries": ["United States"],
            "orgs": ["White House"],
            "people": ["Donald Trump"],
            "tickers": ["EUR"],
        },
        "affected_countries_first_order": ["United States"],
        "market_stats": [],
        "sentiment": "neutral",
        "confidence": 0.7,
        "impact_score": 61.0,
        "is_breaking": False,
        "breaking_window": "none",
        "event_time": "2026-03-01T20:28:48",
        "source_claimed": "AXIOS",
        "summary_1_sentence": "Officials report diplomatic talks.",
        "keywords": ["talks", "diplomacy", "meeting"],
        "event_core": "officials report diplomatic talks",
        "event_fingerprint": "llm-candidate",
    }


def test_backend_fingerprint_is_invariant_to_normalization_variants():
    payload_a = _base_payload()
    payload_a["entities"]["countries"] = ["U.S.", "United States", "uk"]
    payload_a["affected_countries_first_order"] = ["usa", "U.K."]
    payload_a["entities"]["orgs"] = ["  white house ", "WHITE HOUSE"]
    payload_a["entities"]["tickers"] = ["eur", " EUR ", "DXY!"]
    payload_a["keywords"] = [" talks ", "Diplomacy", "MEETING"]
    payload_a["event_fingerprint"] = "random-a"

    payload_b = _base_payload()
    payload_b["entities"]["countries"] = ["United Kingdom", "United States"]
    payload_b["affected_countries_first_order"] = ["United Kingdom", "United States"]
    payload_b["entities"]["orgs"] = ["WHITE HOUSE"]
    payload_b["entities"]["tickers"] = ["DXY", "EUR"]
    payload_b["keywords"] = ["meeting", "talks", "diplomacy"]
    payload_b["event_fingerprint"] = "random-b"

    canonical_a, rules_a, fp_a = canonicalize_extraction(payload_a)
    canonical_b, rules_b, fp_b = canonicalize_extraction(payload_b)

    assert canonical_a.event_fingerprint == canonical_b.event_fingerprint
    assert fp_a.fingerprint == fp_b.fingerprint
    assert fp_a.version == "v1"
    assert fp_b.version == "v1"
    assert fp_a.canonical_input.startswith("v1|event_type=")
    assert "event_fingerprint_backend_override" in rules_a
    assert "event_fingerprint_backend_override" in rules_b


def test_alias_canonicalization_is_applied_before_backend_fingerprinting():
    payload = _base_payload()
    payload["entities"]["countries"] = ["U.S.", "uk", "United States"]
    payload["affected_countries_first_order"] = ["usa", "U.K."]

    canonical, rules, _ = canonicalize_extraction(payload)

    assert canonical.entities.countries == ["United Kingdom", "United States"]
    assert canonical.affected_countries_first_order == ["United Kingdom", "United States"]
    assert "country_alias_normalization" in rules
    assert "affected_country_alias_normalization" in rules


def test_different_facts_with_overlapping_keywords_produce_different_fingerprints():
    payload_a = _base_payload()
    payload_a["topic"] = "commodities"
    payload_a["entities"]["countries"] = ["Russia"]
    payload_a["entities"]["orgs"] = ["Russian Foreign Ministry"]
    payload_a["keywords"] = ["hormuz", "oil", "gas"]
    payload_a["event_time"] = "2026-03-01T10:00:00"

    payload_b = _base_payload()
    payload_b["topic"] = "commodities"
    payload_b["entities"]["countries"] = ["Saudi Arabia"]
    payload_b["entities"]["orgs"] = ["Saudi Energy Ministry"]
    payload_b["keywords"] = ["hormuz", "oil", "gas"]
    payload_b["event_time"] = "2026-03-01T10:00:00"

    canonical_a, _, _ = canonicalize_extraction(payload_a)
    canonical_b, _, _ = canonicalize_extraction(payload_b)

    assert canonical_a.event_fingerprint != canonical_b.event_fingerprint


def test_malformed_or_arbitrary_llm_fingerprint_is_non_authoritative():
    payload_a = _base_payload()
    payload_b = _base_payload()

    payload_a["event_fingerprint"] = "### not deterministic ###"
    payload_b["event_fingerprint"] = "different-arbitrary-token"

    canonical_a, rules_a, fp_a = canonicalize_extraction(payload_a)
    canonical_b, rules_b, fp_b = canonicalize_extraction(payload_b)

    assert canonical_a.event_fingerprint == canonical_b.event_fingerprint
    assert fp_a.fingerprint == fp_b.fingerprint
    assert "event_fingerprint_backend_override" in rules_a
    assert "event_fingerprint_backend_override" in rules_b


def test_summary_safety_rewrites_high_risk_without_attribution():
    payload = {
        "topic": "geopolitics",
        "entities": {
            "countries": ["United States"],
            "orgs": ["Defense Ministry"],
            "people": [],
            "tickers": [],
        },
        "affected_countries_first_order": [],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.85,
        "impact_score": 85.0,
        "is_breaking": True,
        "breaking_window": "15m",
        "event_time": None,
        "source_claimed": "Defense Ministry",
        "summary_1_sentence": "Missiles launched toward border positions.",
        "keywords": ["missile"],
        "event_core": None,
        "event_fingerprint": "any",
    }

    canonical, rules, _ = canonicalize_extraction(payload)
    assert canonical.summary_1_sentence.startswith("Defense Ministry said")
    assert "summary_high_risk_attribution_rewrite" in rules


def test_summary_pronoun_disambiguation_uses_existing_actor():
    payload = {
        "topic": "war_security",
        "entities": {
            "countries": ["United States"],
            "orgs": ["NATO"],
            "people": [],
            "tickers": [],
        },
        "affected_countries_first_order": [],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.8,
        "impact_score": 70.0,
        "is_breaking": True,
        "breaking_window": "15m",
        "event_time": None,
        "source_claimed": "NATO",
        "summary_1_sentence": "It warned of a growing threat.",
        "keywords": [],
        "event_core": None,
        "event_fingerprint": "any",
    }

    canonical, rules, _ = canonicalize_extraction(payload)
    assert canonical.summary_1_sentence.startswith("NATO warned")
    assert "summary_pronoun_disambiguated" in rules

def test_insufficient_identity_does_not_emit_hard_fingerprint():
    payload = {
        "topic": "other",
        "entities": {
            "countries": [],
            "orgs": [],
            "people": [],
            "tickers": [],
        },
        "affected_countries_first_order": [],
        "market_stats": [],
        "sentiment": "unknown",
        "confidence": 0.4,
        "impact_score": 20.0,
        "is_breaking": False,
        "breaking_window": "none",
        "event_time": None,
        "source_claimed": None,
        "summary_1_sentence": "Wire reports unspecified development.",
        "keywords": [],
        "event_core": None,
        "event_fingerprint": "llm-generated-candidate",
    }

    canonical, rules, fp = canonicalize_extraction(payload)

    assert canonical.event_fingerprint == ""
    assert fp.fingerprint is None
    assert fp.hard_identity_sufficient is False
    assert "event_fingerprint_insufficient_identity" in rules
    assert "event_fingerprint_llm_candidate_ignored" in rules

def test_summary_rewrite_does_not_use_generic_feed_as_attribution_source():
    payload = {
        "topic": "war_security",
        "entities": {
            "countries": ["United States"],
            "orgs": ["UK PM Office"],
            "people": ["Keir Starmer"],
            "tickers": [],
        },
        "affected_countries_first_order": ["United States"],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.9,
        "impact_score": 80.0,
        "is_breaking": True,
        "breaking_window": "15m",
        "event_time": None,
        "source_claimed": "Market News Feed",
        "summary_1_sentence": "UK's PM Starmer has accepted a US request to use British bases for defensive strikes.",
        "keywords": ["Starmer", "strikes"],
        "event_core": None,
        "event_fingerprint": "any",
    }

    canonical, rules, _ = canonicalize_extraction(payload)

    assert canonical.summary_1_sentence.lower().startswith("reportedly,")
    assert "market news feed said" not in canonical.summary_1_sentence.lower()
    assert "summary_high_risk_attribution_rewrite" in rules


def test_summary_with_stated_or_warned_is_treated_as_already_attributed():
    payload = {
        "topic": "war_security",
        "entities": {
            "countries": ["United States"],
            "orgs": [],
            "people": ["Trump"],
            "tickers": [],
        },
        "affected_countries_first_order": ["United States"],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.9,
        "impact_score": 85.0,
        "is_breaking": True,
        "breaking_window": "15m",
        "event_time": None,
        "source_claimed": "Market News Feed",
        "summary_1_sentence": "Trump stated that 3 US service members have been killed and warned that there will likely be more.",
        "keywords": ["Trump", "casualties"],
        "event_core": None,
        "event_fingerprint": "any",
    }

    canonical, rules, _ = canonicalize_extraction(payload)

    assert canonical.summary_1_sentence.startswith("Trump stated")
    assert "summary_high_risk_attribution_rewrite" not in rules
