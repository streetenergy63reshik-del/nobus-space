"""Strict local server-side Telegram actor binding loader.

The operator-owned file and its OS permissions are the local trust root. The
unkeyed digest binds approved fields against accidental or partial tampering;
it is not a signature against an attacker who can rewrite the whole file.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .models import ActorBinding


_MAX_CONFIG_BYTES = 64 * 1024
_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_ERROR_MESSAGES = {
    "telegram_binding_configuration_invalid": "Telegram binding configuration is invalid.",
    "telegram_binding_unavailable": "Telegram binding configuration is unavailable.",
}


class TelegramBindingError(RuntimeError):
    """Stable public failure containing no path, identifier or raw payload."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


class BindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TelegramChallengeProof(BindingModel):
    kind: Literal["telegram_owner_challenge_v1"]
    update_id: int = Field(ge=0)
    challenge_digest: str = Field(pattern=_DIGEST_PATTERN)


class StoredActorBinding(BindingModel):
    user_id: int = Field(gt=0)
    chat_id: int = Field(gt=0)
    tenant_id: str = Field(min_length=1, max_length=128)
    actor_identity: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=64)
    auth_context_ref: str = Field(pattern=_DIGEST_PATTERN)
    proof: TelegramChallengeProof

    @field_validator("tenant_id", "actor_identity", "role")
    @classmethod
    def canonical_authorization_text(cls, value: str) -> str:
        if not _canonical_text(value):
            raise ValueError("authorization text is not canonical")
        return value


class TelegramBindingConfig(BindingModel):
    version: Literal[1]
    bot_id: int = Field(gt=0)
    bot_username: str = Field(min_length=5, max_length=64)
    bindings: tuple[StoredActorBinding, ...] = Field(min_length=1, max_length=32)

    @field_validator("version", mode="before")
    @classmethod
    def strict_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value

    @field_validator("bot_username")
    @classmethod
    def canonical_bot_username(cls, value: str) -> str:
        if (
            not _canonical_text(value)
            or value.startswith("@")
            or not value.replace("_", "").isalnum()
        ):
            raise ValueError("bot username is not canonical")
        return value

    @field_validator("bindings", mode="before")
    @classmethod
    def freeze_json_bindings(cls, value: Any) -> tuple[Any, ...]:
        if type(value) is not list:
            raise ValueError("bindings must be a JSON array")
        return tuple(value)

    @model_validator(mode="after")
    def exact_pairs_are_unique(self) -> "TelegramBindingConfig":
        pairs = [(item.user_id, item.chat_id) for item in self.bindings]
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate Telegram user/chat binding")
        return self


def load_telegram_bindings(
    path: Path,
    *,
    expected_bot_id: int,
    expected_bot_username: str,
    expected_tenant_id: str,
    expected_actor_identity: str,
    expected_role: str,
) -> MappingProxyType[tuple[int, int], ActorBinding]:
    """Load a bounded exact-pair allowlist and verify all approved fields."""

    expected_username = (
        expected_bot_username.removeprefix("@")
        if isinstance(expected_bot_username, str)
        else ""
    )
    if (
        not isinstance(path, Path)
        or type(expected_bot_id) is not int
        or expected_bot_id <= 0
        or not _canonical_text(expected_username, 64)
        or not _canonical_text(expected_tenant_id, 128)
        or not _canonical_text(expected_actor_identity, 256)
        or not _canonical_text(expected_role, 64)
    ):
        raise TelegramBindingError("telegram_binding_configuration_invalid")

    raw = _read_bounded_regular_file(path)
    config: TelegramBindingConfig | None = None
    failed = False
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
        )
        config = TelegramBindingConfig.model_validate(value)
    except (UnicodeError, ValueError, ValidationError):
        failed = True
    if failed or config is None:
        raise TelegramBindingError("telegram_binding_configuration_invalid")
    if (
        config.bot_id != expected_bot_id
        or config.bot_username.casefold() != expected_username.casefold()
    ):
        raise TelegramBindingError("telegram_binding_configuration_invalid")

    bindings: dict[tuple[int, int], ActorBinding] = {}
    for item in config.bindings:
        if (
            item.user_id != item.chat_id
            or item.tenant_id != expected_tenant_id
            or item.actor_identity != expected_actor_identity
            or item.role != expected_role
            or item.auth_context_ref != _proof_digest(config, item)
        ):
            raise TelegramBindingError("telegram_binding_configuration_invalid")
        bindings[(item.user_id, item.chat_id)] = ActorBinding(
            tenant_id=item.tenant_id,
            actor_identity=item.actor_identity,
            role=item.role,
            auth_context_ref=item.auth_context_ref,
        )
    return MappingProxyType(bindings)


def _read_bounded_regular_file(path: Path) -> bytes:
    raw: bytes | None = None
    descriptor = -1
    failed = False
    try:
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_CONFIG_BYTES:
            failed = True
        if not failed:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
            descriptor = os.open(path, flags)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > _MAX_CONFIG_BYTES
                or _file_identity(before) != _file_identity(opened)
                or _file_version(before) != _file_version(opened)
            ):
                failed = True
        chunks: list[bytes] = []
        remaining = _MAX_CONFIG_BYTES + 1
        while not failed and remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if not failed:
            raw = b"".join(chunks)
            after_opened = os.fstat(descriptor)
            after_path = os.stat(path, follow_symlinks=False)
            if (
                len(raw) > _MAX_CONFIG_BYTES
                or not stat.S_ISREG(after_path.st_mode)
                or _file_identity(opened) != _file_identity(after_opened)
                or _file_identity(after_opened) != _file_identity(after_path)
                or _file_version(opened) != _file_version(after_opened)
                or _file_version(after_opened) != _file_version(after_path)
            ):
                failed = True
    except (OSError, ValueError):
        failed = True
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                failed = True
    if failed or raw is None or not raw:
        raise TelegramBindingError("telegram_binding_unavailable")
    return raw


def _proof_digest(config: TelegramBindingConfig, item: StoredActorBinding) -> str:
    payload = {
        "actor_identity": item.actor_identity,
        "bot_id": config.bot_id,
        "bot_username": config.bot_username,
        "challenge_digest": item.proof.challenge_digest,
        "chat_id": item.chat_id,
        "proof": item.proof.kind,
        "role": item.role,
        "schema_version": config.version,
        "tenant_id": item.tenant_id,
        "update_id": item.proof.update_id,
        "user_id": item.user_id,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _file_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _file_version(value: os.stat_result) -> tuple[int, int]:
    return value.st_size, value.st_mtime_ns


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _canonical_text(value: object, limit: int = 256) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= limit
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
    )
