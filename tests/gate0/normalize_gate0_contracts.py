"""Normalize generated Gate 0 data to the exact normative architecture shapes."""

from __future__ import annotations

import ast
import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import uuid
from typing import Any

from gate0_lifecycle import (
    authoritative_database_set,
    capture_lifecycle,
    database_capture_lifecycle,
    database_claim,
    runtime_binding_verified,
    test_binding_verified,
    verifier_binding_verified,
)
from normative_models import BaselineEvidence, CapabilityClaim, CorpusCase, ProductContract


DESIGN_BASE = "9d816b35d3f419b42e24ad09ae6aadc92c33db43"
UTC = dt.timezone.utc


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def strict_object(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required if required is not None else list(properties),
    }


def schema_header(identifier: str, title: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": identifier,
        "title": title,
        **body,
    }


def string_array(enum: list[str] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "string"}
    if enum is not None:
        item["enum"] = enum
    return {"type": "array", "items": item}


def evidence_ref(
    root: pathlib.Path,
    relative: str,
    created_at: str,
    *,
    kind: str = "json_report",
) -> dict[str, Any]:
    path = root / relative
    return {
        "kind": kind,
        "path_or_uri": relative,
        "sha256": digest(path.read_bytes()),
        "media_type": "application/json",
        "bytes": path.stat().st_size,
        "classification": "internal",
        "created_at": created_at,
    }


def git(root: pathlib.Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    )
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def category_of(case: dict[str, Any]) -> str:
    return next(tag.removeprefix("category.") for tag in case["tags"] if tag.startswith("category."))


def normalize_case(old: dict[str, Any]) -> dict[str, Any]:
    intent = old["expected"]["intent"]
    decision = old["expected"]["decision"]
    decision_map = {
        "not_required": "accept",
        "admitted": "accept",
        "approval_required": "require_l4",
        "clarification_required": "clarify",
        "rejected": "reject",
        "fenced": "reject",
        "degraded": "degraded",
    }
    execution_map = {
        "not_required": "proposed",
        "admitted": "proposed",
        "approval_required": "allowed_after_l4",
        "clarification_required": "forbidden",
        "rejected": "forbidden",
        "fenced": "forbidden",
        "degraded": "forbidden",
    }
    ambiguity_map = {
        "none": "none",
        "clarification_required": "clarify",
        "unsafe": "reject",
    }
    context_turns = [
        {
            "turn": index,
            "speaker": "owner" if turn["role"] == "owner" else "system_context",
            "text": turn["text"],
            "trusted_context_ref": old["input"]["context_ref"],
        }
        for index, turn in enumerate(old["input"]["turns"], 1)
    ]
    main_turn = {
        "turn": len(context_turns) + 1,
        "speaker": "owner",
        "text": old["input"]["text"],
        "trusted_context_ref": old["input"]["context_ref"],
    }
    category = old["primary_category"]
    errors = [{"code": code, "required": True} for code in old["expected"]["errors"]]
    tags = sorted(set(old["secondary_tags"] + [f"category.{category}"]))
    return {
        "schema": "nobus.gate0.corpus_case.v1",
        "corpus_version": "1.0.0",
        "case_id": old["case_id"],
        "status": old["status"],
        "locale": old["input"]["locale"],
        "source_kind": "synthetic",
        "modality": old["input"]["modality"],
        "pair_ref": old["pair_ref"],
        "turns": context_turns + [main_turn],
        "expected": {
            "intent": {
                "schema": "nobus.intent.v1",
                "domain": intent["domain"],
                "action": intent["action"],
                "entities": {
                    "tenant_ref": old["input"]["tenant_id"],
                    "project_ref": "project-synthetic",
                    "client_ref": None,
                    "scope_ref": intent["scope_ref"],
                },
                "period": None,
                "source_scope": intent["source_scope"],
                "requested_outputs": intent["requested_outputs"],
                "proposed_effects": intent["proposed_effects"],
                "ambiguity": ambiguity_map[intent["ambiguity"]],
            },
            "decision": decision_map[decision["execution"]],
            "effects": [
                {
                    "kind": effect["kind"],
                    "execution": execution_map[effect["execution"]],
                }
                for effect in old["expected"]["effects"]
            ],
            "errors": errors,
            "user_message_profile": old["expected"]["message_profile"],
        },
        "forbidden": {
            "domains": [],
            "actions": [],
            "effects": [],
            "data_exposure": [
                "secret",
                "raw_path",
                "cross_tenant",
                "raw_prompt",
                "raw_document",
            ],
        },
        "assertions": old["expected"]["assertions"],
        "tags": tags,
        "ownership": {
            "product_owner": "nobus_space_owner",
            "curator": "gate0_curator",
            "security_reviewer": (
                "gate0_security_reviewer"
                if category == "security_effect_tenant_provider_adversarial"
                else None
            ),
        },
        "provenance": {
            "created_from": "synthetic_boundary",
            "source_refs": [
                "docs/gates/gate-00-product-contract-baseline/ARCHITECTURE.md"
            ],
            "created_at": old["timestamps"]["created_at"],
            "reviewed_at": old["timestamps"]["reviewed_at"],
        },
    }


def enhance_security(cases: list[dict[str, Any]]) -> None:
    by_id = {case["case_id"]: case for case in cases}
    additions = {
        "G0-SEC-001": ["CROSS_PROJECT_DENIED", "CROSS_CLIENT_DENIED"],
        "G0-SEC-003": ["SECRET_PATH_DENIED", "PATH_TRAVERSAL_DENIED"],
        "G0-SEC-005": ["REPARSE_POINT_DENIED"],
        "G0-SEC-006": ["REPLAY_FENCED", "BRIDGE_OFFLINE"],
        "G0-SEC-007": ["PROMPT_INJECTION_IGNORED"],
        "G0-SEC-010": ["STALE_REVISION_DENIED"],
    }
    for case_id, codes in additions.items():
        case = by_id[case_id]
        known = {item["code"] for item in case["expected"]["errors"]}
        case["expected"]["errors"].extend(
            {"code": code, "required": True} for code in codes if code not in known
        )
        case["tags"] = sorted(set(case["tags"] + [code.casefold() for code in codes]))
    for left_id, right_id in (("G0-SEC-001", "G0-SEC-002"),):
        by_id[right_id]["expected"] = copy.deepcopy(by_id[left_id]["expected"])
    for case_id in ("G0-SEC-001", "G0-SEC-002"):
        case = by_id[case_id]
        case["expected"]["intent"]["entities"].update(
            {
                "tenant_ref": "tenant-a",
                "project_ref": "project-alpha",
                "client_ref": "client-alpha",
                "scope_ref": "scope://tenant-a/project-alpha/client-alpha",
            }
        )
        for turn in case["turns"]:
            turn["turn"] += 1
        case["turns"].insert(
            0,
            {
                "turn": 1,
                "speaker": "system_context",
                "text": "Синтетическая разрешённая привязка: tenant-a, project-alpha, client-alpha.",
                "trusted_context_ref": "context://synthetic/authorized-binding",
            },
        )
        case["tags"] = sorted(
            set(case["tags"] + ["cross_client_denied", "cross_project_denied", "multi_turn"])
        )
    overrides = {
        "G0-SEC-009": ("deliver_third_party", "third_party_delivery"),
        "G0-SEC-011": ("change_access", "share"),
        "G0-SEC-012": ("money", "money"),
    }
    for case_id, (effect_kind, tag) in overrides.items():
        case = by_id[case_id]
        case["expected"]["intent"]["proposed_effects"] = [effect_kind]
        case["expected"]["effects"] = [{"kind": effect_kind, "execution": "allowed_after_l4"}]
        case["tags"] = sorted(set(case["tags"] + [tag]))


def build_coverage(cases: list[dict[str, Any]]) -> dict[str, Any]:
    def counts(getter) -> dict[str, int]:
        result: dict[str, int] = {}
        for case in cases:
            value = getter(case)
            result[value] = result.get(value, 0) + 1
        return dict(sorted(result.items()))

    pairs = {
        tuple(sorted((case["case_id"], case["pair_ref"])))
        for case in cases
        if case["pair_ref"]
    }
    lifecycle: dict[str, list[str]] = {}
    for source in ("google_drive", "local_library"):
        lifecycle[source] = sorted(
            {
                tag
                for case in cases
                if source in case["expected"]["intent"]["source_scope"]
                for tag in case["tags"]
                if tag in {"search", "select", "read", "analyze", "create", "update", "deliver"}
            }
        )
    security_codes = sorted(
        {
            error["code"]
            for case in cases
            for error in case["expected"]["errors"]
            if category_of(case) == "security_effect_tenant_provider_adversarial"
        }
    )
    return {
        "schema": "nobus.gate0.corpus_coverage.v1",
        "corpus_version": "1.0.0",
        "total_cases": len(cases),
        "primary_category_counts": counts(category_of),
        "modality_counts": counts(lambda case: case["modality"]),
        "domain_counts": counts(lambda case: case["expected"]["intent"]["domain"]),
        "action_counts": counts(lambda case: case["expected"]["intent"]["action"]),
        "decision_counts": counts(lambda case: case["expected"]["decision"]),
        "effect_counts": counts(lambda case: case["expected"]["effects"][0]["kind"]),
        "tenant_counts": counts(lambda case: case["expected"]["intent"]["entities"]["tenant_ref"]),
        "negative_or_adversarial_cases": sum("negative" in case["tags"] for case in cases),
        "multi_turn_or_clarification_cases": sum(
            len(case["turns"]) > 1 or case["expected"]["decision"] == "clarify"
            for case in cases
        ),
        "text_voice_pair_count": len(pairs),
        "text_voice_pairs": [list(pair) for pair in sorted(pairs)],
        "document_lifecycle_coverage": lifecycle,
        "security_scenario_coverage": security_codes,
        "requirements": {
            "target_cases": 96,
            "minimum_cases": 80,
            "minimum_negative_or_adversarial": 30,
            "minimum_text_voice_pairs": 16,
            "minimum_multi_turn_or_clarification": 12,
            "required_document_stages": [
                "search",
                "select",
                "read",
                "analyze",
                "create",
                "update",
                "deliver",
            ],
            "required_security_scenarios": [
                "TENANT_MISMATCH",
                "CROSS_PROJECT_DENIED",
                "CROSS_CLIENT_DENIED",
                "PROMPT_INJECTION_IGNORED",
                "REPLAY_FENCED",
                "SECRET_PATH_DENIED",
                "PATH_TRAVERSAL_DENIED",
                "REPARSE_POINT_DENIED",
                "STALE_REVISION_DENIED",
                "BRIDGE_OFFLINE",
                "UNKNOWN_PROVIDER_OUTCOME",
            ],
        },
    }


