"""Independent deterministic checks for the normative Gate 0 candidate."""

from __future__ import annotations

import ast
import collections
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import uuid
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from collect_gate0_snapshot import _snapshot_evidence
from gate0_precapture import STATUS_VOLATILE_PATHS
from gate0_lifecycle import capture_lifecycle, database_capture_lifecycle
from normative_models import (
    BaselineEvidence,
    CapabilityClaim,
    CorpusCase,
    ProductContract,
    UtcTimestamp,
)
from target_golden_semantics import validate_target_contract_golden


ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "docs/gates/gate-00-product-contract-baseline"
CORPUS = GATE / "corpus/requests.v1.jsonl"
DESIGN_BASE = "9d816b35d3f419b42e24ad09ae6aadc92c33db43"
REPO_HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd=ROOT,
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
RUNTIME_HEAD = "1ac52a00fd22b25cb6fcbd9f694688157c900cc8"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: pathlib.Path) -> Any:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert b"\r\n" not in raw, path
    return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)


def load_cases() -> list[dict[str, Any]]:
    raw = CORPUS.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw
    return [
        json.loads(line, object_pairs_hook=no_duplicates)
        for line in raw.decode("utf-8").splitlines()
    ]


def category(case: dict[str, Any]) -> str:
    return next(
        tag.removeprefix("category.")
        for tag in case["tags"]
        if tag.startswith("category.")
    )


def artifact_paths() -> list[pathlib.Path]:
    return sorted(
        [ROOT / ".gitattributes"]
        + [
            path
            for base in (GATE, ROOT / "tests/gate0")
            for path in base.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        ]
    )


def manifest_paths() -> list[pathlib.Path]:
    return sorted(
        artifact_paths()
        + [
            ROOT / "tests/test_fake_vertical.py",
            ROOT / "tests/test_telegram_gateway.py",
            ROOT / "tests/test_trusted_ingress.py",
        ]
    )


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class Acceptance(ClosedModel):
    id: str
    status: Literal["pass", "blocked", "pending"]
    evidence_refs: list[str]
    reason_code: str | None


class CurrentBefore(ClosedModel):
    documentation_commit: str
    repository_commit: str
    runtime_commit: str
    runner_status: str
    database_migration_status: str
    database_runtime_binding_status: str
    server_profile_status: str


class CurrentAfter(ClosedModel):
    product_contract: str
    corpus: str
    baseline_evidence: str
    runtime_mutated: bool
    gate_status: Literal["ready", "blocked"]


class VerificationRefs(ClosedModel):
    l1: str
    l2: str
    l3: str


class Mutations(ClosedModel):
    migrations: bool
    backups: bool
    external_effects: bool
    runtime: bool


class ConsumerHandoff(ClosedModel):
    gate: StrictInt | Literal["2a"]
    name: str
    required_inputs: list[str]
    not_precompleted: list[str]


class GateHandoff(ClosedModel):
    schema_value: Literal["nobus.gate0.handoff.v1"] = Field(alias="schema")
    gate: StrictInt
    status: Literal["ready", "blocked"]
    product_contract_ref: str
    baseline_ref: str
    corpus_manifest_ref: str
    evidence_manifest_ref: str
    base_commit: str
    artifact_manifest_ref: str
    current_before: CurrentBefore
    current_after: CurrentAfter
    release_readiness_blockers: list[str]
    target_remaining: list[str]
    applied_contract_version: str
    applied_contract_digest: str
    applied_corpus_version: str
    applied_corpus_digest: str
    verification_refs: VerificationRefs
    mutations: Mutations
    l4_ref: str
    unresolved_risks: list[str]
    consumer_handoffs: list[ConsumerHandoff]
    acceptance: list[Acceptance]
    blocking_criteria: list[str]
    next_gate: StrictInt
    result_commit: str | None
    generated_at: UtcTimestamp


def test_required_artifact_layout() -> None:
    required = {
        "HANDOFF.md",
        "decisions/decision-register.json",
        "schemas/baseline-evidence.schema.json",
        "schemas/capability-claim.schema.json",
        "schemas/product-contract.schema.json",
        "schemas/corpus-case.schema.json",
        "schemas/gate-handoff.schema.json",
        "product/product-contract.json",
        "corpus/requests.v1.jsonl",
        "corpus/coverage.json",
        "corpus/corpus-manifest.json",
        "evidence/baseline-evidence.json",
        "evidence/dirty-manifest.json",
        "evidence/dependency-inventory.json",
        "evidence/test-inventory.json",
        "evidence/external-capabilities.json",
        "evidence/current-corpus-baseline.json",
        "fixtures/golden/contract-examples.json",
        "fixtures/golden/target-contract-schema-projections.json",
        "fixtures/golden/gate-acceptance-score.json",
        "evidence/evidence-manifest.json",
        "verification/l1.json",
        "verification/l2.json",
        "verification/l3.json",
    }
    assert all((GATE / relative).is_file() for relative in required)
    assert not (GATE / "fixtures/golden/baseline-score.json").exists()
    assert not (GATE / "fixtures/golden/contract-catalog.json").exists()
    assert not (ROOT / "tests/gate0/manifest_v2.py").exists()
    assert not (ROOT / "tests/gate0/normalize_gate0_contracts_v2.py").exists()
    assert not (ROOT / "tests/gate0/normalize_gate0_contracts_v3.py").exists()
    assert (ROOT / ".gitattributes").is_file()
    assert (ROOT / "tests/gate0/verifier-requirements.txt").is_file()
    assert (ROOT / "tests/gate0/verifier-toolchain.json").is_file()


def test_all_json_and_jsonl_are_utf8_lf_without_duplicate_keys() -> None:
    for path in artifact_paths():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        assert b"\r" not in raw, path
        if path.suffix == ".json":
            load_json(path)
    cases = load_cases()
    assert len(cases) == 104
    assert CORPUS.read_bytes() == b"".join(
        canonical_bytes(case) + b"\n" for case in cases
    )


def test_all_five_json_schemas_are_unique_and_closed() -> None:
    schemas = [load_json(path) for path in sorted((GATE / "schemas").glob("*.json"))]
    assert len(schemas) == 5
    assert len({schema["$id"] for schema in schemas}) == 5

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert "required" in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for schema in schemas:
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        walk(schema)


