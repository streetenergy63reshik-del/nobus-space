"""Adversarial tests for local Telegram actor bindings."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.transport.telegram import bindings as binding_module
from src.transport.telegram.bindings import (
    TelegramBindingError,
    load_telegram_bindings,
)


BOT_ID = 123
BOT_USERNAME = "Nobusspacebot"
USER_ID = 42
UPDATE_ID = 10
CHALLENGE_DIGEST = "sha256:" + "a" * 64


def config() -> dict[str, Any]:
    proof_payload = {
        "actor_identity": "telegram:owner",
        "bot_id": BOT_ID,
        "bot_username": BOT_USERNAME,
        "challenge_digest": CHALLENGE_DIGEST,
        "chat_id": USER_ID,
        "proof": "telegram_owner_challenge_v1",
        "role": "owner",
        "schema_version": 1,
        "tenant_id": "owner",
        "update_id": UPDATE_ID,
        "user_id": USER_ID,
    }
    auth_ref = "sha256:" + hashlib.sha256(
        json.dumps(proof_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "version": 1,
        "bot_id": BOT_ID,
        "bot_username": BOT_USERNAME,
        "bindings": [
            {
                "user_id": USER_ID,
                "chat_id": USER_ID,
                "tenant_id": "owner",
                "actor_identity": "telegram:owner",
                "role": "owner",
                "auth_context_ref": auth_ref,
                "proof": {
                    "kind": "telegram_owner_challenge_v1",
                    "update_id": UPDATE_ID,
                    "challenge_digest": CHALLENGE_DIGEST,
                },
            }
        ],
    }


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def load(path: Path, **overrides: Any) -> Any:
    options = {
        "expected_bot_id": BOT_ID,
        "expected_bot_username": "@nobusspacebot",
        "expected_tenant_id": "owner",
        "expected_actor_identity": "telegram:owner",
        "expected_role": "owner",
        **overrides,
    }
    return load_telegram_bindings(path, **options)


def test_loads_exact_immutable_actor_binding(tmp_path: Path) -> None:
    path = tmp_path / "bindings.json"
    write(path, config())
    bindings = load(path)
    assert tuple(bindings) == ((USER_ID, USER_ID),)
    assert bindings[(USER_ID, USER_ID)].tenant_id == "owner"
    with pytest.raises(TypeError):
        bindings[(99, 99)] = bindings[(USER_ID, USER_ID)]  # type: ignore[index]


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("bot_id", 999, {}),
        ("bot_username", "OtherBot", {}),
        ("tenant_id", "tenant-b", {}),
        ("actor_identity", "telegram:admin", {}),
        ("role", "admin", {}),
        ("role", "owner", {"expected_role": "admin"}),
    ],
)
def test_rejects_identity_or_authorization_tamper(
    tmp_path: Path,
    field: str,
    value: object,
    expected: dict[str, object],
) -> None:
    data = config()
    if field in {"bot_id", "bot_username"}:
        data[field] = value
    else:
        data["bindings"][0][field] = value
    path = tmp_path / "bindings.json"
    write(path, data)
    with pytest.raises(TelegramBindingError) as caught:
        load(path, **expected)
    assert caught.value.code == "telegram_binding_configuration_invalid"


@pytest.mark.parametrize("mutation", ["auth", "chat", "duplicate"])
def test_rejects_proof_tamper_and_duplicate_pairs(tmp_path: Path, mutation: str) -> None:
    data = config()
    binding = data["bindings"][0]
    if mutation == "auth":
        binding["auth_context_ref"] = "sha256:" + "b" * 64
    elif mutation == "chat":
        binding["chat_id"] = 99
    else:
        data["bindings"].append(dict(binding))
    path = tmp_path / "bindings.json"
    write(path, data)
    with pytest.raises(TelegramBindingError):
        load(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("bot_id", True),
        ("user_id", True),
        ("chat_id", True),
        ("update_id", True),
    ],
)
def test_rejects_bool_for_every_integer_field(
    tmp_path: Path, field: str, value: object
) -> None:
    data = config()
    if field in {"version", "bot_id"}:
        data[field] = value
    elif field == "update_id":
        data["bindings"][0]["proof"][field] = value
    else:
        data["bindings"][0][field] = value
    path = tmp_path / "bindings.json"
    write(path, data)
    with pytest.raises(TelegramBindingError):
        load(path)


@pytest.mark.parametrize("value", [" owner", "owner ", "own\x00er", "own\ner"])
def test_rejects_noncanonical_authorization_text(tmp_path: Path, value: str) -> None:
    data = config()
    data["bindings"][0]["role"] = value
    path = tmp_path / "bindings.json"
    write(path, data)
    with pytest.raises(TelegramBindingError):
        load(path)


def test_rejects_duplicate_key_and_oversized_file(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"version":1,"version":1}', encoding="utf-8")
    with pytest.raises(TelegramBindingError) as caught:
        load(duplicate)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert str(duplicate) not in str(caught.value)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (64 * 1024 + 1))
    with pytest.raises(TelegramBindingError) as caught:
        load(oversized)
    assert caught.value.code == "telegram_binding_unavailable"


def test_rejects_symlink_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    link = tmp_path / "link.json"
    write(target, config())
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(TelegramBindingError):
        load(link)


def test_rejects_path_identity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bindings.json"
    write(path, config())
    real_stat = os.stat
    calls = 0

    def changing_stat(target: object, *, follow_symlinks: bool = True) -> Any:
        nonlocal calls
        value = real_stat(target, follow_symlinks=follow_symlinks)
        calls += 1
        if calls == 2:
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_dev=value.st_dev,
                st_ino=value.st_ino + 1,
                st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns,
            )
        return value

    monkeypatch.setattr(binding_module.os, "stat", changing_stat)
    with pytest.raises(TelegramBindingError) as caught:
        load(path)
    assert caught.value.code == "telegram_binding_unavailable"