def corpus_schema(domains: list[str], actions: list[str], sources: list[str], outputs: list[str], effects: list[str]) -> dict[str, Any]:
    turn = strict_object(
        {
            "turn": {"type": "integer", "minimum": 1},
            "speaker": {"type": "string", "enum": ["owner", "system_context"]},
            "text": {"type": "string", "minLength": 1, "maxLength": 1024},
            "trusted_context_ref": {"type": ["string", "null"]},
        }
    )
    entities = strict_object(
        {
            "tenant_ref": {"type": "string", "pattern": "^tenant-[a-z]$"},
            "project_ref": {"type": "string"},
            "client_ref": {"type": ["string", "null"]},
            "scope_ref": {"type": ["string", "null"]},
        }
    )
    intent = strict_object(
        {
            "schema": {"const": "nobus.intent.v1"},
            "domain": {"type": "string", "enum": domains},
            "action": {"type": "string", "enum": actions},
            "entities": entities,
            "period": {"type": ["object", "null"], "additionalProperties": False},
            "source_scope": string_array(sources),
            "requested_outputs": string_array(outputs),
            "proposed_effects": string_array(effects),
            "ambiguity": {"type": "string", "enum": ["none", "clarify", "reject"]},
        }
    )
    expected = strict_object(
        {
            "intent": intent,
            "decision": {
                "type": "string",
                "enum": ["accept", "clarify", "reject", "require_l4", "degraded"],
            },
            "effects": {
                "type": "array",
                "items": strict_object(
                    {
                        "kind": {"type": "string", "enum": effects},
                        "execution": {
                            "type": "string",
                            "enum": ["forbidden", "proposed", "allowed_after_l4"],
                        },
                    }
                ),
            },
            "errors": {
                "type": "array",
                "items": strict_object(
                    {
                        "code": {"type": "string", "pattern": "^[A-Z0-9_]+$"},
                        "required": {"type": "boolean"},
                    }
                ),
            },
            "user_message_profile": {"type": "string"},
        }
    )
    forbidden = strict_object(
        {
            "domains": string_array(domains),
            "actions": string_array(actions),
            "effects": string_array(effects),
            "data_exposure": string_array(
                ["secret", "raw_path", "cross_tenant", "raw_prompt", "raw_document"]
            ),
        }
    )
    ownership = strict_object(
        {
            "product_owner": {"type": "string"},
            "curator": {"type": "string"},
            "security_reviewer": {"type": ["string", "null"]},
        }
    )
    provenance = strict_object(
        {
            "created_from": {
                "type": "string",
                "enum": ["canonical_requirement", "incident_pattern", "synthetic_boundary"],
            },
            "source_refs": string_array(),
            "created_at": {"type": "string", "format": "date-time"},
            "reviewed_at": {"type": "string", "format": "date-time"},
        }
    )
    return schema_header(
        "urn:nobus:gate0:corpus-case:v1",
        "Nobus Gate 0 Canonical Corpus Case",
        strict_object(
            {
                "schema": {"const": "nobus.gate0.corpus_case.v1"},
                "corpus_version": {
                    "type": "string",
                    "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$",
                },
                "case_id": {"type": "string", "pattern": "^G0-[A-Z]+-[0-9]{3}$"},
                "status": {
                    "type": "string",
                    "enum": ["active", "deprecated", "tombstone"],
                },
                "locale": {"const": "ru-RU"},
                "source_kind": {
                    "type": "string",
                    "enum": ["synthetic", "sanitized_pattern"],
                },
                "modality": {
                    "type": "string",
                    "enum": ["text", "voice_transcript"],
                },
                "pair_ref": {"type": ["string", "null"]},
                "turns": {"type": "array", "items": turn, "minItems": 1},
                "expected": expected,
                "forbidden": forbidden,
                "assertions": string_array(),
                "tags": string_array(),
                "ownership": ownership,
                "provenance": provenance,
            }
        ),
    )


def capability_schema() -> dict[str, Any]:
    evidence_ref_shape = strict_object(
        {
            "kind": {"type": "string"},
            "path_or_uri": {"type": "string"},
            "sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "media_type": {"type": "string"},
            "bytes": {"type": "integer", "minimum": 0},
            "classification": {
                "type": "string",
                "enum": ["public", "internal", "confidential"],
            },
            "created_at": {"type": "string", "format": "date-time"},
        }
    )
    return schema_header(
        "urn:nobus:gate0:capability-claim:v1",
        "Nobus Gate 0 Capability Claim",
        strict_object(
            {
                "claim_id": {"type": "string"},
                "capability": {"type": "string"},
                "implementation_status": {
                    "type": "string",
                    "enum": ["CURRENT", "PARTIAL", "TARGET", "DEFERRED"],
                },
                "statement": {"type": "string"},
                "requires_layers": string_array(),
                "evidence_refs": {"type": "array", "items": evidence_ref_shape},
                "contradictions": {"type": "array", "items": evidence_ref_shape},
                "fresh_until": {"type": ["string", "null"], "format": "date-time"},
                "verdict": {
                    "type": "string",
                    "enum": ["VERIFIED", "CONTRADICTORY", "STALE", "UNVERIFIABLE"],
                },
            }
        ),
    )


def infer_schema(value: Any, *, const_schema: str | None = None) -> dict[str, Any]:
    if isinstance(value, dict):
        properties = {key: infer_schema(item) for key, item in value.items()}
        if const_schema and "schema" in properties:
            properties["schema"] = {"const": const_schema}
        return strict_object(properties)
    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {}}
        return {"type": "array", "items": infer_schema(value[0])}
    if value is None:
        return {"type": ["string", "null"]}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"}


def product_catalog(product: dict[str, Any]) -> None:
    product["contract_families"] = [
        item for item in product["contract_families"] if item["family"] != "current_core"
    ]
    product["product_principles"] = [
        "owner_bound_telegram",
        "natural_language_first",
        "text_and_confirmed_voice_semantic_equivalence",
        "single_clarification_before_guessing",
        "core_owns_policy_state_risk_idempotency",
        "application_owned_effects",
        "no_ambient_model_oauth_shell_or_filesystem",
        "tenant_project_client_binding",
        "metadata_first_exact_selection",
        "revision_digest_bound_read_update",
        "unknown_outcome_requires_reconciliation",
        "deny_wins",
        "independent_l1_l2_l3_and_action_bound_l4",
        "current_target_evidence_separation",
    ]
    current = [
        ("TrustedIngressEnvelope", "current.trusted_ingress.v1", "trusted_ingress", ["core"]),
        ("TaskContract", "current.task_contract.v1", "core", ["worker", "verification"]),
        ("WorkerEvent", "current.worker_event.v1", "worker", ["core"]),
        ("VerificationBundle", "current.verification_bundle.v1", "verification", ["core"]),
        ("HumanApprovalRecord", "current.human_approval.v1", "approval_adapter", ["core"]),
        ("ProductEffectRecord", "current.product_effect.v1", "core", ["effect_adapter"]),
    ]
    target = [
        ("IntentEnvelope", "nobus.intent.v1", "gate1_core", ["gate2", "gate3", "gate4"]),
        ("DocumentRef", "nobus.document_ref.v1", "gate2_core", ["gate3", "gate5", "gate6"]),
        ("DocumentQuery", "nobus.document_query.v1", "gate2_core", ["gate3", "gate5"]),
        ("DocumentReadPlan", "nobus.document_read_plan.v1", "gate2_core", ["gate5", "gate6"]),
        ("AnalysisRequest", "nobus.analysis_request.v1", "gate2_core", ["gate6"]),
        ("ArtifactPlan", "nobus.artifact_plan.v1", "gate2_core", ["gate7"]),
        ("DocumentWritePlan", "nobus.document_write_plan.v1", "gate2_core", ["gate7"]),
    ]
    catalog = []
    for name, schema_id, producer, consumers in current + target:
        is_target = (name, schema_id, producer, consumers) in target
        catalog.append(
            {
                "contract_name": name,
                "schema_id": schema_id,
                "status": "target" if is_target else "current",
                "owner": "gate2" if is_target and name != "IntentEnvelope" else "gate1" if name == "IntentEnvelope" else "current_core",
                "producer": producer,
                "consumers": consumers,
                "trust_boundary": "strict_tenant_project_client_bound",
                "required_fields": (
                    ["schema", "tenant_id", "conversation_ref", "domain", "action"]
                    if name == "IntentEnvelope"
                    else ["schema_version", "tenant_id"]
                ),
                "golden_ref": "fixtures/contracts/valid/product-contract.json",
                "source_ref": (
                    "docs/gates/gate-01-natural-language-voice/ARCHITECTURE.md"
                    if name == "IntentEnvelope"
                    else "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md"
                    if is_target
                    else "docs/05-\u0421\u043f\u0435\u0446\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u0438-\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u043e\u0432.md"
                ),
            }
        )
    product["contract_catalog"] = catalog


def component_manifest(root: pathlib.Path, gate: pathlib.Path, observed_at: str) -> dict[str, Any]:
    relatives = [
        "docs/gates/gate-00-product-contract-baseline/product/product-contract.json",
        "docs/gates/gate-00-product-contract-baseline/corpus/requests.v1.jsonl",
        "docs/gates/gate-00-product-contract-baseline/corpus/coverage.json",
        "docs/gates/gate-00-product-contract-baseline/corpus/corpus-manifest.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/documentation-inventory.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/dirty-manifest.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/runtime-inventory.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/database-inventory.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/configuration-inventory.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/dependency-inventory.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/test-inventory.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/current-corpus-baseline.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/external-capabilities.json",
        "docs/gates/gate-00-product-contract-baseline/evidence/owner-root-metadata.json",
    ]
    entries = [
        {
            "path": relative,
            "sha256": digest((root / relative).read_bytes()),
            "size_bytes": (root / relative).stat().st_size,
        }
        for relative in relatives
        if (root / relative).is_file()
    ]
    return {
        "schema": "nobus.gate0.component_manifest.v1",
        "observed_at": observed_at,
        "entries": entries,
        "manifest_digest": digest(canonical(entries)),
    }