def test_pydantic_accepts_all_valid_contracts() -> None:
    ProductContract.model_validate(load_json(GATE / "product/product-contract.json"))
    BaselineEvidence.model_validate(load_json(GATE / "evidence/baseline-evidence.json"))
    GateHandoff.model_validate(
        load_json(GATE / "fixtures/contracts/valid/gate-handoff.json")
    )
    for case in load_cases():
        CorpusCase.model_validate(case)


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("product-contract-unknown-field.json", ProductContract),
        ("corpus-case-unknown-enum.json", CorpusCase),
        ("corpus-case-unknown-field.json", CorpusCase),
        ("corpus-case-tenant-swap.json", CorpusCase),
        ("corpus-case-naive-datetime.json", CorpusCase),
        ("corpus-case-real-payload-flag.json", CorpusCase),
        ("baseline-bool-as-int.json", BaselineEvidence),
        ("baseline-naive-timestamp.json", BaselineEvidence),
        ("baseline-non-utc-timestamp.json", BaselineEvidence),
        ("capability-naive-timestamp.json", CapabilityClaim),
        ("capability-non-utc-timestamp.json", CapabilityClaim),
        ("gate-handoff-naive-timestamp.json", GateHandoff),
        ("gate-handoff-non-utc-timestamp.json", GateHandoff),
    ],
)
def test_invalid_fixtures_fail_closed(name: str, model: type[BaseModel]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(load_json(GATE / "fixtures/contracts/invalid" / name))


def test_corpus_has_exact_architecture_distribution() -> None:
    cases = load_cases()
    assert collections.Counter(category(case) for case in cases) == {
        "business_notes": 8,
        "calendar": 12,
        "tasks": 12,
        "documents_google_local_lifecycle": 24,
        "analytics_research_general": 12,
        "voice_text_context_clarification": 12,
        "security_effect_tenant_provider_adversarial": 16,
        "development_miniapp_control": 8,
    }
    assert len({case["case_id"] for case in cases}) == 104

def test_reworked_corpus_oracles_are_explicitly_grounded() -> None:
    cases = {case["case_id"]: case for case in load_cases()}

    for case_id in ("G0-CAL-008", "G0-CAL-012"):
        case = cases[case_id]
        assert case["expected"]["decision"] == "clarify"
        assert case["expected"]["intent"]["period"] is None
        assert [item["code"] for item in case["expected"]["errors"]] == [
            "TARGET_AMBIGUOUS"
        ]
        request = case["turns"][-1]["text"]
        assert "Google Calendar" in request and "2030" in request

    for case_id in ("G0-TASK-008", "G0-TASK-012"):
        case = cases[case_id]
        assert case["expected"]["decision"] == "clarify"
        assert [item["code"] for item in case["expected"]["errors"]] == [
            "TARGET_AMBIGUOUS"
        ]
        assert "Google Tasks" in case["turns"][-1]["text"]

    safe_view = cases["G0-DOC-024"]
    assert safe_view["expected"]["decision"] == "accept"
    assert safe_view["expected"]["errors"] == []
    assert "provenance_safe_view" in safe_view["tags"]
    assert safe_view["expected"]["effects"] == [
        {"kind": "read", "execution": "proposed"}
    ]

    for case_id in ("G0-SEC-001", "G0-SEC-002"):
        case = cases[case_id]
        assert case["turns"][0]["speaker"] == "system_context"
        assert case["turns"][0]["trusted_context_ref"] == (
            "context://synthetic/authorized-binding"
        )
        authorized = case["turns"][0]["text"]
        requested = case["turns"][-1]["text"]
        assert all(value in authorized for value in ("tenant-a", "project-alpha", "client-alpha"))
        assert all(value in requested for value in ("tenant-b", "project-beta", "client-beta"))
        entities = case["expected"]["intent"]["entities"]
        assert entities["tenant_ref"] == "tenant-a"
        assert entities["project_ref"] == "project-alpha"
        assert entities["client_ref"] == "client-alpha"
        assert {item["code"] for item in case["expected"]["errors"]} >= {
            "TENANT_MISMATCH", "CROSS_PROJECT_DENIED", "CROSS_CLIENT_DENIED"
        }
        assert case["expected"]["decision"] == "reject"
        assert all(
            effect["execution"] == "forbidden"
            for effect in case["expected"]["effects"]
        )

def test_text_voice_pairs_are_reciprocal_and_semantically_equal() -> None:
    cases = {case["case_id"]: case for case in load_cases()}
    pairs = {
        tuple(sorted((case_id, case["pair_ref"])))
        for case_id, case in cases.items()
        if case["pair_ref"]
    }
    assert len(pairs) == 20
    for left_id, right_id in pairs:
        left, right = cases[left_id], cases[right_id]
        assert left["pair_ref"] == right_id and right["pair_ref"] == left_id
        assert {left["modality"], right["modality"]} == {"text", "voice_transcript"}
        assert left["turns"][-1]["text"] == right["turns"][-1]["text"]
        assert left["expected"] == right["expected"]


def test_natural_corpus_oracles_are_grounded_in_each_request() -> None:
    cases = load_cases()
    source_cues = {
        "business_notes": ("бизнес-замет", "заметк"),
        "google_calendar": ("google calendar",),
        "google_tasks": ("google tasks",),
        "google_drive": ("google",),
        "local_library": ("локальн", "bridge"),
        "public_web": ("публичн",),
        "telegram_attachment": ("telegram attachment",),
        "registered_repository": ("модель", "candidate commit"),
        "control_plane": ("live service", "mini app"),
    }
    action_cues = {
        "remember": ("запомни", "сохрани"),
        "search": ("найди", "поищи", "поиск"),
        "read": ("прочитай", "открой", "покажи", "раскрой", "чтен", "выбери"),
        "list": ("покажи", "перечисли"),
        "summarize": ("суммируй",),
        "extract_tasks": ("извлеки",),
        "create": ("создай", "добавь"),
        "update": ("обнови", "обновл", "измени", "перенеси", "сдвинь", "перезапиши", "запиши", "доступ"),
        "complete": ("отметь", "заверши"),
        "delete": ("удали", "удаление"),
        "deliver": ("отправь", "передай", "доставк", "ссылк"),
        "compare": ("сравни", "сопоставь"),
        "analyze": ("проанализируй", "оцени"),
        "audit": ("аудит",),
        "report": ("отчёт",),
        "status": ("статус", "status"),
        "cancel": ("отмени",),
        "limit": ("ограничь",),
        "help": ("помоги", "доступные"),
        "answer": ("объясни", "ответь", "покупк", "policy"),
        "commit": ("commit",),
        "deploy": ("deploy",),
    }
    for case in cases:
        request = case["turns"][-1]["text"].casefold()
        assert not re.search(r"синтетическ(?:ий|ая)\s+(?:запрос|реплик)\s+\d+", request)
        action = case["expected"]["intent"]["action"]
        assert any(cue in request for cue in action_cues[action]), case["case_id"]
        for source in case["expected"]["intent"]["source_scope"]:
            if source not in {"none"}:
                assert any(cue in request for cue in source_cues[source]), case["case_id"]
        period = case["expected"]["intent"]["period"]
        if period is not None:
            assert period["original_text"].casefold() in request
        codes = {error["code"] for error in case["expected"]["errors"]}
        if "L4_REQUIRED" in codes:
            assert "l4" in request
            assert case["expected"]["decision"] == "require_l4"
        if codes & {"UNKNOWN_PROVIDER_OUTCOME", "DELIVERY_OUTCOME_UNKNOWN", "ACK_LOSS_NO_BLIND_RESEND"}:
            assert case["expected"]["decision"] == "degraded"
            assert case["expected"]["user_message_profile"] == "status"
            assert all(effect["execution"] == "forbidden" for effect in case["expected"]["effects"])
        assert not codes & {"UNKNOWN_FIELD_REJECTED", "UNKNOWN_ENUM_REJECTED"}


def test_coverage_is_recalculated_not_trusted() -> None:
    cases = load_cases()
    coverage = load_json(GATE / "corpus/coverage.json")

    def counted(getter) -> dict[str, int]:
        return dict(sorted(collections.Counter(getter(case) for case in cases).items()))

    assert coverage["total_cases"] == len(cases)
    assert coverage["primary_category_counts"] == counted(category)
    assert coverage["modality_counts"] == counted(lambda case: case["modality"])
    assert coverage["domain_counts"] == counted(lambda case: case["expected"]["intent"]["domain"])
    assert coverage["action_counts"] == counted(lambda case: case["expected"]["intent"]["action"])
    assert coverage["decision_counts"] == counted(lambda case: case["expected"]["decision"])
    assert coverage["effect_counts"] == counted(lambda case: case["expected"]["effects"][0]["kind"])
    assert coverage["tenant_counts"] == counted(lambda case: case["expected"]["intent"]["entities"]["tenant_ref"])

    negative_count = sum("negative" in case["tags"] for case in cases)
    multi_count = sum(len(case["turns"]) > 1 or case["expected"]["decision"] == "clarify" for case in cases)
    pairs = sorted({tuple(sorted((case["case_id"], case["pair_ref"]))) for case in cases if case["pair_ref"]})
    assert coverage["negative_or_adversarial_cases"] == negative_count >= 30
    assert coverage["multi_turn_or_clarification_cases"] == multi_count >= 12
    assert coverage["text_voice_pair_count"] == len(pairs) >= 16
    assert coverage["text_voice_pairs"] == [list(pair) for pair in pairs]

    lifecycle = {}
    for source in ("google_drive", "local_library"):
        lifecycle[source] = sorted({
            tag for case in cases
            if source in case["expected"]["intent"]["source_scope"]
            for tag in case["tags"]
            if tag in {"search", "select", "read", "analyze", "create", "update", "deliver"}
        })
    assert coverage["document_lifecycle_coverage"] == lifecycle
    security_codes = sorted({
        error["code"] for case in cases if category(case) == "security_effect_tenant_provider_adversarial"
        for error in case["expected"]["errors"]
    })
    assert coverage["security_scenario_coverage"] == security_codes
    assert set(coverage["requirements"]["required_document_stages"]) == set(lifecycle["google_drive"]) == set(lifecycle["local_library"])
    assert set(coverage["requirements"]["required_security_scenarios"]) <= set(security_codes)

def test_corpus_manifest_binds_exact_bytes() -> None:
    manifest = load_json(GATE / "corpus/corpus-manifest.json")
    assert manifest["line_count"] == 104
    assert manifest["corpus_digest"] == sha256(CORPUS.read_bytes())
    assert manifest["coverage_digest"] == sha256(
        (GATE / "corpus/coverage.json").read_bytes()
    )
    assert manifest["case_ids_digest"] == sha256(
        canonical_bytes([case["case_id"] for case in load_cases()])
    )
    assert manifest["provenance"] == "fully_synthetic"
    assert manifest["contains_owner_or_client_payload"] is False


def test_effect_and_security_semantics_are_explicit() -> None:
    cases = load_cases()
    for case in cases:
        intent = case["expected"]["intent"]
        for effect in case["expected"]["effects"]:
            assert effect["kind"] in intent["proposed_effects"]
            if case["expected"]["decision"] in {"reject", "clarify"}:
                assert effect["execution"] == "forbidden"
        if case["expected"]["decision"] == "require_l4":
            assert {error["code"] for error in case["expected"]["errors"]} == {"L4_REQUIRED"}
            assert all(
                effect["execution"] == "allowed_after_l4"
                for effect in case["expected"]["effects"]
            )
        if case["expected"]["decision"] == "degraded":
            assert all(effect["execution"] == "forbidden" for effect in case["expected"]["effects"])
            assert case["expected"]["user_message_profile"] == "status"
            assert {error["code"] for error in case["expected"]["errors"]} <= {
                "UNKNOWN_PROVIDER_OUTCOME",
                "DELIVERY_OUTCOME_UNKNOWN",
                "ACK_LOSS_NO_BLIND_RESEND",
            }
    security = [
        case
        for case in cases
        if category(case) == "security_effect_tenant_provider_adversarial"
    ]
    error_codes = {
        error["code"] for case in security for error in case["expected"]["errors"]
    }
    assert {
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
        "ACK_LOSS_NO_BLIND_RESEND",
    } <= error_codes


def test_time_ranges_are_grounded_aware_and_half_open_moscow_days() -> None:
    calendar = [
        case for case in load_cases()
        if category(case) == "calendar" and case["expected"]["decision"] == "accept"
    ]
    assert calendar
    for case in calendar:
        period = case["expected"]["intent"]["period"]
        request = case["turns"][-1]["text"]
        assert period == {
            "start": "2030-01-09T21:00:00Z",
            "end": "2030-01-10T21:00:00Z",
            "timezone": "Europe/Moscow",
            "original_text": "10 января 2030 года",
            "inclusive_end": False,
        }
        assert period["original_text"] in request
        start = dt.datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
        assert end - start == dt.timedelta(days=1)

def test_artifacts_contain_no_secret_pii_or_absolute_local_path_patterns() -> None:
    selected = [
        path
        for path in artifact_paths()
        if path.name == "HANDOFF.md"
        or any(
            part in {"corpus", "evidence", "fixtures", "product", "verification"}
            for part in path.parts
        )
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="strict") for path in selected
    )
    assert not re.search(r"(?i)\b[A-Z]:[\\/]", combined)
    assert not re.search(r"(?i)(ghp_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,})", combined)
    assert "BEGIN PRIVATE KEY" not in combined
    assert not re.search(r"(?i)Bearer\s+[A-Za-z0-9._-]{16,}", combined)
    assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", combined)
    assert not re.search(r"\+7[\s()-]*\d{3}[\s()-]*\d{3}", combined)


