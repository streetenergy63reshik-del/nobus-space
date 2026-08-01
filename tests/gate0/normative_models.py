"""Strict Pydantic mirrors of the normative Gate 0 machine contracts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)


DESIGN_BASE = "9d816b35d3f419b42e24ad09ae6aadc92c33db43"
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
COMMIT_PATTERN = r"^[0-9a-f]{40}$"
UTC_TIMESTAMP_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|\+00:00)$"
)
UtcTimestamp = Annotated[
    str, Field(pattern=UTC_TIMESTAMP_PATTERN, json_schema_extra={"format": "date-time"})
]
AwareTimestamp = UtcTimestamp

EvidenceStatus = Literal[
    "VERIFIED",
    "CONTRADICTORY",
    "STALE",
    "UNVERIFIABLE",
    "NOT_APPLICABLE",
    "NOT_CHECKED",
    "FAILED",
]
Domain = Literal[
    "notes",
    "calendar",
    "tasks",
    "documents",
    "research",
    "development",
    "general",
]
Action = Literal[
    "none",
    "answer",
    "help",
    "status",
    "limit",
    "cancel",
    "search",
    "read",
    "list",
    "summarize",
    "compare",
    "analyze",
    "audit",
    "report",
    "remember",
    "extract_tasks",
    "create",
    "update",
    "complete",
    "delete",
    "deliver",
    "commit",
    "deploy",
]
SourceKind = Literal[
    "none",
    "public_web",
    "nobus_memory",
    "business_notes",
    "google_calendar",
    "google_tasks",
    "google_drive",
    "local_library",
    "telegram_attachment",
    "registered_repository",
    "control_plane",
]
OutputFormat = Literal[
    "telegram_text",
    "jpeg",
    "html",
    "xlsx",
    "docx",
    "pdf",
    "google_doc",
    "google_sheet",
]
CorpusTag = Literal[
    "adversarial",
    "analysis",
    "authority_boundary",
    "analyze",
    "bridge_offline",
    "category.analytics_research_general",
    "category.business_notes",
    "category.development_miniapp_control",
    "category.calendar",
    "category.documents_google_local_lifecycle",
    "category.security_effect_tenant_provider_adversarial",
    "category.tasks",
    "category.voice_text_context_clarification",
    "clarification",
    "context",
    "create",
    "cross_client_denied",
    "cross_project_denied",
    "deliver",
    "gate2a",
    "delivery_unknown",
    "google",
    "half_open_time",
    "local",
    "money",
    "multi_turn",
    "negative",
    "opaque_doc_id",
    "path_traversal_denied",
    "positive",
    "prompt_injection_ignored",
    "provenance_safe_view",
    "provider_unknown",
    "read",
    "registry_denied",
    "reparse_point_denied",
    "replay_fenced",
    "safe_provenance",
    "search",
    "secret_path_denied",
    "security",
    "select",
    "specialist_worker",
    "share",
    "stale_revision_denied",
    "tenant_isolation",
    "text_pair",
    "third_party_delivery",
    "update",
    "version_or_deny",
    "voice_pair",
]

EffectKind = Literal[
    "read",
    "create",
    "update",
    "complete",
    "delete",
    "deliver_owner",
    "deliver_third_party",
    "publish",
    "change_access",
    "money",
    "push",
    "local_candidate_commit",
    "deploy",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def require_aware(value: str | None) -> str | None:
    if value is None:
        return value
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if (
        parsed.utcoffset() != dt.timedelta(0)
        or re.fullmatch(UTC_TIMESTAMP_PATTERN, value) is None
    ):
        raise ValueError("RFC 3339 UTC timestamp required")
    return value


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class CorpusTurn(ClosedModel):
    turn: StrictInt = Field(ge=1)
    speaker: Literal["owner", "system_context"]
    text: str = Field(min_length=1, max_length=1024)
    trusted_context_ref: str | None = Field(default=None, pattern=r"^context://synthetic/[a-z0-9._/-]+$")


class CorpusEntities(ClosedModel):
    tenant_ref: Literal["tenant-a", "tenant-b"]
    project_ref: str = Field(pattern=r"^project-[a-z0-9-]+$")
    client_ref: str | None = Field(default=None, pattern=r"^client-[a-z0-9-]+$")
    scope_ref: str | None = Field(
        default=None,
        pattern=r"^scope://tenant-(?:a|b)/[a-z0-9._/-]+$",
    )


class CorpusTimeRange(ClosedModel):
    start: AwareTimestamp | None
    end: AwareTimestamp | None
    timezone: Literal["Europe/Moscow"]
    original_text: str = Field(min_length=1, max_length=128)
    inclusive_end: StrictBool

    @field_validator("start", "end")
    @classmethod
    def timestamps_are_aware(cls, value: str | None) -> str | None:
        return require_aware(value)

    @model_validator(mode="after")
    def range_is_ordered(self) -> "CorpusTimeRange":
        if self.start is not None and self.end is not None:
            start = dt.datetime.fromisoformat(self.start.replace("Z", "+00:00"))
            end = dt.datetime.fromisoformat(self.end.replace("Z", "+00:00"))
            if start >= end:
                raise ValueError("time range must be half-open and ordered")
        return self


class CorpusIntent(ClosedModel):
    schema_value: Literal["nobus.intent.v1"] = Field(alias="schema")
    domain: Domain
    action: Action
    entities: CorpusEntities
    period: CorpusTimeRange | None
    source_scope: list[SourceKind]
    requested_outputs: list[OutputFormat]
    proposed_effects: list[EffectKind]
    ambiguity: Literal["none", "clarify", "reject"]


class CorpusEffect(ClosedModel):
    kind: EffectKind
    execution: Literal["forbidden", "proposed", "allowed_after_l4"]


class CorpusError(ClosedModel):
    code: str = Field(pattern=r"^[A-Z0-9_]+$")
    required: StrictBool


class CorpusExpected(ClosedModel):
    intent: CorpusIntent
    decision: Literal["accept", "clarify", "reject", "require_l4", "degraded"]
    effects: list[CorpusEffect]
    errors: list[CorpusError]
    user_message_profile: Literal["answer", "clarification", "denial", "preview", "status"]


class CorpusForbidden(ClosedModel):
    domains: list[Domain]
    actions: list[Action]
    effects: list[EffectKind]
    data_exposure: list[
        Literal["secret", "raw_path", "cross_tenant", "raw_prompt", "raw_document"]
    ]


class CorpusOwnership(ClosedModel):
    product_owner: str
    curator: str
    security_reviewer: str | None


class CorpusProvenance(ClosedModel):
    created_from: Literal[
        "canonical_requirement", "incident_pattern", "synthetic_boundary"
    ]
    source_refs: list[str] = Field(min_length=1)
    created_at: AwareTimestamp
    reviewed_at: AwareTimestamp

    @field_validator("created_at", "reviewed_at")
    @classmethod
    def timestamps_are_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class CorpusCase(ClosedModel):
    schema_value: Literal["nobus.gate0.corpus_case.v1"] = Field(alias="schema")
    corpus_version: Literal["2.0.0"]
    case_id: str = Field(pattern=r"^G0-[A-Z]+-[0-9]{3}$")
    status: Literal["active", "deprecated", "tombstone"]
    locale: Literal["ru-RU"]
    source_kind: Literal["synthetic", "sanitized_pattern"]
    modality: Literal["text", "voice_transcript"]
    pair_ref: str | None = Field(default=None, pattern=r"^G0-[A-Z]+-[0-9]{3}$")
    turns: list[CorpusTurn] = Field(min_length=1)
    expected: CorpusExpected
    forbidden: CorpusForbidden
    assertions: list[
        Literal["strict_intent", "tenant_bound", "deterministic_expected_output"]
    ]
    tags: list[CorpusTag]
    ownership: CorpusOwnership
    provenance: CorpusProvenance

    @model_validator(mode="after")
    def bindings_are_closed(self) -> "CorpusCase":
        tenant = self.expected.intent.entities.tenant_ref
        scope_ref = self.expected.intent.entities.scope_ref
        if scope_ref is not None and not scope_ref.startswith(f"scope://{tenant}/"):
            raise ValueError("tenant scope mismatch")
        if [turn.turn for turn in self.turns] != list(range(1, len(self.turns) + 1)):
            raise ValueError("turn numbers must be contiguous")
        if self.ownership.product_owner != "nobus_space_owner":
            raise ValueError("product owner mismatch")
        return self


class Vocabulary(ClosedModel):
    domains: list[str]
    actions: list[str]
    source_kinds: list[str]
    agent_roles: list[str]
    output_formats: list[str]
    effect_kinds: list[str]
    authorities: list[str]
    risks: list[str]


class Invariant(ClosedModel):
    id: str
    statement: str
    owner: str
    fitness_ref: str


class ContractFamily(ClosedModel):
    family: str
    owner_gate: StrictInt | Literal["2a"]
    contracts: list[str]
    status: Literal["current", "target"]
    source_ref: str
    consumer_gates: list[StrictInt | Literal["2a"]]


class NormativeInput(ClosedModel):
    catalog_ref: Literal[
        "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json"
    ]
    catalog_sha256: str = Field(pattern=DIGEST_PATTERN)
    source_count: StrictInt = Field(ge=1)
    source_set_sha256: str = Field(pattern=DIGEST_PATTERN)


class ContractCatalogEntry(ClosedModel):
    contract_name: str
    schema_id: str
    status: Literal["current", "target"]
    owner: str
    producer: str
    consumers: list[str]
    trust_boundary: str
    required_fields: list[str]
    closed_enum_refs: list[str]
    invariant_refs: list[str]
    golden_ref: str
    source_ref: str


class ChangeControl(ClosedModel):
    required_inputs: list[str]
    version_rule: str
    approval_rule: str
    corpus_rule: str


class ProductContract(ClosedModel):
    schema_value: Literal["nobus.gate0.product_contract.v1"] = Field(alias="schema")
    contract_version: Literal["2.0.0"]
    status: Literal["frozen_target"]
    frozen_at: AwareTimestamp
    owner: Literal["nobus_space_owner"]
    design_base_commit: Literal[DESIGN_BASE]
    normative_input: NormativeInput
    product_outcome: str
    non_goals: list[str]
    source_of_truth: list[str]
    product_principles: list[str]
    vocabularies: Vocabulary
    invariants: list[Invariant]
    contract_families: list[ContractFamily]
    contract_catalog: list[ContractCatalogEntry]
    change_control: ChangeControl

    @field_validator("frozen_at")
    @classmethod
    def frozen_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class EvidenceRef(ClosedModel):
    kind: Literal[
        "command_output",
        "json_report",
        "manifest",
        "git_object",
        "test_report",
        "database_check",
        "process_snapshot",
        "scheduler_snapshot",
        "external_receipt",
        "review",
    ]
    path_or_uri: str
    sha256: str = Field(pattern=DIGEST_PATTERN)
    media_type: str
    bytes: StrictInt = Field(ge=0)
    classification: Literal["public", "internal", "confidential"]
    created_at: AwareTimestamp

    @field_validator("created_at")
    @classmethod
    def created_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]

    @field_validator("path_or_uri")
    @classmethod
    def reference_is_not_absolute_path(cls, value: str) -> str:
        if re.match(r"(?i)^[a-z]:[\\/]", value):
            raise ValueError("absolute local path is forbidden")
        return value


class Capture(ClosedModel):
    started_at: AwareTimestamp
    completed_at: AwareTimestamp
    collector_identity: str
    host_ref: str
    policy_version: str
    method_version: str

    @field_validator("started_at", "completed_at")
    @classmethod
    def timestamps_are_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class DocumentBlob(ClosedModel):
    path: str
    git_blob: str = Field(pattern=COMMIT_PATTERN)
    sha256: str = Field(pattern=DIGEST_PATTERN)
    status: EvidenceStatus


class CurrentWorktreeDocument(ClosedModel):
    path: str
    sha256: str = Field(pattern=DIGEST_PATTERN)
    status: Literal["VERIFIED"]


class DocumentationEvidence(ClosedModel):
    canonical_commit: str = Field(pattern=COMMIT_PATTERN)
    head_commit: str = Field(pattern=COMMIT_PATTERN)
    head_matches_canonical: StrictBool
    required_documents: list[DocumentBlob]
    current_worktree_documents: list[CurrentWorktreeDocument]
    source_hierarchy_version: str = Field(pattern=COMMIT_PATTERN)
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class DirtyEntry(ClosedModel):
    path: str
    status: str
    tracked: StrictBool
    safe_content_sha256: str | None = Field(pattern=DIGEST_PATTERN)
    content_omitted_reason: (
        Literal[
            "secret_like",
            "binary",
            "unreadable",
            "not_needed",
            "covered_by_evidence_manifest",
        ]
        | None
    )
    owner: Literal["preexisting", "gate0"]


class DirtyState(ClosedModel):
    is_dirty: StrictBool
    entries: list[DirtyEntry]


class MergeBases(ClosedModel):
    docs_to_repo: str | None = Field(pattern=COMMIT_PATTERN)
    docs_to_runtime_release: str | None = Field(pattern=COMMIT_PATTERN)
    repo_to_runtime_release: str | None = Field(pattern=COMMIT_PATTERN)


class RepositoryEvidence(ClosedModel):
    repo_ref: str
    worktree_ref: str
    head_commit: str = Field(pattern=COMMIT_PATTERN)
    branch_or_detached: str
    upstream_ref: str | None
    merge_bases: MergeBases
    dirty: DirtyState
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class RuntimeReleaseEvidence(ClosedModel):
    runtime_worktree_ref: str
    runtime_head_commit: str = Field(pattern=COMMIT_PATTERN)
    runtime_branch_or_detached: str
    expected_feature_commit: str | None = Field(pattern=COMMIT_PATTERN)
    expected_feature_is_ancestor: StrictBool | None
    docs_commit_is_ancestor: StrictBool
    release_artifact_ref: EvidenceRef | None
    release_artifact_digest: str | None = Field(pattern=DIGEST_PATTERN)
    runtime_code_manifest_digest: str | None = Field(pattern=DIGEST_PATTERN)
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class ProcessInstance(ClosedModel):
    pid: StrictInt
    parent_pid: StrictInt | None
    started_at: AwareTimestamp
    executable_ref: str
    executable_sha256: str = Field(pattern=DIGEST_PATTERN)
    executable_version: str | None
    argv_profile: str
    argv_digest: str = Field(pattern=DIGEST_PATTERN)
    working_directory_ref: str
    identity_ref: str
    loaded_release_commit: str | None = Field(pattern=COMMIT_PATTERN)
    loaded_code_digest: str | None = Field(pattern=DIGEST_PATTERN)
    config_digest: str | None = Field(pattern=DIGEST_PATTERN)
    health: Literal["healthy", "degraded", "unhealthy", "unknown"]


class PollingCheckpoint(ClosedModel):
    observed_at: AwareTimestamp | None
    age_seconds: StrictInt | None
    source_ref: EvidenceRef | None

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str | None) -> str | None:
        return require_aware(value)


class ProcessEvidence(ClosedModel):
    process_role: Literal["telegram_runner", "codex_app_server", "bridge", "helper"]
    expected_count: StrictInt = Field(ge=0)
    observed_count: StrictInt = Field(ge=0)
    instances: list[ProcessInstance]
    polling_checkpoint: PollingCheckpoint
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class CountProfile(ClosedModel):
    count: StrictInt = Field(ge=0)


class ModeProfile(ClosedModel):
    mode: str


class SchedulerEvidence(ClosedModel):
    scheduler_kind: Literal["windows_task_scheduler", "systemd", "other"]
    task_ref: str
    enabled: StrictBool
    state: Literal["ready", "running", "disabled", "unknown"]
    action_executable_ref: str
    action_executable_digest: str = Field(pattern=DIGEST_PATTERN)
    action_arguments_profile: str
    action_arguments_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)] | None
    working_directory_ref: str
    principal_ref: str
    trigger_profile: CountProfile
    restart_policy_profile: ModeProfile
    last_run_at: AwareTimestamp | None
    last_result_code: StrictInt | None
    next_run_at: AwareTimestamp | None
    definition_changed_at: AwareTimestamp | None
    definition_digest: str = Field(pattern=DIGEST_PATTERN)
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator(
        "last_run_at", "next_run_at", "definition_changed_at", "observed_at"
    )
    @classmethod
    def timestamps_are_aware(cls, value: str | None) -> str | None:
        return require_aware(value)


class MigrationInventory(ClosedModel):
    applied: list[str]
    pending: list[str]
    unknown: list[str]


class DatabaseIntegrity(ClosedModel):
    quick_check: Literal["ok", "failed", "not_checked"]
    foreign_key_check: Literal["ok", "failed", "not_applicable", "not_checked"]


class StateAggregates(ClosedModel):
    pending: StrictInt | None
    in_progress: StrictInt | None
    waiting_human: StrictInt | None
    failed: StrictInt | None
    dead_letters: StrictInt | None
    orphaned_leases: StrictInt | None
    unreconciled_effects: StrictInt | None
    undelivered_outbox: StrictInt | None


class DatabaseEvidence(ClosedModel):
    database_role: Literal[
        "core", "telegram_state", "product_effects", "checkpoint", "legacy"
    ]
    database_ref: str
    source_profile: str
    runtime_binding_status: EvidenceStatus
    runtime_binding_reason: str
    engine: Literal["sqlite"]
    file_identity_digest: str = Field(pattern=DIGEST_PATTERN)
    size_bytes: StrictInt = Field(ge=0)
    modified_at: AwareTimestamp
    journal_mode: Literal[
        "delete", "wal", "truncate", "persist", "memory", "off", "unknown"
    ]
    user_version: StrictInt
    application_id: StrictInt
    schema_digest: str = Field(pattern=DIGEST_PATTERN)
    migration_inventory: MigrationInventory
    integrity: DatabaseIntegrity
    state_aggregates: StateAggregates
    content_exported: Literal[False]
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("modified_at", "observed_at")
    @classmethod
    def timestamps_are_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class SecretStore(ClosedModel):
    provider: Literal[
        "windows_credential_manager", "environment_ref", "vault", "other"
    ]
    required_refs_present: StrictBool | None
    values_read: Literal[False]


class RegistryEvidence(ClosedModel):
    schema_version: str | None
    digest: str | None = Field(pattern=DIGEST_PATTERN)
    entries_count: StrictInt | None


class Registries(ClosedModel):
    source: RegistryEvidence
    output: RegistryEvidence
    deny: RegistryEvidence
    google_folders: RegistryEvidence


class ConfigurationEvidence(ClosedModel):
    config_schema_version: str
    active_profile: str
    safe_config_digest: str = Field(pattern=DIGEST_PATTERN)
    secret_store: SecretStore
    registries: Registries
    policy_digest: str = Field(pattern=DIGEST_PATTERN)
    model_profile_digest: str = Field(pattern=DIGEST_PATTERN)
    config_sources: list[str]
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class OSEvidence(ClosedModel):
    family: Literal["windows", "linux"]
    version: str
    architecture: str


class PythonEvidence(ClosedModel):
    implementation: str
    version: str
    executable_digest: str = Field(pattern=DIGEST_PATTERN)


class PipEvidence(ClosedModel):
    version: str
    inspect_schema_version: str
    inspect_report_ref: EvidenceRef
    inspect_report_digest: str = Field(pattern=DIGEST_PATTERN)


class RequirementFile(ClosedModel):
    path: str
    sha256: str = Field(pattern=DIGEST_PATTERN)


class RequirementsEvidence(ClosedModel):
    files: list[RequirementFile]
    fully_pinned: StrictBool


class PipCheckEvidence(ClosedModel):
    status: Literal["passed", "failed", "not_run"]


class ExternalToolEvidence(ClosedModel):
    name: str
    version: str
    executable_digest: str | None = Field(pattern=DIGEST_PATTERN)


class VulnerabilityReport(ClosedModel):
    tool: Literal["pip-audit"]
    version: str
    database_observed_at: AwareTimestamp
    status: Literal["passed", "findings", "unavailable", "not_run"]
    report_ref: EvidenceRef | None

    @field_validator("database_observed_at")
    @classmethod
    def timestamp_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class DependencyEvidence(ClosedModel):
    os: OSEvidence
    python: PythonEvidence
    pip: PipEvidence
    requirements: RequirementsEvidence
    pip_check: PipCheckEvidence
    external_tools: list[ExternalToolEvidence]
    vulnerability_report: VulnerabilityReport
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class TestCollection(ClosedModel):
    files: StrictInt = Field(ge=0)
    collected_cases: StrictInt = Field(ge=0)
    collection_report_ref: EvidenceRef


class TestRun(ClosedModel):
    profile: Literal[
        "gate0_docs",
        "gate0_contracts",
        "full_regression",
        "property",
        "architecture",
        "release_security",
    ]
    command_profile: str
    started_at: AwareTimestamp
    finished_at: AwareTimestamp
    exit_code: StrictInt
    passed: StrictInt | None
    failed: StrictInt | None
    skipped: StrictInt | None
    warnings: StrictInt | None
    seed: str | None
    report_ref: EvidenceRef
    report_digest: str = Field(pattern=DIGEST_PATTERN)

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_are_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class CurrentBaselineScore(ClosedModel):
    corpus_version: str
    corpus_digest: str = Field(pattern=DIGEST_PATTERN)
    report_ref: EvidenceRef
    pass_rate: StrictFloat | None


class BaselineScores(ClosedModel):
    current_system: CurrentBaselineScore


class TestEvidence(ClosedModel):
    test_contract_version: str
    commit_under_test: str = Field(pattern=COMMIT_PATTERN)
    environment_digest: str = Field(pattern=DIGEST_PATTERN)
    collection: TestCollection
    runs: list[TestRun]
    baseline_scores: BaselineScores
    status: EvidenceStatus
    observed_at: AwareTimestamp
    evidence_refs: list[EvidenceRef]

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: str) -> str:
        return require_aware(value)  # type: ignore[return-value]


class ExternalCapabilityEvidence(ClosedModel):
    capability: Literal[
        "telegram_polling",
        "codex_sdk",
        "web_search",
        "google_calendar",
        "google_tasks",
        "google_drive",
        "google_docs",
        "google_sheets",
        "local_owner_files",
        "local_library_bridge_read_v1",
        "local_library_bridge_write_v2",
    ]
    implementation_status: Literal["current", "partial", "target", "deferred"]
    verification_status: Literal[
        "verified_live",
        "verified_fake",
        "configured_not_called",
        "unavailable",
        "not_checked",
        "unverifiable",
    ]
    mode: Literal["read_only", "fake", "metadata_only", "not_applicable"]
    provider_or_adapter_version: str | None
    last_success_at: AwareTimestamp | None
    fresh_evidence_at: AwareTimestamp | None
    safe_summary: str
    limitations: list[str]
    status: EvidenceStatus
    evidence_refs: list[EvidenceRef]

    @field_validator("last_success_at", "fresh_evidence_at")
    @classmethod
    def timestamps_are_aware(cls, value: str | None) -> str | None:
        return require_aware(value)


class CapabilityClaim(ClosedModel):
    claim_id: str
    capability: str
    implementation_status: Literal["CURRENT", "PARTIAL", "TARGET", "DEFERRED"]
    statement: str
    requires_layers: list[str]
    evidence_refs: list[EvidenceRef]
    contradictions: list[EvidenceRef]
    fresh_until: AwareTimestamp | None
    verdict: Literal["VERIFIED", "CONTRADICTORY", "STALE", "UNVERIFIABLE"]

    @field_validator("fresh_until")
    @classmethod
    def fresh_until_is_aware(cls, value: str | None) -> str | None:
        return require_aware(value)

    @model_validator(mode="after")
    def current_requires_verified_evidence(self) -> "CapabilityClaim":
        if self.implementation_status == "CURRENT" and self.verdict != "VERIFIED":
            raise ValueError("CURRENT claim requires VERIFIED evidence")
        return self


class SafeLimitation(ClosedModel):
    code: str
    status: EvidenceStatus
    blocking_criteria: list[str]
    statement: str
    evidence_refs: list[EvidenceRef]


class BaselineEvidence(ClosedModel):
    schema_value: Literal["nobus.gate0.baseline.v1"] = Field(alias="schema")
    baseline_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )

    @field_validator("baseline_id")
    @classmethod
    def baseline_id_is_not_placeholder(cls, value: str) -> str:
        if value == "00000000-0000-4000-8000-000000000000":
            raise ValueError("baseline_id must identify this evidence capture")
        return value
    gate: StrictInt
    scope: Literal["nobus-space-mvp1"]
    capture: Capture
    documentation: DocumentationEvidence
    repository: RepositoryEvidence
    runtime_release: RuntimeReleaseEvidence
    processes: list[ProcessEvidence]
    scheduler: list[SchedulerEvidence]
    databases: list[DatabaseEvidence]
    configuration: ConfigurationEvidence
    dependencies: DependencyEvidence
    tests: TestEvidence
    external_capabilities: list[ExternalCapabilityEvidence]
    claims: list[CapabilityClaim]
    limitations: list[SafeLimitation]
    evidence_manifest_ref: EvidenceRef
    baseline_digest: str = Field(pattern=DIGEST_PATTERN)

    @model_validator(mode="after")
    def invariants_hold(self) -> "BaselineEvidence":
        if self.gate != 0:
            raise ValueError("gate must be integer zero")
        if self.documentation.canonical_commit != DESIGN_BASE:
            raise ValueError("documentation base mismatch")
        if self.documentation.head_commit != self.repository.head_commit:
            raise ValueError("repository layer mismatch")
        projection = self.model_dump(by_alias=True, mode="json")
        expected = projection.pop("baseline_digest")
        if expected != digest_bytes(canonical_bytes(projection)):
            raise ValueError("baseline digest mismatch")
        return self