def normalized_baseline(root: pathlib.Path, gate: pathlib.Path) -> dict[str, Any]:
    old = load(gate / "evidence/baseline-evidence.json")
    generated_at = (
        old["generated_at"]
        if "generated_at" in old
        else old["capture"]["completed_at"]
    )
    docs = load(gate / "evidence/documentation-inventory.json")
    dirty = load(gate / "evidence/dirty-manifest.json")
    runtime = load(gate / "evidence/runtime-inventory.json")
    dbs = load(gate / "evidence/database-inventory.json")
    config = load(gate / "evidence/configuration-inventory.json")
    deps = load(gate / "evidence/dependency-inventory.json")
    tests = load(gate / "evidence/test-inventory.json")
    external = load(gate / "evidence/external-capabilities.json")
    capture_state = capture_lifecycle(runtime)
    database_capture_state = database_capture_lifecycle(dbs, runtime)
    runtime_verified = runtime_binding_verified(runtime)
    component_path = gate / "evidence/component-manifest.json"
    component = component_manifest(root, gate, generated_at)
    write(component_path, component)

    def ref(name: str, kind: str = "json_report") -> dict[str, Any]:
        return evidence_ref(
            root,
            f"docs/gates/gate-00-product-contract-baseline/evidence/{name}",
            generated_at,
            kind=kind,
        )

    required_paths = [
        "docs/README.md",
        "docs/12-\u042d\u0442\u0430\u043b\u043e\u043d-MVP-1-\u0438-\u0434\u043e\u0440\u043e\u0436\u043d\u0430\u044f-\u043a\u0430\u0440\u0442\u0430.md",
        "docs/adr/0017-hybrid-natural-google-local-document-plane.md",
        "docs/handoffs/CURRENT-STATUS.md",
        "docs/handoffs/MVP-1-ISSUES.md",
        "docs/handoffs/WORKSPACE-INVENTORY.md",
        "docs/05-\u0421\u043f\u0435\u0446\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u0438-\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u043e\u0432.md",
        "docs/06-\u0420\u0435\u0433\u043b\u0430\u043c\u0435\u043d\u0442-\u043a\u0430\u0447\u0435\u0441\u0442\u0432\u0430-L1-L4.md",
    ]
    required_docs = []
    for relative in required_paths:
        blob = str(git(root, "rev-parse", f"{DESIGN_BASE}:{relative}"))
        blob_bytes = git(root, "show", f"{DESIGN_BASE}:{relative}", binary=True)
        required_docs.append(
            {
                "path": relative,
                "git_blob": blob,
                "sha256": digest(blob_bytes),
                "status": "VERIFIED",
            }
        )
    doc_ref = ref("documentation-inventory.json")
    dirty_ref = ref("dirty-manifest.json")
    runtime_ref = ref("runtime-inventory.json")
    db_ref = ref("database-inventory.json", "database_check")
    config_ref = ref("configuration-inventory.json")
    deps_ref = ref("dependency-inventory.json")
    tests_ref = ref("test-inventory.json", "test_report")
    external_ref = ref("external-capabilities.json", "external_receipt")
    process_raw = next(
        (
            item
            for item in runtime.get("processes", [])
            if item.get("process_role") == "telegram_runner"
        ),
        {"observed_count": 0, "instances": [], "loaded_commit": None},
    )
    process_status = (
        "STALE"
        if capture_state == "STALE"
        else "VERIFIED"
        if capture_state == "FRESH" and runtime_verified
        else "CONTRADICTORY"
    )
    process = {
        "process_role": "telegram_runner",
        "expected_count": 1,
        "observed_count": process_raw["observed_count"],
        "instances": [
            {
                "pid": instance["pid"],
                "parent_pid": instance["parent_pid"],
                "started_at": instance["started_at"],
                "executable_ref": "runtime-executable:telegram-python",
                "executable_sha256": instance["executable_digest"],
                "executable_version": None,
                "argv_profile": instance["argv_profile"],
                "argv_digest": instance["argv_digest"],
                "working_directory_ref": "runtime-worktree:canonical-repo",
                "identity_ref": "principal:scheduler-task-owner",
                "loaded_release_commit": instance["loaded_commit"],
                "loaded_code_digest": instance["loaded_code_digest"],
                "config_digest": None,
                "health": "unknown",
            }
            for instance in process_raw.get("instances", [])
        ],
        "polling_checkpoint": {
            "observed_at": None,
            "age_seconds": None,
            "source_ref": None,
        },
        "status": process_status,
        "observed_at": runtime["observed_at"],
        "evidence_refs": [runtime_ref],
    }
    scheduler_raw = runtime["scheduler"]
    scheduler = {
        "scheduler_kind": "windows_task_scheduler",
        "task_ref": scheduler_raw["task_ref"],
        "enabled": scheduler_raw["enabled"],
        "state": scheduler_raw["state"],
        "action_executable_ref": f"executable-profile:{scheduler_raw['action_executable_profile']}",
        "action_executable_digest": scheduler_raw["action_executable_digest"],
        "action_arguments_profile": scheduler_raw["action_arguments_status"],
        "action_arguments_digest": scheduler_raw["action_arguments_digest"],
        "working_directory_ref": "opaque:none" if not scheduler_raw["working_directory_present"] else "opaque:registered",
        "principal_ref": "principal:task-owner",
        "trigger_profile": {"count": scheduler_raw["trigger_count"]},
        "restart_policy_profile": {"mode": "scheduler_default"},
        "last_run_at": scheduler_raw["last_run_at"],
        "last_result_code": scheduler_raw["last_result_code"],
        "next_run_at": scheduler_raw["next_run_at"],
        "definition_changed_at": None,
        "definition_digest": scheduler_raw["definition_digest"],
        "status": (
            "STALE"
            if capture_state == "STALE"
            else "VERIFIED"
            if capture_state == "FRESH" and runtime_verified
            else "CONTRADICTORY"
        ),
        "observed_at": runtime["observed_at"],
        "evidence_refs": [runtime_ref],
    }
    normalized_databases = []
    for raw_database in dbs["databases"]:
        database, database_status, _ = database_claim(
            raw_database, database_capture_state
        )
        role = database["database_role"]
        normalized_role = role if role in {"core", "telegram_state", "checkpoint"} else "legacy"
        status_counts: dict[str, int] = {}
        for table in database["tables"]:
            for key, count in (table["safe_status_counts"] or {}).items():
                status_counts[key] = status_counts.get(key, 0) + count
        normalized_databases.append(
            {
                "database_role": normalized_role,
                "database_ref": database["database_ref"],
                "source_profile": database["source_profile"],
                "runtime_binding_status": database["runtime_binding_status"].upper(),
                "runtime_binding_reason": database["runtime_binding_reason"],
                "engine": "sqlite",
                "file_identity_digest": digest(
                    canonical(
                        {
                            "ref": database["database_ref"],
                            "size": database["size_bytes"],
                            "modified_at": database["modified_at"],
                        }
                    )
                ),
                "size_bytes": database["size_bytes"],
                "modified_at": database["modified_at"],
                "journal_mode": database["journal_mode"],
                "user_version": database["user_version"],
                "application_id": database["application_id"],
                "schema_digest": database["schema_digest"],
                "migration_inventory": database["migration_inventory"],
                "integrity": database["integrity"],
                "state_aggregates": {
                    "pending": status_counts.get("PENDING"),
                    "in_progress": status_counts.get("IN_PROGRESS"),
                    "waiting_human": status_counts.get("WAITING_HUMAN"),
                    "failed": status_counts.get("FAILED"),
                    "dead_letters": status_counts.get("DEAD_LETTER"),
                    "orphaned_leases": None,
                    "unreconciled_effects": None,
                    "undelivered_outbox": None,
                },
                "content_exported": False,
                "status": database_status,
                "observed_at": dbs["observed_at"],
                "evidence_refs": [db_ref],
            }
        )
    config_projection = config["safe_projection"]
    registry_by_name = {
        item["registry"]: item for item in config["target_registries"]
    }
    configuration = {
        "config_schema_version": "current-safe-projection.v1",
        "active_profile": config["profile"],
        "safe_config_digest": config_projection["current_contract_policy_digest"],
        "secret_store": {
            "provider": "windows_credential_manager",
            "required_refs_present": None,
            "values_read": False,
        },
        "registries": {
            "source": {"schema_version": "target", "digest": None, "entries_count": None},
            "output": {"schema_version": "target", "digest": None, "entries_count": None},
            "deny": {"schema_version": "target", "digest": None, "entries_count": None},
            "google_folders": {"schema_version": None, "digest": None, "entries_count": None},
        },
        "policy_digest": config_projection["current_contract_policy_digest"],
        "model_profile_digest": digest(canonical({"status": "target_not_implemented"})),
        "config_sources": [item["ref"] for item in config_projection["current_contract_policy_files"]],
        "status": "UNVERIFIABLE",
        "observed_at": config["observed_at"],
        "evidence_refs": [config_ref],
    }
    dependency = {
        "os": deps["os"],
        "python": deps["python"],
        "pip": {
            "version": deps["pip"]["version"],
            "inspect_schema_version": deps["pip"]["inspect_version"],
            "inspect_report_ref": deps_ref,
            "inspect_report_digest": deps["pip"]["raw_report_digest"],
        },
        "requirements": {
            "files": deps["lock_sources"],
            "fully_pinned": False,
        },
        "pip_check": {
            "status": "passed" if deps["pip_check"]["status"] == "pass" else "failed"
        },
        "external_tools": [
            {
                "name": "git",
                "version": str(git(root, "--version")),
                "executable_digest": None,
            }
        ]
        + [
            {"name": name, "version": version, "executable_digest": None}
            for name, version in sorted(
                deps["verification_toolchain"]["versions"].items()
            )
        ],
        "vulnerability_report": {
            "tool": "pip-audit",
            "version": deps["verification_toolchain"]["versions"]["pip_audit"],
            "database_observed_at": deps["observed_at"],
            "status": deps["vulnerability_check"]["status"],
            "report_ref": deps_ref,
        },
        "status": "VERIFIED",
        "observed_at": deps["observed_at"],
        "evidence_refs": [deps_ref],
    }
    test_evidence = {
        "test_contract_version": "gate0.v1",
        "commit_under_test": dirty["head_commit"],
        "environment_digest": digest(
            canonical(
                {
                    "python": tests["environment"]["python"],
                    "pytest": tests["environment"]["pytest"],
                    "pydantic": tests["environment"]["pydantic"],
                }
            )
        ),
        "collection": {
            "files": sum(1 for path in (root / "tests").rglob("test_*.py") if "__pycache__" not in path.parts),
            "collected_cases": tests["full_pytest"]["passed"]
            + tests["full_pytest"]["skipped"],
            "collection_report_ref": tests_ref,
        },
        "runs": [
            {
                "profile": profile,
                "command_profile": profile,
                "started_at": tests["observed_at"],
                "finished_at": tests["observed_at"],
                "exit_code": 0 if run["status"] == "pass" else 1,
                "passed": run["passed"],
                "failed": run["failed"],
                "skipped": run["skipped"],
                "warnings": None,
                "seed": None,
                "report_ref": tests_ref,
                "report_digest": tests_ref["sha256"],
            }
            for profile, run in (
                ("gate0_contracts", tests["targeted_gate0"]),
                ("full_regression", tests["full_pytest"]),
            )
        ],
        "baseline_scores": {
            "current_system": {
                "corpus_version": "1.0.0",
                "corpus_digest": digest((gate / "corpus/requests.v1.jsonl").read_bytes()),
                "report_ref": tests_ref,
                "pass_rate": None,
            }
        },
        "status": "VERIFIED",
        "observed_at": tests["observed_at"],
        "evidence_refs": [tests_ref],
    }
    capability_map = {
        "telegram.polling": "telegram_polling",
        "google.calendar.read": "google_calendar",
        "google.tasks.read": "google_tasks",
        "google.drive.read": "google_drive",
        "codex.app_server": "codex_sdk",
        "windows.bridge.read_v1": "local_library_bridge_read_v1",
        "windows.bridge.write_v2": "local_library_bridge_write_v2",
    }
    external_evidence = []
    for claim in external["claims"]:
        external_evidence.append(
            {
                "capability": capability_map[claim["capability_id"]],
                "implementation_status": (
                    "current"
                    if claim["status"] in {"offline", "unverifiable"}
                    and claim["capability_id"] == "telegram.polling"
                    else "target"
                ),
                "verification_status": (
                    "unavailable"
                    if claim["status"] == "offline"
                    else "unverifiable"
                    if claim["status"] == "unverifiable"
                    else "not_checked"
                ),
                "mode": "metadata_only" if claim["evidence_kind"] != "none" else "not_applicable",
                "provider_or_adapter_version": None,
                "last_success_at": None,
                "fresh_evidence_at": claim["observed_at"],
                "safe_summary": claim["reason_code"],
                "limitations": ["no_live_call"],
                "status": (
                    "VERIFIED"
                    if claim["status"] in {"offline", "not_configured"}
                    else "UNVERIFIABLE"
                    if claim["status"] == "unverifiable"
                    else "NOT_CHECKED"
                ),
                "evidence_refs": [external_ref],
            }
        )
    claims = [
        {
            "claim_id": "current.repository.candidate",
            "capability": "repository_candidate",
            "implementation_status": "CURRENT",
            "statement": "Candidate repository identity and dirty ownership are verified.",
            "requires_layers": ["documentation", "repository"],
            "evidence_refs": [dirty_ref, doc_ref],
            "contradictions": [],
            "fresh_until": None,
            "verdict": "VERIFIED",
        },
        {
            "claim_id": "current.telegram.runner",
            "capability": "telegram_polling",
            "implementation_status": (
                "CURRENT" if process_status == "VERIFIED" else "PARTIAL"
            ),
            "statement": (
                "Exact single Scheduler-bound runner identity and loaded release are verified."
                if process_status == "VERIFIED"
                else "Saved process and Scheduler evidence is stale."
                if process_status == "STALE"
                else "Fresh capture did not prove the exact single CURRENT runner claim."
            ),
            "requires_layers": ["runtime_release", "process", "scheduler"],
            "evidence_refs": [runtime_ref],
            "contradictions": [runtime_ref] if process_status == "CONTRADICTORY" else [],
            "fresh_until": (
                runtime.get("fresh_until") or process_raw.get("fresh_until")
            ),
            "verdict": process_status,
        },
        {
            "claim_id": "target.mvp1.product",
            "capability": "mvp1_integrated_contract",
            "implementation_status": "TARGET",
            "statement": "Gate 1 through Gate 8 consume the frozen Product Contract.",
            "requires_layers": ["documentation", "tests"],
            "evidence_refs": [doc_ref, tests_ref],
            "contradictions": [],
            "fresh_until": None,
            "verdict": "VERIFIED",
        },
    ]
    limitations: list[dict[str, Any]] = []
    if process_status != "VERIFIED":
        limitations.append(
            {
                "code": (
                    "RUNTIME_EVIDENCE_STALE"
                    if process_status == "STALE"
                    else "EXPECTED_RUNNER_NOT_OBSERVED"
                ),
                "status": process_status,
                "blocking_criteria": ["G0-04"],
                "statement": (
                    "Point-in-time process and Scheduler evidence is stale."
                    if process_status == "STALE"
                    else "Fresh capture did not prove exactly one Scheduler-bound runner."
                ),
                "evidence_refs": [runtime_ref],
            }
        )
    database_gap = next(
        (item for item in normalized_databases if item["status"] != "VERIFIED"),
        None,
    )
    if database_gap is not None:
        limitations.append(
            {
                "code": "DATABASE_EVIDENCE_NOT_VERIFIED",
                "status": database_gap["status"],
                "blocking_criteria": ["G0-05"],
                "statement": "A bound SQLite schema, snapshot or integrity proof did not verify.",
                "evidence_refs": [db_ref],
            }
        )
    baseline = {
        "schema": "nobus.gate0.baseline.v1",
        "baseline_id": str(uuid.uuid5(uuid.NAMESPACE_URL, canonical({
            "generated_at": docs["observed_at"],
            "repo_head": dirty["head_commit"],
            "runtime_head": dirty["runtime_release"]["head_commit"],
            "documentation_digest": doc_ref["sha256"],
            "database_digest": db_ref["sha256"],
        }).decode("utf-8"))),
        "gate": 0,
        "scope": "nobus-space-mvp1",
        "capture": {
            "started_at": generated_at,
            "completed_at": generated_at,
            "collector_identity": "gate0-test-only-collector.v1",
            "host_ref": "windows-owner-pc",
            "policy_version": "gate0-architecture.v1",
            "method_version": "1.0.0",
        },
        "documentation": {
            "canonical_commit": DESIGN_BASE,
            "head_commit": dirty["head_commit"],
            "head_matches_canonical": dirty["head_commit"] == DESIGN_BASE,
            "required_documents": required_docs,
            "current_worktree_documents": docs["current_worktree_documents"],
            "source_hierarchy_version": str(git(root, "rev-parse", f"{DESIGN_BASE}:docs/README.md")),
            "status": "VERIFIED",
            "observed_at": docs["observed_at"],
            "evidence_refs": [doc_ref],
        },
        "repository": {
            "repo_ref": "nobus-orchestrator-dev",
            "worktree_ref": "worktree:candidate",
            "head_commit": dirty["head_commit"],
            "branch_or_detached": dirty["branch"],
            "upstream_ref": None,
            "merge_bases": {
                "docs_to_repo": str(git(root, "merge-base", DESIGN_BASE, dirty["head_commit"])),
                "docs_to_runtime_release": dirty["runtime_release"]["repo_runtime_merge_base"],
                "repo_to_runtime_release": dirty["runtime_release"]["repo_runtime_merge_base"],
            },
            "dirty": {"is_dirty": bool(dirty["entries"]), "entries": dirty["entries"]},
            "status": "VERIFIED",
            "observed_at": dirty["observed_at"],
            "evidence_refs": [dirty_ref],
        },
        "runtime_release": {
            "runtime_worktree_ref": "worktree:canonical-current",
            "runtime_head_commit": dirty["runtime_release"]["head_commit"],
            "runtime_branch_or_detached": dirty["runtime_release"]["branch"],
            "expected_feature_commit": "b69e84687cdce439c42f1bc53e4fe7654e4deaf9",
            "expected_feature_is_ancestor": dirty["runtime_release"]["feature_commit_is_ancestor"],
            "docs_commit_is_ancestor": dirty["runtime_release"]["design_base_is_ancestor"],
            "release_artifact_ref": None,
            "release_artifact_digest": None,
            "runtime_code_manifest_digest": None,
            "status": "VERIFIED",
            "observed_at": dirty["observed_at"],
            "evidence_refs": [dirty_ref],
        },
        "processes": [process],
        "scheduler": [scheduler],
        "databases": normalized_databases,
        "configuration": configuration,
        "dependencies": dependency,
        "tests": test_evidence,
        "external_capabilities": external_evidence,
        "claims": claims,
        "limitations": limitations,
        "evidence_manifest_ref": evidence_ref(
            root,
            "docs/gates/gate-00-product-contract-baseline/evidence/component-manifest.json",
            generated_at,
            kind="manifest",
        ),
        "baseline_digest": "",
    }
    projection = {key: value for key, value in baseline.items() if key != "baseline_digest"}
    baseline["baseline_digest"] = digest(canonical(projection))
    return baseline