def test_baseline_keeps_docs_repo_runtime_process_layers_separate() -> None:
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    assert baseline["documentation"]["canonical_commit"] == DESIGN_BASE
    assert baseline["repository"]["head_commit"] == REPO_HEAD
    assert baseline["runtime_release"]["runtime_head_commit"] == RUNTIME_HEAD
    assert baseline["documentation"]["head_matches_canonical"] is False
    assert baseline["runtime_release"]["docs_commit_is_ancestor"] is False
    process = baseline["processes"][0]
    assert process["status"] in {"STALE", "VERIFIED", "CONTRADICTORY"}
    claim = next(
        claim
        for claim in baseline["claims"]
        if claim["claim_id"] == "current.telegram.runner"
    )
    assert claim["verdict"] == process["status"]
    assert claim["implementation_status"] == (
        "CURRENT" if process["status"] == "VERIFIED" else "PARTIAL"
    )
    assert claim["fresh_until"] is not None
    observed = dt.datetime.fromisoformat(process["observed_at"].replace("Z", "+00:00"))
    deadline = dt.datetime.fromisoformat(claim["fresh_until"].replace("Z", "+00:00"))
    completed = dt.datetime.fromisoformat(
        baseline["capture"]["completed_at"].replace("Z", "+00:00")
    )
    assert deadline - observed == dt.timedelta(minutes=5)
    if process["status"] == "VERIFIED":
        assert completed <= deadline
        assert process["observed_count"] == 1
        assert len(process["instances"]) == 1
        assert claim["statement"].startswith("Exact single Scheduler-bound")
    elif process["status"] == "STALE":
        assert completed > deadline
    elif process["status"] == "CONTRADICTORY":
        assert process["observed_count"] != 1
        assert claim["implementation_status"] == "PARTIAL"
        assert claim["contradictions"]

def test_capture_interval_encloses_all_persisted_observations() -> None:
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    start = dt.datetime.fromisoformat(
        baseline["capture"]["started_at"].replace("Z", "+00:00")
    )
    completed = dt.datetime.fromisoformat(
        baseline["capture"]["completed_at"].replace("Z", "+00:00")
    )
    observed: list[dt.datetime] = []

    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif key in {"observed_at", "generated_at", "created_at", "started_at", "finished_at"} and isinstance(value, str):
            observed.append(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))

    for key, value in baseline.items():
        if key != "capture":
            walk(value, key)
    assert start <= completed
    assert observed
    assert all(start <= value <= completed for value in observed)


def test_dirty_manifest_preserves_preexisting_ownership() -> None:
    dirty = load_json(GATE / "evidence/dirty-manifest.json")
    assert dirty["head_commit"] == REPO_HEAD
    assert dirty["runtime_release"]["head_commit"] == RUNTIME_HEAD
    assert dirty["runtime_release"]["design_base_is_ancestor"] is False
    assert dirty["ownership_rule"]["protected_entries_modified_by_gate0"] is False
    quality = next(
        entry
        for entry in dirty["entries"]
        if entry["path"] == ".nobus-quality/cases.ndjson"
    )
    assert quality["status"] == " M"
    assert quality["owner"] == "preexisting"
    assert all(
        entry["owner"] in {"preexisting", "gate0"} for entry in dirty["entries"]
    )
    expected_exact_files = {
        ".gitattributes",
        "README.md",
        "docs/04-Журнал-ADR.md",
        "docs/07-Правила-внешней-записи.md",
        "docs/12-Эталон-MVP-1-и-дорожная-карта.md",
        "docs/13-Интегрированная-архитектура-MVP-1.md",
        "docs/README.md",
        "docs/adr/0019-owner-service-filesystem-and-runtime-decisions.md",
        "docs/adr/0020-early-miniapp-and-specialist-workers.md",
        "docs/gates/README.md",
        "docs/gates/gate-01-natural-language-voice/ARCHITECTURE.md",
        "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md",
        "docs/gates/gate-03-google-foundation/ARCHITECTURE.md",
        "docs/gates/gate-04-notes-calendar-tasks/ARCHITECTURE.md",
        "docs/gates/gate-05-document-gateway-windows-bridge/ARCHITECTURE.md",
        "docs/gates/gate-08-hybrid-release-pilot/ARCHITECTURE.md",
        "docs/handoffs/CURRENT-STATUS.md",
        "tests/test_fake_vertical.py",
        "tests/test_telegram_gateway.py",
        "tests/test_trusted_ingress.py",
    }
    assert set(dirty["ownership_rule"]["gate0_exact_files"]) == expected_exact_files
    assert set(dirty["ownership_rule"]["gate0_prefixes"]) == {
        "docs/gates/gate-00-product-contract-baseline/",
        "docs/gates/gate-02a-miniapp-development-control/",
        "tests/gate0/",
    }
    assert {
        entry["path"] for entry in dirty["entries"]
        if entry["owner"] == "preexisting"
    } == {".nobus-quality/cases.ndjson"}

    raw = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    fields = raw.split("\0")
    current_paths: set[str] = set()
    index = 0
    while index < len(fields) and fields[index]:
        record = fields[index]
        status = record[:2]
        current_paths.add(pathlib.PurePath(record[3:]).as_posix())
        index += 1
        if status[0] in {"R", "C"} and index < len(fields):
            index += 1
    frozen_paths = {entry["path"] for entry in dirty["entries"]}
    assert frozen_paths - STATUS_VOLATILE_PATHS == current_paths - STATUS_VOLATILE_PATHS
    assert frozen_paths.symmetric_difference(current_paths) <= STATUS_VOLATILE_PATHS


