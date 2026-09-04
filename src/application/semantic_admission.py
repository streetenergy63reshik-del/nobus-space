"""Modality-neutral semantic admission before the existing Core boundary."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest


SCHEMA_VERSION = "1.0.0"
SEMANTIC_SCHEMA_SHA256 = (
    "f09457922593bb82bc200cddaa6c6602295df3462627a5b101f0cab5e9115e87"
)
CAPABILITY_REGISTRY_SHA256 = (
    "cabd76d4804474af73373c51cc5a7d361ff5c6d368aee365ffe6cbaa992a4161"
)
_CONTRACT_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "gates"
    / "gate-c0-mvp1-truth-contract"
)
_SCHEMA_PATH = _CONTRACT_DIR / "semantic-contract.schema.json"
_REGISTRY_PATH = _CONTRACT_DIR / "capability-registry.v1.json"
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_MATERIAL_PATTERN = r"^material://(?:intake|artifact|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}$"
_TARGET_PATTERN = r"^(?:material|target)://(?:intake|artifact|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}$"
_CONTEXT_PATTERN = r"^context://(?:intake|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}$"
_INTAKE_PATTERN = r"^intake://(?:telegram|miniapp|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}$"
_SPAN_PATTERN = r"^span://(?:intake|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}$"
_CAPABILITY_PATTERN = r"^[a-z][a-z0-9_.-]{2,95}$"
_REASON_PATTERN = r"^[A-Z][A-Z0-9_]{2,95}$"
_MESSAGE_KEY_PATTERN = r"^[a-z][a-z0-9_.-]{2,95}$"
_EXPLICIT_MATERIAL_BLOCK = re.compile(
    r"\bначало\s+(?:материала|текста|команды)\b.*?"
    r"(?:\bконец\s+(?:материала|текста|команды)\b|\Z)",
    re.I | re.S,
)
_BLOCKQUOTE_INPUT = re.compile(r"(?m)^[ \t]*>[^\r\n]*(?:\r?\n|\Z)")
_MENTIONED_CONTEXT_BOUNDARY = re.compile(
    r"\b(?:коллега|автор|пользователь|"
    r"в\s+(?:материале|тексте|примере))\b[^.!?\r\n]{0,160}"
    r"\b(?:просил|попросил|предлагал|написал|содержит|"
    r"перечислен\w*)\b",
    re.I,
)
_TAIL_MATERIAL_BOUNDARY = re.compile(
    r"\b(?:материал|текст|образец|цитат[ау]|команд[ау])\s+"
    r"(?:ниже|далее|следующ\w*)\b|"
    r"\bследующ\w*\s+(?:материал|текст|команд\w*)\b",
    re.I,
)
_COLON_MATERIAL_BOUNDARY = re.compile(
    r"\b(?:материал|текст|образец|цитат[ау]|фраз[ау]|команд[ау])\s*:",
    re.I,
)
_CONDITION_TOKEN = re.compile(r"[0-9A-Za-zА-Яа-яЁё-]+")
_SUPPORTED_CONDITION_TOKENS = frozenset(
    {
        "если",
        "в",
        "предоставленном",
        "обезличенном",
        "текущем",
        "списке",
        "есть",
        "хотя",
        "бы",
        "просроченный",
        "просроченные",
        "пункт",
        "пункты",
    }
)
_MAX_TEXT_SPANS = 24
_MAX_DIRECT_SPAN_COMPILATIONS = 8


class SemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceMaterialRef(SemanticModel):
    ref: str = Field(pattern=_MATERIAL_PATTERN)
    boundary: Literal["full_material", "quoted_fragment", "summary_only"]


class PredicateArguments(SemanticModel):
    item_state: Literal["overdue"]


class Predicate(SemanticModel):
    kind: Literal["material_item_state_exists"]
    subject_ref: str = Field(pattern=_MATERIAL_PATTERN)
    arguments: PredicateArguments


class Operation(SemanticModel):
    operation_kind: Literal[
        "respond",
        "transform_material",
        "cancel_task",
        "read_public_information",
        "create_file",
        "write_calendar_event",
        "disclose_secret",
        "write_marketplace_campaign",
    ]
    role: Literal["requested", "quoted", "mentioned_only", "negated", "conditional"]
    target_ref: str | None = Field(pattern=_TARGET_PATTERN)
    predicate: Predicate | None

    @model_validator(mode="after")
    def validate_predicate_role(self) -> "Operation":
        if (self.role == "conditional") is not (self.predicate is not None):
            raise ValueError("only conditional operations have a predicate")
        return self


class SemanticProposal(SemanticModel):
    schema_version: Literal["1.0.0"]
    interpretation_state: Literal["understood", "ambiguous"]
    primary_goal: str = Field(min_length=1, max_length=2048)
    deliverables: tuple[str, ...] = Field(min_length=1, max_length=12)
    constraints: tuple[str, ...] = Field(max_length=24)
    source_material_refs: tuple[SourceMaterialRef, ...] = Field(max_length=12)
    input_role: Literal["direct_request", "material_transformation", "question", "mixed"]
    source_need: Literal["none", "provided_material", "external_read", "clarification"]
    output_kind: Literal["answer", "prompt", "document", "data", "action", "status", "artifact", "none"]
    operations: tuple[Operation, ...] = Field(min_length=1, max_length=24)
    ambiguities: tuple[str, ...] = Field(max_length=8)
    clarification_question: str | None = Field(min_length=1, max_length=512)

    @field_validator("deliverables", "constraints", "ambiguities")
    @classmethod
    def validate_unique_text(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or len(value) > 2048 for value in values):
            raise ValueError("semantic text item is invalid")
        if len(values) != len(set(values)):
            raise ValueError("semantic text items must be unique")
        return values

    @field_validator("source_material_refs")
    @classmethod
    def validate_unique_materials(
        cls, values: tuple[SourceMaterialRef, ...]
    ) -> tuple[SourceMaterialRef, ...]:
        if len(values) != len({value.ref for value in values}):
            raise ValueError("source material refs must be unique across boundaries")
        return values

    @model_validator(mode="after")
    def validate_interpretation(self) -> "SemanticProposal":
        understood = self.interpretation_state == "understood"
        if understood and (self.ambiguities or self.clarification_question is not None):
            raise ValueError("understood proposal cannot request clarification")
        if not understood and (not self.ambiguities or self.clarification_question is None):
            raise ValueError("ambiguous proposal must request clarification")
        if sum(operation.role == "conditional" for operation in self.operations) > 1:
            raise ValueError("only one conditional operation is supported")
        return self


class OperationProvenance(SemanticModel):
    operation_index: int = Field(ge=0, le=23)
    span_ref: str = Field(pattern=_SPAN_PATTERN)
    trusted_origin: Literal[
        "DIRECT_OWNER_COMMAND",
        "PROVIDED_MATERIAL",
        "QUOTED_MATERIAL",
        "NESTED_MATERIAL",
        "MENTIONED_CONTEXT",
    ]
    authority_scope: Literal["OWNER_REQUESTED", "OWNER_CONDITIONAL", "INERT"]


class TrustedReferenceBinding(SemanticModel):
    """Server ledger fact for one opaque source, target or predicate ref."""

    ref: str = Field(pattern=_TARGET_PATTERN)
    trusted_boundary: Literal[
        "full_material", "quoted_fragment", "summary_only", "operation_target"
    ]
    issued_by_server: StrictBool
    current_intake_member: StrictBool
    owner_binding: str = Field(pattern=_DIGEST_PATTERN)
    tenant_binding: str = Field(pattern=_DIGEST_PATTERN)
    conversation_binding: str = Field(pattern=_DIGEST_PATTERN)
    intake_ref: str = Field(pattern=_INTAKE_PATTERN)
    intake_revision: int = Field(ge=1)


class TrustedOperationBinding(SemanticModel):
    """Server provenance fact; intentionally contains no model role."""

    operation_index: int = Field(ge=0, le=23)
    operation_kind: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    proposal_digest: str = Field(pattern=_DIGEST_PATTERN)
    span_ref: str = Field(pattern=_SPAN_PATTERN)
    owner_binding: str = Field(pattern=_DIGEST_PATTERN)
    tenant_binding: str = Field(pattern=_DIGEST_PATTERN)
    conversation_binding: str = Field(pattern=_DIGEST_PATTERN)
    intake_ref: str = Field(pattern=_INTAKE_PATTERN)
    intake_revision: int = Field(ge=1)
    trusted_origin: Literal[
        "DIRECT_OWNER_COMMAND",
        "PROVIDED_MATERIAL",
        "QUOTED_MATERIAL",
        "NESTED_MATERIAL",
        "MENTIONED_CONTEXT",
    ]
    authority_scope: Literal["OWNER_REQUESTED", "OWNER_CONDITIONAL", "INERT"]


class TrustedTextSpanBinding(SemanticModel):
    """Exact server-issued owner/material span; raw text stays in the intake."""

    span_ref: str = Field(pattern=_SPAN_PATTERN)
    start: int = Field(ge=0, le=16_000)
    end: int = Field(gt=0, le=16_000)
    content_digest: str = Field(pattern=_DIGEST_PATTERN)
    owner_binding: str = Field(pattern=_DIGEST_PATTERN)
    tenant_binding: str = Field(pattern=_DIGEST_PATTERN)
    conversation_binding: str = Field(pattern=_DIGEST_PATTERN)
    intake_ref: str = Field(pattern=_INTAKE_PATTERN)
    intake_revision: int = Field(ge=1)
    trusted_origin: Literal[
        "DIRECT_OWNER_COMMAND",
        "PROVIDED_MATERIAL",
        "QUOTED_MATERIAL",
        "NESTED_MATERIAL",
        "MENTIONED_CONTEXT",
    ]

    @model_validator(mode="after")
    def validate_range(self) -> "TrustedTextSpanBinding":
        if self.end <= self.start:
            raise ValueError("trusted text span range is invalid")
        return self


class ReferenceCheck(SemanticModel):
    ref: str = Field(pattern=_TARGET_PATTERN)
    usages: tuple[
        Literal["SOURCE_MATERIAL", "OPERATION_TARGET", "PREDICATE_SUBJECT"], ...
    ] = Field(min_length=1, max_length=3)
    trusted_boundary: Literal[
        "full_material", "quoted_fragment", "summary_only", "operation_target"
    ]
    status: Literal[
        "VERIFIED",
        "WRONG_OWNER",
        "WRONG_TENANT",
        "WRONG_CONVERSATION",
        "NOT_IN_CURRENT_INTAKE",
        "BOUNDARY_MISMATCH",
        "FORGED_REF",
        "STALE_REF",
    ]

    @field_validator("usages")
    @classmethod
    def validate_unique_usages(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("reference usages must be unique")
        return values


class PredicateEvaluation(SemanticModel):
    outcome: Literal["NOT_APPLICABLE", "TRUE", "FALSE", "UNKNOWN"]
    evaluator: Literal["NONE", "MATERIAL_ITEM_STATE_V1"]
    subject_ref: str | None = Field(default=None, pattern=_MATERIAL_PATTERN)

    @model_validator(mode="after")
    def validate_evaluator(self) -> "PredicateEvaluation":
        not_applicable = self.outcome == "NOT_APPLICABLE"
        if not_applicable and (self.evaluator != "NONE" or self.subject_ref is not None):
            raise ValueError("non-applicable predicate must use NONE")
        if not not_applicable and (
            self.evaluator != "MATERIAL_ITEM_STATE_V1" or self.subject_ref is None
        ):
            raise ValueError("predicate outcome requires the v1 evaluator")
        return self


class TrustedAdmissionContext(SemanticModel):
    schema_version: Literal["1.0.0"]
    context_ref: str = Field(pattern=_CONTEXT_PATTERN)
    intake_ref: str = Field(pattern=_INTAKE_PATTERN)
    intake_revision: int = Field(ge=1)
    owner_binding: str = Field(pattern=_DIGEST_PATTERN)
    tenant_binding: str = Field(pattern=_DIGEST_PATTERN)
    conversation_binding: str = Field(pattern=_DIGEST_PATTERN)
    reference_validation: Literal[
        "VERIFIED",
        "WRONG_OWNER",
        "WRONG_TENANT",
        "WRONG_CONVERSATION",
        "NOT_IN_CURRENT_INTAKE",
        "BOUNDARY_MISMATCH",
        "FORGED_REF",
        "STALE_REF",
    ]
    operation_provenance: tuple[OperationProvenance, ...] = Field(
        min_length=1, max_length=24
    )
    reference_checks: tuple[ReferenceCheck, ...] = Field(max_length=36)
    predicate_evaluation: PredicateEvaluation


class PolicyEvidence(SemanticModel):
    kind: Literal[
        "proposal_schema",
        "registry",
        "policy",
        "predicate",
        "owner_binding",
        "admission_context",
        "predicate_result",
    ]
    ref: str = Field(min_length=1, max_length=512, pattern=r"^[a-z][a-z0-9+.-]*://[^\s]+$")


class UserVisibleState(SemanticModel):
    state: Literal[
        "accepted",
        "needs_clarification",
        "approval_required",
        "unavailable",
        "refused",
        "condition_not_met",
        "condition_unknown",
    ]
    message_key: str = Field(pattern=_MESSAGE_KEY_PATTERN)


class CoreDecision(SemanticModel):
    schema_version: Literal["1.0.0"]
    proposal_digest: str = Field(pattern=_DIGEST_PATTERN)
    admission_context_digest: str = Field(pattern=_DIGEST_PATTERN)
    decision: Literal["EXECUTE", "CLARIFY", "APPROVAL", "UNAVAILABLE", "REFUSE"]
    decision_stage: Literal[
        "TRUST_VIOLATION",
        "POLICY_PROHIBITED",
        "AMBIGUITY",
        "HETEROGENEOUS_CAPABILITIES",
        "IMPLEMENTATION_STATE",
        "PREDICATE_FALSE",
        "PREDICATE_UNKNOWN",
        "APPROVAL_REQUIRED",
        "EXECUTE_ALLOWED",
    ]
    predicate_outcome: Literal["NOT_APPLICABLE", "TRUE", "FALSE", "UNKNOWN"]
    selected_capability: str | None = Field(default=None, pattern=_CAPABILITY_PATTERN)
    policy_reason_code: str = Field(pattern=_REASON_PATTERN)
    policy_evidence: tuple[PolicyEvidence, ...] = Field(min_length=1, max_length=16)
    user_visible_state: UserVisibleState
    task_contract_allowed: StrictBool
    effect_allowed: StrictBool


class CanonicalMaterial(SemanticModel):
    ref: str = Field(pattern=_MATERIAL_PATTERN)
    boundary: Literal["full_material", "quoted_fragment", "summary_only"]


class CanonicalSemanticInput(SemanticModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    modality: Literal["text", "voice_transcript", "miniapp_text"]
    locale: str = Field(min_length=2, max_length=16, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    owner_text: str = Field(min_length=1, max_length=16_000)
    materials: tuple[CanonicalMaterial, ...] = Field(max_length=12)

    def model_input(self) -> dict[str, object]:
        """Return content only; identity and authority bindings never reach the model."""
        return self.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class AdmissionBindings:
    intake_ref: str
    intake_revision: int
    owner_binding: str
    tenant_binding: str
    conversation_binding: str
    materials: tuple[CanonicalMaterial, ...]
    material_item_states: Mapping[str, frozenset[str]]
    reference_bindings: tuple[TrustedReferenceBinding, ...] = ()
    operation_bindings: tuple[TrustedOperationBinding, ...] = ()
    text_span_bindings: tuple[TrustedTextSpanBinding, ...] = ()
    conditional_structure: Literal[
        "UNASSESSED", "NONE", "SUPPORTED", "UNSUPPORTED"
    ] = "UNASSESSED"
    context_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticAdmission:
    canonical_input: CanonicalSemanticInput
    proposal: SemanticProposal
    context: TrustedAdmissionContext
    decision: CoreDecision


class SemanticAdmissionError(RuntimeError):
    """Safe compiler failure code without owner content or provider details."""

    def __init__(self, code: str, *, provider_code: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.provider_code = provider_code


class SemanticClarificationRequired(RuntimeError):
    """Safe Mini App response carrying one question and an opaque reply token."""

    def __init__(self, question: str, token: str) -> None:
        super().__init__("semantic_clarification_required")
        self.question = question
        self.token = token


class SemanticClarificationRejected(RuntimeError):
    """A supplied clarification token did not bind to current pending state."""


class PendingClarification(SemanticModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    owner_binding: str = Field(pattern=_DIGEST_PATTERN)
    tenant_binding: str = Field(pattern=_DIGEST_PATTERN)
    conversation_binding: str = Field(pattern=_DIGEST_PATTERN)
    intake_ref: str = Field(pattern=_INTAKE_PATTERN)
    intake_revision: int = Field(ge=1)
    envelope_revision: str = Field(pattern=_DIGEST_PATTERN)
    answer_binding: str = Field(pattern=_DIGEST_PATTERN)
    canonical_input: CanonicalSemanticInput
    proposal_digest: str = Field(pattern=_DIGEST_PATTERN)
    clarification_question: str = Field(min_length=1, max_length=512)
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_expiry(self) -> "PendingClarification":
        if (
            self.issued_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.issued_at
            or self.expires_at - self.issued_at > timedelta(minutes=30)
        ):
            raise ValueError("clarification expiry is invalid")
        return self


class SemanticClarificationStore(Protocol):
    def put(self, pending: PendingClarification) -> None: ...

    def read(
        self,
        *,
        owner_binding: str,
        tenant_binding: str,
        conversation_binding: str,
        answer_binding: str,
        reply_envelope_revision: str,
    ) -> PendingClarification | None: ...

    def delete(self, pending: PendingClarification) -> bool: ...


class InMemorySemanticClarificationStore:
    """Bounded test/local state; production uses encrypted SQLite."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if not timedelta(seconds=1) <= ttl <= timedelta(minutes=30):
            raise ValueError("clarification TTL is invalid")
        self._clock = clock
        self._ttl = ttl
        self._entries: dict[str, PendingClarification] = {}
        self._lock = RLock()

    @property
    def ttl(self) -> timedelta:
        return self._ttl

    def put(self, pending: PendingClarification) -> None:
        if not isinstance(pending, PendingClarification):
            raise ValueError("pending clarification is invalid")
        with self._lock:
            self._sweep()
            self._entries[pending.conversation_binding] = pending

    def read(
        self,
        *,
        owner_binding: str,
        tenant_binding: str,
        conversation_binding: str,
        answer_binding: str,
        reply_envelope_revision: str,
    ) -> PendingClarification | None:
        with self._lock:
            self._sweep()
            pending = self._entries.get(conversation_binding)
            if pending is None:
                return None
            if (
                pending.owner_binding != owner_binding
                or pending.tenant_binding != tenant_binding
                or pending.conversation_binding != conversation_binding
                or pending.answer_binding != answer_binding
                or pending.envelope_revision == reply_envelope_revision
            ):
                return None
            return pending

    def delete(self, pending: PendingClarification) -> bool:
        if not isinstance(pending, PendingClarification):
            return False
        with self._lock:
            current = self._entries.get(pending.conversation_binding)
            if current != pending:
                return False
            del self._entries[pending.conversation_binding]
            return True

    def _sweep(self) -> None:
        now = self._clock().astimezone(UTC)
        for key, value in tuple(self._entries.items()):
            if value.expires_at <= now:
                del self._entries[key]