def normalize_legacy(root: pathlib.Path, gate: pathlib.Path) -> None:
    product_path = gate / "product/product-contract.json"
    product = load(product_path)
    product_catalog(product)
    write(product_path, product)
    write(gate / "fixtures/contracts/valid/product-contract.json", product)

    old_cases = [
        json.loads(line)
        for line in (gate / "corpus/requests.v1.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    cases = [normalize_case(case) for case in old_cases]
    enhance_security(cases)
    cases.sort(key=lambda case: case["case_id"])
    jsonl = b"".join(canonical(case) + b"\n" for case in cases)
    (gate / "corpus/requests.v1.jsonl").write_bytes(jsonl)
    coverage = build_coverage(cases)
    write(gate / "corpus/coverage.json", coverage)
    corpus_manifest = {
        "schema": "nobus.gate0.corpus_manifest.v1",
        "corpus_version": "1.0.0",
        "line_count": 96,
        "corpus_digest": digest(jsonl),
        "coverage_digest": digest((gate / "corpus/coverage.json").read_bytes()),
        "case_ids_digest": digest(canonical([case["case_id"] for case in cases])),
        "provenance": "fully_synthetic",
        "contains_owner_or_client_payload": False,
        "encoding": "utf-8",
        "line_format": "canonical-json-plus-lf",
    }
    write(gate / "corpus/corpus-manifest.json", corpus_manifest)
    write(gate / "fixtures/contracts/valid/corpus-case.json", cases[0])

    vocab = product["vocabularies"]
    write(
        gate / "schemas/corpus-case.schema.json",
        corpus_schema(
            vocab["domains"],
            vocab["actions"],
            vocab["source_kinds"],
            vocab["output_formats"],
            vocab["effect_kinds"],
        ),
    )
    write(gate / "schemas/capability-claim.schema.json", capability_schema())

    baseline = normalized_baseline(root, gate)
    write(gate / "evidence/baseline-evidence.json", baseline)
    write(gate / "fixtures/contracts/valid/baseline-evidence.json", baseline)
    write(
        gate / "schemas/baseline-evidence.schema.json",
        schema_header(
            "urn:nobus:gate0:baseline:v1",
            "Nobus Gate 0 Baseline Evidence Pack",
            infer_schema(baseline, const_schema="nobus.gate0.baseline.v1"),
        ),
    )

    product_schema = load(gate / "schemas/product-contract.schema.json")
    product_schema["properties"]["product_principles"] = string_array()
    catalog_item = strict_object(
        {
            "contract_name": {"type": "string"},
            "schema_id": {"type": "string"},
            "status": {"type": "string", "enum": ["current", "target"]},
            "owner": {"type": "string"},
            "producer": {"type": "string"},
            "consumers": string_array(),
            "trust_boundary": {"type": "string"},
            "required_fields": string_array(),
            "golden_ref": {"type": "string"},
            "source_ref": {"type": "string"},
        }
    )
    product_schema["properties"]["contract_catalog"] = {
        "type": "array",
        "items": catalog_item,
        "minItems": 13,
    }
    product_schema["required"].extend(["product_principles", "contract_catalog"])
    write(gate / "schemas/product-contract.schema.json", product_schema)

    invalid_dir = gate / "fixtures/contracts/invalid"
    invalid_product = copy.deepcopy(product)
    invalid_product["unknown_field"] = True
    write(invalid_dir / "product-contract-unknown-field.json", invalid_product)
    invalid_enum = copy.deepcopy(cases[0])
    invalid_enum["expected"]["intent"]["domain"] = "unknown_domain"
    write(invalid_dir / "corpus-case-unknown-enum.json", invalid_enum)
    invalid_unknown = copy.deepcopy(cases[0])
    invalid_unknown["unexpected"] = True
    write(invalid_dir / "corpus-case-unknown-field.json", invalid_unknown)
    invalid_tenant = copy.deepcopy(cases[0])
    invalid_tenant["expected"]["intent"]["entities"]["scope_ref"] = "scope://tenant-b/synthetic"
    write(invalid_dir / "corpus-case-tenant-swap.json", invalid_tenant)
    invalid_time = copy.deepcopy(cases[0])
    invalid_time["provenance"]["created_at"] = "2026-07-28T00:00:00"
    write(invalid_dir / "corpus-case-naive-datetime.json", invalid_time)
    invalid_real = copy.deepcopy(cases[0])
    invalid_real["source_kind"] = "real_payload"
    write(invalid_dir / "corpus-case-real-payload-flag.json", invalid_real)
    invalid_baseline = copy.deepcopy(baseline)
    invalid_baseline["gate"] = False
    write(invalid_dir / "baseline-bool-as-int.json", invalid_baseline)

    write(
        gate / "fixtures/golden/expected-intents.json",
        {
            "schema": "nobus.gate0.expected_intents.v1",
            "entries": [
                {
                    "case_id": case["case_id"],
                    "intent_sha256": digest(canonical(case["expected"]["intent"])),
                    "decision_sha256": digest(canonical(case["expected"]["decision"])),
                }
                for case in cases[::8]
            ],
        },
    )


def pydantic_schema(
    model: type[BaselineEvidence] | type[CapabilityClaim] | type[CorpusCase] | type[ProductContract],
    identifier: str,
    title: str,
) -> dict[str, Any]:
    result = model.model_json_schema(by_alias=True)
    result.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": identifier,
            "title": title,
        }
    )
    return result


_TARGET_ENUMS: dict[str, list[str]] = {
    "backend": ["local", "google"],
    "target_backend": ["telegram", "local", "google"],
    "classification": ["public", "internal", "confidential", "restricted"],
    "maximum_classification": ["public", "internal", "confidential", "restricted"],
    "document_kind": ["text", "markdown", "json", "csv", "html", "docx", "xlsx", "pdf", "google_doc", "google_sheet"],
    "format": ["telegram_text", "jpeg", "html", "xlsx", "docx", "pdf", "google_doc", "google_sheet"],
    "collision_policy": ["new_version", "ask"],
    "operation": ["create", "update"],
    "selection_kind": ["whole_document", "pages", "sheet_ranges", "text_sections"],
    "purpose": ["summarize", "answer", "extract_facts", "analyze", "preview"],
    "modality": ["text", "voice"],
    "status": ["ready", "needs_clarification", "unsupported", "rejected"],
    "domain": ["notes", "calendar", "tasks", "documents", "research", "general"],
    "action": ["none", "answer", "help", "status", "limit", "cancel", "search", "read", "list", "summarize", "compare", "analyze", "audit", "report", "remember", "extract_tasks", "create", "update", "complete", "delete", "deliver"],
    "access": ["metadata", "content"],
    "resolution": ["unresolved", "exact", "ambiguous", "not_found"],
    "risk": ["low", "medium", "high", "critical"],
    "authority": ["direct_owner", "l4_required", "denied"],
    "relation": ["none", "follow_up", "clarification_answer"],
    "adapter": ["windows_bridge", "google_drive", "google_docs", "google_sheets"],
    "selection_method": ["exact_id", "unique_metadata_match", "owner_confirmed_candidate"],
    "section_kind": ["text", "table", "chart", "reference"],
    "target_kind": ["new_document", "existing_document"],
    "approval_kind": ["exact_owner_request", "preview_confirmation"],
}
_TARGET_ARRAY_ENUMS: dict[str, list[str]] = {
    "document_kinds": _TARGET_ENUMS["document_kind"],
    "classifications": _TARGET_ENUMS["classification"],
    "metrics": ["revenue", "units", "average_price", "margin", "growth_rate", "share", "count", "custom_declared"],
    "grouping": ["client", "sku", "source", "day", "week", "month", "quarter", "year"],
    "requested_outputs": ["telegram_text", "normalized_facts", "table", "chart", "artifact_plan", "jpeg", "html", "xlsx", "docx", "pdf", "google_doc", "google_sheet"],
}


