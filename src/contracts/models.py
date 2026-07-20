"""Version 1 contracts exchanged through Nobus Core."""

from __future__ import annotations

import math
import ntpath
import posixpath
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

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


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_KEY_MARKERS = (
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "credential",
    "password",
    "privatekey",
    "secret",
    "sessionid",
    "token",
)


class ContractModel(BaseModel):
    """Strict immutable base for versioned Core contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskLevel(str, Enum):
    """Risk assigned before a task is executed."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationLevelStatus(str, Enum):
    """Result of one verification level."""

    PASSED = "passed"
    FAILED = "failed"


class VerificationBundleStatus(str, Enum):
    """Aggregate state of a verification bundle."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkerEventType(str, Enum):
    """Closed WorkerEvent v1 type registry."""

    STARTED = "started"
    PROGRESS = "progress"
    WAITING_INPUT = "waiting_input"
    ARTIFACT_READY = "artifact_ready"
    RESULT_READY = "result_ready"
    USAGE = "usage"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalized_items(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = [_non_empty(value, field_name) for value in values]
    return tuple(dict.fromkeys(normalized))


def _normalize_digest(value: str, field_name: str) -> str:
    normalized = _non_empty(value, field_name)
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must be sha256:<64 lowercase hex characters>"
        )
    return normalized


def _normalize_allowed_path(value: str) -> str:
    raw = _non_empty(value, "allowed_paths")
    if "\x00" in raw:
        raise ValueError("allowed_paths must not contain NUL")
    if ".." in re.split(r"[\\/]", raw):
        raise ValueError("allowed_paths must not contain path traversal")

    path_module = ntpath if "\\" in raw or re.match(r"^[A-Za-z]:", raw) else posixpath
    normalized = path_module.normpath(raw)
    if normalized == ".." or normalized.startswith(("../", "..\\")):
        raise ValueError("allowed_paths must not contain path traversal")
    return normalized


def _validate_json_value(value: Any, path: str = "payload") -> None:
    """Reject values that cannot be represented by strict JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} object keys must be strings")
            _validate_json_value(nested, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_json_value(nested, f"{path}[{index}]")
        return
    raise ValueError(f"{path} must contain JSON-compatible values only")


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            compact = re.sub(r"[^a-z0-9]+", "", key.casefold())
            if any(marker in compact for marker in _SECRET_KEY_MARKERS):
                raise ValueError("WorkerEvent payload must not contain secret fields")
            _reject_secret_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_keys(nested)


class TaskContract(ContractModel):
    """Normalized task accepted by Nobus Core."""

    schema_version: Literal["1"] = "1"
    task_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    tenant_id: str
    source: str
    instruction: str
    allowed_paths: tuple[str, ...] = Field(min_length=1)
    permissions: tuple[str, ...]
    risk: RiskLevel
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)
    timeout_seconds: StrictInt = Field(ge=1, le=3600)
    quality_profile: str

    @field_validator(
        "idempotency_key", "tenant_id", "source", "instruction", "quality_profile"
    )
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, info.field_name)

    @field_validator("allowed_paths")
    @classmethod
    def normalize_allowed_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_normalize_allowed_path(value) for value in values))

    @field_validator("permissions")
    @classmethod
    def normalize_permissions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalized_items(values, "permissions") if values else ()

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        return _normalized_items(values, "acceptance_criteria")


class _StartedPayload(ContractModel):
    lease_ref: str

    _lease_ref = field_validator("lease_ref")(
        lambda value: _non_empty(value, "lease_ref")
    )


class _ProgressPayload(ContractModel):
    stage: str
    percent: Annotated[StrictInt | StrictFloat, Field(ge=0, le=100)] | None = None

    _stage = field_validator("stage")(lambda value: _non_empty(value, "stage"))


class _WaitingInputPayload(ContractModel):
    question_ref: str

    _question_ref = field_validator("question_ref")(
        lambda value: _non_empty(value, "question_ref")
    )


class _ArtifactReadyPayload(ContractModel):
    artifact_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("artifact_refs")
    @classmethod
    def normalize_artifact_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalized_items(values, "artifact_refs")


class _ResultReadyPayload(ContractModel):
    result_ref: str
    result_revision: StrictInt = Field(ge=1)
    result_digest: str

    _result_ref = field_validator("result_ref")(
        lambda value: _non_empty(value, "result_ref")
    )
    _result_digest = field_validator("result_digest")(
        lambda value: _normalize_digest(value, "result_digest")
    )


