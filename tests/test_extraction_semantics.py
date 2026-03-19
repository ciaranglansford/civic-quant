from __future__ import annotations

from datetime import datetime

from app.contexts.extraction.canonicalization import canonicalize_extraction
from app.contexts.extraction.extraction_validation import parse_and_validate_extraction
from app.contexts.extraction.prompt_templates import render_extraction_prompt


def test_prompt_version_uses_v4_and_includes_claim_semantics():
    rendered = render_extraction_prompt(
        normalized_text='NEITHER IRAN NOR THE U.S. HAVE CONFIRMED THE REPORT.',
        message_time=datetime.utcnow(),
        source_channel_name="feed",
    )
    assert rendered.prompt_version == "extraction_agent_v4"
    assert "literal reported claim" in rendered.prompt_text.lower()
    assert "not convert reported claims into confirmed facts" in rendered.prompt_text.lower()
    assert "backend deterministic scoring and routing are authoritative" in rendered.prompt_text.lower()
    assert '"tags"' in rendered.prompt_text
    assert '"relations"' in rendered.prompt_text
    assert '"impact_inputs"' in rendered.prompt_text
    assert "organizations|companies" in rendered.prompt_text
    assert "emit 0..3 relations only" in rendered.prompt_text.lower()
    assert "use `organizations` for institutions" in rendered.prompt_text.lower()
    assert "directionality tags" in rendered.prompt_text.lower()
    assert "raw aggregate model signal" in rendered.prompt_text.lower()


def test_validation_accepts_uncertain_reported_claim_shape():
    raw_json = (
        '{"topic":"geopolitics","entities":{"countries":["United States"],"orgs":["AP"],'
        '"people":[],"tickers":[]},"affected_countries_first_order":["United States"],'
        '"market_stats":[],"sentiment":"unknown","confidence":0.61,"impact_score":66,'
        '"is_breaking":true,"breaking_window":"1h","event_time":null,"source_claimed":"AP",'
        '"summary_1_sentence":"AP reports officials made an unconfirmed claim.",'
        '"keywords":["unconfirmed","reported"],"event_core":"officials made a claim",'
        '"event_fingerprint":"f"}'
    )
    parsed = parse_and_validate_extraction(raw_json)
    assert parsed["confidence"] == 0.61
    assert parsed["impact_score"] == 66.0
    assert "unconfirmed claim" in parsed["summary_1_sentence"].lower()
    assert parsed["event_core"] == "officials made a claim"


def test_validation_allows_missing_or_null_llm_fingerprint_candidate():
    raw_json = (
        '{"topic":"macro_econ","entities":{"countries":["United States"],"orgs":[],"people":[],"tickers":[]},'
        '"affected_countries_first_order":[],"market_stats":[],"sentiment":"neutral","confidence":0.7,'
        '"impact_score":50,"is_breaking":false,"breaking_window":"none","event_time":null,'
        '"source_claimed":null,"summary_1_sentence":"Officials report inflation update.",'
        '"keywords":["inflation"],"event_core":null,"event_fingerprint":null}'
    )
    parsed = parse_and_validate_extraction(raw_json)
    assert parsed["event_fingerprint"] == ""


def test_structured_fields_accept_valid_values_and_drop_invalid_entries():
    raw_json = (
        '{"topic":"geopolitics","event_type":"conflict","directionality":"stress",'
        '"entities":{"countries":["Iran","United States"],"orgs":["NIOC"],"people":[],"tickers":[]},'
        '"affected_countries_first_order":["Iran","United States"],'
        '"market_stats":[],"tags":['
        '{"tag_type":"countries","tag_value":"Iran","tag_source":"observed","confidence":0.8},'
        '{"tag_type":"unknown_family","tag_value":"x","tag_source":"observed","confidence":0.8},'
        '{"tag_type":"directionality","tag_value":"stress","tag_source":"observed","confidence":0.8}'
        '],"relations":['
        '{"bad":"shape"},'
        '{"subject_type":"country","subject_value":"Iran","relation_type":"restricts_export_of","object_type":"commodity","object_value":"Oil","relation_source":"observed","inference_level":1,"confidence":0.9},'
        '{"subject_type":"country","subject_value":"Iran","relation_type":"made_up_relation","object_type":"commodity","object_value":"Oil","relation_source":"observed","inference_level":1,"confidence":0.9}'
        '],"impact_inputs":{"severity_cues":["military escalation"],"economic_relevance_cues":[],"propagation_potential_cues":[],"specificity_cues":[],"novelty_cues":[],"strategic_tag_hits":["supply_risk"]},'
        '"sentiment":"negative","confidence":0.8,"impact_score":74,"is_breaking":true,"breaking_window":"1h","event_time":"2026-03-19T10:00:00",'
        '"source_claimed":"Reuters","summary_1_sentence":"Iran says it may restrict oil exports.","keywords":["Iran","oil"],"event_core":"export restriction","event_fingerprint":"candidate"}'
    )
    parsed = parse_and_validate_extraction(raw_json)
    canonical, rules, _ = canonicalize_extraction(parsed)

    assert canonical.event_type == "conflict"
    assert canonical.directionality == "stress"
    assert any(tag.tag_type == "countries" and tag.tag_value == "Iran" for tag in canonical.tags)
    assert all(tag.tag_type != "unknown_family" for tag in canonical.tags)
    assert any(
        tag.tag_type == "directionality"
        and tag.tag_value == "stress"
        and tag.tag_source == "inferred"
        for tag in canonical.tags
    )
    assert len(canonical.relations) == 1
    relation = canonical.relations[0]
    assert relation.relation_type == "restricts_export_of"
    assert relation.relation_source == "observed"
    assert relation.inference_level == 0
    assert "structured_tags_invalid_dropped" in rules
    assert "structured_relations_invalid_dropped" in rules