def test_database_evidence_is_sanitized_and_genesis_is_bounded() -> None:
    raw = load_json(GATE / "evidence/database-inventory.json")
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    assert len(raw["databases"]) == len(baseline["databases"]) == 4
    raw_by_role = {item["database_role"]: item for item in raw["databases"]}
    telegram = raw_by_role["telegram_state"]
    migration_id = "unrecorded_source_migration:telegram_jobs_legacy_to_current"
    for database in raw["databases"]:
        assert database["integrity"] == {
            "quick_check": "ok",
            "foreign_key_check": "ok",
        }
        assert database["content_exported"] is False
        assert database["source_schema_match"] is True
        assert database["expected_schema_object_count"] > 0
        assert all(
            set(table) == {"table", "columns", "rows", "safe_status_counts"}
            for table in database["tables"]
        )
    all_snapshots_consistent = all(
        database["runtime_binding_status"] == "verified"
        and database["snapshot"]["mode"] == "sqlite_read_transaction"
        and database["snapshot"]["wal_aware"] is True
        and database["snapshot"]["data_version_stable"] is True
        and database["snapshot"]["consistent"] is True
        for database in raw["databases"]
    )
    database_state = database_capture_lifecycle(
        raw,
        load_json(GATE / "evidence/runtime-inventory.json"),
    )
    if all_snapshots_consistent:
        assert telegram["migration_inventory"] == {
            "applied": [],
            "pending": [],
            "unknown": [],
        }
        assert telegram["migration_lineage_status"] == "genesis_baseline_verified"
        assert telegram["genesis_baseline"] == {
            "genesis_id": "genesis_baseline:telegram_state_current_schema",
            "authority_ref": "owner-authority:gate0-evidence-closure-2026-07-29",
            "schema_digest": telegram["schema_digest"],
            "historical_legacy_migration_proven": False,
            "durable_ledger_deferred_to_gate": 2,
            "production_database_mutated": False,
        }
        assert telegram["source_migrations"] == [
            {
                "historical_application_recorded": False,
                "migration_id": migration_id,
                "source_ref": "src/application/durable_telegram_state.py",
                "source_sha256": sha256(
                    (ROOT / "src/application/durable_telegram_state.py").read_bytes()
                ),
            }
        ]
        expected_status = (
            "VERIFIED" if database_state == "FRESH" else database_state
        )
        assert expected_status in {"VERIFIED", "STALE", "UNVERIFIABLE"}
        assert all(
            database["status"] == expected_status
            and database["runtime_binding_status"] == "VERIFIED"
            for database in baseline["databases"]
        )
    else:
        assert telegram["genesis_baseline"] is None
        assert telegram["migration_lineage_status"] == "contradictory"
        assert any(
            database["snapshot"]["consistent"] is False
            for database in raw["databases"]
        )

        expected_status = (
            database_state
            if database_state in {"STALE", "UNVERIFIABLE"}
            else "CONTRADICTORY"
        )
        assert any(
            database["status"] == expected_status
            for database in baseline["databases"]
        )


def test_sqlite_snapshot_consistency_uses_transaction_not_file_quiescence() -> None:
    stable = (("main", True, 10, 100), ("-wal", True, 20, 100))
    changed = (("main", True, 10, 100), ("-wal", True, 30, 200))

    concurrent = _snapshot_evidence(7, 7, stable, changed)
    assert concurrent == {
        "mode": "sqlite_read_transaction",
        "wal_aware": True,
        "data_version_stable": True,
        "file_markers_stable": False,
        "concurrent_file_activity_observed": True,
        "consistent": True,
    }

    unstable = _snapshot_evidence(7, 8, stable, changed)
    assert unstable == {
        "mode": "sqlite_read_transaction",
        "wal_aware": True,
        "data_version_stable": False,
        "file_markers_stable": False,
        "concurrent_file_activity_observed": True,
        "consistent": False,
    }


def test_runtime_scheduler_capture_is_authorized_sanitized_and_bounded() -> None:
    runtime = load_json(GATE / "evidence/runtime-inventory.json")
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    runner = next(
        process
        for process in runtime["processes"]
        if process["process_role"] == "telegram_runner"
    )
    server = next(
        process
        for process in runtime["processes"]
        if process["process_role"] == "codex_app_server"
    )
    assert server["status"] == "not_configured"
    assert server["reason_code"] == "OWNER_VERIFIED_SERVER_NOT_DEPLOYED"
    assert runtime["server"] == {
        "status": "not_applicable_verified",
        "authority_ref": "owner-decision:gate0-l4-server-not-deployed",
    }
    scheduler = runtime["scheduler"]
    assert scheduler["enabled"] is True
    assert scheduler["state"] in {"ready", "running"}
    assert scheduler["action_arguments_status"] == "verified_sanitized"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", scheduler["action_arguments_digest"])
    assert scheduler["arguments_present"] is True
    assert scheduler["arguments_persisted"] is False
    constraints = runtime["collector_constraints"]
    assert constraints["access_profile"] == "one_time_transient_prefiltered"
    assert constraints["environment_values_read"] is False
    assert constraints["raw_values_persisted"] is False
    assert constraints["secret_values_detected"] is False
    if runner["status"] == "verified":
        assert constraints["authority_ref"] == "owner-authority:gate0-evidence-closure-2026-07-29"
        assert runner["observed_count"] == 1
        assert (
            runner["loaded_commit"]
            == runner["scheduled_commit"]
            == runtime["runtime_claim"]["process_loaded_commit"]
            == runtime["runtime_claim"]["scheduled_commit"]
        )
        assert scheduler["status"] == "verified"
        assert runtime["database_binding"]["status"] == "verified"
        runtime_state = capture_lifecycle(runtime)
        expected_status = "VERIFIED" if runtime_state == "FRESH" else runtime_state
        assert baseline["processes"][0]["status"] == expected_status
        assert baseline["scheduler"][0]["status"] == expected_status
    elif runner["status"] == "stale":
        assert constraints["authority_ref"] == "owner-authority:gate0-evidence-closure-2026-07-28"
        assert runner["observed_count"] == 0
        assert baseline["scheduler"][0]["status"] == "STALE"
    else:
        assert constraints["authority_ref"] == "owner-authority:gate0-evidence-closure-2026-07-29"
        assert runner["status"] == "not_observed"
        assert runner["observed_count"] == 0
        assert scheduler["status"] == "verified"
        assert runtime["database_binding"]["status"] == "verified"
        expected_status = (
            "STALE"
            if capture_lifecycle(runtime) == "STALE"
            else "CONTRADICTORY"
        )
        assert baseline["processes"][0]["status"] == expected_status
        assert baseline["scheduler"][0]["status"] == expected_status


