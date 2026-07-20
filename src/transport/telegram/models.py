"""Immutable models for Telegram ingress normalization."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


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
    role: str

    @field_validator("tenant_id", "role")
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


class TextMessage(IngressModel):
    """Normalized domain model for a text message."""

    update_id: int
    tenant_id: str
    actor_role: str
    user_id: int
    chat_id: int
    message_id: int
    text: str


class VoiceMessage(IngressModel):
    """Normalized domain model for a voice message (no download)."""

    update_id: int
    tenant_id: str
    actor_role: str
    user_id: int
    chat_id: int
    message_id: int
    file_id: str
    duration: int
    metadata: VoiceMetadata


class CallbackQuery(IngressModel):
    """Normalized callback containing only an opaque single-use token."""

    update_id: int
    tenant_id: str
    actor_role: str
    user_id: int
    chat_id: int
    query_id: str
    callback_token: str


class IngressResult(IngressModel):
    """Result of normalizing a raw Telegram update."""

    status: IngressStatus
    update_id: int | None
    payload: TextMessage | VoiceMessage | CallbackQuery | None = None
    reason: str | None = None
