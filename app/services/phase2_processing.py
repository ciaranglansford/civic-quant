from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Extraction, MessageProcessingState, ProcessingLock, RawMessage
from ..schemas import ExtractionJson
from .canonicalization import (
    CANONICALIZER_VERSION,
    canonicalize_extraction,
    compute_canonical_payload_hash,
    compute_claim_hash,
    derive_action_class,
    event_time_bucket,
)
from .entity_indexing import index_entities_for_extraction
from .enrichment_selection import select_and_store_enrichment_candidate
from .event_manager import EventUpsertResult, find_candidate_event, upsert_event
from .extraction_llm_client import OpenAiExtractionClient, ProviderError
from .extraction_validation import ExtractionValidationError, parse_and_validate_extraction
from .impact_scoring import ImpactCalibrationResult, calibrate_impact, distribution_metrics
from .prompt_templates import render_extraction_prompt
from .routing_engine import route_extraction
from .triage_engine import (
    CandidateEventContext,
    TriageContext,
    compute_triage_action,
    impact_band,
    entity_signature,
)
from .ingest_pipeline import store_routing_decision

logger = logging.getLogger("civicquant.phase2")
OPENAI_EXTRACTOR_NAME = "extract-and-score-openai-v1"
EXTRACTION_SCHEMA_VERSION = 1


@dataclass
class RunSummary:
    processing_run_id: str
    selected: int = 0
    processed: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_replay_identity_key(
    *,
    raw_message_id: int,
    normalized_text_hash: str,
    extractor_name: str,
    prompt_version: str,
    schema_version: int,
    canonicalizer_version: str,
) -> str:
    source = (
        f"raw_message_id={raw_message_id}"
        f"|normalized_text_hash={normalized_text_hash}"
        f"|extractor_name={extractor_name}"
        f"|prompt_version={prompt_version}"
        f"|schema_version={schema_version}"
        f"|canonicalizer_version={canonicalizer_version}"
    )
    return _sha256_text(source)


def _calibration_from_metadata(extraction: Extraction, extraction_model: ExtractionJson) -> ImpactCalibrationResult:
    metadata = extraction.metadata_json if isinstance(extraction.metadata_json, dict) else {}
    impact_meta = metadata.get("impact_scoring") if isinstance(metadata, dict) else {}
    if not isinstance(impact_meta, dict):
        impact_meta = {}
    return ImpactCalibrationResult(
        raw_llm_score=float(impact_meta.get("raw_llm_score", extraction_model.impact_score)),
        calibrated_score=float(impact_meta.get("calibrated_score", extraction_model.impact_score)),
        score_band=str(impact_meta.get("score_band", impact_band(float(extraction_model.impact_score)))),
        shock_flags=list(impact_meta.get("shock_flags", [])),
        rules_fired=list(impact_meta.get("rules_fired", [])),
        score_breakdown=dict(impact_meta.get("score_breakdown", {})),
    )


def ensure_processing_state(db: Session, raw_message_id: int) -> MessageProcessingState:
    state = db.query(MessageProcessingState).filter_by(raw_message_id=raw_message_id).one_or_none()
    if state:
        return state
    state = MessageProcessingState(raw_message_id=raw_message_id, status="pending", attempt_count=0)
    db.add(state)
    db.flush()
    return state


def get_eligible_messages_for_extraction(db: Session, *, batch_size: int) -> list[RawMessage]:
    now = datetime.utcnow()
    return (
        db.query(RawMessage)
        .outerjoin(MessageProcessingState, MessageProcessingState.raw_message_id == RawMessage.id)
        .filter(
            or_(
                MessageProcessingState.id.is_(None),
                MessageProcessingState.status.in_(["pending", "failed"]),
                (MessageProcessingState.status == "in_progress")
                & (MessageProcessingState.lease_expires_at.is_not(None))
                & (MessageProcessingState.lease_expires_at <= now),
            )
        )
        .order_by(RawMessage.message_timestamp_utc.asc(), RawMessage.id.asc())
        .limit(batch_size)
        .all()
    )