def pending_clarification(
    admission: SemanticAdmission,
    envelope: TrustedIngressEnvelope,
    *,
    now: datetime,
    ttl: timedelta,
    answer_binding: str,
) -> PendingClarification:
    question = semantic_clarification_question(admission)
    return PendingClarification(
        owner_binding=admission.context.owner_binding,
        tenant_binding=admission.context.tenant_binding,
        conversation_binding=admission.context.conversation_binding,
        intake_ref=admission.context.intake_ref,
        intake_revision=admission.context.intake_revision,
        envelope_revision=envelope.envelope_revision,
        answer_binding=answer_binding,
        canonical_input=admission.canonical_input,
        proposal_digest=admission.decision.proposal_digest,
        clarification_question=question,
        issued_at=now.astimezone(UTC),
        expires_at=(now + ttl).astimezone(UTC),
    )


def semantic_clarification_question(admission: SemanticAdmission) -> str:
    """Return one concrete question for both ambiguity and typed UNKNOWN."""
    if admission.proposal.clarification_question is not None:
        return admission.proposal.clarification_question
    if admission.decision.decision_stage == "PREDICATE_UNKNOWN":
        return (
            "Есть ли в текущем предоставленном списке хотя бы один "
            "просроченный пункт?"
        )
    return "Что именно нужно уточнить в задаче?"


