"""Independent semantic checks for Gate 1/2 TARGET contract goldens.

This is a test-only oracle. It does not define or export production models.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)
_DOCUMENT_KINDS = {
    "text", "markdown", "json", "csv", "html", "docx", "xlsx", "pdf",
    "google_doc", "google_sheet",
}
_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _assert_digest(value: Any) -> None:
    assert isinstance(value, str) and _DIGEST_RE.fullmatch(value)


def _assert_utc(value: Any) -> dt.datetime:
    assert isinstance(value, str) and _UTC_RE.fullmatch(value)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() == dt.timedelta(0)
    return parsed


def _assert_uuid(value: Any) -> None:
    assert isinstance(value, str) and uuid.UUID(value).int != 0


def _assert_int(value: Any, minimum: int, maximum: int) -> None:
    assert type(value) is int and minimum <= value <= maximum


def _assert_no_floats(value: Any) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _assert_no_floats(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_floats(child)
    else:
        assert not isinstance(value, float)


def _validate_common(instance: dict[str, Any], schema: str) -> None:
    assert instance["schema"] == schema
    assert instance["schema_version"] == "1"
    _assert_digest(instance["schema_digest"])
    assert instance["contract_digest"] == _digest(
        _canonical_bytes(
            {key: value for key, value in instance.items() if key != "contract_digest"}
        )
    )
    _assert_utc(instance["created_at"])
    assert all(
        isinstance(instance[key], str) and instance[key]
        for key in ("tenant_id", "project_ref", "policy_version")
    )
    assert instance["client_ref"] is None or (
        isinstance(instance["client_ref"], str) and instance["client_ref"]
    )
    _assert_digest(instance["registry_bundle_digest"])


def _validate_document_ref(instance: dict[str, Any]) -> None:
    _validate_common(instance, "nobus.document_ref.v1")
    _assert_uuid(instance["document_ref_id"])
    _assert_uuid(instance["source_id"])
    assert instance["backend"] in {"local", "google"}
    assert instance["document_kind"] in _DOCUMENT_KINDS
    assert instance["classification"] in _CLASSIFICATIONS
    assert isinstance(instance["source_scope_id"], str) and instance["source_scope_id"]
    assert isinstance(instance["display_name"], str) and 1 <= len(instance["display_name"]) <= 255
    assert isinstance(instance["media_type"], str) and "/" in instance["media_type"]
    _assert_int(instance["size_bytes"], 0, 52_428_800)
    if instance["content_digest"] is not None:
        _assert_digest(instance["content_digest"])
    revision = instance["revision"]
    assert revision["kind"] in {
        "local_sha256", "google_drive_version", "google_docs_revision",
        "google_sheets_observation",
    }
    if revision["kind"] == "local_sha256":
        assert set(revision) == {
            "kind", "sha256", "volume_id_digest", "file_id_digest", "observed_at"
        }
        for key in ("sha256", "volume_id_digest", "file_id_digest"):
            _assert_digest(revision[key])
    _assert_utc(revision["observed_at"])
    provenance = instance["provenance"]
    assert set(provenance) == {
        "adapter", "observed_at", "parent_scope_id", "metadata_digest",
        "selection_method",
    }
    assert provenance["adapter"] in {
        "windows_bridge", "google_drive", "google_docs", "google_sheets",
    }
    assert provenance["selection_method"] in {
        "exact_id", "unique_metadata_match", "owner_confirmed_candidate",
    }
    _assert_utc(provenance["observed_at"])
    _assert_digest(provenance["metadata_digest"])
    assert _assert_utc(instance["expires_at"]) > _assert_utc(instance["created_at"])


def _validate_intent(instance: dict[str, Any]) -> None:
    assert instance["schema"] == "nobus.intent.v1"
    _assert_uuid(instance["intent_id"])
    _assert_digest(instance["ingress_digest"])
    _assert_utc(instance["received_at"])
    assert instance["modality"] in {"text", "voice"}
    assert instance["status"] in {
        "ready", "needs_clarification", "unsupported", "rejected",
    }
    assert instance["domain"] in {
        "notes", "calendar", "tasks", "documents", "research", "general",
    }
    assert instance["action"] in {
        "none", "answer", "help", "status", "limit", "cancel", "search",
        "read", "list", "summarize", "compare", "analyze", "audit", "report",
        "remember", "extract_tasks", "create", "update", "complete", "delete",
        "deliver",
    }
    assert (instance["modality"] == "voice") == (instance["voice"] is not None)
    _assert_int(instance["confidence"], 0, 10_000)
    assert isinstance(instance["owner_text"], str) and 1 <= len(instance["owner_text"]) <= 2000
    assert len(instance["entities"]) <= 32
    for entity in instance["entities"]:
        assert set(entity) == {
            "kind", "raw", "normalized", "resolution", "resolved_ref", "confidence"
        }
        assert entity["kind"] in {
            "query", "title", "project", "client", "marketplace", "sku", "person",
            "task_list", "task", "calendar_event", "document", "folder", "file",
            "destination", "format", "date", "time", "duration", "quantity",
        }
        assert entity["resolution"] in {"unresolved", "exact", "ambiguous", "not_found"}
        assert (entity["resolved_ref"] is not None) == (entity["resolution"] == "exact")
        _assert_int(entity["confidence"], 0, 10_000)
    for selector in instance["source_scope"]:
        assert set(selector) == {"source", "access", "selector", "scope_ref", "explicit"}
        assert selector["source"] in {
            "none", "public_web", "nobus_memory", "business_notes", "google_calendar",
            "google_tasks", "google_drive", "local_library", "telegram_attachment",
        }
        assert selector["access"] in {"metadata", "content"}
        assert type(selector["explicit"]) is bool
    for effect in instance["proposed_effects"]:
        assert set(effect) == {
            "kind", "source", "target_hint", "target_ref", "summary", "risk",
            "authority", "requires_confirmation", "idempotency_scope",
        }
        assert effect["kind"] in {
            "read", "create", "update", "complete", "delete", "deliver_owner",
            "deliver_third_party", "publish", "change_access", "money", "push", "deploy",
        }
        assert effect["risk"] in {"low", "medium", "high", "critical"}
        assert effect["authority"] in {"direct_owner", "l4_required", "denied"}
        assert type(effect["requires_confirmation"]) is bool
    assert set(instance["context"]) == {
        "relation", "frame_id", "frame_revision", "parent_intent_id", "expires_at"
    }
    assert instance["context"]["relation"] in {"none", "follow_up", "clarification_answer"}
    if instance["status"] == "ready":
        assert not instance["ambiguities"] and instance["clarification"] is None
    assert instance["intent_revision"] == _digest(
        _canonical_bytes(
            {key: value for key, value in instance.items() if key != "intent_revision"}
        )
    )


def validate_target_contract_golden(name: str, instance: dict[str, Any]) -> None:
    """Assert semantic validity against the exact owning Gate 1/2 contracts."""

    _assert_no_floats(instance)
    if name == "IntentEnvelope":
        _validate_intent(instance)
        return
    if name == "DocumentRef":
        _validate_document_ref(instance)
        return

    schema = {
        "DocumentQuery": "nobus.document_query.v1",
        "DocumentReadPlan": "nobus.document_read_plan.v1",
        "AnalysisRequest": "nobus.analysis_request.v1",
        "ArtifactPlan": "nobus.artifact_plan.v1",
        "DocumentWritePlan": "nobus.document_write_plan.v1",
    }[name]
    _validate_common(instance, schema)
    if name == "DocumentQuery":
        _assert_uuid(instance["query_id"])
        assert 1 <= len(instance["source_scope_ids"]) <= 8
        assert len(instance["source_scope_ids"]) == len(set(instance["source_scope_ids"]))
        _assert_int(instance["max_candidates"], 1, 50)
        _assert_int(instance["max_pages"], 1, 5)
        _assert_int(instance["metadata_timeout_ms"], 100, 10_000)
        assert set(instance["document_kinds"]) <= _DOCUMENT_KINDS
        assert set(instance["classifications"]) <= _CLASSIFICATIONS
    elif name == "DocumentReadPlan":
        _assert_uuid(instance["read_plan_id"])
        assert 1 <= len(instance["documents"]) <= 32
        assert instance["purpose"] in {"summarize", "answer", "extract_facts", "analyze", "preview"}
        for selection in instance["documents"]:
            assert set(selection) == {"selection_kind", "document_ref"}
            assert selection["selection_kind"] == "whole_document"
            _validate_document_ref(selection["document_ref"])
        for key, maximum in {
            "max_source_bytes_per_document": 52_428_800,
            "max_source_bytes_total": 104_857_600,
            "max_extracted_chars_per_document": 24_000,
            "max_extracted_chars_total": 96_000,
            "max_parser_seconds_per_document": 30,
            "max_parser_seconds_total": 120,
        }.items():
            _assert_int(instance[key], 1, maximum)
        assert instance["max_source_bytes_total"] >= instance["max_source_bytes_per_document"]
        assert instance["max_extracted_chars_total"] >= instance["max_extracted_chars_per_document"]
    elif name == "AnalysisRequest":
        _assert_uuid(instance["analysis_id"])
        _assert_digest(instance["read_plan_digest"])
        assert 1 <= len(instance["sources"]) <= 32
        for source in instance["sources"]:
            _validate_document_ref(source)
        assert set(instance["metrics"]) <= {
            "revenue", "units", "average_price", "margin", "growth_rate", "share",
            "count", "custom_declared",
        }
        assert set(instance["grouping"]) <= {
            "client", "sku", "source", "day", "week", "month", "quarter", "year",
        }
        assert 1 <= len(instance["requested_outputs"]) <= 8
        assert set(instance["requested_outputs"]) <= {
            "telegram_text", "normalized_facts", "table", "chart", "artifact_plan",
        }
        assert instance["maximum_classification"] in _CLASSIFICATIONS
        limits = instance["limits"]
        assert set(limits) == {
            "max_documents", "max_source_bytes", "max_extracted_characters", "max_cells",
            "max_pages", "max_model_input_bytes", "max_provider_calls",
        }
        for key, bounds in {
            "max_documents": (1, 32), "max_source_bytes": (1, 536_870_912),
            "max_extracted_characters": (1, 2_000_000), "max_cells": (1, 200_000),
            "max_pages": (1, 1_000), "max_model_input_bytes": (0, 2_000_000),
            "max_provider_calls": (0, 256),
        }.items():
            _assert_int(limits[key], *bounds)
    elif name == "ArtifactPlan":
        _assert_uuid(instance["artifact_plan_id"])
        assert instance["format"] in {
            "telegram_text", "jpeg", "html", "xlsx", "docx", "pdf", "google_doc",
            "google_sheet",
        }
        assert instance["target_backend"] in {"telegram", "local", "google"}
        assert instance["collision_policy"] in {"new_version", "ask"}
        assert 1 <= len(instance["sections"]) <= 64
        assert instance["target_backend"] == "telegram" or instance["output_scope_id"]
        for section in instance["sections"]:
            assert section["section_kind"] in {"text", "table", "chart", "reference"}
            if section["section_kind"] == "text":
                assert set(section) == {"section_kind", "heading", "content_ref", "content_digest"}
                _assert_digest(section["content_digest"])
        _assert_digest(instance["content_digest"])
        for provenance_ref in instance["provenance_refs"]:
            _assert_uuid(provenance_ref)
    elif name == "DocumentWritePlan":
        _assert_uuid(instance["write_plan_id"])
        _assert_uuid(instance["artifact_ref"])
        assert instance["backend"] in {"local", "google"}
        assert instance["operation"] in {"create", "update"}
        assert instance["collision_policy"] in {"new_version", "ask"}
        assert type(instance["snapshot_required"]) is bool
        assert type(instance["strict_cas_required"]) is bool
        _assert_digest(instance["artifact_plan_digest"])
        _assert_digest(instance["artifact_digest"])
        target = instance["target"]
        assert target["target_kind"] in {"new_document", "existing_document"}
        if instance["operation"] == "create":
            assert target["target_kind"] == "new_document"
            assert set(target) == {"target_kind", "destination_name"}
            assert instance["expected_revision"] is None
        else:
            assert target["target_kind"] == "existing_document"
            assert instance["expected_revision"] is not None
            if instance["backend"] == "local":
                assert instance["snapshot_required"] is True
        approval = instance["approval_binding"]
        assert approval["approval_kind"] in {"exact_owner_request", "preview_confirmation"}
        if approval["approval_kind"] == "exact_owner_request":
            assert set(approval) == {
                "approval_kind", "ingress_digest", "intent_digest",
                "unchanged_payload_digest", "unchanged_destination_digest",
            }
            for key in set(approval) - {"approval_kind"}:
                _assert_digest(approval[key])
        assert _assert_utc(instance["expires_at"]) > _assert_utc(instance["created_at"])