def _acquire_lock(db: Session, *, run_id: str, lock_seconds: int) -> bool:
    now = datetime.utcnow()
    lock = db.query(ProcessingLock).filter_by(lock_name="phase2_extraction").one_or_none()
    if lock and lock.locked_until > now:
        return False
    until = now + timedelta(seconds=lock_seconds)
    if lock is None:
        db.add(ProcessingLock(lock_name="phase2_extraction", locked_until=until, owner_run_id=run_id))
    else:
        lock.locked_until = until
        lock.owner_run_id = run_id
    db.flush()
    return True


def _release_lock(db: Session, run_id: str) -> None:
    lock = db.query(ProcessingLock).filter_by(lock_name="phase2_extraction").one_or_none()
    if lock and lock.owner_run_id == run_id:
        lock.locked_until = datetime.utcnow()
        db.flush()


def _payload_for_extraction_row(row: Extraction) -> dict:
    payload = row.canonical_payload_json or row.payload_json or {}
    return payload if isinstance(payload, dict) else {}


def _entities_from_payload(payload: dict) -> set[str]:
    entities = payload.get("entities") if isinstance(payload, dict) else {}
    if not isinstance(entities, dict):
        entities = {}
    out: set[str] = set()
    for key, prefix in (("countries", "country"), ("orgs", "org"), ("people", "person")):
        values = entities.get(key, [])
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    out.add(f"{prefix}:{value.strip().lower()}")
    return out


def _keywords_from_payload(payload: dict) -> set[str]:
    values = payload.get("keywords", []) if isinstance(payload, dict) else []
    out: set[str] = set()
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str) and value.strip():
                out.add(value.strip().lower())
    return out


def _source_from_payload(payload: dict) -> str:
    value = payload.get("source_claimed") if isinstance(payload, dict) else None
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def _summary_tags_from_text(summary: str) -> set[str]:
    normalized = summary.lower()
    tags: set[str] = set()
    if any(token in normalized for token in ("condemn", "concern", "urge", "calls for", "unacceptable", "warn", "respond")):
        tags.add("reaction")
    if any(token in normalized for token in ("strike", "attack", "launched", "killed", "injured", "casualties", "missile", "troops", "explosion")):
        tags.add("operational")
    return tags


def _source_class_from_payload(payload: dict) -> str:
    source = str(payload.get("source_claimed") or "").lower()
    summary = str(payload.get("summary_1_sentence") or "").lower()
    combined = f"{source} {summary}"
    if any(token in combined for token in ("police", "ministry", "official", "military", "agency", "spokesperson", "according to")):
        return "authority"
    if any(token in combined for token in ("commentary", "analyst", "opinion", "urges", "condemns", "concerned")):
        return "commentary"
    return "unknown"


def _candidate_event_context(db: Session, existing_event) -> CandidateEventContext | None:
    if existing_event is None or existing_event.latest_extraction_id is None:
        return None
    latest = db.query(Extraction).filter_by(id=existing_event.latest_extraction_id).one_or_none()
    if latest is None:
        return None
    payload = _payload_for_extraction_row(latest)
    summary = str(payload.get("summary_1_sentence") or "")
    impact_val = latest.impact_score if latest.impact_score is not None else float(payload.get("impact_score") or 0.0)
    return CandidateEventContext(
        impact_band=impact_band(float(impact_val)),
        entities=_entities_from_payload(payload),
        summary_tags=_summary_tags_from_text(summary),
        source_class=_source_class_from_payload(payload),
    )


def _recent_related_rows(
    db: Session,
    *,
    extraction_model: ExtractionJson,
    raw_message_id: int,
    now_time: datetime,
) -> list[Extraction]:
    start = now_time - timedelta(minutes=15)
    end = now_time
    return (
        db.query(Extraction)
        .filter(
            Extraction.raw_message_id != raw_message_id,
            Extraction.topic == extraction_model.topic,
            Extraction.created_at >= start,
            Extraction.created_at <= end,
        )
        .order_by(Extraction.created_at.asc())
        .all()
    )