class SemanticCompiler(Protocol):
    async def compile_semantic(
        self,
        model_input: Mapping[str, object],
        output_schema: Mapping[str, object],
        *,
        timeout_seconds: int,
    ) -> str | Mapping[str, object]: ...

@dataclass(frozen=True, slots=True)
class _Capability:
    id: str
    operations: frozenset[str]
    implementation_state: str
    policy_state: str
    effect_type: str
    approval_requirement: str


def _read_bound_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        canonical = raw.replace(b"\r\n", b"\n")
        if hashlib.sha256(canonical).hexdigest() != expected_sha256:
            raise RuntimeError("semantic contract digest mismatch")
        value = json.loads(canonical, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise RuntimeError("semantic contract unavailable") from None
    if not isinstance(value, dict):
        raise RuntimeError("semantic contract invalid")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class SemanticContract:
    """Load the exact accepted C0 schema and registry; neither is model-owned."""

    def __init__(self) -> None:
        schema = _read_bound_json(_SCHEMA_PATH, SEMANTIC_SCHEMA_SHA256)
        registry = _read_bound_json(_REGISTRY_PATH, CAPABILITY_REGISTRY_SHA256)
        if (
            schema.get("$id")
            != "https://nobusspace.local/contracts/semantic-admission/1.0.0"
            or registry.get("registry_version") != SCHEMA_VERSION
            or registry.get("decision_order")
            != [
                "TRUST_VIOLATION",
                "POLICY_PROHIBITED",
                "AMBIGUITY",
                "HETEROGENEOUS_CAPABILITIES",
                "IMPLEMENTATION_STATE",
                "APPROVAL_REQUIRED",
                "EXECUTE_ALLOWED",
            ]
        ):
            raise RuntimeError("semantic contract binding mismatch")
        definitions = schema.get("$defs")
        if not isinstance(definitions, dict) or "SemanticProposal" not in definitions:
            raise RuntimeError("semantic proposal schema unavailable")
        accepted_proposal = definitions["SemanticProposal"]
        proposal_definitions = {
            name: copy.deepcopy(definitions[name])
            for name in (
                "NonEmptyString",
                "OpaqueMaterialRef",
                "OpaqueTargetRef",
                "SourceMaterialRef",
                "Predicate",
                "Operation",
            )
        }
        self.accepted_output_schema = copy.deepcopy(accepted_proposal)
        self.accepted_output_schema["$defs"] = proposal_definitions
        self.output_schema: dict[str, object] = SemanticProposal.model_json_schema()
        capabilities: list[_Capability] = []
        for value in registry.get("capabilities", []):
            if not isinstance(value, dict):
                raise RuntimeError("capability registry invalid")
            capabilities.append(
                _Capability(
                    id=value["id"],
                    operations=frozenset(value["semantic_operation_kinds"]),
                    implementation_state=value["implementation_state"],
                    policy_state=value["policy_state"],
                    effect_type=value["effect_type"],
                    approval_requirement=value["approval_requirement"],
                )
            )
        self.capabilities = tuple(capabilities)
        self.by_operation = {
            operation: capability
            for capability in self.capabilities
            for operation in capability.operations
        }


def _quoted_intervals(text: str) -> tuple[tuple[int, int], ...]:
    """Scan bounded input once; ambiguous structure makes the whole intake inert."""
    pairs = {"«": "»", "“": "”", "‘": "’", '"': '"', "'": "'"}
    intervals: list[tuple[int, int]] = []
    stack: list[tuple[str, str]] = []
    start = 0
    cursor = 0
    while cursor < len(text):
        character = text[cursor]
        if stack and stack[-1][0].startswith("`"):
            if character != "`":
                cursor += 1
                continue
            run_end = cursor + 1
            while run_end < len(text) and text[run_end] == "`":
                run_end += 1
            if text[cursor:run_end] == stack[-1][1]:
                stack.pop()
                if not stack:
                    intervals.append((start, run_end))
            cursor = run_end
            continue
        if character in {"'", "‘", "’"} and _is_word_apostrophe(text, cursor):
            cursor += 1
            continue
        if stack and character == "\\":
            cursor = min(len(text), cursor + 2)
            continue
        if character == "`":
            run_end = cursor + 1
            while run_end < len(text) and text[run_end] == "`":
                run_end += 1
            delimiter = text[cursor:run_end]
            if not stack:
                start = cursor
            stack.append((delimiter, delimiter))
            cursor = run_end
            continue
        if stack and character == stack[-1][1]:
            nested_symmetric = (
                stack[-1][0] == character
                and cursor > 0
                and not text[cursor - 1].isalnum()
                and cursor + 1 < len(text)
                and text[cursor + 1].isalnum()
            )
            if nested_symmetric:
                stack.append((character, character))
            else:
                stack.pop()
                if not stack:
                    intervals.append((start, cursor + 1))
        elif character in pairs:
            if not stack:
                start = cursor
            stack.append((character, pairs[character]))
        elif character in {"»", "”", "’"}:
            # A mismatched closing delimiter cannot expose a possibly quoted command.
            return ((0, len(text)),)
        cursor += 1
    if stack:
        return ((0, len(text)),)
    return tuple(intervals)


def _is_word_apostrophe(text: str, index: int) -> bool:
    return (
        0 < index < len(text) - 1
        and (text[index - 1].isalnum() or text[index - 1] == "_")
        and (text[index + 1].isalnum() or text[index + 1] == "_")
    )


def _material_intervals(text: str) -> tuple[tuple[int, int, str], ...]:
    """Find only explicit structural material bounds; never infer user intent."""
    intervals: list[tuple[int, int, str]] = [
        (start, end, "QUOTED_MATERIAL")
        for start, end in _quoted_intervals(text)
    ]
    intervals.extend(
        (match.start(), match.end(), "NESTED_MATERIAL")
        for match in _EXPLICIT_MATERIAL_BLOCK.finditer(text)
    )
    intervals.extend(
        (match.start(), match.end(), "NESTED_MATERIAL")
        for match in _BLOCKQUOTE_INPUT.finditer(text)
    )
    for match in _MENTIONED_CONTEXT_BOUNDARY.finditer(text):
        start = max(
            text.rfind(".", 0, match.start()),
            text.rfind("!", 0, match.start()),
            text.rfind("?", 0, match.start()),
            text.rfind("\n", 0, match.start()),
        ) + 1
        terminator = re.search(r"[.!?](?:\s|\Z)|\r?\n", text[match.end() :])
        end = (
            len(text)
            if terminator is None
            else match.end() + terminator.end()
        )
        intervals.append((start, end, "MENTIONED_CONTEXT"))
    for match in _TAIL_MATERIAL_BOUNDARY.finditer(text):
        sentence_end = re.search(r"[.!?](?:\s|\Z)", text[match.end() :])
        if sentence_end is not None:
            start = match.end() + sentence_end.end()
            if text[start:].strip():
                intervals.append((start, len(text), "PROVIDED_MATERIAL"))
    for match in _COLON_MATERIAL_BOUNDARY.finditer(text):
        if text[match.end() :].strip():
            intervals.append((match.end(), len(text), "PROVIDED_MATERIAL"))
    if not intervals:
        return ()
    priority = {
        "QUOTED_MATERIAL": 1,
        "MENTIONED_CONTEXT": 2,
        "PROVIDED_MATERIAL": 2,
        "NESTED_MATERIAL": 3,
    }
    merged: list[list[int | str]] = []
    for start, end, origin in sorted(intervals, key=lambda value: (value[0], value[1])):
        if not merged or start > int(merged[-1][1]):
            merged.append([start, end, origin])
            continue
        merged[-1][1] = max(int(merged[-1][1]), end)
        if priority[origin] > priority[str(merged[-1][2])]:
            merged[-1][2] = origin
    return tuple((int(start), int(end), str(origin)) for start, end, origin in merged)


def _all_text_intervals(text: str) -> tuple[tuple[int, int, str], ...]:
    material = _material_intervals(text)
    values: list[tuple[int, int, str]] = []
    cursor = 0
    for start, end, origin in material:
        if cursor < start and _has_word_content(text[cursor:start]):
            values.append((cursor, start, "DIRECT_OWNER_COMMAND"))
        if _has_word_content(text[start:end]):
            values.append((start, end, origin))
        cursor = max(cursor, end)
    if cursor < len(text) and _has_word_content(text[cursor:]):
        values.append((cursor, len(text), "DIRECT_OWNER_COMMAND"))
    if not values and _has_word_content(text):
        values.append((0, len(text), "DIRECT_OWNER_COMMAND"))
    return tuple(values)


def _has_word_content(text: str) -> bool:
    return re.search(r"[0-9A-Za-zА-Яа-яЁё]", text) is not None


def _direct_owner_text(text: str) -> str:
    return " ".join(
        text[start:end]
        for start, end, origin in _all_text_intervals(text)
        if origin == "DIRECT_OWNER_COMMAND"
    )


def _conditional_structure(text: str) -> Literal["NONE", "SUPPORTED", "UNSUPPORTED"]:
    """Validate only the closed v1 predicate surface and only to fail closed."""
    direct = _direct_owner_text(text)
    markers = tuple(re.finditer(r"\bесли\b", direct, re.I))
    if not markers:
        return "NONE"
    if len(markers) != 1:
        return "UNSUPPORTED"
    separator = re.search(r"[,;]", direct[markers[0].end() :])
    if separator is None:
        return "UNSUPPORTED"
    condition_end = markers[0].end() + separator.start()
    tokens = {
        value.casefold()
        for value in _CONDITION_TOKEN.findall(direct[markers[0].start() : condition_end])
    }
    if (
        not {"если", "есть", "просроченный", "пункт"}.issubset(tokens)
        or not tokens.issubset(_SUPPORTED_CONDITION_TOKENS)
    ):
        return "UNSUPPORTED"
    return "SUPPORTED"


def _conditional_tail_text(text: str) -> str:
    """Return the command tail after the one server-recognized v1 predicate."""
    direct = _direct_owner_text(text)
    marker = re.search(r"\bесли\b", direct, re.I)
    if marker is None:
        raise ValueError("conditional tail is unavailable")
    separator = re.search(r"[,;]", direct[marker.end() :])
    if separator is None:
        raise ValueError("conditional tail is unavailable")
    tail_start = marker.end() + separator.end()
    tail = direct[tail_start:].strip()
    if not _has_word_content(tail):
        raise ValueError("conditional tail is unavailable")
    return tail


def _mint_text_span_bindings(
    text: str,
    *,
    intake_ref: str,
    intake_revision: int,
    owner_binding: str,
    tenant_binding: str,
    conversation_binding: str,
) -> tuple[TrustedTextSpanBinding, ...]:
    values: list[TrustedTextSpanBinding] = []
    intervals = _all_text_intervals(text)
    if len(intervals) > _MAX_TEXT_SPANS:
        raise ValueError("semantic input has too many structural spans")
    for start, end, origin in intervals:
        content_digest = canonical_json_digest({"text": text[start:end]})
        span_digest = hashlib.sha256(
            (
                intake_ref
                + "\0"
                + str(intake_revision)
                + "\0"
                + str(start)
                + "\0"
                + str(end)
                + "\0"
                + origin
                + "\0"
                + content_digest
            ).encode("utf-8")
        ).hexdigest()
        values.append(
            TrustedTextSpanBinding(
                span_ref=f"span://intake/{span_digest}",
                start=start,
                end=end,
                content_digest=content_digest,
                owner_binding=owner_binding,
                tenant_binding=tenant_binding,
                conversation_binding=conversation_binding,
                intake_ref=intake_ref,
                intake_revision=intake_revision,
                trusted_origin=origin,
            )
        )
    return tuple(values)


def telegram_semantic_input(
    text: str,
    envelope: TrustedIngressEnvelope,
    *,
    modality: Literal["text", "voice_transcript", "miniapp_text"],
    chat_id: int,
    message_thread_id: int | None,
    locale: str = "ru-RU",
) -> tuple[CanonicalSemanticInput, AdmissionBindings]:
    """Mint opaque intake/material refs and keep authority outside model input."""
    trusted = TrustedIngressEnvelope.model_validate(envelope.model_dump(mode="json"))
    normalized = text.strip()
    if not normalized or len(normalized) > 16_000 or "\x00" in normalized:
        raise ValueError("semantic input is invalid")
    suffix = trusted.content_ref.removeprefix("sha256:")
    source = "miniapp" if modality == "miniapp_text" else "telegram"
    full_material = CanonicalMaterial(
        ref=f"material://intake/{suffix}", boundary="full_material"
    )
    materials = [full_material]
    for index, (start, end) in enumerate(_quoted_intervals(normalized), 1):
        if len(materials) == 12:
            break
        span_digest = hashlib.sha256(
            (
                trusted.content_ref
                + "\0"
                + str(index)
                + "\0"
                + str(start)
                + "\0"
                + str(end)
            ).encode("utf-8")
        ).hexdigest()
        materials.append(
            CanonicalMaterial(
                ref=f"material://intake/quoted/{span_digest}",
                boundary="quoted_fragment",
            )
        )
    canonical = CanonicalSemanticInput(
        modality=modality,
        locale=locale,
        owner_text=normalized,
        materials=tuple(materials),
    )
    conversation = canonical_json_digest(
        {
            "chat_id": chat_id,
            "message_thread_id": message_thread_id,
            "source": source,
            "tenant_id": trusted.tenant_id,
        }
    )
    intake_ref = f"intake://{source}/{suffix}"
    intake_revision = max(1, int(suffix[:12], 16))
    owner_binding = canonical_json_digest(
        {
            "actor_identity": trusted.actor_identity,
            "auth_context_ref": trusted.auth_context_ref,
        }
    )
    tenant_binding = canonical_json_digest({"tenant_id": trusted.tenant_id})
    bindings = AdmissionBindings(
        intake_ref=intake_ref,
        intake_revision=intake_revision,
        owner_binding=owner_binding,
        tenant_binding=tenant_binding,
        conversation_binding=conversation,
        materials=tuple(materials),
        material_item_states={},
        reference_bindings=tuple(
            TrustedReferenceBinding(
                ref=material.ref,
                trusted_boundary=material.boundary,
                issued_by_server=True,
                current_intake_member=True,
                owner_binding=owner_binding,
                tenant_binding=tenant_binding,
                conversation_binding=conversation,
                intake_ref=intake_ref,
                intake_revision=intake_revision,
            )
            for material in materials
        ),
        text_span_bindings=_mint_text_span_bindings(
            normalized,
            intake_ref=intake_ref,
            intake_revision=intake_revision,
            owner_binding=owner_binding,
            tenant_binding=tenant_binding,
            conversation_binding=conversation,
        ),
        conditional_structure=_conditional_structure(normalized),
    )
    return canonical, bindings


class TrustedAdmissionContextBuilder:
    """Derive provenance, reference checks and predicates from server-owned facts."""

    def build(
        self,
        canonical: CanonicalSemanticInput,
        proposal: SemanticProposal,
        bindings: AdmissionBindings,
    ) -> TrustedAdmissionContext:
        issued = {binding.ref: binding for binding in bindings.reference_bindings}
        if len(issued) != len(bindings.reference_bindings):
            raise ValueError("duplicate trusted reference binding")
        usage_map: dict[str, set[str]] = {}
        proposal_boundaries = {
            material.ref: material.boundary for material in proposal.source_material_refs
        }
        for reference in proposal.source_material_refs:
            usage_map.setdefault(reference.ref, set()).add("SOURCE_MATERIAL")
        for operation in proposal.operations:
            if operation.target_ref is not None:
                usage_map.setdefault(operation.target_ref, set()).add("OPERATION_TARGET")
            if operation.predicate is not None:
                usage_map.setdefault(operation.predicate.subject_ref, set()).add(
                    "PREDICATE_SUBJECT"
                )

        checks: list[ReferenceCheck] = []
        first_failure = "VERIFIED"
        usage_order = ("SOURCE_MATERIAL", "OPERATION_TARGET", "PREDICATE_SUBJECT")
        for ref, usages in usage_map.items():
            binding = issued.get(ref)
            if binding is None:
                status = "FORGED_REF"
                boundary = "operation_target"
            elif not binding.issued_by_server:
                status = "FORGED_REF"
                boundary = binding.trusted_boundary
            elif binding.owner_binding != bindings.owner_binding:
                status = "WRONG_OWNER"
                boundary = binding.trusted_boundary
            elif binding.tenant_binding != bindings.tenant_binding:
                status = "WRONG_TENANT"
                boundary = binding.trusted_boundary
            elif binding.conversation_binding != bindings.conversation_binding:
                status = "WRONG_CONVERSATION"
                boundary = binding.trusted_boundary
            elif (
                not binding.current_intake_member
                or binding.intake_ref != bindings.intake_ref
            ):
                status = "NOT_IN_CURRENT_INTAKE"
                boundary = binding.trusted_boundary
            elif binding.intake_revision != bindings.intake_revision:
                status = "STALE_REF"
                boundary = binding.trusted_boundary
            elif (
                ref in proposal_boundaries
                and proposal_boundaries[ref] != binding.trusted_boundary
            ):
                status = "BOUNDARY_MISMATCH"
                boundary = binding.trusted_boundary
            else:
                status = "VERIFIED"
                boundary = binding.trusted_boundary
            if first_failure == "VERIFIED" and status != "VERIFIED":
                first_failure = status
            checks.append(
                ReferenceCheck(
                    ref=ref,
                    usages=tuple(item for item in usage_order if item in usages),
                    trusted_boundary=boundary,
                    status=status,
                )
            )

        trusted_operations = {
            binding.operation_index: binding
            for binding in bindings.operation_bindings
        }
        if len(trusted_operations) != len(bindings.operation_bindings):
            raise ValueError("duplicate trusted operation binding")
        if any(index >= len(proposal.operations) for index in trusted_operations):
            raise ValueError("trusted operation binding is outside proposal")
        provenance: list[OperationProvenance] = []
        proposal_digest = canonical_json_digest(proposal.model_dump(mode="json"))
        for index, operation in enumerate(proposal.operations):
            trusted_operation = trusted_operations.get(index)
            if (
                trusted_operation is not None
                and trusted_operation.operation_kind == operation.operation_kind
                and trusted_operation.proposal_digest == proposal_digest
                and trusted_operation.owner_binding == bindings.owner_binding
                and trusted_operation.tenant_binding == bindings.tenant_binding
                and trusted_operation.conversation_binding
                == bindings.conversation_binding
                and trusted_operation.intake_ref == bindings.intake_ref
                and trusted_operation.intake_revision == bindings.intake_revision
            ):
                provenance.append(
                    OperationProvenance(
                        operation_index=index,
                        span_ref=trusted_operation.span_ref,
                        trusted_origin=trusted_operation.trusted_origin,
                        authority_scope=trusted_operation.authority_scope,
                    )
                )
                continue
            if trusted_operation is not None:
                provenance.append(
                    OperationProvenance(
                        operation_index=index,
                        span_ref=trusted_operation.span_ref,
                        trusted_origin="MENTIONED_CONTEXT",
                        authority_scope="INERT",
                    )
                )
                continue
            origin = {
                "quoted": "QUOTED_MATERIAL",
                "mentioned_only": "MENTIONED_CONTEXT",
                "negated": "DIRECT_OWNER_COMMAND",
                "conditional": "MENTIONED_CONTEXT",
                "requested": "MENTIONED_CONTEXT",
            }[operation.role]
            scope = "INERT"
            span = hashlib.sha256(
                f"{bindings.intake_ref}\0{index}".encode("utf-8")
            ).hexdigest()
            provenance.append(
                OperationProvenance(
                    operation_index=index,
                    span_ref=f"span://intake/{span}",
                    trusted_origin=origin,
                    authority_scope=scope,
                )
            )

        conditional = next(
            (operation for operation in proposal.operations if operation.predicate), None
        )
        if conditional is None:
            predicate = PredicateEvaluation(
                outcome="NOT_APPLICABLE", evaluator="NONE", subject_ref=None
            )
        else:
            assert conditional.predicate is not None
            subject = conditional.predicate.subject_ref
            states = bindings.material_item_states.get(subject)
            outcome = (
                "UNKNOWN"
                if states is None
                else "TRUE"
                if conditional.predicate.arguments.item_state in states
                else "FALSE"
            )
            predicate = PredicateEvaluation(
                outcome=outcome,
                evaluator="MATERIAL_ITEM_STATE_V1",
                subject_ref=subject,
            )
        context_suffix = hashlib.sha256(
            (
                bindings.intake_ref
                + "\0"
                + canonical_json_digest(proposal.model_dump(mode="json"))
            ).encode("utf-8")
        ).hexdigest()
        return TrustedAdmissionContext(
            schema_version=SCHEMA_VERSION,
            context_ref=bindings.context_ref or f"context://intake/{context_suffix}",
            intake_ref=bindings.intake_ref,
            intake_revision=bindings.intake_revision,
            owner_binding=bindings.owner_binding,
            tenant_binding=bindings.tenant_binding,
            conversation_binding=bindings.conversation_binding,
            reference_validation=first_failure,
            operation_provenance=tuple(provenance),
            reference_checks=tuple(checks),
            predicate_evaluation=predicate,
        )


class TrustedOperationBindingIssuer:
    """Mint authority only from exact server spans and isolated direct claims."""

    def issue(
        self,
        canonical: CanonicalSemanticInput,
        proposal: SemanticProposal,
        bindings: AdmissionBindings,
        direct_span_proposals: Mapping[str, SemanticProposal],
    ) -> tuple[TrustedOperationBinding, ...]:
        spans = {value.span_ref: value for value in self._validated_spans(canonical, bindings)}
        direct_spans = {
            ref: span
            for ref, span in spans.items()
            if span.trusted_origin == "DIRECT_OWNER_COMMAND"
        }
        if set(direct_span_proposals) != set(direct_spans):
            raise ValueError("direct span proposal binding is incomplete")
        corroborated = self._corroborated_direct_occurrences(
            proposal, direct_span_proposals
        )
        if self.reference_failure(
            canonical, bindings, (proposal, *direct_span_proposals.values())
        ):
            corroborated = {}
        proposal_digest = canonical_json_digest(proposal.model_dump(mode="json"))
        values: list[TrustedOperationBinding] = []
        for index, operation in enumerate(proposal.operations):
            matched_ref = corroborated.get(index)
            span = direct_spans.get(matched_ref) if matched_ref is not None else None
            if span is None:
                span_ref = self._fallback_span_ref(bindings.intake_ref, index)
                origin = {
                    "quoted": "QUOTED_MATERIAL",
                    "negated": "DIRECT_OWNER_COMMAND",
                }.get(operation.role, "MENTIONED_CONTEXT")
                scope = "INERT"
            else:
                span_ref = span.span_ref
                origin = span.trusted_origin
                if operation.role == "requested":
                    scope = "OWNER_REQUESTED"
                elif operation.role == "conditional":
                    scope = "OWNER_CONDITIONAL"
                else:
                    scope = "INERT"
            values.append(
                TrustedOperationBinding(
                    operation_index=index,
                    operation_kind=operation.operation_kind,
                    proposal_digest=proposal_digest,
                    span_ref=span_ref,
                    owner_binding=bindings.owner_binding,
                    tenant_binding=bindings.tenant_binding,
                    conversation_binding=bindings.conversation_binding,
                    intake_ref=bindings.intake_ref,
                    intake_revision=bindings.intake_revision,
                    trusted_origin=origin,
                    authority_scope=scope,
                )
            )
        return tuple(values)

    @staticmethod
    def reference_failure(
        canonical: CanonicalSemanticInput,
        bindings: AdmissionBindings,
        proposals: Iterable[SemanticProposal],
    ) -> ReferenceCheck | None:
        builder = TrustedAdmissionContextBuilder()
        reference_bindings = replace(bindings, operation_bindings=())
        for proposal in proposals:
            context = builder.build(canonical, proposal, reference_bindings)
            for check in context.reference_checks:
                if check.status != "VERIFIED":
                    return check
        return None

    @classmethod
    def direct_span_inputs(
        cls,
        canonical: CanonicalSemanticInput,
        bindings: AdmissionBindings,
    ) -> dict[str, CanonicalSemanticInput]:
        return {
            span.span_ref: canonical.model_copy(
                update={"owner_text": canonical.owner_text[span.start : span.end].strip()}
            )
            for span in cls._validated_spans(canonical, bindings)
            if span.trusted_origin == "DIRECT_OWNER_COMMAND"
        }

    @staticmethod
    def _operation_signature(operation: Operation) -> str:
        return canonical_json_digest(
            {
                "operation_kind": operation.operation_kind,
                "predicate": (
                    {
                        "kind": operation.predicate.kind,
                        "arguments": operation.predicate.arguments.model_dump(
                            mode="json"
                        ),
                    }
                    if operation.predicate is not None
                    else None
                ),
                "role": operation.role,
            }
        )

    @classmethod
    def _corroborated_direct_occurrences(
        cls,
        proposal: SemanticProposal,
        direct_span_proposals: Mapping[str, SemanticProposal],
    ) -> dict[int, str]:
        if proposal.interpretation_state != "understood" or any(
            direct.interpretation_state != "understood"
            or direct.ambiguities
            or direct.clarification_question is not None
            for direct in direct_span_proposals.values()
        ):
            return {}
        active = [
            (index, cls._operation_signature(operation))
            for index, operation in enumerate(proposal.operations)
            if operation.role in {"requested", "conditional"}
        ]
        occurrences = [
            (cls._operation_signature(candidate), ref)
            for ref, direct_proposal in direct_span_proposals.items()
            for candidate in direct_proposal.operations
            if candidate.role in {"requested", "conditional"}
        ]
        if Counter(signature for _, signature in active) != Counter(
            signature for signature, _ in occurrences
        ):
            return {}
        matched: dict[int, str] = {}
        for index, signature in active:
            occurrence_index = next(
                offset for offset, (value, _) in enumerate(occurrences)
                if value == signature
            )
            _, matched[index] = occurrences.pop(occurrence_index)
        return matched

    @staticmethod
    def _fallback_span_ref(intake_ref: str, operation_index: int) -> str:
        suffix = hashlib.sha256(
            f"{intake_ref}\0{operation_index}\0unbound".encode("utf-8")
        ).hexdigest()
        return f"span://intake/{suffix}"

    @staticmethod
    def _validated_spans(
        canonical: CanonicalSemanticInput,
        bindings: AdmissionBindings,
    ) -> tuple[TrustedTextSpanBinding, ...]:
        spans = bindings.text_span_bindings
        expected = _mint_text_span_bindings(
            canonical.owner_text,
            intake_ref=bindings.intake_ref,
            intake_revision=bindings.intake_revision,
            owner_binding=bindings.owner_binding,
            tenant_binding=bindings.tenant_binding,
            conversation_binding=bindings.conversation_binding,
        )
        if not spans or spans != expected:
            raise ValueError("trusted text span ledger binding is invalid")
        return spans


class SemanticDecisionCore:
    """Map a proposal to one server-owned capability in the frozen C0 order."""

    _REFERENCE_REASONS = {
        "WRONG_OWNER": "REFERENCE_WRONG_OWNER",
        "WRONG_TENANT": "REFERENCE_WRONG_TENANT",
        "WRONG_CONVERSATION": "REFERENCE_WRONG_CONVERSATION",
        "NOT_IN_CURRENT_INTAKE": "REFERENCE_NOT_IN_CURRENT_INTAKE",
        "BOUNDARY_MISMATCH": "REFERENCE_BOUNDARY_MISMATCH",
        "FORGED_REF": "REFERENCE_FORGED_REF",
        "STALE_REF": "REFERENCE_STALE_REF",
    }

    def __init__(self, contract: SemanticContract) -> None:
        self._contract = contract

    def decide(
        self, proposal: SemanticProposal, context: TrustedAdmissionContext
    ) -> CoreDecision:
        proposal_digest = canonical_json_digest(proposal.model_dump(mode="json"))
        context_digest = canonical_json_digest(context.model_dump(mode="json"))

        trust_reason = self._trust_failure(proposal, context)
        if trust_reason is not None:
            return self._decision(
                proposal_digest,
                context_digest,
                decision="REFUSE",
                stage="TRUST_VIOLATION",
                selected=None,
                reason=trust_reason,
                evidence=self._binding_evidence(),
                state="refused",
                message=(
                    "task.provenance.refused"
                    if trust_reason == "TRUST_PROVENANCE_ROLE_CONFLICT"
                    else "task.reference.refused"
                ),
            )

        actionable = [
            operation
            for operation in proposal.operations
            if operation.role in {"requested", "conditional"}
        ]
        capabilities = [
            self._contract.by_operation[operation.operation_kind]
            for operation in actionable
            if operation.operation_kind in self._contract.by_operation
        ]
        prohibited = next(
            (capability for capability in capabilities if capability.policy_state == "PROHIBITED"),
            None,
        )
        if prohibited is not None:
            return self._decision(
                proposal_digest,
                context_digest,
                decision="REFUSE",
                stage="POLICY_PROHIBITED",
                selected=prohibited.id,
                reason="PROHIBITED_SECRET_EXFILTRATION",
                evidence=(
                    PolicyEvidence(kind="policy", ref="policy://global/secrets"),
                    self._context_evidence(),
                ),
                state="refused",
                message="security.secret.refused",
            )

        if proposal.interpretation_state == "ambiguous":
            case_ref = context.context_ref.rsplit("/", 1)[-1].upper()
            return self._decision(
                proposal_digest,
                context_digest,
                decision="CLARIFY",
                stage="AMBIGUITY",
                selected=None,
                reason="MATERIAL_TARGET_AMBIGUOUS",
                evidence=(
                    PolicyEvidence(
                        kind="proposal_schema", ref=f"proposal://ambiguity/{case_ref}"
                    ),
                    self._context_evidence(),
                ),
                state="needs_clarification",
                message="task.target.clarify",
            )

        unique = {capability.id: capability for capability in capabilities}
        if len(unique) != 1:
            refs = tuple(
                PolicyEvidence(
                    kind="registry", ref=f"registry://capabilities/1.0.0/{identifier}"
                )
                for identifier in unique
            )
            return self._decision(
                proposal_digest,
                context_digest,
                decision="UNAVAILABLE" if unique else "CLARIFY",
                stage="HETEROGENEOUS_CAPABILITIES" if unique else "AMBIGUITY",
                selected=None,
                reason=(
                    "HETEROGENEOUS_COMPOUND_UNSUPPORTED_V1"
                    if unique
                    else "NO_ACTIONABLE_OPERATION"
                ),
                evidence=refs
                + (
                    PolicyEvidence(
                        kind="proposal_schema",
                        ref="contract://semantic-admission/1.0.0/compound-single-capability",
                    ),
                    self._context_evidence(),
                ),
                state="unavailable" if unique else "needs_clarification",
                message=(
                    "task.compound.heterogeneous.unavailable"
                    if unique
                    else "task.operation.clarify"
                ),
            )
        capability = next(iter(unique.values()))

        if capability.implementation_state != "CURRENT":
            reason = {
                "FROZEN": "IMPLEMENTATION_FROZEN",
                "UNAVAILABLE": "CAPABILITY_UNAVAILABLE",
                "TARGET": "IMPLEMENTATION_NOT_CURRENT",
            }.get(capability.implementation_state, "IMPLEMENTATION_NOT_CURRENT")
            evidence: tuple[PolicyEvidence, ...] = (
                PolicyEvidence(kind="registry", ref="registry://capabilities/1.0.0"),
            )
            if capability.id == "task.cancel":
                evidence += (
                    PolicyEvidence(kind="owner_binding", ref="owner://synthetic/exact-task"),
                )
            elif capability.effect_type == "write_external":
                evidence += (
                    PolicyEvidence(
                        kind="policy", ref="policy://effects/action-bound-approval"
                    ),
                )
            evidence += (self._context_evidence(),)
            message = {
                "task.cancel": "task.cancel.unavailable",
                "web.public.read": "web.read.unavailable",
                "owner.file.create": "owner.file.create.unavailable",
                "marketplace.campaign.write": "marketplace.campaign.unavailable",
            }.get(capability.id, "task.capability.unavailable")
            return self._decision(
                proposal_digest,
                context_digest,
                decision="UNAVAILABLE",
                stage="IMPLEMENTATION_STATE",
                selected=capability.id,
                reason=reason,
                evidence=evidence,
                state="unavailable",
                message=message,
            )

        predicate = context.predicate_evaluation
        if predicate.outcome in {"FALSE", "UNKNOWN"}:
            unknown = predicate.outcome == "UNKNOWN"
            return self._decision(
                proposal_digest,
                context_digest,
                decision="CLARIFY" if unknown else "UNAVAILABLE",
                stage="PREDICATE_UNKNOWN" if unknown else "PREDICATE_FALSE",
                selected=None,
                reason="PREDICATE_UNKNOWN" if unknown else "PREDICATE_FALSE_NO_EFFECT",
                evidence=self._binding_evidence()
                + (
                    PolicyEvidence(
                        kind="predicate_result",
                        ref="predicate://material-item-state-v1",
                    ),
                ),
                state="condition_unknown" if unknown else "condition_not_met",
                message="task.condition.unknown" if unknown else "task.condition.not_met",
                predicate_outcome=predicate.outcome,
            )

        if capability.approval_requirement != "none":
            return self._decision(
                proposal_digest,
                context_digest,
                decision="APPROVAL",
                stage="APPROVAL_REQUIRED",
                selected=capability.id,
                reason="OWNER_ACTION_APPROVAL_REQUIRED",
                evidence=(
                    PolicyEvidence(kind="registry", ref="registry://capabilities/1.0.0"),
                    PolicyEvidence(
                        kind="policy", ref="policy://effects/action-bound-approval"
                    ),
                    self._context_evidence(),
                ),
                state="approval_required",
                message="task.approval.required",
                predicate_outcome=predicate.outcome,
            )

        reason, evidence, message = self._allowed_details(
            proposal, context, capability.id
        )
        return self._decision(
            proposal_digest,
            context_digest,
            decision="EXECUTE",
            stage="EXECUTE_ALLOWED",
            selected=capability.id,
            reason=reason,
            evidence=evidence,
            state="accepted",
            message=message,
            predicate_outcome=predicate.outcome,
            allow=True,
        )

    def _trust_failure(
        self, proposal: SemanticProposal, context: TrustedAdmissionContext
    ) -> str | None:
        if context.reference_validation != "VERIFIED":
            return self._REFERENCE_REASONS[context.reference_validation]
        if len(context.operation_provenance) != len(proposal.operations):
            return "TRUST_PROVENANCE_MISSING"
        provenance = {item.operation_index: item for item in context.operation_provenance}
        if len(provenance) != len(proposal.operations):
            return "TRUST_PROVENANCE_MISSING"
        for index, operation in enumerate(proposal.operations):
            value = provenance.get(index)
            if value is None:
                return "TRUST_PROVENANCE_MISSING"
            if (
                proposal.interpretation_state == "ambiguous"
                and value.authority_scope == "INERT"
            ):
                # Uncorroborated claims may only reach the no-effect ambiguity gate.
                continue
            if operation.role == "requested" and (
                value.trusted_origin != "DIRECT_OWNER_COMMAND"
                or value.authority_scope != "OWNER_REQUESTED"
            ):
                return "TRUST_PROVENANCE_ROLE_CONFLICT"
            if operation.role == "conditional" and (
                value.trusted_origin != "DIRECT_OWNER_COMMAND"
                or value.authority_scope != "OWNER_CONDITIONAL"
            ):
                return "TRUST_PROVENANCE_ROLE_CONFLICT"
            if operation.role in {"quoted", "mentioned_only", "negated"} and (
                value.authority_scope != "INERT"
            ):
                return "TRUST_PROVENANCE_ROLE_CONFLICT"
        required: dict[str, set[str]] = {}
        boundaries = {item.ref: item.boundary for item in proposal.source_material_refs}
        for item in proposal.source_material_refs:
            required.setdefault(item.ref, set()).add("SOURCE_MATERIAL")
        for operation in proposal.operations:
            if operation.target_ref is not None:
                required.setdefault(operation.target_ref, set()).add("OPERATION_TARGET")
            if operation.predicate is not None:
                required.setdefault(operation.predicate.subject_ref, set()).add(
                    "PREDICATE_SUBJECT"
                )
        checks = {item.ref: item for item in context.reference_checks}
        for ref, usages in required.items():
            check = checks.get(ref)
            if check is None or check.status != "VERIFIED" or not usages.issubset(check.usages):
                return "REFERENCE_NOT_IN_CURRENT_INTAKE"
            if ref in boundaries and check.trusted_boundary != boundaries[ref]:
                return "REFERENCE_BOUNDARY_MISMATCH"
        return None

    @staticmethod
    def _context_evidence() -> PolicyEvidence:
        return PolicyEvidence(
            kind="admission_context", ref="context://semantic-admission/1.0.0"
        )

    def _binding_evidence(self) -> tuple[PolicyEvidence, ...]:
        return (
            PolicyEvidence(
                kind="proposal_schema", ref="contract://semantic-admission/1.0.0"
            ),
            PolicyEvidence(
                kind="policy", ref="policy://semantic/admission-binding"
            ),
            self._context_evidence(),
        )

    def _allowed_details(
        self,
        proposal: SemanticProposal,
        context: TrustedAdmissionContext,
        capability_id: str,
    ) -> tuple[str, tuple[PolicyEvidence, ...], str]:
        origins = {value.trusted_origin for value in context.operation_provenance}
        inert = any(value.authority_scope == "INERT" for value in context.operation_provenance)
        conditional = any(operation.role == "conditional" for operation in proposal.operations)
        actionable = sum(
            operation.role in {"requested", "conditional"}
            for operation in proposal.operations
        )
        if conditional:
            return (
                "CONDITIONAL_CURRENT_ALLOWED",
                (
                    PolicyEvidence(kind="registry", ref="registry://capabilities/1.0.0"),
                    PolicyEvidence(kind="predicate", ref="predicate://synthetic/overdue-item"),
                    self._context_evidence(),
                    PolicyEvidence(
                        kind="predicate_result", ref="predicate://material-item-state-v1"
                    ),
                ),
                "task.conditional.accepted",
            )
        if inert:
            if "NESTED_MATERIAL" in origins:
                reason = "NESTED_INJECTION_INERT"
            elif "QUOTED_MATERIAL" in origins:
                reason = "QUOTED_OPERATION_INERT"
            elif capability_id == "content.transform":
                reason = "INERT_MATERIAL_CURRENT_ALLOWED"
            else:
                reason = "MENTIONED_OPERATION_INERT"
            return (
                reason,
                (
                    PolicyEvidence(kind="registry", ref="registry://capabilities/1.0.0"),
                    PolicyEvidence(kind="policy", ref="policy://semantic/inert-material"),
                    self._context_evidence(),
                ),
                "task.transform.accepted"
                if capability_id == "content.transform"
                else "task.answer.accepted",
            )
        if actionable > 1:
            reason, message = "COMPOUND_SINGLE_CAPABILITY_ALLOWED", "task.compound.accepted"
        else:
            reason, message = "CURRENT_ALLOWED", "task.accepted"
        return (
            reason,
            (
                PolicyEvidence(kind="registry", ref="registry://capabilities/1.0.0"),
                PolicyEvidence(
                    kind="proposal_schema", ref="contract://semantic-admission/1.0.0"
                ),
                self._context_evidence(),
            ),
            message,
        )

    @staticmethod
    def _decision(
        proposal_digest: str,
        context_digest: str,
        *,
        decision: str,
        stage: str,
        selected: str | None,
        reason: str,
        evidence: tuple[PolicyEvidence, ...],
        state: str,
        message: str,
        predicate_outcome: str = "NOT_APPLICABLE",
        allow: bool = False,
    ) -> CoreDecision:
        return CoreDecision.model_validate_json(
            json.dumps(
                {
                "schema_version": SCHEMA_VERSION,
                "proposal_digest": proposal_digest,
                "admission_context_digest": context_digest,
                "decision": decision,
                "decision_stage": stage,
                "predicate_outcome": predicate_outcome,
                "selected_capability": selected,
                "policy_reason_code": reason,
                "policy_evidence": [value.model_dump(mode="json") for value in evidence],
                "user_visible_state": {"state": state, "message_key": message},
                "task_contract_allowed": allow,
                "effect_allowed": allow,
                },
                ensure_ascii=False,
            )
        )


class SemanticAdmissionService:
    """Compile untrusted meaning, derive trust facts, then ask deterministic Core."""

    def __init__(
        self,
        compiler: SemanticCompiler,
        *,
        contract: SemanticContract | None = None,
        context_builder: TrustedAdmissionContextBuilder | None = None,
        binding_issuer: TrustedOperationBindingIssuer | None = None,
        timeout_seconds: int = 45,
    ) -> None:
        if not callable(getattr(compiler, "compile_semantic", None)) or (
            type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120
        ):
            raise ValueError("semantic admission configuration is invalid")
        self._compiler = compiler
        self.contract = contract or SemanticContract()
        self._builder = context_builder or TrustedAdmissionContextBuilder()
        self._binding_issuer = binding_issuer or TrustedOperationBindingIssuer()
        self._timeout = timeout_seconds
        self._core = SemanticDecisionCore(self.contract)

    async def admit(
        self, canonical: CanonicalSemanticInput, bindings: AdmissionBindings
    ) -> SemanticAdmission:
        deadline = asyncio.get_running_loop().time() + self._timeout
        try:
            remaining, provider_timeout = self._remaining_timeout(deadline)
            operation = self._compiler.compile_semantic(
                canonical.model_input(),
                self._provider_output_schema(canonical),
                timeout_seconds=provider_timeout,
            )
            raw = await asyncio.wait_for(operation, timeout=remaining)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise SemanticAdmissionError("SEMANTIC_COMPILER_TIMEOUT") from None
        except Exception as error:
            provider_code = getattr(error, "code", None)
            raise SemanticAdmissionError(
                "SEMANTIC_COMPILER_UNAVAILABLE",
                provider_code=(
                    provider_code
                    if isinstance(provider_code, str)
                    else type(error).__name__
                ),
            ) from None
        try:
            proposal = SemanticProposal.model_validate_json(
                json.dumps(
                    self._structured_value(raw),
                    allow_nan=False,
                    ensure_ascii=False,
                )
            )
        except Exception:
            raise SemanticAdmissionError("SEMANTIC_PROPOSAL_INVALID") from None
        proposal = self._apply_structural_safety(proposal, bindings)
        effective_bindings = bindings
        reference_failure: ReferenceCheck | None = None
        if not bindings.operation_bindings and bindings.text_span_bindings:
            try:
                direct_inputs = self._binding_issuer.direct_span_inputs(
                    canonical, bindings
                )
                conditional_tail_input: CanonicalSemanticInput | None = None
                if (
                    bindings.conditional_structure == "SUPPORTED"
                    and proposal.interpretation_state == "understood"
                ):
                    conditional_tail_input = canonical.model_copy(
                        update={
                            "owner_text": _conditional_tail_text(
                                canonical.owner_text
                            )
                        }
                    )
                if (
                    len(direct_inputs) + int(conditional_tail_input is not None)
                    > _MAX_DIRECT_SPAN_COMPILATIONS
                ):
                    raise SemanticAdmissionError("SEMANTIC_CONTEXT_INVALID")
                if conditional_tail_input is not None:
                    tail_proposal = await self._compile_direct_span(
                        conditional_tail_input, deadline
                    )
                    reference_failure = self._binding_issuer.reference_failure(
                        canonical, bindings, (tail_proposal,)
                    )
                    if reference_failure is not None or not self._conditional_tail_matches(
                        proposal, tail_proposal
                    ):
                        proposal = self._force_condition_clarification(proposal)
                direct_span_proposals: dict[str, SemanticProposal] = {}
                for span_ref, direct_input in direct_inputs.items():
                    if direct_input.owner_text == canonical.owner_text:
                        direct_span_proposals[span_ref] = proposal
                    else:
                        direct_span_proposals[span_ref] = (
                            await self._compile_direct_span(direct_input, deadline)
                        )
                if any(
                    direct.interpretation_state == "ambiguous"
                    for direct in direct_span_proposals.values()
                ):
                    proposal = self._force_direct_span_clarification(proposal)
                direct_failure = self._binding_issuer.reference_failure(
                    canonical, bindings, (proposal, *direct_span_proposals.values())
                )
                reference_failure = reference_failure or direct_failure
                operation_bindings = (
                    () if reference_failure is not None
                    else self._binding_issuer.issue(
                        canonical, proposal, bindings, direct_span_proposals
                    )
                )
                effective_bindings = replace(
                    bindings, operation_bindings=operation_bindings
                )
            except SemanticAdmissionError:
                raise
            except Exception:
                raise SemanticAdmissionError("SEMANTIC_CONTEXT_INVALID") from None
        try:
            if reference_failure is not None:
                effective_bindings = replace(effective_bindings, operation_bindings=())
            context = self._builder.build(canonical, proposal, effective_bindings)
            if reference_failure is not None and context.reference_validation == "VERIFIED":
                context = context.model_copy(update={
                    "reference_validation": reference_failure.status,
                    "reference_checks": (reference_failure,),
                })
            validated_context = TrustedAdmissionContext.model_validate_json(
                context.model_dump_json()
            )
            decision = self._core.decide(proposal, validated_context)
        except SemanticAdmissionError:
            raise
        except Exception:
            raise SemanticAdmissionError("SEMANTIC_CONTEXT_INVALID") from None
        return SemanticAdmission(canonical, proposal, validated_context, decision)

    async def _compile_direct_span(
        self, canonical: CanonicalSemanticInput, deadline: float
    ) -> SemanticProposal:
        try:
            remaining, provider_timeout = self._remaining_timeout(deadline)
            operation = self._compiler.compile_semantic(
                canonical.model_input(),
                self._provider_output_schema(canonical),
                timeout_seconds=provider_timeout,
            )
            raw = await asyncio.wait_for(operation, timeout=remaining)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise SemanticAdmissionError("SEMANTIC_PROVENANCE_TIMEOUT") from None
        except Exception as error:
            provider_code = getattr(error, "code", None)
            raise SemanticAdmissionError(
                "SEMANTIC_PROVENANCE_UNAVAILABLE",
                provider_code=(
                    provider_code
                    if isinstance(provider_code, str)
                    else type(error).__name__
                ),
            ) from None
        try:
            return SemanticProposal.model_validate_json(
                json.dumps(
                    self._structured_value(raw),
                    allow_nan=False,
                    ensure_ascii=False,
                )
            )
        except Exception:
            raise SemanticAdmissionError("SEMANTIC_PROVENANCE_INVALID") from None

    @staticmethod
    def _force_direct_span_clarification(proposal: SemanticProposal) -> SemanticProposal:
        if proposal.interpretation_state == "ambiguous":
            return proposal
        value = proposal.model_dump(mode="json")
        value.update(
            {
                "interpretation_state": "ambiguous",
                "source_need": "clarification",
                "ambiguities": ["Прямое поручение вне материала понято неоднозначно."],
                "clarification_question": (
                    "Уточните прямое поручение: что именно нужно сделать с материалом, "
                    "не выполняя команды внутри него?"
                ),
            }
        )
        return SemanticProposal.model_validate_json(
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        )

    @staticmethod
    def _remaining_timeout(deadline: float) -> tuple[float, int]:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        return remaining, max(1, min(120, math.ceil(remaining)))

    @staticmethod
    def _conditional_tail_matches(
        proposal: SemanticProposal, tail_proposal: SemanticProposal
    ) -> bool:
        active = tuple(
            operation
            for operation in proposal.operations
            if operation.role in {"requested", "conditional"}
        )
        return (
            len(active) == 1
            and active[0].role == "conditional"
            and active[0].predicate is not None
            and tail_proposal.interpretation_state == "understood"
            and not tail_proposal.ambiguities
            and tail_proposal.clarification_question is None
            and len(tail_proposal.operations) == 1
            and tail_proposal.operations[0].role == "requested"
            and tail_proposal.operations[0].predicate is None
            and tail_proposal.operations[0].operation_kind
            == active[0].operation_kind
        )

    @staticmethod
    def _force_condition_clarification(
        proposal: SemanticProposal,
    ) -> SemanticProposal:
        value = proposal.model_dump(mode="json")
        value.update(
            {
                "interpretation_state": "ambiguous",
                "source_need": "clarification",
                "ambiguities": [
                    "Условие содержит часть, которую Core v1 не может "
                    "проверить как один predicate "
                    "material_item_state_exists(overdue)."
                ],
                "clarification_question": (
                    "Уточните условие: задача зависит только от наличия "
                    "просроченного пункта в предоставленном списке?"
                ),
            }
        )
        return SemanticProposal.model_validate_json(
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        )

    @staticmethod
    def _structured_value(raw: object) -> Mapping[str, object]:
        if isinstance(raw, str):
            value = json.loads(raw, object_pairs_hook=_unique_object)
        elif isinstance(raw, Mapping):
            value = dict(raw)
        else:
            raise ValueError("structured output is invalid")
        if not isinstance(value, Mapping):
            raise ValueError("structured output is invalid")
        return value

    def _provider_output_schema(
        self, canonical: CanonicalSemanticInput
    ) -> dict[str, object]:
        """Constrain generation to refs already issued for this exact intake."""
        schema = copy.deepcopy(self.contract.output_schema)
        if not canonical.materials:
            return schema
        definitions = schema["$defs"]
        assert isinstance(definitions, dict)
        refs = [material.ref for material in canonical.materials]
        definitions["SourceMaterialRef"] = {
            "anyOf": [
                {
                    "additionalProperties": False,
                    "properties": {
                        "ref": {"const": material.ref, "type": "string"},
                        "boundary": {
                            "const": material.boundary,
                            "type": "string",
                        },
                    },
                    "required": ["ref", "boundary"],
                    "type": "object",
                }
                for material in canonical.materials
            ],
            "title": "SourceMaterialRef",
        }
        operation = definitions["Operation"]
        predicate = definitions["Predicate"]
        assert isinstance(operation, dict) and isinstance(predicate, dict)
        operation["properties"]["target_ref"]["anyOf"][0] = {
            "enum": refs,
            "type": "string",
        }
        predicate["properties"]["subject_ref"] = {
            "enum": refs,
            "type": "string",
        }
        return schema

    @staticmethod
    def _apply_structural_safety(
        proposal: SemanticProposal, bindings: AdmissionBindings
    ) -> SemanticProposal:
        active = tuple(
            operation
            for operation in proposal.operations
            if operation.role in {"requested", "conditional"}
        )
        missing_material = (
            bool(bindings.text_span_bindings)
            and len(active) == 1
            and active[0].operation_kind == "transform_material"
            and not any(
                span.trusted_origin != "DIRECT_OWNER_COMMAND"
                for span in bindings.text_span_bindings
            )
        )
        if (
            bindings.conditional_structure != "UNSUPPORTED"
            and not missing_material
        ):
            return proposal
        if missing_material and bindings.conditional_structure != "UNSUPPORTED":
            detail = "Для преобразования не выделена точная граница материала."
            safe_question = "Какой именно материал нужно преобразовать?"
        else:
            detail = (
                "Условие содержит часть, которую Core v1 не может проверить "
                "как один predicate material_item_state_exists(overdue)."
            )
            safe_question = (
                "Уточните условие: задача зависит только от наличия "
                "просроченного пункта в предоставленном списке?"
            )
        if proposal.interpretation_state == "ambiguous":
            ambiguities = proposal.ambiguities
            question = proposal.clarification_question
        else:
            ambiguities = (detail,)
            question = safe_question
        value = proposal.model_dump(mode="json")
        value.update(
            {
                "interpretation_state": "ambiguous",
                "source_need": "clarification",
                "ambiguities": ambiguities,
                "clarification_question": question,
            }
        )
        return SemanticProposal.model_validate_json(
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        )