def test_dependency_and_verifier_inventory_is_exact_and_sanitized() -> None:
    dependencies = load_json(GATE / "evidence/dependency-inventory.json")
    assert dependencies["pip"]["inspect_version"] == "1"
    assert dependencies["pip_check"]["status"] == "pass"
    assert dependencies["required_tools"] == {
        **dependencies["required_tools"],
        "pydantic": "2.13.4",
        "pytest": "9.1.1",
    }
    verifier = dependencies["verification_toolchain"]
    assert verifier["profile"] == "isolated_temp_official_artifacts"
    assert verifier["versions"] == {
        "gitleaks": "8.30.1",
        "hypothesis": "6.163.0",
        "import_linter": "2.13",
        "jsonschema": "4.26.0",
        "pip_audit": "2.10.1",
    }
    assert verifier["dev_checks"] == {
        "jsonschema": "passed",
        "hypothesis": "passed",
        "import_linter": "passed",
    }
    assert len(verifier["wheel_manifest"]) == 39
    assert all(
        item["source"] == "https://pypi.org/simple/"
        for item in verifier["wheel_manifest"]
    )
    assert verifier["gitleaks_checksum_verified"] is True
    assert verifier["raw_reports_persisted"] is False
    assert verifier["absolute_paths_persisted"] is False
    assert verifier["secret_values_persisted"] is False
    vulnerability = dependencies["vulnerability_check"]
    secret_scan = dependencies["secret_scan"]
    if verifier.get("release_environment", {}).get("pip") == "26.1.2":
        assert verifier["release_environment"] == {
            "python": "3.12.10",
            "pip": "26.1.2",
            "canonical_venv_mutated": False,
        }
        assert vulnerability["status"] == "passed"
        assert vulnerability["finding_count"] == 0
        assert vulnerability["findings"] == []
        assert secret_scan["status"] == "passed"
        assert secret_scan["finding_count"] == 0
        assert secret_scan["findings"] == []
        scan_count = verifier["gitleaks"]["scanned_file_count"]
        assert scan_count == secret_scan["scanned_file_count"]
        assert isinstance(scan_count, int) and not isinstance(scan_count, bool)
        assert scan_count > 0
        if verifier["candidate_binding"]["status"] == "verified":
            core = load_json(GATE / "evidence/pre-capture-core.json")
            assert scan_count == len(core["input_entries"])
        assert re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            verifier["gitleaks"]["raw_report_sha256"],
        )
    else:
        assert vulnerability["status"] == "findings"
        assert vulnerability["finding_count"] == 6
        assert secret_scan["status"] == "findings"
        assert secret_scan["finding_count"] == 6
        assert verifier["candidate_binding"]["status"] == "stale"
        assert all(
            item["match_value_persisted"] is False
            for item in secret_scan["findings"]
        )