def _find_reusable_extraction(
    db: Session,
    *,
    raw_message_id: int,
    normalized_text_hash: str,
    extractor_name: str,
    prompt_version: str,
    schema_version: int,
    canonicalizer_version: str,
    reuse_window_hours: int,
) -> Extraction | None:
    query = (
        db.query(Extraction)
        .filter(
            Extraction.raw_message_id != raw_message_id,
            Extraction.normalized_text_hash == normalized_text_hash,
            Extraction.extractor_name == extractor_name,
            Extraction.prompt_version == prompt_version,
            Extraction.schema_version == schema_version,
            Extraction.canonicalizer_version == canonicalizer_version,
            Extraction.canonical_payload_json.is_not(None),
            Extraction.canonical_payload_hash.is_not(None),
        )
        .order_by(Extraction.created_at.desc(), Extraction.id.desc())
    )
    if reuse_window_hours > 0:
        query = query.filter(
            Extraction.created_at >= datetime.utcnow() - timedelta(hours=reuse_window_hours)
        )
    return query.first()


def _burst_low_delta_prior_count(
    extraction_model: ExtractionJson,
    recent_rows: list[Extraction],
) -> tuple[bool, int]:
    current_entities = entity_signature(extraction_model)
    current_keywords = {k.strip().lower() for k in extraction_model.keywords if k and k.strip()}
    current_source = (extraction_model.source_claimed or "").strip().lower()
    current_band_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}[impact_band(extraction_model.impact_score)]
    prior_entity_union: set[str] = set()
    qualifying = 0
    soft_related_match = False

    for row in recent_rows:
        payload = _payload_for_extraction_row(row)
        row_fp = str(payload.get("event_fingerprint") or row.event_fingerprint or "")
        row_entities = _entities_from_payload(payload)
        row_keywords = _keywords_from_payload(payload)
        row_source = _source_from_payload(payload)
        overlap = len(current_entities & row_entities)
        keyword_overlap = len(current_keywords & row_keywords)
        same_source_keyword_overlap = bool(current_source and row_source and current_source == row_source and keyword_overlap >= 2)
        related = (row_fp and row_fp == extraction_model.event_fingerprint) or overlap >= 2 or same_source_keyword_overlap
        if not related:
            continue
        soft_related_match = True
        prior_entity_union |= row_entities
        row_impact = row.impact_score if row.impact_score is not None else float(payload.get("impact_score") or 0.0)
        row_band_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}[impact_band(float(row_impact))]
        impact_not_increasing = current_band_rank <= row_band_rank
        no_new_entities = len(current_entities - prior_entity_union) == 0
        if impact_not_increasing and (no_new_entities or same_source_keyword_overlap):
            qualifying += 1

    return soft_related_match, qualifying