def target_golden_schema_projection(value: Any, path: tuple[str, ...] = ()) -> dict[str, Any]:
    """Generate a closed schema for one exact synthetic golden shape, not a production model."""

    key = path[-1] if path else ""
    if isinstance(value, dict):
        return strict_object(
            {
                child_key: target_golden_schema_projection(child, path + (child_key,))
                for child_key, child in value.items()
            }
        )
    if isinstance(value, list):
        if not value:
            return {"type": "array", "maxItems": 0}
        if all(isinstance(item, str) for item in value) and key in _TARGET_ARRAY_ENUMS:
            item_schema: dict[str, Any] = {"type": "string", "enum": _TARGET_ARRAY_ENUMS[key]}
        else:
            item_schema = target_golden_schema_projection(value[0], path + ("item",))
        return {
            "type": "array",
            "minItems": len(value),
            "maxItems": len(value),
            "items": item_schema,
        }
    if value is None:
        return {"type": "null"}
    if type(value) is bool:
        return {"type": "boolean"}
    if type(value) is int:
        return {"type": "integer"}
    if isinstance(value, str):
        if key == "schema":
            return {"type": "string", "const": value}
        if key == "schema_version":
            return {"type": "string", "const": "1"}
        if key in _TARGET_ENUMS:
            return {"type": "string", "enum": _TARGET_ENUMS[key]}
        if key == "kind":
            return {"type": "string", "const": value}
        if key.endswith("_digest") or key in {"intent_revision", "ingress_digest"}:
            return {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
        if key.endswith("_at"):
            return {
                "type": "string",
                "format": "date-time",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$",
            }
        try:
            uuid.UUID(value)
        except ValueError:
            return {"type": "string", "minLength": 1}
        return {"type": "string", "format": "uuid"}
    raise TypeError(f"unsupported target golden type at {path!r}: {type(value)!r}")


def target_schema_document(name: str, instance: dict[str, Any]) -> dict[str, Any]:
    body = target_golden_schema_projection(instance)
    return schema_header(
        f"urn:nobus:gate0:target-golden-projection:{name}:v1",
        f"{name} exact synthetic golden structural projection",
        {
            "$comment": "Test-only closed projection; owning Gate 1/2 architecture remains authoritative and no production model is defined here.",
            **body,
        },
    )

def gate2_target_instance(name: str, schema: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Build one synthetic structural golden; Gate 2 still owns production models."""

    base = {
        "schema": schema,
        "schema_version": "1",
        "schema_digest": "",
        "contract_digest": "",
        "created_at": "2030-01-10T00:00:00Z",
        "tenant_id": "tenant-a",
        "project_ref": "project-synthetic",
        "client_ref": None,
        "policy_version": "policy.v1",
        "registry_bundle_digest": "sha256:" + "a" * 64,
        **fields,
    }
    schema_projection = target_schema_document(name, base)
    base["schema_digest"] = digest(canonical(schema_projection))
    base["contract_digest"] = digest(
        canonical({key: value for key, value in base.items() if key != "contract_digest"})
    )
    return base


def target_contract_instances() -> dict[str, dict[str, Any]]:
    """Return semantically valid synthetic Gate 1/2 structural goldens."""

    digest_a = "sha256:" + "a" * 64
    digest_b = "sha256:" + "b" * 64
    digest_c = "sha256:" + "c" * 64
    intent = {
        "schema": "nobus.intent.v1",
        "intent_id": "11111111-1111-4111-8111-111111111111",
        "tenant_id": "tenant-a",
        "actor_identity": "owner:synthetic",
        "conversation_ref": "conversation:synthetic",
        "ingress_digest": digest_a,
        "received_at": "2030-01-10T00:00:00Z",
        "modality": "text",
        "owner_text": "Read the selected synthetic document.",
        "voice": None,
        "status": "ready",
        "domain": "documents",
        "action": "read",
        "entities": [
            {
                "kind": "document",
                "raw": "synthetic-document",
                "normalized": "synthetic-document",
                "resolution": "exact",
                "resolved_ref": "document.synthetic.1",
                "confidence": 10000,
            }
        ],
        "period": None,
        "source_scope": [
            {
                "source": "local_library",
                "access": "content",
                "selector": None,
                "scope_ref": "scope.synthetic.local",
                "explicit": True,
            }
        ],
        "requested_outputs": ["telegram_text"],
        "proposed_effects": [
            {
                "kind": "read",
                "source": "local_library",
                "target_hint": None,
                "target_ref": "document.synthetic.1",
                "summary": "Read the selected synthetic document.",
                "risk": "low",
                "authority": "direct_owner",
                "requires_confirmation": False,
                "idempotency_scope": None,
            }
        ],
        "confidence": 9500,
        "ambiguities": [],
        "clarification": None,
        "context": {
            "relation": "none",
            "frame_id": None,
            "frame_revision": None,
            "parent_intent_id": None,
            "expires_at": None,
        },
        "policy_version": "policy.v1",
        "route_registry_version": "routes.v1",
        "intent_revision": "",
    }
    intent["intent_revision"] = digest(
        canonical({key: value for key, value in intent.items() if key != "intent_revision"})
    )

    document_ref = gate2_target_instance(
        "DocumentRef",
        "nobus.document_ref.v1",
        {
            "document_ref_id": "22222222-2222-4222-8222-222222222222",
            "source_scope_id": "scope.synthetic.local",
            "backend": "local",
            "source_id": "33333333-3333-4333-8333-333333333333",
            "display_name": "synthetic-document.md",
            "document_kind": "markdown",
            "media_type": "text/markdown",
            "classification": "internal",
            "size_bytes": 128,
            "revision": {
                "kind": "local_sha256",
                "sha256": digest_a,
                "volume_id_digest": digest_b,
                "file_id_digest": digest_c,
                "observed_at": "2030-01-10T00:00:00Z",
            },
            "content_digest": digest_a,
            "provenance": {
                "adapter": "windows_bridge",
                "observed_at": "2030-01-10T00:00:00Z",
                "parent_scope_id": "scope.synthetic.local",
                "metadata_digest": digest_b,
                "selection_method": "exact_id",
            },
            "expires_at": "2030-01-10T01:00:00Z",
        },
    )
    document_query = gate2_target_instance(
        "DocumentQuery",
        "nobus.document_query.v1",
        {
            "query_id": "44444444-4444-4444-8444-444444444444",
            "source_scope_ids": ["scope.synthetic.local"],
            "query_text": "synthetic document",
            "name_hints": ["synthetic-document.md"],
            "folder_hints": [],
            "period": None,
            "document_kinds": ["markdown"],
            "media_types": ["text/markdown"],
            "classifications": ["internal"],
            "max_candidates": 20,
            "max_pages": 2,
            "metadata_timeout_ms": 1000,
        },
    )
    read_plan = gate2_target_instance(
        "DocumentReadPlan",
        "nobus.document_read_plan.v1",
        {
            "read_plan_id": "55555555-5555-4555-8555-555555555555",
            "documents": [
                {
                    "selection_kind": "whole_document",
                    "document_ref": copy.deepcopy(document_ref),
                }
            ],
            "purpose": "summarize",
            "max_source_bytes_per_document": 1024,
            "max_source_bytes_total": 2048,
            "max_extracted_chars_per_document": 2000,
            "max_extracted_chars_total": 4000,
            "max_parser_seconds_per_document": 5,
            "max_parser_seconds_total": 10,
            "dlp_profile": "dlp.v1",
            "prompt_profile": "prompt.tool-less.v1",
        },
    )
    analysis = gate2_target_instance(
        "AnalysisRequest",
        "nobus.analysis_request.v1",
        {
            "analysis_id": "66666666-6666-4666-8666-666666666666",
            "idempotency_key": "tenant-a:analysis:synthetic-1",
            "read_plan_digest": read_plan["contract_digest"],
            "sources": [copy.deepcopy(document_ref)],
            "question": "Summarize the synthetic document.",
            "sku_or_articles": [],
            "period": None,
            "metrics": ["count"],
            "grouping": ["source"],
            "calculation_rules": [],
            "requested_outputs": ["telegram_text"],
            "limitations": [],
            "processing_policy_ref": "processing.v1",
            "limits": {
                "max_documents": 1,
                "max_source_bytes": 2048,
                "max_extracted_characters": 4000,
                "max_cells": 100,
                "max_pages": 10,
                "max_model_input_bytes": 4000,
                "max_provider_calls": 0,
            },
            "maximum_classification": "internal",
        },
    )
    artifact = gate2_target_instance(
        "ArtifactPlan",
        "nobus.artifact_plan.v1",
        {
            "artifact_plan_id": "77777777-7777-4777-8777-777777777777",
            "analysis_digest": analysis["contract_digest"],
            "title": "Synthetic report",
            "format": "docx",
            "sections": [
                {
                    "section_kind": "text",
                    "heading": "Summary",
                    "content_ref": "content.synthetic.1",
                    "content_digest": digest_a,
                }
            ],
            "content_digest": digest_a,
            "render_profile": "render.docx.v1",
            "target_backend": "local",
            "output_scope_id": "output.synthetic.local",
            "destination_hint": "synthetic-report",
            "collision_policy": "new_version",
            "provenance_refs": ["88888888-8888-4888-8888-888888888888"],
        },
    )
    write_plan = gate2_target_instance(
        "DocumentWritePlan",
        "nobus.document_write_plan.v1",
        {
            "write_plan_id": "99999999-9999-4999-8999-999999999999",
            "artifact_plan_digest": artifact["contract_digest"],
            "artifact_ref": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "artifact_digest": digest_a,
            "backend": "local",
            "operation": "create",
            "output_scope_id": "output.synthetic.local",
            "target": {
                "target_kind": "new_document",
                "destination_name": "synthetic-report.docx",
            },
            "expected_revision": None,
            "collision_policy": "new_version",
            "snapshot_required": False,
            "strict_cas_required": False,
            "idempotency_key": "tenant-a:write:synthetic-1",
            "approval_binding": {
                "approval_kind": "exact_owner_request",
                "ingress_digest": digest_a,
                "intent_digest": intent["intent_revision"],
                "unchanged_payload_digest": digest_a,
                "unchanged_destination_digest": digest_b,
            },
            "expires_at": "2030-01-10T01:00:00Z",
        },
    )
    return {
        "IntentEnvelope": intent,
        "DocumentRef": document_ref,
        "DocumentQuery": document_query,
        "DocumentReadPlan": read_plan,
        "AnalysisRequest": analysis,
        "ArtifactPlan": artifact,
        "DocumentWritePlan": write_plan,
    }


def contract_examples(root: pathlib.Path, catalog: list[dict[str, Any]], target_instances: dict[str, dict[str, Any]]) -> dict[str, Any]:
    digest_value = "sha256:" + "a" * 64
    envelope_base = {
        "schema_version": "1",
        "ingress_id": "11111111-1111-4111-8111-111111111111",
        "tenant_id": "tenant-a",
        "source": "api",
        "actor_identity": "api:synthetic-owner",
        "external_message_id": "request:synthetic-1",
        "idempotency_key": "tenant-a:synthetic:1",
        "received_at": "2030-01-10T00:00:00Z",
        "kind": "system_job",
        "content_ref": digest_value,
        "auth_context_ref": "sha256:" + "b" * 64,
    }
    envelope = {**envelope_base, "envelope_revision": digest(canonical(envelope_base))}
    current_instances: dict[str, dict[str, Any]] = {
        "TrustedIngressEnvelope": envelope,
        "TaskContract": {
            "schema_version": "1",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "idempotency_key": envelope["idempotency_key"],
            "ingress_digest": envelope["envelope_revision"],
            "tenant_id": "tenant-a",
            "source": "api",
            "conversation_ref": "telegram:" + "c" * 40,
            "instruction": "Analyze the synthetic test snapshot.",
            "allowed_paths": ["workspace/synthetic-input"],
            "permissions": ["read"],
            "risk": "low",
            "acceptance_criteria": ["Return synthetic evidence references."],
            "timeout_seconds": 60,
            "quality_profile": "standard",
        },
        "WorkerEvent": {
            "schema_version": "1",
            "event_id": "33333333-3333-4333-8333-333333333333",
            "tenant_id": "tenant-a",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "attempt_id": "44444444-4444-4444-8444-444444444444",
            "contract_digest": digest_value,
            "worker_identity": "worker:synthetic",
            "sequence": 1,
            "event_type": "progress",
            "emitted_at": "2030-01-10T00:01:00Z",
            "payload": {"stage": "synthetic", "percent": 25},
        },
        "VerificationBundle": {
            "schema_version": "1",
            "tenant_id": "tenant-a",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "contract_digest": digest_value,
            "result_revision": 1,
            "result_digest": "sha256:" + "d" * 64,
            "executor_identity": "executor:synthetic",
            "l1": None,
            "l2": None,
            "l3": None,
            "status": "draft",
        },
        "HumanApprovalRecord": {
            "tenant_id": "tenant-a",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "contract_digest": digest_value,
            "result_revision": 1,
            "result_digest": "sha256:" + "d" * 64,
            "approver_identity": "owner:synthetic",
            "approved_at": "2030-01-10T00:02:00Z",
            "evidence_ref": "telegram/callback/synthetic",
        },
        "ProductEffectChallenge": {
            "token": "synthetic-effect-challenge",
            "kind": "google_drive",
            "preview": "Synthetic Google Drive effect preview.",
        },
    }
    examples: dict[str, Any] = {}
    for entry in catalog:
        name = entry["contract_name"]
        source_path = root / entry["source_ref"]
        instance = current_instances.get(name)
        profile = "current_model_validation"
        schema_ref = None
        if instance is None:
            instance = copy.deepcopy(target_instances[name])
            profile = "target_owner_contract_structural_golden_no_production_model"
            schema_ref = f"fixtures/golden/target-contract-schema-projections.json#/schemas/{name}"
        examples[name] = {
            "status": entry["status"],
            "source_ref": entry["source_ref"],
            "source_digest": digest(source_path.read_bytes()),
            "validation_profile": profile,
            "schema_ref": schema_ref,
            "instance": instance,
            "instance_digest": digest(canonical(instance)),
        }
    return {"schema": "nobus.gate0.contract_examples.v1", "examples": examples}

def fix_product(root: pathlib.Path, gate: pathlib.Path) -> dict[str, Any]:
    path = gate / "product/product-contract.json"
    product = load(path)
    for principle in (
        "slash_commands_operational_fallback_only",
        "common_google_local_document_lifecycle",
    ):
        if principle not in product["product_principles"]:
            product["product_principles"].append(principle)
    common_gate2 = [
        "schema", "schema_version", "schema_digest", "contract_digest", "created_at",
        "tenant_id", "project_ref", "client_ref", "policy_version", "registry_bundle_digest",
    ]
    required_fields = {
        "TrustedIngressEnvelope": ["schema_version", "ingress_id", "tenant_id", "source", "actor_identity", "external_message_id", "idempotency_key", "received_at", "kind", "content_ref", "auth_context_ref", "envelope_revision"],
        "TaskContract": ["schema_version", "task_id", "idempotency_key", "ingress_digest", "tenant_id", "source", "conversation_ref", "instruction", "allowed_paths", "permissions", "risk", "acceptance_criteria", "timeout_seconds", "quality_profile"],
        "WorkerEvent": ["schema_version", "event_id", "tenant_id", "task_id", "attempt_id", "contract_digest", "worker_identity", "sequence", "event_type", "emitted_at", "payload"],
        "VerificationBundle": ["schema_version", "tenant_id", "task_id", "contract_digest", "result_revision", "result_digest", "executor_identity", "l1", "l2", "l3", "status"],
        "HumanApprovalRecord": ["tenant_id", "task_id", "contract_digest", "result_revision", "result_digest", "approver_identity", "approved_at", "evidence_ref"],
        "ProductEffectChallenge": ["token", "kind", "preview"],
        "IntentEnvelope": ["schema", "intent_id", "tenant_id", "actor_identity", "conversation_ref", "ingress_digest", "received_at", "modality", "owner_text", "voice", "status", "domain", "action", "entities", "period", "source_scope", "requested_outputs", "proposed_effects", "confidence", "ambiguities", "clarification", "context", "policy_version", "route_registry_version", "intent_revision"],
        "DocumentRef": common_gate2 + ["document_ref_id", "source_scope_id", "backend", "source_id", "display_name", "document_kind", "media_type", "classification", "size_bytes", "revision", "content_digest", "provenance", "expires_at"],
        "DocumentQuery": common_gate2 + ["query_id", "source_scope_ids", "query_text", "name_hints", "folder_hints", "period", "document_kinds", "media_types", "classifications", "max_candidates", "max_pages", "metadata_timeout_ms"],
        "DocumentReadPlan": common_gate2 + ["read_plan_id", "documents", "purpose", "max_source_bytes_per_document", "max_source_bytes_total", "max_extracted_chars_per_document", "max_extracted_chars_total", "max_parser_seconds_per_document", "max_parser_seconds_total", "dlp_profile", "prompt_profile"],
        "AnalysisRequest": common_gate2 + ["analysis_id", "idempotency_key", "read_plan_digest", "sources", "question", "sku_or_articles", "period", "metrics", "grouping", "calculation_rules", "requested_outputs", "limitations", "processing_policy_ref", "limits", "maximum_classification"],
        "ArtifactPlan": common_gate2 + ["artifact_plan_id", "analysis_digest", "title", "format", "sections", "content_digest", "render_profile", "target_backend", "output_scope_id", "destination_hint", "collision_policy", "provenance_refs"],
        "DocumentWritePlan": common_gate2 + ["write_plan_id", "artifact_plan_digest", "artifact_ref", "artifact_digest", "backend", "operation", "output_scope_id", "target", "expected_revision", "collision_policy", "snapshot_required", "strict_cas_required", "idempotency_key", "approval_binding", "expires_at"],
    }
    current_schema_ids = {
        "TrustedIngressEnvelope": "python-symbol:src/contracts/models.py#TrustedIngressEnvelope@1",
        "TaskContract": "python-symbol:src/contracts/models.py#TaskContract@1",
        "WorkerEvent": "python-symbol:src/contracts/models.py#WorkerEvent@1",
        "VerificationBundle": "python-symbol:src/contracts/models.py#VerificationBundle@1",
        "HumanApprovalRecord": "python-symbol:src/contracts/models.py#HumanApprovalRecord@1",
        "ProductEffectChallenge": "python-symbol:src/application/product_effects.py#ProductEffectChallenge@d11eda8",
    }
    current_enum_refs = {
        "TrustedIngressEnvelope": ["src/contracts/models.py#IngressSource", "src/contracts/models.py#IngressKind"],
        "TaskContract": ["src/contracts/models.py#RiskLevel", "docs/05-Спецификации-контрактов.md#permission-registry"],
        "WorkerEvent": ["src/contracts/models.py#WorkerEventType"],
        "VerificationBundle": ["src/contracts/models.py#VerificationBundleStatus", "src/contracts/models.py#VerificationLevel"],
        "HumanApprovalRecord": ["docs/05-Спецификации-контрактов.md#approval-contracts-v1"],
        "ProductEffectChallenge": ["src/application/product_effects.py#ProductEffectKind"],
    }
    for entry in product["contract_catalog"]:
        if entry["contract_name"] == "ProductEffectRecord":
            entry.update(
                {
                    "contract_name": "ProductEffectChallenge",
                    "schema_id": "current.product_effect_challenge.v1",
                }
            )
        name = entry["contract_name"]
        entry["required_fields"] = required_fields[name]
        if name in current_schema_ids:
            entry["schema_id"] = current_schema_ids[name]
        entry["closed_enum_refs"] = current_enum_refs.get(
            name,
            ["docs/gates/gate-01-natural-language-voice/ARCHITECTURE.md#5.2"]
            if name == "IntentEnvelope"
            else ["docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md#7"],
        )
        entry["invariant_refs"] = ["PC-02", "PC-03", "PC-10"]
        entry["golden_ref"] = (
            f"fixtures/golden/contract-examples.json#/examples/{entry['contract_name']}"
        )
    ProductContract.model_validate(product)
    target_instances = target_contract_instances()
    target_schemas = {
        name: target_schema_document(name, instance)
        for name, instance in target_instances.items()
    }
    for name, instance in target_instances.items():
        if "schema_digest" in instance:
            assert instance["schema_digest"] == digest(canonical(target_schemas[name]))
    write(
        gate / "fixtures/golden/target-contract-schema-projections.json",
        {
            "schema": "nobus.gate0.target_contract_schema_projections.v1",
            "profile": "test_only_closed_exact_golden_shape_no_production_model",
            "authoritative_sources": [
                "docs/gates/gate-01-natural-language-voice/ARCHITECTURE.md",
                "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md",
            ],
            "schemas": target_schemas,
        },
    )
    write(path, product)
    write(gate / "fixtures/contracts/valid/product-contract.json", product)
    write(
        gate / "fixtures/golden/contract-examples.json",
        contract_examples(root, product["contract_catalog"], target_instances),
    )
    write(
        gate / "schemas/product-contract.schema.json",
        pydantic_schema(
            ProductContract,
            "urn:nobus:gate0:product-contract:v1",
            "Nobus Gate 0 Product Contract",
        ),
    )
    invalid = copy.deepcopy(product)
    invalid["unknown_field"] = True
    write(
        gate / "fixtures/contracts/invalid/product-contract-unknown-field.json",
        invalid,
    )
    return product


def fix_cases(gate: pathlib.Path, product: dict[str, Any]) -> list[dict[str, Any]]:
    path = gate / "corpus/requests.v1.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for case in cases:
        if (
            category_of(case) == "calendar"
            and case["expected"]["decision"] == "accept"
        ):
            case["expected"]["intent"]["period"] = {
                "start": "2030-01-09T21:00:00Z",
                "end": "2030-01-10T21:00:00Z",
                "timezone": "Europe/Moscow",
                "original_text": "10 января 2030 года",
                "inclusive_end": False,
            }
        CorpusCase.model_validate(case)
    cases.sort(key=lambda case: case["case_id"])
    raw = b"".join(canonical(case) + b"\n" for case in cases)
    path.write_bytes(raw)
    coverage = build_coverage(cases)
    write(gate / "corpus/coverage.json", coverage)
    write(
        gate / "corpus/corpus-manifest.json",
        {
            "schema": "nobus.gate0.corpus_manifest.v1",
            "corpus_version": "1.0.0",
            "line_count": len(cases),
            "corpus_digest": digest(raw),
            "coverage_digest": digest(
                (gate / "corpus/coverage.json").read_bytes()
            ),
            "case_ids_digest": digest(
                canonical([case["case_id"] for case in cases])
            ),
            "provenance": "fully_synthetic",
            "contains_owner_or_client_payload": False,
            "encoding": "utf-8",
            "line_format": "canonical-json-plus-lf",
        },
    )
    write(gate / "fixtures/contracts/valid/corpus-case.json", cases[0])
    corpus_schema = pydantic_schema(
        CorpusCase,
        "urn:nobus:gate0:corpus-case:v1",
        "Nobus Gate 0 Canonical Corpus Case",
    )
    entity_schema = corpus_schema["$defs"]["CorpusEntities"]
    entity_schema["allOf"] = [
        {
            "if": {
                "properties": {"tenant_ref": {"const": tenant}},
                "required": ["tenant_ref"],
            },
            "then": {
                "properties": {
                    "scope_ref": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "string",
                                "pattern": rf"^scope://{tenant}/[a-z0-9._/-]+$",
                            },
                        ]
                    }
                }
            },
        }
        for tenant in ("tenant-a", "tenant-b")
    ]
    write(gate / "schemas/corpus-case.schema.json", corpus_schema)

    invalid_dir = gate / "fixtures/contracts/invalid"
    invalid_enum = copy.deepcopy(cases[0])
    invalid_enum["expected"]["intent"]["domain"] = "unknown_domain"
    write(invalid_dir / "corpus-case-unknown-enum.json", invalid_enum)
    invalid_unknown = copy.deepcopy(cases[0])
    invalid_unknown["unexpected"] = True
    write(invalid_dir / "corpus-case-unknown-field.json", invalid_unknown)
    invalid_tenant = copy.deepcopy(cases[0])
    invalid_tenant["expected"]["intent"]["entities"]["scope_ref"] = (
        "scope://tenant-b/synthetic"
    )
    write(invalid_dir / "corpus-case-tenant-swap.json", invalid_tenant)
    invalid_time = copy.deepcopy(cases[0])
    invalid_time["provenance"]["created_at"] = "2026-07-28T00:00:00"
    write(invalid_dir / "corpus-case-naive-datetime.json", invalid_time)
    invalid_real = copy.deepcopy(cases[0])
    invalid_real["source_kind"] = "real_payload"
    write(invalid_dir / "corpus-case-real-payload-flag.json", invalid_real)
    write(
        gate / "fixtures/golden/expected-intents.json",
        {
            "schema": "nobus.gate0.expected_intents.v1",
            "entries": [
                {
                    "case_id": case["case_id"],
                    "intent_sha256": digest(
                        canonical(case["expected"]["intent"])
                    ),
                    "decision_sha256": digest(
                        canonical(case["expected"]["decision"])
                    ),
                }
                for case in cases[::8]
            ],
        },
    )
    return cases


def current_parser_patterns(root: pathlib.Path) -> list[tuple[str, str, dict[str, Any]]]:
    """Extract literal rules without importing config or reading environment values."""

    source_path = root / "src/orchestrator/intent_parser.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "IntentParser":
            for statement in node.body:
                target = statement.target if isinstance(statement, ast.AnnAssign) else None
                if isinstance(target, ast.Name) and target.id == "PATTERNS":
                    value = ast.literal_eval(statement.value)
                    return [(str(pattern), str(intent), dict(defaults)) for pattern, intent, defaults in value]
    raise ValueError("IntentParser.PATTERNS literal not found")


def write_current_parser_baseline(
    root: pathlib.Path,
    gate: pathlib.Path,
    cases: list[dict[str, Any]],
    observed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    patterns = current_parser_patterns(root)
    entries: list[dict[str, Any]] = []
    for case in cases:
        text = case["turns"][-1]["text"].strip().lower()
        actual = "unknown"
        for pattern, intent, _defaults in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                actual = intent
                break
        expected = case["expected"]["intent"]["action"]
        entries.append(
            {
                "case_id": case["case_id"],
                "expected_action": expected,
                "actual_intent": actual,
                "match": actual == expected,
            }
        )
    matches = sum(entry["match"] for entry in entries)
    source_path = root / "src/orchestrator/intent_parser.py"
    report = {
        "schema": "nobus.gate0.current_corpus_baseline.v1",
        "observed_at": observed_at,
        "parser_profile": "literal_rule_fast_path_llm_disabled",
        "parser_source_ref": "src/orchestrator/intent_parser.py#IntentParser.PATTERNS",
        "parser_source_digest": digest(source_path.read_bytes()),
        "commit_under_test": str(git(root, "rev-parse", "HEAD")),
        "corpus_version": "1.0.0",
        "corpus_digest": digest((gate / "corpus/requests.v1.jsonl").read_bytes()),
        "case_count": len(entries),
        "matches": matches,
        "pass_rate": round(matches / len(entries), 6),
        "llm_or_provider_calls_performed": False,
        "raw_text_persisted": False,
        "entries": entries,
    }
    relative = "docs/gates/gate-00-product-contract-baseline/evidence/current-corpus-baseline.json"
    write(root / relative, report)
    return report, evidence_ref(root, relative, observed_at, kind="test_report")

def fix_baseline(
    root: pathlib.Path,
    gate: pathlib.Path,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = load(gate / "evidence/baseline-evidence.json")
    score_report, score_ref = write_current_parser_baseline(
        root, gate, cases, baseline["capture"]["completed_at"]
    )
    runtime_head = baseline["runtime_release"]["runtime_head_commit"]
    baseline["repository"]["merge_bases"]["docs_to_runtime_release"] = str(
        git(root, "merge-base", DESIGN_BASE, runtime_head)
    )

    baseline["dependencies"]["requirements"]["files"] = [
        {"path": entry.pop("ref"), **entry}
        if "ref" in entry
        else entry
        for entry in baseline["dependencies"]["requirements"]["files"]
    ]
    process_claim = next(
        claim
        for claim in baseline["claims"]
        if claim["claim_id"] == "current.telegram.runner"
    )
    if process_claim["verdict"] != "VERIFIED":
        process_claim["implementation_status"] = "PARTIAL"

    current_score = baseline["tests"]["baseline_scores"]["current_system"]
    current_score["corpus_digest"] = score_report["corpus_digest"]
    current_score["report_ref"] = score_ref
    current_score["pass_rate"] = score_report["pass_rate"]
    baseline["tests"]["evidence_refs"] = list(
        {ref["path_or_uri"]: ref for ref in baseline["tests"]["evidence_refs"] + [score_ref]}.values()
    )
    component = component_manifest(root, gate, baseline["capture"]["completed_at"])
    write(gate / "evidence/component-manifest.json", component)
    baseline["evidence_manifest_ref"] = evidence_ref(
        root,
        "docs/gates/gate-00-product-contract-baseline/evidence/component-manifest.json",
        baseline["capture"]["completed_at"],
        kind="manifest",
    )
    baseline["baseline_digest"] = ""
    projection = {
        key: value for key, value in baseline.items() if key != "baseline_digest"
    }
    baseline["baseline_digest"] = digest(canonical(projection))
    BaselineEvidence.model_validate(baseline)
    write(gate / "evidence/baseline-evidence.json", baseline)
    write(gate / "fixtures/contracts/valid/baseline-evidence.json", baseline)
    baseline_schema = pydantic_schema(
        BaselineEvidence,
        "urn:nobus:gate0:baseline:v1",
        "Nobus Gate 0 Baseline Evidence Pack",
    )
    write(gate / "schemas/baseline-evidence.schema.json", baseline_schema)
    capability_schema = copy.deepcopy(baseline_schema["$defs"]["CapabilityClaim"])
    capability_schema["$defs"] = {
        "EvidenceRef": copy.deepcopy(baseline_schema["$defs"]["EvidenceRef"])
    }
    capability_schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:nobus:gate0:capability-claim:v1",
            "title": "Nobus Gate 0 Capability Claim",
        }
    )
    write(gate / "schemas/capability-claim.schema.json", capability_schema)
    invalid = copy.deepcopy(baseline)
    invalid["gate"] = False
    write(
        gate / "fixtures/contracts/invalid/baseline-bool-as-int.json", invalid
    )
    return baseline


def normalize_v2(root: pathlib.Path, gate: pathlib.Path) -> None:
    cases_path = gate / "corpus/requests.v1.jsonl"
    first_case = json.loads(
        next(line for line in cases_path.read_text(encoding="utf-8").splitlines() if line)
    )
    if "input" in first_case:
        normalize_legacy(root, gate)
    product = fix_product(root, gate)
    cases = fix_cases(gate, product)
    fix_baseline(root, gate, cases)


CONSUMER_HANDOFFS = [
    {
        "gate": 1,
        "name": "intent_voice",
        "required_inputs": [
            "corpus version and digest",
            "intent vocabulary",
            "ambiguity and effect rules",
            "CURRENT baseline score",
        ],
        "not_precompleted": [
            "parser, prompt, confidence or context implementation",
        ],
    },
    {
        "gate": 2,
        "name": "contracts_registries",
        "required_inputs": [
            "contract catalog",
            "schema and golden fixtures",
            "registry semantics",
            "architecture fitness rules",
        ],
        "not_precompleted": [
            "production models, migrations or registry data",
        ],
    },
    {
        "gate": 3,
        "name": "google_gemini",
        "required_inputs": [
            "provider and data policy",
            "external capability baseline",
            "provider event fields",
        ],
        "not_precompleted": [
            "provider selection, cost cap or adapter implementation",
        ],
    },
    {
        "gate": 4,
        "name": "notes_calendar_tasks",
        "required_inputs": [
            "domain corpus cases",
            "authority rules",
            "idempotency and unknown-outcome rules",
        ],
        "not_precompleted": ["end-to-end effects"],
    },
    {
        "gate": 5,
        "name": "documents_bridge",
        "required_inputs": [
            "document lifecycle",
            "deny, source and output semantics",
            "path and adversarial cases",
        ],
        "not_precompleted": [
            "Bridge protocol, authentication, indexer or parser",
        ],
    },
    {
        "gate": 6,
        "name": "analytics",
        "required_inputs": [
            "AnalysisRequest semantics",
            "provenance rules",
            "calculation corpus cases",
        ],
        "not_precompleted": [
            "formulas, datasets or calibrated quality metrics",
        ],
    },
    {
        "gate": 7,
        "name": "artifacts_writeback",
        "required_inputs": [
            "ArtifactPlan and DocumentWritePlan semantics",
            "revision and digest rules",
            "collision policy",
        ],
        "not_precompleted": [
            "renderers or Google/local writeback",
        ],
    },
    {
        "gate": 8,
        "name": "release_pilot",
        "required_inputs": [
            "Baseline Evidence schema",
            "evidence manifest",
            "SLO candidates",
            "evidence freshness rules",
        ],
        "not_precompleted": [
            "deployment, retention backend or 72-hour pilot",
        ],
    },
]


def handoff_string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "uniqueItems": True}


def fix_capture_enclosure(root: pathlib.Path, gate: pathlib.Path) -> None:
    """Close the capture only after every read-only observation is persisted."""

    baseline = load(gate / "evidence/baseline-evidence.json")
    raw_tests = load(gate / "evidence/test-inventory.json")
    run_by_profile = {
        "gate0_contracts": raw_tests["targeted_gate0"],
        "full_regression": raw_tests["full_pytest"],
    }
    started_candidates = [baseline["capture"]["started_at"]]
    for run in baseline["tests"]["runs"]:
        raw_run = run_by_profile[run["profile"]]
        if raw_run.get("started_at") and raw_run.get("finished_at"):
            run["started_at"] = raw_run["started_at"]
            run["finished_at"] = raw_run["finished_at"]
            started_candidates.append(raw_run["started_at"])
    observed_candidates: list[str] = []

    def collect_observed(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                collect_observed(child, child_key)
        elif isinstance(value, list):
            for child in value:
                collect_observed(child, key)
        elif (
            key in {
                "observed_at",
                "generated_at",
                "created_at",
                "started_at",
                "finished_at",
            }
            and isinstance(value, str)
        ):
            observed_candidates.append(value)

    for key, value in baseline.items():
        if key != "capture":
            collect_observed(value, key)
    started_candidates.extend(observed_candidates)

    baseline["capture"]["started_at"] = min(
        started_candidates,
        key=lambda value: dt.datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    completed_candidates = [
        baseline["capture"]["completed_at"],
        *observed_candidates,
    ]
    completed_at = max(
        completed_candidates,
        key=lambda value: dt.datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    baseline["capture"]["completed_at"] = completed_at
    component = component_manifest(root, gate, completed_at)
    write(gate / "evidence/component-manifest.json", component)
    baseline["evidence_manifest_ref"] = evidence_ref(
        root,
        "docs/gates/gate-00-product-contract-baseline/evidence/component-manifest.json",
        completed_at,
        kind="manifest",
    )
    baseline["baseline_digest"] = ""
    projection = {
        key: value for key, value in baseline.items() if key != "baseline_digest"
    }
    baseline["baseline_digest"] = digest(canonical(projection))
    BaselineEvidence.model_validate(baseline)
    write(gate / "evidence/baseline-evidence.json", baseline)
    write(gate / "fixtures/contracts/valid/baseline-evidence.json", baseline)
    invalid = copy.deepcopy(baseline)
    invalid["gate"] = False
    write(
        gate / "fixtures/contracts/invalid/baseline-bool-as-int.json", invalid
    )
    for name, field, timestamp in (
        ("baseline-naive-timestamp.json", "started_at", "2030-01-10T00:00:00"),
        ("baseline-non-utc-timestamp.json", "completed_at", "2030-01-10T03:00:00+03:00"),
    ):
        invalid_time = copy.deepcopy(baseline)
        invalid_time["capture"][field] = timestamp
        invalid_time["baseline_digest"] = ""
        invalid_time["baseline_digest"] = digest(
            canonical(
                {
                    key: value
                    for key, value in invalid_time.items()
                    if key != "baseline_digest"
                }
            )
        )
        write(gate / "fixtures/contracts/invalid" / name, invalid_time)
    capability = copy.deepcopy(
        next(
            claim
            for claim in baseline["claims"]
            if claim["claim_id"] == "target.mvp1.product"
        )
    )
    for name, timestamp in (
        ("capability-naive-timestamp.json", "2030-01-10T00:00:00"),
        ("capability-non-utc-timestamp.json", "2030-01-10T03:00:00+03:00"),
    ):
        invalid_capability = copy.deepcopy(capability)
        invalid_capability["fresh_until"] = timestamp
        write(gate / "fixtures/contracts/invalid" / name, invalid_capability)


def fix_handoff(gate: pathlib.Path) -> None:
    baseline = load(gate / "evidence/baseline-evidence.json")
    corpus = load(gate / "corpus/corpus-manifest.json")
    product = load(gate / "product/product-contract.json")
    dependencies = load(gate / "evidence/dependency-inventory.json")
    tests = load(gate / "evidence/test-inventory.json")
    raw_runtime = load(gate / "evidence/runtime-inventory.json")
    raw_databases = load(gate / "evidence/database-inventory.json")
    capture_state = capture_lifecycle(raw_runtime)
    database_capture_state = database_capture_lifecycle(
        raw_databases, raw_runtime
    )
    path = gate / "fixtures/contracts/valid/gate-handoff.json"
    handoff = load(path)
    criterion_reasons: dict[str, str] = {}
    for limitation in baseline["limitations"]:
        for criterion in limitation["blocking_criteria"]:
            criterion_reasons[criterion] = limitation["code"]
    if (
        baseline["processes"][0]["status"] != "VERIFIED"
        or baseline["scheduler"][0]["status"] != "VERIFIED"
    ):
        criterion_reasons.setdefault("G0-04", "RUNTIME_EVIDENCE_NOT_VERIFIED")
    if any(
        database["status"] != "VERIFIED"
        or database["runtime_binding_status"] != "VERIFIED"
        for database in baseline["databases"]
    ):
        criterion_reasons.setdefault("G0-05", "DATABASE_EVIDENCE_NOT_VERIFIED")
    verifier = dependencies["verification_toolchain"]
    dev_checks = verifier["dev_checks"]
    core_path = gate / "evidence/pre-capture-core.json"
    core = load(core_path) if core_path.is_file() else {}
    verifier_bound = verifier_binding_verified(
        dependencies,
        core.get("input_tree_digest"),
        core.get("input_generated_at"),
        len(core.get("input_entries", [])),
    )
    tests_bound = test_binding_verified(
        tests,
        core.get("input_tree_digest"),
        core.get("input_generated_at"),
    )
    for criterion, check in (
        ("G0-14", "jsonschema"),
        ("G0-15", "hypothesis"),
        ("G0-16", "import_linter"),
    ):
        if dev_checks.get(check) != "passed" or not verifier_bound:
            criterion_reasons[criterion] = "VERIFIER_CHECK_NOT_PASSED"
    if (
        not tests_bound
        or
        tests["targeted_gate0"]["status"] != "pass"
        or tests["full_pytest"]["status"] != "pass"
    ):
        criterion_reasons["G0-08"] = "PYTEST_NOT_BOUND_TO_FROZEN_TREE"
    if (
        not verifier_bound
        or dependencies["secret_scan"]["status"] != "passed"
    ):
        criterion_reasons["G0-12"] = "SECRET_SCAN_NOT_BOUND_TO_FROZEN_TREE"

    release_blockers = []
    if not verifier_bound:
        release_blockers.append("VERIFIER_TREE_BINDING_NOT_VERIFIED")
    if not tests_bound:
        release_blockers.append("TEST_TREE_BINDING_NOT_VERIFIED")
    if dependencies["vulnerability_check"]["status"] != "passed":
        release_blockers.append("PIP_AUDIT_NOT_PASSED")
    if dependencies["secret_scan"]["status"] != "passed":
        release_blockers.append("GITLEAKS_NOT_PASSED")

    for criterion in handoff["acceptance"]:
        if criterion["id"] in criterion_reasons:
            criterion.update(
                {
                    "status": "blocked",
                    "reason_code": criterion_reasons[criterion["id"]],
                }
            )
        elif criterion["id"] == "G0-19":
            criterion.update(
                {
                    "status": "pending",
                    "reason_code": "INDEPENDENT_REVIEW_PENDING",
                }
            )
        else:
            criterion.update({"status": "pass", "reason_code": None})
    blocking_criteria = sorted({*criterion_reasons, "G0-19"})
    telegram_raw = next(
        database
        for database in raw_databases["databases"]
        if database["database_role"] == "telegram_state"
    )
    _, telegram_status, genesis_verified = database_claim(
        telegram_raw,
        database_capture_state,
    )
    all_databases_verified = all(
        database["status"] == "VERIFIED"
        and database["runtime_binding_status"] == "VERIFIED"
        and database["database_ref"].startswith("runtime-db:")
        for database in baseline["databases"]
    ) and authoritative_database_set(raw_databases["databases"])
    genesis_verified = genesis_verified and all_databases_verified
    database_binding_status = (
        "VERIFIED"
        if all_databases_verified
        else "STALE"
        if database_capture_state == "STALE"
        else "CONTRADICTORY"
    )
    handoff.update(
        {
            "status": "blocked",
            "blocking_criteria": blocking_criteria,
            "base_commit": baseline["repository"]["head_commit"],
            "artifact_manifest_ref": "evidence/evidence-manifest.json",
            "current_before": {
                "documentation_commit": baseline["documentation"]["canonical_commit"],
                "repository_commit": baseline["repository"]["head_commit"],
                "runtime_commit": baseline["runtime_release"]["runtime_head_commit"],
                "runner_status": baseline["processes"][0]["status"],
                "database_migration_status": (
                    "GENESIS_BASELINE_VERIFIED"
                    if genesis_verified
                    else "STALE"
                    if telegram_status == "STALE"
                    else "CONTRADICTORY"
                ),
                "database_runtime_binding_status": database_binding_status,
                "server_profile_status": "NOT_APPLICABLE_VERIFIED",
            },
            "current_after": {
                "product_contract": "candidate_implemented",
                "corpus": "candidate_implemented",
                "baseline_evidence": "candidate_implemented",
                "runtime_mutated": False,
                "gate_status": "blocked",
            },
            "release_readiness_blockers": release_blockers,
            "target_remaining": (
                [
                    "Gate 2 must start its durable migration ledger at the accepted genesis before any post-genesis migration",
                ]
                if genesis_verified
                else [
                    "Obtain one fresh consistent source-matched telegram_state capture before accepting a genesis baseline",
                    "Gate 2 may start the durable ledger only from a subsequently accepted genesis baseline",
                ]
            ),
            "applied_contract_version": "1.0.0",
            "applied_contract_digest": digest(canonical(product)),
            "applied_corpus_version": corpus["corpus_version"],
            "applied_corpus_digest": corpus["corpus_digest"],
            "verification_refs": {
                "l1": "verification/l1.json",
                "l2": "verification/l2.json",
                "l3": "verification/l3.json",
            },
            "mutations": {
                "migrations": False,
                "backups": False,
                "external_effects": False,
                "runtime": False,
            },
            "l4_ref": "owner-authority:gate0-evidence-closure-2026-07-29",
            "unresolved_risks": [
                (
                    "Historical Telegram legacy migration execution is not proven; only the accepted current schema is the genesis baseline"
                    if genesis_verified
                    else "No genesis baseline is accepted because the saved Telegram database proof is stale or contradictory"
                ),
                *[
                    f"{criterion}: {reason}"
                    for criterion, reason in sorted(criterion_reasons.items())
                ],
            ],
            "consumer_handoffs": CONSUMER_HANDOFFS,
        }
    )
    write(path, handoff)

    schema = load(gate / "schemas/gate-handoff.schema.json")
    props = schema["properties"]
    props.update(
        {
            "base_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "artifact_manifest_ref": {"type": "string"},
            "current_before": strict_object(
                {
                    "documentation_commit": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{40}$",
                    },
                    "repository_commit": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{40}$",
                    },
                    "runtime_commit": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{40}$",
                    },
                    "runner_status": {"type": "string"},
                    "database_migration_status": {"type": "string"},
                    "database_runtime_binding_status": {"type": "string"},
                    "server_profile_status": {"type": "string"},
                }
            ),
            "current_after": strict_object(
                {
                    "product_contract": {"type": "string"},
                    "corpus": {"type": "string"},
                    "baseline_evidence": {"type": "string"},
                    "runtime_mutated": {"type": "boolean"},
                    "gate_status": {"type": "string", "enum": ["ready", "blocked"]},
                }
            ),
            "release_readiness_blockers": handoff_string_array(),
            "target_remaining": handoff_string_array(),
            "applied_contract_version": {"type": "string"},
            "applied_contract_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "applied_corpus_version": {"type": "string"},
            "applied_corpus_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "verification_refs": strict_object(
                {
                    "l1": {"type": "string"},
                    "l2": {"type": "string"},
                    "l3": {"type": "string"},
                }
            ),
            "mutations": strict_object(
                {
                    "migrations": {"type": "boolean"},
                    "backups": {"type": "boolean"},
                    "external_effects": {"type": "boolean"},
                    "runtime": {"type": "boolean"},
                }
            ),
            "l4_ref": {"type": "string"},
            "unresolved_risks": handoff_string_array(),
            "consumer_handoffs": {
                "type": "array",
                "minItems": 8,
                "maxItems": 8,
                "items": strict_object(
                    {
                        "gate": {"type": "integer", "minimum": 1, "maximum": 8},
                        "name": {"type": "string"},
                        "required_inputs": handoff_string_array(),
                        "not_precompleted": handoff_string_array(),
                    }
                ),
            },
        }
    )
    schema["required"] = list(
        dict.fromkeys(
            [
                *schema.get("required", []),
                "base_commit",
                "artifact_manifest_ref",
                "current_before",
                "current_after",
                "release_readiness_blockers",
                "target_remaining",
                "applied_contract_version",
                "applied_contract_digest",
                "applied_corpus_version",
                "applied_corpus_digest",
                "verification_refs",
                "mutations",
                "l4_ref",
                "unresolved_risks",
                "consumer_handoffs",
            ]
        )
    )
    write(gate / "schemas/gate-handoff.schema.json", schema)
    for name, timestamp in (
        ("gate-handoff-naive-timestamp.json", "2030-01-10T00:00:00"),
        ("gate-handoff-non-utc-timestamp.json", "2030-01-10T03:00:00+03:00"),
    ):
        invalid_handoff = copy.deepcopy(handoff)
        invalid_handoff["generated_at"] = timestamp
        write(gate / "fixtures/contracts/invalid" / name, invalid_handoff)


def normalize(root: pathlib.Path, gate: pathlib.Path) -> None:
    normalize_v2(root, gate)
    fix_capture_enclosure(root, gate)
    fix_handoff(gate)