def test_verifier_lock_reproduces_recorded_official_artifacts() -> None:
    dependencies = load_json(GATE / "evidence/dependency-inventory.json")
    toolchain = load_json(ROOT / "tests/gate0/verifier-toolchain.json")
    lock_path = ROOT / "tests/gate0/verifier-requirements.txt"
    lock_lines = [
        line
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    parsed = [
        re.fullmatch(
            r"(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[A-Za-z0-9_.+-]+) "
            r"--hash=(?P<sha256>sha256:[0-9a-f]{64})",
            line,
        )
        for line in lock_lines
    ]
    assert all(parsed)
    assert len(lock_lines) == 39
    assert len({match.group("name").casefold() for match in parsed if match}) == 39
    assert {match.group("sha256") for match in parsed if match} == {
        item["sha256"]
        for item in dependencies["verification_toolchain"]["wheel_manifest"]
    }
    assert "pip==26.1.2" in {
        line.split(" --hash=", 1)[0] for line in lock_lines
    }
    recorded = dependencies["verification_toolchain"]
    assert toolchain["sources"] == {
        "package_index": "https://pypi.org/simple/",
        "require_hashes": True,
        "wheels_only": True,
    }
    assert toolchain["gitleaks"]["version"] == recorded["versions"]["gitleaks"]
    assert toolchain["gitleaks"]["asset_url"] == recorded["gitleaks_asset_source"]
    assert (
        toolchain["gitleaks"]["asset_sha256"]
        == recorded["gitleaks_asset_sha256"]
    )
    assert (
        toolchain["gitleaks"]["checksums_url"]
        == recorded["gitleaks_checksums_source"]
    )


def test_each_baseline_gap_is_bound_to_an_acceptance_criterion() -> None:
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    limitations = {
        item["code"]: set(item["blocking_criteria"])
        for item in baseline["limitations"]
    }
    handoff = load_json(GATE / "fixtures/contracts/valid/gate-handoff.json")
    assert handoff["current_before"]["server_profile_status"] == "NOT_APPLICABLE_VERIFIED"
    acceptance = {item["id"]: item for item in handoff["acceptance"]}
    if limitations:
        assert limitations["DATABASE_EVIDENCE_NOT_VERIFIED"] == {"G0-05"}
        assert (
            limitations.get("RUNTIME_EVIDENCE_STALE")
            or limitations.get("EXPECTED_RUNNER_NOT_OBSERVED")
        ) == {"G0-04"}
        assert acceptance["G0-04"]["status"] == "blocked"
        assert acceptance["G0-05"]["status"] == "blocked"
    else:
        assert handoff["current_before"]["database_runtime_binding_status"] == "VERIFIED"
        assert handoff["current_before"]["database_migration_status"] == "GENESIS_BASELINE_VERIFIED"
        assert acceptance["G0-04"]["status"] == "pass"
        assert acceptance["G0-05"]["status"] == "pass"

def test_external_capabilities_do_not_infer_online_status() -> None:
    evidence = load_json(GATE / "evidence/external-capabilities.json")
    assert evidence["live_calls_performed"] is False
    assert all(
        claim["status"] in {
            "offline",
            "not_configured",
            "not_checked",
            "unverifiable",
        }
        for claim in evidence["claims"]
    )
    assert "online" not in {claim["status"] for claim in evidence["claims"]}


def test_owner_root_evidence_is_metadata_only_and_name_free() -> None:
    owner = load_json(GATE / "evidence/owner-root-metadata.json")
    assert owner["mode"] == "metadata_only_top_level"
    assert owner["descendants_read"] is False
    assert owner["names_persisted"] is False
    assert owner["counts"]["protected_entries_excluded"] >= 2


def test_product_contract_freezes_one_owner_and_catalog_binding() -> None:
    product = load_json(GATE / "product/product-contract.json")
    families = product["contract_families"]
    assert len({family["family"] for family in families}) == len(families)
    assert {
        family["owner_gate"]
        for family in families
        if not isinstance(family["owner_gate"], int)
    } == {"2a"}
    assert product["contract_version"] == "2.0.0"
    assert product["normative_input"]["source_count"] == 20
    assert "development_specialist" in product["vocabularies"]["agent_roles"]
    catalog = product["contract_catalog"]
    assert {entry["contract_name"] for entry in catalog} >= {
        "TrustedIngressEnvelope",
        "TaskContract",
        "WorkerEvent",
        "VerificationBundle",
        "HumanApprovalRecord",
        "ProductEffectChallenge",
        "IntentEnvelope",
        "DocumentRef",
        "DocumentQuery",
        "DocumentReadPlan",
        "AnalysisRequest",
        "ArtifactPlan",
        "DocumentWritePlan",
    }
    assert all(entry["required_fields"] for entry in catalog)
    assert all(entry["closed_enum_refs"] for entry in catalog)
    assert all(entry["invariant_refs"] for entry in catalog)


def test_contract_goldens_are_dereferenceable_bound_and_current_models_validate() -> None:
    product = load_json(GATE / "product/product-contract.json")
    golden = load_json(GATE / "fixtures/golden/contract-examples.json")
    examples = golden["examples"]
    assert set(examples) == {entry["contract_name"] for entry in product["contract_catalog"]}
    catalog = {entry["contract_name"]: entry for entry in product["contract_catalog"]}
    schema_bundle = load_json(
        GATE / "fixtures/golden/target-contract-schema-projections.json"
    )
    assert schema_bundle["profile"] == (
        "test_only_closed_exact_golden_shape_no_production_model"
    )
    target_names = {
        name for name, entry in catalog.items() if entry["status"] == "target"
    }
    assert set(schema_bundle["schemas"]) == target_names
    assert all(
        (ROOT / source).is_file()
        for source in schema_bundle["authoritative_sources"]
    )

    def assert_schema_objects_closed(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for child in node.values():
                assert_schema_objects_closed(child)
        elif isinstance(node, list):
            for child in node:
                assert_schema_objects_closed(child)
    for name, entry in catalog.items():
        prefix = "fixtures/golden/contract-examples.json#/examples/"
        assert entry["golden_ref"] == prefix + name
        example = examples[name]
        source = ROOT / example["source_ref"]
        assert source.is_file()
        assert example["source_digest"] == sha256(source.read_bytes())
        assert example["instance_digest"] == sha256(canonical_bytes(example["instance"]))
        if entry["status"] == "target":
            assert example["validation_profile"] == "target_owner_contract_structural_golden_no_production_model"
            assert example["schema_ref"] == (
                "fixtures/golden/target-contract-schema-projections.json"
                f"#/schemas/{name}"
            )
            schema_projection = schema_bundle["schemas"][name]
            assert_schema_objects_closed(schema_projection)
            if "schema_digest" in example["instance"]:
                assert example["instance"]["schema_digest"] == sha256(
                    canonical_bytes(schema_projection)
                )
            validate_target_contract_golden(name, example["instance"])
            assert set(example["instance"]) == set(entry["required_fields"])

    from src.contracts.models import (
        HumanApprovalRecord,
        TaskContract,
        TrustedIngressEnvelope,
        VerificationBundle,
        WorkerEvent,
    )
    TrustedIngressEnvelope.model_validate(examples["TrustedIngressEnvelope"]["instance"])
    TaskContract.model_validate(examples["TaskContract"]["instance"])
    WorkerEvent.model_validate(examples["WorkerEvent"]["instance"])
    VerificationBundle.model_validate(examples["VerificationBundle"]["instance"])
    HumanApprovalRecord.model_validate(examples["HumanApprovalRecord"]["instance"])

    from src.application.product_effects import ProductEffectChallenge, ProductEffectKind
    effect = examples["ProductEffectChallenge"]["instance"]
    challenge = ProductEffectChallenge(effect["token"], ProductEffectKind(effect["kind"]), effect["preview"])
    assert {"token": challenge.token, "kind": challenge.kind.value, "preview": challenge.preview} == effect


def test_documentation_inventory_binds_current_worktree_and_all_gate_sources() -> None:
    expected = {
        "docs/05-Спецификации-контрактов.md",
        "docs/06-Регламент-качества-L1-L4.md",
        "docs/07-Правила-внешней-записи.md",
        "docs/10-Политика-памяти.md",
        "docs/12-Эталон-MVP-1-и-дорожная-карта.md",
        "docs/13-Интегрированная-архитектура-MVP-1.md",
        "docs/adr/0017-hybrid-natural-google-local-document-plane.md",
        "docs/adr/0018-cross-gate-mvp1-integration.md",
        "docs/adr/0019-owner-service-filesystem-and-runtime-decisions.md",
        "docs/adr/0020-early-miniapp-and-specialist-workers.md",
        "docs/gates/gate-00-product-contract-baseline/ARCHITECTURE.md",
        *{f"docs/gates/gate-{gate:02d}-{slug}/ARCHITECTURE.md" for gate, slug in [
            (1, "natural-language-voice"),
            (2, "scope-document-contracts"),
            (3, "google-foundation"),
            (4, "notes-calendar-tasks"),
            (5, "document-gateway-windows-bridge"),
            (6, "multidocument-analytics"),
            (7, "artifact-factory-writeback"),
            (8, "hybrid-release-pilot"),
        ]},
        "docs/gates/gate-02a-miniapp-development-control/ARCHITECTURE.md",
    }
    inventory = load_json(GATE / "evidence/documentation-inventory.json")
    records = {entry["path"]: entry for entry in inventory["current_worktree_documents"]}
    assert set(records) == expected
    for relative, entry in records.items():
        assert entry["status"] == "VERIFIED"
        assert entry["sha256"] == sha256((ROOT / relative).read_bytes())
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    assert baseline["documentation"]["current_worktree_documents"] == inventory["current_worktree_documents"]
    product = load_json(GATE / "product/product-contract.json")
    bound_sources = {family["source_ref"] for family in product["contract_families"]} | {entry["source_ref"] for entry in product["contract_catalog"]}
    assert bound_sources <= expected


def test_current_parser_baseline_is_independently_recomputed_without_import() -> None:
    report = load_json(GATE / "evidence/current-corpus-baseline.json")
    source_path = ROOT / "src/orchestrator/intent_parser.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    patterns = None
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "IntentParser":
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.target.id == "PATTERNS":
                    patterns = ast.literal_eval(statement.value)
    assert patterns is not None
    entries = []
    for case in load_cases():
        request = case["turns"][-1]["text"].strip().lower()
        actual = "unknown"
        for pattern, intent, _defaults in patterns:
            if re.search(pattern, request, re.IGNORECASE):
                actual = intent
                break
        expected_action = case["expected"]["intent"]["action"]
        entries.append({"case_id": case["case_id"], "expected_action": expected_action, "actual_intent": actual, "match": actual == expected_action})
    assert report["entries"] == entries
    assert report["matches"] == sum(entry["match"] for entry in entries)
    assert report["pass_rate"] == round(report["matches"] / len(entries), 6)
    assert report["parser_source_digest"] == sha256(source_path.read_bytes())
    assert report["corpus_digest"] == sha256(CORPUS.read_bytes())
    assert report["llm_or_provider_calls_performed"] is False
    assert report["raw_text_persisted"] is False
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    score = baseline["tests"]["baseline_scores"]["current_system"]
    assert score["pass_rate"] == report["pass_rate"]
    assert score["report_ref"]["sha256"] == sha256((GATE / "evidence/current-corpus-baseline.json").read_bytes())
    acceptance_score = load_json(GATE / "fixtures/golden/gate-acceptance-score.json")
    assert acceptance_score["schema"] == "nobus.gate0.gate_acceptance_score.v1"
    handoff = load_json(GATE / "fixtures/contracts/valid/gate-handoff.json")
    status_counts = collections.Counter(
        row["status"] for row in handoff["acceptance"]
    )
    expected_score = (
        status_counts["pass"],
        status_counts["pending"],
        status_counts["blocked"],
        round(status_counts["pass"] * 100 / 22, 2),
    )
    assert (
        acceptance_score["passed"],
        acceptance_score["pending"],
        acceptance_score["blocked"],
        acceptance_score["score_percent"],
    ) == expected_score
    assert acceptance_score["gate_ready"] is (
        handoff["status"] == "ready"
        and status_counts == {"pass": 22}
    )


def test_baseline_ids_scheduler_db_config_and_bridge_claims_are_bounded() -> None:
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    assert uuid.UUID(baseline["baseline_id"]).int != 0
    documentation = load_json(GATE / "evidence/documentation-inventory.json")
    expected_id_input = {
        "generated_at": documentation["observed_at"],
        "repo_head": baseline["repository"]["head_commit"],
        "runtime_head": baseline["runtime_release"]["runtime_head_commit"],
        "documentation_digest": baseline["documentation"]["evidence_refs"][0]["sha256"],
        "database_digest": baseline["databases"][0]["evidence_refs"][0]["sha256"],
    }
    assert baseline["baseline_id"] == str(
        uuid.uuid5(uuid.NAMESPACE_URL, canonical_bytes(expected_id_input).decode("utf-8"))
    )
    scheduler = baseline["scheduler"][0]
    assert scheduler["action_arguments_profile"] == "verified_sanitized"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", scheduler["action_arguments_digest"])
    assert scheduler["status"] in {"STALE", "VERIFIED"}
    assert scheduler["action_executable_digest"] != scheduler["definition_digest"]
    collector = (ROOT / "tests/gate0/collect_runtime_snapshot.ps1").read_text(encoding="utf-8")
    assert "$actionArgumentsDigest = Get-SafeDigest" in collector
    assert ".Arguments" in collector
    assert "raw_values_persisted = $false" in collector
    assert "secret_values_detected" in collector
    assert '. $maintenanceHelper' in collector
    assert collector.count(
        "Get-RegisteredRuntimeDefinition -CanonicalRepoRoot $repoRootFull"
    ) == 2
    assert "$firstRuntimeAuthority.DefinitionDigest" in collector
    assert "$secondRuntimeAuthority.DefinitionDigest" in collector
    assert "$firstRuntimeAuthority.LauncherDigest" in collector
    assert "$firstRuntimeAuthority.ActionExecutableDigest" in collector
    assert "$definitionDigest = [string] $secondRuntimeAuthority.DefinitionDigest" in collector
    assert "Runtime authority drifted during capture." in collector
    for database in baseline["databases"]:
        assert database["source_profile"] in {
            "scheduler_bound_canonical_runtime_directory",
            "scheduler_bound_registered_runtime_directory",
        }
        assert database["runtime_binding_status"] in {"STALE", "VERIFIED"}
        assert database["runtime_binding_reason"] in {
            "SCHEDULER_BINDING_EVIDENCE_STALE",
            "SCHEDULER_RUNNER_ROOT_BOUND_IN_SINGLE_CAPTURE",
        }
        assert database["database_ref"].startswith(
            ("candidate-worktree-db:", "runtime-db:")
        )
    assert baseline["configuration"]["secret_store"]["required_refs_present"] is None
    capabilities = {item["capability"] for item in baseline["external_capabilities"]}
    assert {"local_library_bridge_read_v1", "local_library_bridge_write_v2"} <= capabilities

def test_canonical_and_core_golden_digests_are_stable() -> None:
    canonical = load_json(GATE / "fixtures/golden/canonicalization.json")
    raw = canonical_bytes(canonical["input"])
    assert canonical["canonical_utf8"] == raw.decode("utf-8")
    assert canonical["sha256"] == sha256(raw)
    golden = load_json(GATE / "fixtures/golden/core-digests.json")
    for entry in golden["entries"]:
        assert entry["sha256"] == sha256((ROOT / entry["path"]).read_bytes())
    assert golden["core_digest"] == sha256(canonical_bytes(golden["entries"]))


def test_component_manifest_binds_non_recursive_baseline_inputs() -> None:
    component = load_json(GATE / "evidence/component-manifest.json")
    for entry in component["entries"]:
        path = ROOT / entry["path"]
        assert entry["sha256"] == sha256(path.read_bytes())
        assert entry["size_bytes"] == path.stat().st_size
    assert component["manifest_digest"] == sha256(
        canonical_bytes(component["entries"])
    )


def test_evidence_manifest_exact_set_roles_hashes_and_digest() -> None:
    path = GATE / "evidence/evidence-manifest.json"
    manifest = load_json(path)
    expected = {
        artifact.relative_to(ROOT).as_posix()
        for artifact in manifest_paths()
        if artifact != path
    }
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    assert set(entries) == expected
    assert manifest["schema"] == "nobus.gate0.evidence_manifest.v1"
    assert manifest["base_commit"] == REPO_HEAD
    assert manifest["result_commit"] is None
    for relative, entry in entries.items():
        artifact = ROOT / relative
        assert entry["sha256"] == sha256(artifact.read_bytes())
        assert entry["bytes"] == artifact.stat().st_size
        assert entry["role"] in {
            "research",
            "architecture",
            "repository_policy",
            "verification_fixture",
            "schema",
            "product_contract",
            "corpus",
            "fixture",
            "evidence",
            "verification",
            "handoff",
        }
        assert entry["classification"] == "internal"
    assert manifest["result_tree_digest"] == sha256(
        canonical_bytes(manifest["entries"])
    )
    projection = {
        key: value for key, value in manifest.items() if key != "manifest_digest"
    }
    assert manifest["manifest_digest"] == sha256(canonical_bytes(projection))


def test_exact_digest_bound_eol_policy_and_lf_bytes() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    expected = {
        ".gitattributes text eol=lf",
        "docs/gates/gate-00-product-contract-baseline/** text eol=lf",
        "tests/gate0/** text eol=lf",
        "tests/test_fake_vertical.py text eol=lf",
        "tests/test_telegram_gateway.py text eol=lf",
        "tests/test_trusted_ingress.py text eol=lf",
    }
    assert set(attributes) == expected
    for relative in (
        "tests/test_fake_vertical.py",
        "tests/test_telegram_gateway.py",
        "tests/test_trusted_ingress.py",
    ):
        data = (ROOT / relative).read_bytes()
        assert b"\r" not in data
        assert data.endswith(b"\n")


@pytest.mark.parametrize("autocrlf", ("true", "false"))
def test_clean_checkout_with_autocrlf_preserves_manifest_bytes(
    tmp_path: pathlib.Path,
    autocrlf: str,
) -> None:
    manifest_path = GATE / "evidence/evidence-manifest.json"
    manifest = load_json(manifest_path)
    source = tmp_path / "source"
    checkout = tmp_path / "checkout"
    source.mkdir()

    copied = [manifest_path] + [
        ROOT / pathlib.PurePosixPath(entry["path"])
        for entry in manifest["entries"]
    ]
    for path in copied:
        relative = path.relative_to(ROOT)
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)

    def git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

    git(source, "init", "--quiet")
    git(source, "config", "user.name", "Gate 0 Synthetic Verifier")
    git(source, "config", "user.email", "gate0-verifier.invalid")
    git(source, "config", "core.autocrlf", autocrlf)
    git(source, "add", "--all")
    git(source, "commit", "--quiet", "-m", "synthetic clean-checkout fixture")
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "-c",
            f"core.autocrlf={autocrlf}",
            str(source),
            str(checkout),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )

    cloned_manifest = load_json(
        checkout
        / "docs/gates/gate-00-product-contract-baseline/evidence/evidence-manifest.json"
    )
    assert cloned_manifest == manifest
    for entry in cloned_manifest["entries"]:
        path = checkout / pathlib.PurePosixPath(entry["path"])
        assert path.stat().st_size == entry["bytes"]
        assert sha256(path.read_bytes()) == entry["sha256"]
    assert git(checkout, "status", "--porcelain").stdout == ""