def process_phase2_batch(
    db: Session,
    settings: Settings | None = None,
    *,
    force_reprocess: bool = False,
) -> RunSummary:
    settings = settings or get_settings()
    effective_force_reprocess = bool(force_reprocess or settings.phase2_force_reprocess)
    run_id = str(uuid.uuid4())
    summary = RunSummary(processing_run_id=run_id)
    calibrated_scores: list[float] = []

    if not _acquire_lock(db, run_id=run_id, lock_seconds=settings.phase2_scheduler_lock_seconds):
        logger.info("phase2_lock_busy processing_run_id=%s", run_id)
        return summary

    try:
        if not settings.phase2_extraction_enabled:
            raise ValueError("PHASE2_EXTRACTION_ENABLED must be true for phase2 extraction job")
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when PHASE2_EXTRACTION_ENABLED=true")

        logger.info(
            "Using extractor: %s force_reprocess=%s canonicalizer_version=%s",
            OPENAI_EXTRACTOR_NAME,
            effective_force_reprocess,
            CANONICALIZER_VERSION,
        )

        client = OpenAiExtractionClient(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )

        eligible = get_eligible_messages_for_extraction(db, batch_size=settings.phase2_batch_size)
        summary.selected = len(eligible)
        for raw in eligible:
            state = ensure_processing_state(db, raw.id)
            if state.status == "completed":
                summary.skipped += 1
                continue

            state.status = "in_progress"
            state.processing_run_id = run_id
            state.last_attempted_at = datetime.utcnow()
            state.attempt_count += 1
            state.lease_expires_at = datetime.utcnow() + timedelta(seconds=settings.phase2_lease_seconds)
            state.last_error = None
            db.flush()

            try:
                prompt = render_extraction_prompt(
                    normalized_text=raw.normalized_text,
                    message_time=raw.message_timestamp_utc,
                    source_channel_name=raw.source_channel_name,
                )
                normalized_text_hash = _sha256_text(raw.normalized_text or "")
                replay_identity_key = _build_replay_identity_key(
                    raw_message_id=raw.id,
                    normalized_text_hash=normalized_text_hash,
                    extractor_name=OPENAI_EXTRACTOR_NAME,
                    prompt_version=prompt.prompt_version,
                    schema_version=EXTRACTION_SCHEMA_VERSION,
                    canonicalizer_version=CANONICALIZER_VERSION,
                )
                extraction = db.query(Extraction).filter_by(raw_message_id=raw.id).one_or_none()

                replay_reused = False
                content_reused = False
                content_reuse_source_extraction_id: int | None = None
                reusable_extraction: Extraction | None = None
                canonical_payload_unchanged = False
                raw_payload: dict | None = None
                llm_fingerprint_candidate: str | None = None
                backend_fingerprint_version = "unknown"
                backend_fingerprint_input = ""
                llm_response = None
                canonicalization_rules: list[str] = []
                canonical_payload_hash: str
                claim_hash: str
                action_class: str
                time_bucket: str

                if (
                    extraction is not None
                    and not effective_force_reprocess
                    and extraction.replay_identity_key == replay_identity_key
                    and isinstance(extraction.canonical_payload_json, dict)
                    and bool(extraction.canonical_payload_hash)
                ):
                    replay_reused = True
                    extraction_model = ExtractionJson.model_validate(extraction.canonical_payload_json)
                    calibration = _calibration_from_metadata(extraction, extraction_model)
                    canonical_payload = extraction_model.model_dump(mode="json")
                    canonical_payload_hash = extraction.canonical_payload_hash or compute_canonical_payload_hash(extraction_model)
                    claim_hash = extraction.claim_hash or compute_claim_hash(extraction_model)
                    action_class = derive_action_class(extraction_model)
                    time_bucket = event_time_bucket(extraction_model)
                    extraction.normalized_text_hash = normalized_text_hash
                    extraction.replay_identity_key = replay_identity_key
                    extraction.canonicalizer_version = CANONICALIZER_VERSION
                    extraction.processing_run_id = run_id
                    extraction.event_identity_fingerprint_v2 = extraction_model.event_fingerprint or extraction.event_identity_fingerprint_v2
                    extraction.canonical_payload_hash = canonical_payload_hash
                    extraction.claim_hash = claim_hash
                    logger.info(
                        "phase2_replay_reuse raw_message_id=%s replay_identity_key=%s canonical_payload_hash=%s",
                        raw.id,
                        replay_identity_key,
                        canonical_payload_hash,
                    )
                else:
                    if settings.phase2_content_reuse_enabled and not effective_force_reprocess:
                        reusable_extraction = _find_reusable_extraction(
                            db,
                            raw_message_id=raw.id,
                            normalized_text_hash=normalized_text_hash,
                            extractor_name=OPENAI_EXTRACTOR_NAME,
                            prompt_version=prompt.prompt_version,
                            schema_version=EXTRACTION_SCHEMA_VERSION,
                            canonicalizer_version=CANONICALIZER_VERSION,
                            reuse_window_hours=settings.phase2_content_reuse_window_hours,
                        )
                    if reusable_extraction is not None:
                        content_reused = True
                        content_reuse_source_extraction_id = reusable_extraction.id
                        extraction_model = ExtractionJson.model_validate(reusable_extraction.canonical_payload_json)
                        calibration = _calibration_from_metadata(reusable_extraction, extraction_model)
                        canonical_payload = extraction_model.model_dump(mode="json")
                        canonical_payload_hash = reusable_extraction.canonical_payload_hash or compute_canonical_payload_hash(extraction_model)
                        claim_hash = reusable_extraction.claim_hash or compute_claim_hash(extraction_model)
                        action_class = derive_action_class(extraction_model)
                        time_bucket = event_time_bucket(extraction_model)
                        if isinstance(reusable_extraction.payload_json, dict):
                            raw_payload = reusable_extraction.payload_json
                        source_meta = reusable_extraction.metadata_json if isinstance(reusable_extraction.metadata_json, dict) else {}
                        llm_fingerprint_candidate = source_meta.get("llm_event_fingerprint_candidate")
                        canonicalization_rules = source_meta.get("canonicalization_rules", [])
                        backend_fingerprint_version = source_meta.get("backend_event_fingerprint_version", "v2")
                        backend_fingerprint_input = source_meta.get("backend_event_fingerprint_input", "")
                        logger.info(
                            "phase2_content_reuse raw_message_id=%s source_extraction_id=%s normalized_text_hash=%s canonical_payload_hash=%s",
                            raw.id,
                            reusable_extraction.id,
                            normalized_text_hash,
                            canonical_payload_hash,
                        )
                    else:
                        llm_response = client.extract(prompt.prompt_text)
                        parsed = parse_and_validate_extraction(llm_response.raw_text)
                        llm_fp_raw = parsed.get("event_fingerprint") if isinstance(parsed, dict) else None
                        if isinstance(llm_fp_raw, str) and llm_fp_raw.strip():
                            llm_fingerprint_candidate = llm_fp_raw.strip()

                        raw_payload = parsed
                        extraction_model_raw, canonicalization_rules, fingerprint_info = canonicalize_extraction(parsed)
                        calibration = calibrate_impact(extraction_model_raw)
                        extraction_model = extraction_model_raw.model_copy(update={"impact_score": calibration.calibrated_score})
                        canonical_payload = extraction_model.model_dump(mode="json")
                        canonical_payload_hash = compute_canonical_payload_hash(extraction_model)
                        claim_hash = compute_claim_hash(extraction_model)
                        action_class = derive_action_class(extraction_model)
                        time_bucket = event_time_bucket(extraction_model)
                        backend_fingerprint_version = fingerprint_info.version
                        backend_fingerprint_input = fingerprint_info.canonical_input

                        if extraction is not None and extraction.canonical_payload_hash == canonical_payload_hash:
                            canonical_payload_unchanged = True
                            if isinstance(extraction.canonical_payload_json, dict):
                                extraction_model = ExtractionJson.model_validate(extraction.canonical_payload_json)
                                canonical_payload = extraction_model.model_dump(mode="json")
                            calibration = _calibration_from_metadata(extraction, extraction_model)
                            claim_hash = extraction.claim_hash or claim_hash
                            action_class = extraction.action_class if hasattr(extraction, "action_class") and extraction.action_class else action_class
                            time_bucket = extraction.metadata_json.get("event_time_bucket", time_bucket) if isinstance(extraction.metadata_json, dict) else time_bucket
                            logger.info(
                                "phase2_canonical_payload_noop raw_message_id=%s replay_identity_key=%s canonical_payload_hash=%s",
                                raw.id,
                                replay_identity_key,
                                canonical_payload_hash,
                            )

                if extraction is None:
                    extraction = Extraction(
                        raw_message_id=raw.id,
                        extractor_name=OPENAI_EXTRACTOR_NAME,
                        schema_version=EXTRACTION_SCHEMA_VERSION,
                        payload_json=raw_payload or {},
                    )
                    db.add(extraction)

                extraction.extractor_name = OPENAI_EXTRACTOR_NAME
                extraction.schema_version = EXTRACTION_SCHEMA_VERSION
                extraction.event_fingerprint = extraction_model.event_fingerprint
                extraction.event_identity_fingerprint_v2 = extraction_model.event_fingerprint or None
                extraction.normalized_text_hash = normalized_text_hash
                extraction.replay_identity_key = replay_identity_key
                extraction.canonicalizer_version = CANONICALIZER_VERSION
                extraction.canonical_payload_hash = canonical_payload_hash
                extraction.claim_hash = claim_hash
                extraction.prompt_version = prompt.prompt_version
                extraction.processing_run_id = run_id

                if not replay_reused and not canonical_payload_unchanged:
                    extraction.model_name = (
                        llm_response.model_name
                        if llm_response is not None
                        else (reusable_extraction.model_name if reusable_extraction is not None else extraction.model_name)
                    )
                    extraction.event_time = extraction_model.event_time
                    extraction.topic = extraction_model.topic
                    extraction.impact_score = float(extraction_model.impact_score)
                    extraction.confidence = float(extraction_model.confidence)
                    extraction.sentiment = extraction_model.sentiment
                    extraction.is_breaking = bool(extraction_model.is_breaking)
                    extraction.breaking_window = extraction_model.breaking_window
                    extraction.llm_raw_response = (
                        llm_response.raw_text
                        if llm_response is not None
                        else (reusable_extraction.llm_raw_response if reusable_extraction is not None else extraction.llm_raw_response)
                    )
                    extraction.validated_at = (
                        datetime.utcnow()
                        if llm_response is not None
                        else (reusable_extraction.validated_at if reusable_extraction is not None else extraction.validated_at)
                    )
                    extraction.payload_json = raw_payload or extraction.payload_json or {}
                    extraction.canonical_payload_json = canonical_payload

                metadata_existing = extraction.metadata_json if isinstance(extraction.metadata_json, dict) else {}
                metadata_source = (
                    reusable_extraction.metadata_json
                    if reusable_extraction is not None and isinstance(reusable_extraction.metadata_json, dict)
                    else {}
                )
                extraction.metadata_json = {
                    **metadata_existing,
                    "used_openai": (
                        llm_response.used_openai
                        if llm_response is not None
                        else (
                            metadata_source.get("used_openai")
                            if reusable_extraction is not None
                            else metadata_existing.get("used_openai")
                        )
                    ),
                    "openai_model": (
                        llm_response.model_name
                        if llm_response is not None
                        else (
                            metadata_source.get("openai_model")
                            if reusable_extraction is not None
                            else metadata_existing.get("openai_model")
                        )
                    ),
                    "openai_response_id": (
                        llm_response.openai_response_id
                        if llm_response is not None
                        else (
                            metadata_source.get("openai_response_id")
                            if reusable_extraction is not None
                            else metadata_existing.get("openai_response_id")
                        )
                    ),
                    "latency_ms": (
                        llm_response.latency_ms
                        if llm_response is not None
                        else (
                            metadata_source.get("latency_ms")
                            if reusable_extraction is not None
                            else metadata_existing.get("latency_ms")
                        )
                    ),
                    "retries": (
                        llm_response.retries
                        if llm_response is not None
                        else (
                            metadata_source.get("retries", 0)
                            if reusable_extraction is not None
                            else metadata_existing.get("retries", 0)
                        )
                    ),
                    "fallback_reason": None,
                    "canonicalization_rules": canonicalization_rules or metadata_existing.get("canonicalization_rules", []),
                    "llm_event_fingerprint_candidate": llm_fingerprint_candidate,
                    "backend_event_fingerprint": extraction_model.event_fingerprint or None,
                    "backend_event_fingerprint_authoritative": bool(extraction_model.event_fingerprint),
                    "backend_event_fingerprint_version": backend_fingerprint_version or metadata_existing.get("backend_event_fingerprint_version"),
                    "backend_event_fingerprint_input": backend_fingerprint_input or metadata_existing.get("backend_event_fingerprint_input"),
                    "canonicalizer_version": CANONICALIZER_VERSION,
                    "normalized_text_hash": normalized_text_hash,
                    "replay_identity_key": replay_identity_key,
                    "canonical_payload_hash": canonical_payload_hash,
                    "claim_hash": claim_hash,
                    "action_class": action_class,
                    "event_time_bucket": time_bucket,
                    "replay_reused": replay_reused,
                    "content_reused": content_reused,
                    "content_reuse_source_extraction_id": content_reuse_source_extraction_id,
                    "canonical_payload_unchanged": canonical_payload_unchanged,
                    "impact_scoring": {
                        "raw_llm_score": calibration.raw_llm_score,
                        "calibrated_score": calibration.calibrated_score,
                        "score_band": calibration.score_band,
                        "shock_flags": calibration.shock_flags,
                        "rules_fired": calibration.rules_fired,
                        "score_breakdown": calibration.score_breakdown,
                    },
                }
                db.flush()

                existing_event = find_candidate_event(db, extraction=extraction_model)
                candidate_context = _candidate_event_context(db, existing_event)
                now_time = datetime.utcnow()
                recent = _recent_related_rows(
                    db,
                    extraction_model=extraction_model,
                    raw_message_id=raw.id,
                    now_time=now_time,
                )
                soft_related, burst_prior_count = _burst_low_delta_prior_count(extraction_model, recent)
                triage = compute_triage_action(
                    extraction_model,
                    context=TriageContext(
                        existing_event_id=(existing_event.id if existing_event is not None else None),
                        candidate_event=candidate_context,
                        soft_related_match=soft_related,
                        burst_low_delta_prior_count=burst_prior_count,
                    ),
                )
                decision = route_extraction(
                    extraction_model,
                    triage_action=triage.triage_action,
                    triage_rules=triage.reason_codes,
                )
                if triage.triage_action == "archive":
                    decision.event_action = "ignore"
                elif triage.triage_action == "update" and existing_event is not None:
                    decision.event_action = "update"

                event_id: int | None = None
                upsert_result: EventUpsertResult | None = None
                if decision.event_action != "ignore":
                    upsert_result = upsert_event(
                        db=db,
                        extraction=extraction_model,
                        raw_message_id=raw.id,
                        latest_extraction_id=extraction.id,
                        canonical_payload_hash=canonical_payload_hash,
                        claim_hash=claim_hash,
                        action_class=action_class,
                        time_bucket=time_bucket,
                    )
                    event_id = upsert_result.event_id

                if upsert_result is not None and upsert_result.review_required:
                    triage_rules = list(decision.triage_rules or [])
                    triage_rules.append(f"identity:review_required:{upsert_result.review_reason}")
                    decision.triage_action = "monitor"
                    decision.publish_priority = "none"
                    flags = list(decision.flags or [])
                    flags.append("identity_conflict_review")
                    decision.flags = sorted(set(flags))
                    decision.triage_rules = triage_rules

                store_routing_decision(db, raw.id, decision)

                if event_id is not None:
                    try:
                        select_and_store_enrichment_candidate(
                            db,
                            event_id=event_id,
                            extraction=extraction_model,
                            calibration=calibration,
                            triage_action=decision.triage_action,
                            triage_rules=decision.triage_rules,
                            existing_event_id=(existing_event.id if existing_event is not None else None),
                            now=now_time,
                        )
                    except Exception as enrichment_exc:  # noqa: BLE001
                        logger.warning(
                            "enrichment_selection_failed raw_message_id=%s event_id=%s reason=%s",
                            raw.id,
                            event_id,
                            type(enrichment_exc).__name__,
                        )

                index_entities_for_extraction(
                    db,
                    raw_message_id=raw.id,
                    event_id=event_id,
                    extraction=extraction_model,
                )

                calibrated_scores.append(float(calibration.calibrated_score))
                state.status = "completed"
                state.completed_at = datetime.utcnow()
                state.lease_expires_at = None
                summary.completed += 1
            except ExtractionValidationError as e:
                state.status = "failed"
                state.last_error = f"validation_error:{e}"
                logger.warning(
                    "phase2_extraction_failed raw_message_id=%s reason=%s fallback_reason=%s",
                    raw.id,
                    "validation_error",
                    str(e),
                )
                summary.failed += 1
            except ProviderError as e:
                state.status = "failed"
                state.last_error = f"provider_error:{e}"
                logger.warning(
                    "phase2_extraction_failed raw_message_id=%s reason=%s fallback_reason=%s",
                    raw.id,
                    "provider_error",
                    str(e),
                )
                summary.failed += 1
            except Exception as e:  # noqa: BLE001
                state.status = "failed"
                state.last_error = f"persistence_error:{type(e).__name__}"
                logger.exception(
                    "phase2_extraction_failed raw_message_id=%s reason=%s fallback_reason=%s",
                    raw.id,
                    "persistence_error",
                    type(e).__name__,
                )
                summary.failed += 1
            finally:
                summary.processed += 1
                db.flush()

        if calibrated_scores:
            metrics = distribution_metrics(calibrated_scores)
            logger.info(
                "phase2_score_distribution processing_run_id=%s count=%s p95=%s p99=%s pct_gt_40=%s pct_gt_60=%s pct_gte_80=%s",
                run_id,
                int(metrics["count"]),
                metrics["p95"],
                metrics["p99"],
                metrics["pct_gt_40"],
                metrics["pct_gt_60"],
                metrics["pct_gte_80"],
            )

        logger.info(
            "phase2_run_done processing_run_id=%s selected=%s processed=%s completed=%s failed=%s skipped=%s",
            run_id,
            summary.selected,
            summary.processed,
            summary.completed,
            summary.failed,
            summary.skipped,
        )
        return summary
    finally:
        _release_lock(db, run_id)


