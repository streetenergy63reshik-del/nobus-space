from __future__ import annotations

import json

import pytest

from scripts.bind_business_notes import _candidate, _v2_config
from src.transport.telegram.bindings import (
    StoredActorBinding,
    TelegramBindingConfig,
    TelegramChallengeProof,
    _proof_digest,
)


def _config() -> TelegramBindingConfig:
    item = StoredActorBinding(
        user_id=42,
        chat_id=42,
        tenant_id="owner",
        actor_identity="telegram:owner",
        role="owner",
        auth_context_ref="sha256:" + "0" * 64,
        proof=TelegramChallengeProof(
            kind="telegram_owner_challenge_v1",
            update_id=1,
            challenge_digest="sha256:" + "1" * 64,
        ),
    )
    draft = TelegramBindingConfig(
        version=1,
        bot_id=99,
        bot_username="Nobusspacebot",
        bindings=[item],
    )
    return draft.model_copy(
        update={
            "bindings": (
                item.model_copy(
                    update={"auth_context_ref": _proof_digest(draft, item)}
                ),
            )
        }
    )


def _update(
    update_id: int,
    *,
    user_id: int = 42,
    chat_id: int = -1001,
    title: str = "Заметки бизнеса",
    text: str = "#NOBUS-BIND-NOTES",
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "from": {"id": user_id},
            "chat": {
                "id": chat_id,
                "type": "supergroup",
                "title": title,
            },
            "text": text,
        },
    }


def test_candidate_requires_exact_owner_marker_title_and_group() -> None:
    updates = [
        _update(1, user_id=7),
        _update(2, title="Другая группа"),
        _update(3, text="#wrong"),
        _update(4),
    ]

    assert _candidate(updates, owner_user_id=42) == (4, -1001)


def test_candidate_rejects_ambiguous_group_ids() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        _candidate(
            [_update(1, chat_id=-1001), _update(2, chat_id=-1002)],
            owner_user_id=42,
        )


def test_v2_config_preserves_owner_and_adds_proof_bound_notes() -> None:
    updated = _v2_config(_config(), update_id=77, chat_id=-1001)

    assert updated.version == 2
    assert [item.purpose for item in updated.bindings] == [
        "owner_private",
        "business_notes",
    ]
    assert updated.bindings[1].chat_id == -1001
    assert all(
        item.auth_context_ref == _proof_digest(updated, item)
        for item in updated.bindings
    )
    serialized = json.dumps(updated.model_dump(mode="json"))
    assert "#NOBUS-BIND-NOTES" not in serialized
