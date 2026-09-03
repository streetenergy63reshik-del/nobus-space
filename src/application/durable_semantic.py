"""Restart-safe semantic clarification state backed by encrypted SQLite."""

from __future__ import annotations

import json
from datetime import timedelta

from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.semantic_admission import PendingClarification
from src.contracts.models import canonical_json_digest


class DurableSemanticClarificationStore:
    def __init__(self, state: SQLiteTelegramState) -> None:
        if not isinstance(state, SQLiteTelegramState):
            raise ValueError("durable semantic clarification state is invalid")
        self._state = state
        self._ttl = timedelta(minutes=10)

    @property
    def ttl(self) -> timedelta:
        return self._ttl

    def put(self, pending: PendingClarification) -> None:
        if not isinstance(pending, PendingClarification):
            raise ValueError("pending clarification is invalid")
        payload = pending.model_dump(mode="json")
        self._state.put_semantic_clarification(
            owner_binding=pending.owner_binding,
            tenant_id=pending.tenant_binding,
            tenant_binding=pending.tenant_binding,
            conversation_binding=pending.conversation_binding,
            answer_binding=pending.answer_binding,
            envelope_revision=pending.envelope_revision,
            intake_revision=pending.intake_revision,
            payload=payload,
            expires_at=pending.expires_at,
        )

    def read(
        self,
        *,
        owner_binding: str,
        tenant_binding: str,
        conversation_binding: str,
        answer_binding: str,
        reply_envelope_revision: str,
    ) -> PendingClarification | None:
        payload = self._state.read_semantic_clarification(
            owner_binding=owner_binding,
            tenant_id=tenant_binding,
            tenant_binding=tenant_binding,
            conversation_binding=conversation_binding,
            answer_binding=answer_binding,
            reply_envelope_revision=reply_envelope_revision,
        )
        if payload is None:
            return None
        pending = PendingClarification.model_validate_json(
            json.dumps(payload, allow_nan=False, ensure_ascii=False)
        )
        if (
            pending.owner_binding != owner_binding
            or pending.tenant_binding != tenant_binding
            or pending.conversation_binding != conversation_binding
            or pending.answer_binding != answer_binding
        ):
            raise ValueError("durable semantic clarification is invalid")
        return pending

    def delete(self, pending: PendingClarification) -> bool:
        if not isinstance(pending, PendingClarification):
            return False
        payload = pending.model_dump(mode="json")
        return self._state.delete_semantic_clarification(
            conversation_binding=pending.conversation_binding,
            tenant_id=pending.tenant_binding,
            payload_digest=canonical_json_digest(payload),
        )