class _UsagePayload(ContractModel):
    provider: str
    model: str | None = None
    input_units: StrictInt | None = Field(default=None, ge=0)
    output_units: StrictInt | None = Field(default=None, ge=0)
    amount: Annotated[StrictInt | StrictFloat, Field(ge=0)] | None = None
    currency: str | None = None

    @field_validator("provider", "model", "currency")
    @classmethod
    def normalize_text(cls, value: str | None, info: Any) -> str | None:
        return None if value is None else _non_empty(value, info.field_name)

    @model_validator(mode="after")
    def require_measurement(self) -> _UsagePayload:
        if all(
            value is None
            for value in (self.input_units, self.output_units, self.amount)
        ):
            raise ValueError("usage payload requires measured units or amount")
        if (self.amount is None) != (self.currency is None):
            raise ValueError("usage amount and currency must be supplied together")
        return self


class _FailedPayload(ContractModel):
    error_code: str
    safe_message: str
    retryable: StrictBool

    @field_validator("error_code", "safe_message")
    @classmethod
    def normalize_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, info.field_name)


class _CancelledPayload(ContractModel):
    reason_code: str

    _reason_code = field_validator("reason_code")(
        lambda value: _non_empty(value, "reason_code")
    )


_EVENT_PAYLOAD_MODELS: dict[WorkerEventType, type[ContractModel]] = {
    WorkerEventType.STARTED: _StartedPayload,
    WorkerEventType.PROGRESS: _ProgressPayload,
    WorkerEventType.WAITING_INPUT: _WaitingInputPayload,
    WorkerEventType.ARTIFACT_READY: _ArtifactReadyPayload,
    WorkerEventType.RESULT_READY: _ResultReadyPayload,
    WorkerEventType.USAGE: _UsagePayload,
    WorkerEventType.FAILED: _FailedPayload,
    WorkerEventType.CANCELLED: _CancelledPayload,
}


class WorkerEvent(ContractModel):
    """Strict fact emitted by one worker attempt."""

    schema_version: Literal["1"] = "1"
    event_id: UUID
    tenant_id: str
    task_id: UUID
    attempt_id: UUID
    contract_digest: str
    worker_identity: str
    sequence: StrictInt = Field(ge=1)
    event_type: WorkerEventType
    emitted_at: datetime
    payload: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def validate_typed_payload(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        payload = data.get("payload")
        if isinstance(payload, Mapping):
            _validate_json_value(payload)
            _reject_secret_keys(payload)
            try:
                event_type = WorkerEventType(data.get("event_type"))
            except (TypeError, ValueError):
                return data
            data["payload"] = _EVENT_PAYLOAD_MODELS[event_type].model_validate(
                payload
            ).model_dump(mode="json", exclude_none=True)
        return data

    @field_validator("tenant_id", "worker_identity")
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, info.field_name)

    @field_validator("contract_digest")
    @classmethod
    def validate_contract_digest(cls, value: str) -> str:
        return _normalize_digest(value, "contract_digest")

    @field_validator("emitted_at")
    @classmethod
    def validate_emitted_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("emitted_at must be timezone-aware")
        return value

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_value(value)
        _reject_secret_keys(value)
        return value


class VerificationLevel(ContractModel):
    """Integrity-bound outcome reported by one verifier."""

    status: VerificationLevelStatus
    method: str
    verifier_identity: str
    verified_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    evidence_digest: str

    @field_validator("method", "verifier_identity")
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, info.field_name)

    @field_validator("verified_at")
    @classmethod
    def validate_verified_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def normalize_evidence_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalized_items(values, "evidence_refs")

    @field_validator("evidence_digest")
    @classmethod
    def validate_evidence_digest(cls, value: str) -> str:
        return _normalize_digest(value, "evidence_digest")


class VerificationBundle(ContractModel):
    """Verification evidence bound to one immutable task-result revision."""

    schema_version: Literal["1"] = "1"
    tenant_id: str
    task_id: UUID
    contract_digest: str
    result_revision: StrictInt = Field(ge=1)
    result_digest: str
    executor_identity: str
    l1: VerificationLevel | None = None
    l2: VerificationLevel | None = None
    l3: VerificationLevel | None = None
    status: VerificationBundleStatus

    @field_validator("tenant_id", "executor_identity")
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, info.field_name)

    @field_validator("contract_digest", "result_digest")
    @classmethod
    def validate_digests(cls, value: str, info: Any) -> str:
        return _normalize_digest(value, info.field_name)


class HumanApprovalRecord(ContractModel):
    """Immutable L4 record supplied by a future authenticated boundary."""

    tenant_id: str
    task_id: UUID
    contract_digest: str
    result_revision: StrictInt = Field(ge=1)
    result_digest: str
    approver_identity: str
    approved_at: datetime
    evidence_ref: str

    @field_validator("tenant_id", "approver_identity", "evidence_ref")
    @classmethod
    def normalize_required_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, info.field_name)

    @field_validator("contract_digest", "result_digest")
    @classmethod
    def validate_digests(cls, value: str, info: Any) -> str:
        return _normalize_digest(value, info.field_name)

    @field_validator("approved_at")
    @classmethod
    def validate_approved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        return value
