"""Immutable models for Telegram ingress normalization."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts import IngressKind, IngressSource, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest


class IngressModel(BaseModel):
    """Strict immutable base for data crossing the ingress boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class IngressStatus(str, Enum):
    """Possible outcomes of processing a Telegram update."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IGNORED = "ignored"


class ActorBinding(IngressModel):
    """Server-owned binding for exactly one Telegram user/chat pair."""

    tenant_id: str
    actor_identity: str
    role: str
    auth_context_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    purpose: Literal["owner_private", "business_notes"] = "owner_private"

    @field_validator("tenant_id", "actor_identity", "role", "auth_context_ref")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("binding values must be non-empty strings")
        return value.strip()


class VoiceMetadata(IngressModel):
    """Allowlisted Telegram metadata; arbitrary fields never cross ingress."""

    file_unique_id: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class ActorBoundIngress(IngressModel):
    """Identity fields copied only from one exact server-side binding."""

    update_id: int
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    user_id: int
    chat_id: int
    message_thread_id: int | None = Field(default=None, gt=0)
    reply_to_message_id: int | None = Field(default=None, gt=0)
    binding_purpose: Literal["owner_private", "business_notes"] = (
        "owner_private"
    )

    @field_validator("tenant_id", "actor_identity", "actor_role")
    @classmethod
    def normalize_identity_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("identity values must be non-empty strings")
        return value.strip()


class TextMessage(ActorBoundIngress):
    """Normalized domain model for a text message."""

    message_id: int
    text: str


class VoiceMessage(ActorBoundIngress):
    """Normalized domain model for a voice message (no download)."""

    message_id: int
    file_id: str
    duration: int
    metadata: VoiceMetadata


class CallbackQuery(ActorBoundIngress):
    """Normalized callback containing only an opaque single-use token."""

    message_id: int
    query_id: str
    callback_token: str


TelegramPayload: TypeAlias = TextMessage | VoiceMessage | CallbackQuery


def _telegram_payload_facts(payload: TelegramPayload) -> dict[str, object]:
    """Derive non-authoritative fingerprints used to verify one payload binding."""
    topic = (
        f":thread:{payload.message_thread_id}"
        if payload.message_thread_id is not None
        else ""
    )
    if type(payload) is TextMessage:
        kind = IngressKind.TEXT
        external_message_id = (
            f"update:{payload.update_id}:user:{payload.user_id}:"
            f"chat:{payload.chat_id}{topic}:"
            f"message:{payload.message_id}"
        )
        content = {"text": payload.text}
    elif type(payload) is VoiceMessage:
        kind = IngressKind.VOICE_PREVIEW
        external_message_id = (
            f"update:{payload.update_id}:user:{payload.user_id}:"
            f"chat:{payload.chat_id}{topic}:"
            f"message:{payload.message_id}"
        )
        content = {
            "duration": payload.duration,
            "file_id": payload.file_id,
            "metadata": payload.metadata.model_dump(mode="json"),
        }
    elif type(payload) is CallbackQuery:
        kind = IngressKind.CALLBACK
        external_message_id = (
            f"update:{payload.update_id}:user:{payload.user_id}:"
            f"chat:{payload.chat_id}{topic}:"
            f"callback:{payload.query_id}"
        )
        content = {
            "callback_token": payload.callback_token,
            "message_id": payload.message_id,
        }
    else:
        raise TypeError("unsupported Telegram payload")

    if payload.reply_to_message_id is not None:
        content["reply_to_message_id"] = payload.reply_to_message_id

    if payload.binding_purpose == "business_notes":
        external_message_id += ":purpose:business_notes"
        content["binding_purpose"] = "business_notes"

    source = IngressSource.TELEGRAM
    return {
        "source": source,
        "kind": kind,
        "external_message_id": external_message_id,
        "idempotency_key": canonical_json_digest(
            {
                "actor_identity": payload.actor_identity,
                "actor_role": payload.actor_role,
                "external_message_id": external_message_id,
                "kind": kind.value,
                "source": source.value,
                "tenant_id": payload.tenant_id,
            }
        ),
        "content_ref": canonical_json_digest(content),
    }


class IngressResult(IngressModel):
    """Result of normalizing a raw Telegram update."""

    status: IngressStatus
    update_id: int | None
    payload: TextMessage | VoiceMessage | CallbackQuery | None = None
    reason: str | None = None


class TrustedIngressResult(IngressResult):
    """Public ingress result minted atomically from one raw update."""

    envelope: TrustedIngressEnvelope | None = None

    @model_validator(mode="after")
    def validate_envelope_binding(self) -> "TrustedIngressResult":
        if self.status != IngressStatus.ACCEPTED:
            if self.envelope is not None:
                raise ValueError("non-accepted ingress cannot carry an envelope")
            return self
        if self.payload is None or self.envelope is None:
            raise ValueError("accepted ingress requires payload and envelope")
        facts = _telegram_payload_facts(self.payload)
        expected = {
            "tenant_id": self.payload.tenant_id,
            "actor_identity": self.payload.actor_identity,
            "auth_context_ref": self.payload.auth_context_ref,
            **facts,
        }
        actual = self.envelope.model_dump(
            include={
                "tenant_id",
                "actor_identity",
                "auth_context_ref",
                "source",
                "kind",
                "external_message_id",
                "idempotency_key",
                "content_ref",
            }
        )
        if self.update_id != self.payload.update_id or actual != expected:
            raise ValueError("accepted ingress envelope binding mismatch")
        return self