def test_handoff_has_all_acceptance_ids_and_honest_blockers() -> None:
    handoff = load_json(GATE / "fixtures/contracts/valid/gate-handoff.json")
    GateHandoff.model_validate(handoff)
    rows = {row["id"]: row for row in handoff["acceptance"]}
    assert set(rows) == {f"G0-{number:02d}" for number in range(1, 23)}
    assert handoff["result_commit"] is None
    assert handoff["base_commit"] == REPO_HEAD
    product = load_json(GATE / "product/product-contract.json")
    corpus = load_json(GATE / "corpus/corpus-manifest.json")
    assert handoff["applied_contract_digest"] == sha256(canonical_bytes(product))
    assert handoff["applied_corpus_digest"] == corpus["corpus_digest"]
    assert {item["gate"] for item in handoff["consumer_handoffs"]} == {*range(1, 9), "2a"}
    assert all(value is False for value in handoff["mutations"].values())
    receipts = {
        level: load_json(GATE / f"verification/{level}.json")
        for level in ("l1", "l2", "l3")
    }
    if handoff["status"] == "ready":
        assert handoff["blocking_criteria"] == []
        assert handoff["release_readiness_blockers"] == []
        assert all(row["status"] == "pass" for row in rows.values())
        assert receipts["l1"]["verdict"] == "pass"
        assert receipts["l2"]["verdict"] == "accept"
        assert receipts["l3"]["verdict"] == "accept"
        assert handoff["current_after"]["gate_status"] == "ready"
    else:
        assert handoff["current_after"]["gate_status"] == "blocked"
        assert handoff["blocking_criteria"]
        for identifier in handoff["blocking_criteria"]:
            assert rows[identifier]["status"] in {"blocked", "pending"}
            assert rows[identifier]["reason_code"]
        if handoff["blocking_criteria"] == ["G0-19"]:
            assert handoff["release_readiness_blockers"] == []
            assert all(
                row["status"] == "pass"
                for identifier, row in rows.items()
                if identifier != "G0-19"
            )

def test_all_local_document_and_catalog_links_exist() -> None:
    product = load_json(GATE / "product/product-contract.json")
    for family in product["contract_families"]:
        assert (ROOT / family["source_ref"]).is_file()
    for entry in product["contract_catalog"]:
        assert (ROOT / entry["source_ref"]).is_file()
        golden, _, _fragment = entry["golden_ref"].partition("#")
        assert (GATE / golden).is_file()
    handoff = load_json(GATE / "fixtures/contracts/valid/gate-handoff.json")
    for key in (
        "product_contract_ref",
        "baseline_ref",
        "corpus_manifest_ref",
        "evidence_manifest_ref",
    ):
        assert (GATE / handoff[key]).is_file()


def test_bootstrap_builder_reproduces_normative_corpus() -> None:
    import normalize_gate0_contracts as legacy
    from generate_gate0_artifacts import build_corpus

    cases = [legacy.normalize_case(case) for case in build_corpus()]
    legacy.enhance_security(cases)
    for case in cases:
        if category(case) == "calendar" and case["expected"]["decision"] == "accept":
            case["expected"]["intent"]["period"] = {
                "start": "2030-01-09T21:00:00Z",
                "end": "2030-01-10T21:00:00Z",
                "timezone": "Europe/Moscow",
                "original_text": "10 января 2030 года",
                "inclusive_end": False,
            }
    cases.sort(key=lambda case: case["case_id"])
    assert b"".join(canonical_bytes(case) + b"\n" for case in cases) == CORPUS.read_bytes()