def test_legacy_payload_shape_remains_compatible():
    legacy_raw_json = (
        '{"topic":"macro_econ","entities":{"countries":["United States"],"orgs":[],"people":[],"tickers":["DXY"]},'
        '"affected_countries_first_order":[],"market_stats":[],"sentiment":"neutral","confidence":0.8,'
        '"impact_score":51,"is_breaking":false,"breaking_window":"none","event_time":"2026-03-19T10:00:00",'
        '"source_claimed":"Reuters","summary_1_sentence":"US inflation update reported.","keywords":["inflation"],'
        '"event_core":null,"event_fingerprint":"legacy"}'
    )
    parsed = parse_and_validate_extraction(legacy_raw_json)
    canonical, _, _ = canonicalize_extraction(parsed)
    assert canonical.event_type == "market"
    assert canonical.tags
    assert canonical.relations == []


def test_organizations_split_and_conservative_directionality_defaults():
    raw_json = (
        '{"topic":"company_specific","event_type":"company","directionality":"stress",'
        '"entities":{"countries":["US"],"orgs":["GOOGLE","PENTAGON","IAEA","Multiple Countries"],"people":[],"tickers":["GOOG"]},'
        '"affected_countries_first_order":["US"],"market_stats":[],'
        '"tags":[{"tag_type":"companies","tag_value":"GOOGLE","tag_source":"observed","confidence":0.9}],'
        '"relations":[],"impact_inputs":{"severity_cues":[],"economic_relevance_cues":[],"propagation_potential_cues":[],"specificity_cues":[],"novelty_cues":[],"strategic_tag_hits":[]},'
        '"sentiment":"neutral","confidence":0.8,"impact_score":45,"is_breaking":false,"breaking_window":"none","event_time":"2026-03-19T10:00:00",'
        '"source_claimed":"Reuters","summary_1_sentence":"Jeff Bezos is raising $100B for a fund.","keywords":["fund"],"event_core":"fundraise","event_fingerprint":"candidate"}'
    )
    parsed = parse_and_validate_extraction(raw_json)
    canonical, rules, _ = canonicalize_extraction(parsed)

    assert canonical.directionality == "neutral"
    assert "directionality_demoted_without_support" in rules
    assert any(tag.tag_type == "organizations" and tag.tag_value == "IAEA" for tag in canonical.tags)
    assert any(tag.tag_type == "organizations" and tag.tag_value == "Pentagon" for tag in canonical.tags)
    assert any(tag.tag_type == "companies" and tag.tag_value == "Google" for tag in canonical.tags)
    assert all(tag.tag_value != "Multiple Countries" for tag in canonical.tags)
    assert canonical.entities.countries == ["United States"]


def test_relations_are_capped_and_country_aliases_are_normalized():
    raw_json = (
        '{"topic":"geopolitics","event_type":"conflict","directionality":"stress",'
        '"entities":{"countries":["US"],"orgs":["State Department"],"people":[],"tickers":[]},'
        '"affected_countries_first_order":["US"],"market_stats":[],"tags":[],'
        '"relations":['
        '{"subject_type":"country","subject_value":"US","relation_type":"conflict_with","object_type":"country","object_value":"Iran","relation_source":"observed","inference_level":0,"confidence":0.9},'
        '{"subject_type":"country","subject_value":"US","relation_type":"increases_spending_on","object_type":"conflict","object_value":"conflict","relation_source":"inferred","inference_level":1,"confidence":0.8},'
        '{"subject_type":"country","subject_value":"US","relation_type":"sanctions","object_type":"country","object_value":"Iran","relation_source":"observed","inference_level":0,"confidence":0.8},'
        '{"subject_type":"country","subject_value":"US","relation_type":"restricts_export_of","object_type":"commodity","object_value":"Graphite","relation_source":"observed","inference_level":0,"confidence":0.8},'
        '{"subject_type":"country","subject_value":"US","relation_type":"curtails","object_type":"production","object_value":"Ammonia production","relation_source":"observed","inference_level":0,"confidence":0.8}'
        '],"impact_inputs":{"severity_cues":[],"economic_relevance_cues":[],"propagation_potential_cues":[],"specificity_cues":[],"novelty_cues":[],"strategic_tag_hits":[]},'
        '"sentiment":"negative","confidence":0.8,"impact_score":70,"is_breaking":true,"breaking_window":"1h","event_time":"2026-03-19T10:00:00",'
        '"source_claimed":"Reuters","summary_1_sentence":"U.S. escalates pressure on Iran.","keywords":["Iran"],"event_core":"pressure","event_fingerprint":"candidate"}'
    )
    parsed = parse_and_validate_extraction(raw_json)
    canonical, rules, _ = canonicalize_extraction(parsed)

    assert len(canonical.relations) == 3
    assert any(rel.subject_value == "United States" for rel in canonical.relations)
    inferred = [rel for rel in canonical.relations if rel.relation_source == "inferred"]
    assert inferred
    assert all((rel.inference_level or 0) == 1 for rel in inferred)
    assert "structured_relations_invalid_dropped" in rules



