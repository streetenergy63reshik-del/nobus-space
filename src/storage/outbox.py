"""Strict contracts for the local SQLite notification outbox."""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from src.contracts.models import canonical_json_digest
from src.models.task import TaskStatus


_MESSAGE_NAMESPACE = UUID("31e9673a-5a4f-4c0e-8c94-3dc7c80fe63a")
_ARTIFACT_NAMESPACE = UUID("0e3fcb68-b7f4-4cdf-b01d-16bd5ac2fab7")
_MAX_ARTIFACT_BYTES = 1024 * 1024
_MAX_ARTIFACT_BASE64 = ((_MAX_ARTIFACT_BYTES + 2) // 3) * 4
_SAFE_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class OutboxStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    ACKED = "acked"
    FAILED = "failed"


class ReceiptType(str, Enum):
    ACK = "ack"
    NACK = "nack"
    TIMEOUT = "timeout"


class OutboxArtifact(BaseModel):
    """One immutable answer artifact bound to the exact outbox task result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: UUID
    artifact_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1, max_length=128)
    task_id: UUID
    task_revision: StrictInt = Field(ge=2)
    task_projection_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contract_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    result_revision: StrictInt = Field(ge=1)
    result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    filename: str = Field(min_length=1, max_length=128)
    media_type: Literal["text/plain; charset=utf-8"]
    size: StrictInt = Field(ge=1, le=_MAX_ARTIFACT_BYTES)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_base64: str = Field(
        min_length=4,
        max_length=_MAX_ARTIFACT_BASE64,
        repr=False,
    )

    @model_validator(mode="after")
    def validate_binding_and_content(self) -> "OutboxArtifact":
        if _SAFE_ARTIFACT_NAME.fullmatch(self.filename) is None:
            raise ValueError("artifact filename is invalid")
        try:
            content = base64.b64decode(self.content_base64, validate=True)
        except ValueError:
            raise ValueError("artifact content is invalid") from None
        if (
            len(content) != self.size
            or not content
            or len(content) > _MAX_ARTIFACT_BYTES
            or self.content_digest
            != "sha256:" + hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("artifact content binding is invalid")
        fingerprint = artifact_fingerprint(
            tenant_id=self.tenant_id,
            task_id=self.task_id,
            task_revision=self.task_revision,
            task_projection_digest=self.task_projection_digest,
            contract_digest=self.contract_digest,
            result_revision=self.result_revision,
            result_digest=self.result_digest,
            filename=self.filename,
            media_type=self.media_type,
            size=self.size,
            content_digest=self.content_digest,
        )
        if (
            self.artifact_fingerprint != fingerprint
            or self.artifact_id != artifact_id_for(fingerprint)
        ):
            raise ValueError("artifact identity binding is invalid")
        return self

    def content_bytes(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class OutboxMessage(BaseModel):
    """Tamper-evident safe task notification with optional verified answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: UUID
    message_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1, max_length=128)
    task_id: UUID
    task_revision: StrictInt = Field(ge=2)
    task_projection_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contract_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    result_revision: StrictInt = Field(ge=0)
    result_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    destination_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    template_id: str = Field(pattern=r"^task_status$")
    task_status: TaskStatus
    user_message: str | None = Field(
        default=None, min_length=1, max_length=128 * 1024
    )
    artifact: OutboxArtifact | None = None
    status: OutboxStatus
    attempt_count: StrictInt = Field(ge=0)
    max_attempts: StrictInt = Field(ge=1, le=10)
    next_attempt_at: datetime | None = None
    lease_id: UUID | None = None
    lease_owner: UUID | None = None
    lease_expires_at: datetime | None = None
    state_revision: StrictInt = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "next_attempt_at", "lease_expires_at", "created_at", "updated_at"
    )
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_invariants(self) -> "OutboxMessage":
        for field_name in (
            "next_attempt_at",
            "lease_expires_at",
            "created_at",
            "updated_at",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.result_revision == 0 and self.result_digest is not None:
            raise ValueError("result revision zero cannot have a digest")
        if self.result_revision > 0 and self.result_digest is None:
            raise ValueError("positive result revision requires a digest")
        if self.task_status is TaskStatus.ANSWERED:
            if (
                self.user_message is None
                or self.user_message != self.user_message.strip()
                or any(
                    ord(character) < 32 and character not in "\n\t"
                    for character in self.user_message
                )
            ):
                raise ValueError("answered notification requires a safe message")
            if self.artifact is not None and (
                self.artifact.tenant_id != self.tenant_id
                or self.artifact.task_id != self.task_id
                or self.artifact.task_revision != self.task_revision
                or self.artifact.task_projection_digest
                != self.task_projection_digest
                or self.artifact.contract_digest != self.contract_digest
                or self.artifact.result_revision != self.result_revision
                or self.artifact.result_digest != self.result_digest
                or self.artifact.content_bytes()
                != self.user_message.encode("utf-8")
            ):
                raise ValueError("artifact does not match the answered result")
        elif self.user_message is not None or self.artifact is not None:
            raise ValueError("only answered notifications may carry result content")
        expected_fingerprint = message_fingerprint(
            tenant_id=self.tenant_id,
            task_id=self.task_id,
            task_revision=self.task_revision,
            task_projection_digest=self.task_projection_digest,
            contract_digest=self.contract_digest,
            result_revision=self.result_revision,
            result_digest=self.result_digest,
            destination_ref=self.destination_ref,
            task_status=self.task_status,
            user_message=self.user_message,
            artifact=self.artifact,
        )
        if self.message_fingerprint != expected_fingerprint:
            raise ValueError("message fingerprint does not match its binding")
        if self.message_id != message_id_for(expected_fingerprint):
            raise ValueError("message id does not match its fingerprint")

        lease = (self.lease_id, self.lease_owner, self.lease_expires_at)
        if self.status is OutboxStatus.LEASED:
            if any(value is None for value in lease):
                raise ValueError("leased message requires a complete lease")
            if self.next_attempt_at is not None:
                raise ValueError("leased message cannot have next_attempt_at")
            if self.attempt_count < 1:
                raise ValueError("leased message requires an attempt")
            assert self.lease_expires_at is not None
            if self.lease_expires_at <= self.updated_at:
                raise ValueError("lease must expire after updated_at")
        elif any(value is not None for value in lease):
            raise ValueError("only leased messages may carry lease fields")

        if self.status is OutboxStatus.PENDING:
            if self.attempt_count >= self.max_attempts:
                raise ValueError("pending message has no attempts remaining")
        elif self.next_attempt_at is not None:
            raise ValueError("only pending messages may be scheduled")
        if self.attempt_count > self.max_attempts:
            raise ValueError("attempt_count exceeds max_attempts")
        return self


class DeliveryReceipt(BaseModel):
    """A receipt bound to one exact lease generation and attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: UUID
    tenant_id: str = Field(min_length=1, max_length=128)
    message_id: UUID
    lease_id: UUID
    attempt_count: StrictInt = Field(ge=1)
    receipt_type: ReceiptType
    received_at: datetime

    @field_validator("received_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        return value.astimezone(UTC)


class OutboxEnqueueResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created: bool
    task_revision: StrictInt = Field(ge=2)
    message: OutboxMessage

    @model_validator(mode="after")
    def validate_revision(self) -> "OutboxEnqueueResult":
        if self.task_revision != self.message.task_revision:
            raise ValueError("task revision does not match the message")
        return self


def message_fingerprint(
    *,
    tenant_id: str,
    task_id: UUID,
    task_revision: int,
    task_projection_digest: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    destination_ref: str,
    task_status: TaskStatus,
    user_message: str | None = None,
    artifact: OutboxArtifact | None = None,
) -> str:
    binding = {
            "contract_digest": contract_digest,
            "destination_ref": destination_ref,
            "result_digest": result_digest,
            "result_revision": result_revision,
            "task_id": str(task_id),
            "task_projection_digest": task_projection_digest,
            "task_revision": task_revision,
            "task_status": task_status.value,
            "template_id": "task_status",
            "tenant_id": tenant_id,
        }
    if user_message is not None:
        binding["user_message_digest"] = canonical_json_digest(
            {"user_message": user_message}
        )
    if artifact is not None:
        binding["artifact_fingerprint"] = artifact.artifact_fingerprint
    return canonical_json_digest(binding)


def message_id_for(fingerprint: str) -> UUID:
    return uuid5(_MESSAGE_NAMESPACE, fingerprint)


def artifact_fingerprint(
    *,
    tenant_id: str,
    task_id: UUID,
    task_revision: int,
    task_projection_digest: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str,
    filename: str,
    media_type: str,
    size: int,
    content_digest: str,
) -> str:
    return canonical_json_digest(
        {
            "tenant_id": tenant_id,
            "task_id": str(task_id),
            "task_revision": task_revision,
            "task_projection_digest": task_projection_digest,
            "contract_digest": contract_digest,
            "result_revision": result_revision,
            "result_digest": result_digest,
            "filename": filename,
            "media_type": media_type,
            "size": size,
            "content_digest": content_digest,
        }
    )


def artifact_id_for(fingerprint: str) -> UUID:
    return uuid5(_ARTIFACT_NAMESPACE, fingerprint)


def answer_artifact(
    *,
    tenant_id: str,
    task_id: UUID,
    task_revision: int,
    task_projection_digest: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str,
    user_message: str,
) -> OutboxArtifact:
    content = user_message.encode("utf-8")
    if not content or len(content) > _MAX_ARTIFACT_BYTES:
        raise ValueError("answer artifact is too large")
    filename = f"nobus-result-{task_id}.txt"
    media_type = "text/plain; charset=utf-8"
    content_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    fingerprint = artifact_fingerprint(
        tenant_id=tenant_id,
        task_id=task_id,
        task_revision=task_revision,
        task_projection_digest=task_projection_digest,
        contract_digest=contract_digest,
        result_revision=result_revision,
        result_digest=result_digest,
        filename=filename,
        media_type=media_type,
        size=len(content),
        content_digest=content_digest,
    )
    return OutboxArtifact(
        artifact_id=artifact_id_for(fingerprint),
        artifact_fingerprint=fingerprint,
        tenant_id=tenant_id,
        task_id=task_id,
        task_revision=task_revision,
        task_projection_digest=task_projection_digest,
        contract_digest=contract_digest,
        result_revision=result_revision,
        result_digest=result_digest,
        filename=filename,
        media_type=media_type,
        size=len(content),
        content_digest=content_digest,
        content_base64=base64.b64encode(content).decode("ascii"),
    )