def test_current_fitness_checks_do_not_redefine_gate_contract_owners() -> None:
    gate2 = (ROOT / "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    gate5 = (
        ROOT / "docs/gates/gate-05-document-gateway-windows-bridge/ARCHITECTURE.md"
    ).read_text(encoding="utf-8")
    gate6 = (ROOT / "docs/gates/gate-06-multidocument-analytics/ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    assert "IntentEnvelope" in gate2 and "Gate 1" in gate2
    assert "DocumentSlice" in gate2
    assert "nobus.bridge.write.request.v2" in gate5
    assert "AnalysisRequest" in gate6 and "Gate 2" in gate6


def test_no_document_declares_false_gate0_ready_or_pass() -> None:
    machine = load_json(GATE / "fixtures/contracts/valid/gate-handoff.json")
    handoff = (GATE / "HANDOFF.md").read_text(encoding="utf-8")
    if machine["status"] == "ready":
        receipts = [
            load_json(GATE / f"verification/{level}.json")
            for level in ("l2", "l3")
        ]
        assert all(receipt["verdict"] == "accept" for receipt in receipts)
        assert "**Status:** `GATE 0 READY`" in handoff
    else:
        assert "**Status:** `GATE 0 BLOCKED`" in handoff
        assert "GATE 0 READY" not in handoff


def test_handoff_evidence_boundaries_use_observed_layer_commits() -> None:
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    handoff = (GATE / "HANDOFF.md").read_text(encoding="utf-8")
    expected = " ".join((
        f"- candidate repository is `{baseline['repository']['head_commit']}`, "
        "runtime release is "
        f"  `{baseline['runtime_release']['runtime_head_commit']}`, and design base is "
        f"`{DESIGN_BASE}`;"
    ).split())
    assert expected in " ".join(handoff.split())
    assert "| 2A | development intent" in handoff

def test_json_schema_required_arrays_are_unique() -> None:
    def verify(value: object, location: str) -> None:
        if isinstance(value, dict):
            required = value.get("required")
            if isinstance(required, list):
                assert len(required) == len(set(required)), location
            for key, child in value.items():
                verify(child, f"{location}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                verify(child, f"{location}/{index}")

    for path in sorted((GATE / "schemas").glob("*.json")):
        verify(load_json(path), path.name)


def test_gate_handoff_schema_requires_every_top_level_contract_field() -> None:
    schema = load_json(GATE / "schemas/gate-handoff.schema.json")
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_jsonschema_draft_202012_agreement() -> None:
    if importlib.util.find_spec("jsonschema") is None:
        pytest.skip("G0-14 BLOCKED: jsonschema absent; installation forbidden")
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

    schemas = {
        path.name: load_json(path) for path in sorted((GATE / "schemas").glob("*.json"))
    }
    assert set(schemas) == {
        "baseline-evidence.schema.json",
        "capability-claim.schema.json",
        "corpus-case.schema.json",
        "gate-handoff.schema.json",
        "product-contract.schema.json",
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)

    checker = FormatChecker()
    validators = {
        name: Draft202012Validator(schema, format_checker=checker)
        for name, schema in schemas.items()
    }
    validators["product-contract.schema.json"].validate(load_json(GATE / "product/product-contract.json"))
    for case in load_cases():
        validators["corpus-case.schema.json"].validate(case)
    baseline = load_json(GATE / "evidence/baseline-evidence.json")
    validators["baseline-evidence.schema.json"].validate(baseline)
    validators["gate-handoff.schema.json"].validate(load_json(GATE / "fixtures/contracts/valid/gate-handoff.json"))
    for claim in baseline["claims"]:
        validators["capability-claim.schema.json"].validate(claim)
    target_schema_bundle = load_json(
        GATE / "fixtures/golden/target-contract-schema-projections.json"
    )
    target_examples = load_json(
        GATE / "fixtures/golden/contract-examples.json"
    )["examples"]
    for name, schema in target_schema_bundle["schemas"].items():
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=checker).validate(
            target_examples[name]["instance"]
        )

    invalid_mapping = {
        "product-contract-unknown-field.json": "product-contract.schema.json",
        "corpus-case-unknown-enum.json": "corpus-case.schema.json",
        "corpus-case-unknown-field.json": "corpus-case.schema.json",
        "corpus-case-tenant-swap.json": "corpus-case.schema.json",
        "corpus-case-naive-datetime.json": "corpus-case.schema.json",
        "corpus-case-real-payload-flag.json": "corpus-case.schema.json",
        "baseline-bool-as-int.json": "baseline-evidence.schema.json",
        "baseline-naive-timestamp.json": "baseline-evidence.schema.json",
        "baseline-non-utc-timestamp.json": "baseline-evidence.schema.json",
        "capability-naive-timestamp.json": "capability-claim.schema.json",
        "capability-non-utc-timestamp.json": "capability-claim.schema.json",
        "gate-handoff-naive-timestamp.json": "gate-handoff.schema.json",
        "gate-handoff-non-utc-timestamp.json": "gate-handoff.schema.json",
    }
    for fixture, schema_name in invalid_mapping.items():
        with pytest.raises(JsonSchemaValidationError):
            validators[schema_name].validate(load_json(GATE / "fixtures/contracts/invalid" / fixture))

    standalone = copy.deepcopy(schemas["capability-claim.schema.json"])
    embedded = copy.deepcopy(
        schemas["baseline-evidence.schema.json"]["$defs"]["CapabilityClaim"]
    )
    for projection in (standalone, embedded):
        for metadata in ("$schema", "$id", "title", "$defs"):
            projection.pop(metadata, None)
    assert standalone == embedded


def test_hypothesis_reproducible_contract_properties() -> None:
    if importlib.util.find_spec("hypothesis") is None:
        pytest.skip("G0-15 BLOCKED: Hypothesis absent; installation forbidden")
    from hypothesis import given, seed, settings
    from hypothesis import strategies as st

    deterministic = settings(
        max_examples=48,
        derandomize=True,
        database=None,
        deadline=None,
    )

    @seed(20300728)
    @deterministic
    @given(st.dictionaries(st.text(min_size=1, max_size=12), st.one_of(st.none(), st.booleans(), st.integers()), max_size=12))
    def canonical_order_is_stable(value: dict[str, Any]) -> None:
        reversed_value = dict(reversed(list(value.items())))
        assert canonical_bytes(value) == canonical_bytes(reversed_value)
        assert sha256(canonical_bytes(value)) == sha256(canonical_bytes(reversed_value))

    known = set(load_cases()[0])

    @seed(20300728)
    @deterministic
    @given(st.from_regex(r"x_[a-z]{1,12}", fullmatch=True).filter(lambda value: value not in known))
    def unknown_top_level_fields_fail_closed(field_name: str) -> None:
        candidate = copy.deepcopy(load_cases()[0])
        candidate[field_name] = True
        with pytest.raises(ValidationError):
            CorpusCase.model_validate(candidate)

    @seed(20300728)
    @deterministic
    @given(st.sampled_from([("tenant-a", "tenant-b"), ("tenant-b", "tenant-a")]))
    def tenant_scope_swaps_fail_closed(binding: tuple[str, str]) -> None:
        tenant, other = binding
        candidate = copy.deepcopy(load_cases()[0])
        candidate["expected"]["intent"]["entities"]["tenant_ref"] = tenant
        candidate["expected"]["intent"]["entities"]["scope_ref"] = f"scope://{other}/synthetic"
        with pytest.raises(ValidationError):
            CorpusCase.model_validate(candidate)

    canonical_order_is_stable()
    unknown_top_level_fields_fail_closed()
    tenant_scope_swaps_fail_closed()


def test_architecture_fitness_matrix_has_six_enforced_rules() -> None:
    config = (ROOT / "tests/gate0/importlinter-gate0.ini").read_text(encoding="utf-8")
    assert config.count("[importlinter:contract:") == 4

    production_modules = (ROOT / "src").rglob("*.py")
    for path in production_modules:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name != "tests" and not alias.name.startswith("tests.")
                    for alias in node.names
                ), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module != "tests" and not node.module.startswith("tests."), path

    # The sixth rule is the always-on sanitized corpus/evidence scan.
    test_artifacts_contain_no_secret_pii_or_absolute_local_path_patterns()


def test_import_linter_architecture_contract() -> None:
    if importlib.util.find_spec("importlinter") is None:
        pytest.skip("G0-16 BLOCKED: Import Linter absent; installation forbidden")
    executable = shutil.which("lint-imports")
    if executable is None:
        candidate = pathlib.Path(sys.executable).with_name("lint-imports.exe")
        executable = str(candidate) if candidate.is_file() else None
    assert executable is not None, "Import Linter package exists but lint-imports entry point is missing"
    result = subprocess.run(
        [executable, "--config", str(ROOT / "tests/gate0/importlinter-gate0.ini")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
