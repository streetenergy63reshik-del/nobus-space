"""Restart-safe Telegram confirmation stores backed by encrypted SQLite."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import SecretStr

from src.application import patch_confirmation as patch_state
from src.application import task_confirmation as task_state
from src.application import telegram_actions as action_state
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.durable_runtime import PreparedTask
from src.contracts import TaskContract, TrustedIngressEnvelope
from src.transport.telegram import CallbackQuery


def _digest(token: str) -> str:
    return f"sha256:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


class DurableTaskConfirmationStore(task_state.InMemoryTaskConfirmationStore):
    """Use the proven in-memory policy and hydrate its encrypted binding on demand."""

    def __init__(self, state: SQLiteTelegramState, **values: object) -> None:
        if not isinstance(state, SQLiteTelegramState):
            raise ValueError("durable task confirmation state is invalid")
        super().__init__(**values)  # type: ignore[arg-type]
        self._durable_state = state

    def issue(self, **values: object) -> task_state.TaskConfirmationChallenge:
        challenge = super().issue(**values)  # type: ignore[arg-type]
        token = challenge.confirmation_token.get_secret_value()
        digest = _digest(token)
        with self._lock:
            binding = self._entries[digest]
            payload = {
                "prepared": {
                    "contract": binding.prepared.contract.model_dump(mode="json"),
                    "envelope_revision": binding.prepared.envelope_revision,
                },
                "envelope": binding.envelope.model_dump(mode="json"),
                "tenant_id": binding.tenant_id,
                "actor_identity": binding.actor_identity,
                "actor_role": binding.actor_role,
                "auth_context_ref": binding.auth_context_ref,
                "user_id": binding.user_id,
                "chat_id": binding.chat_id,
                "request_key": list(binding.request_key),
                "request_digest": binding.request_digest,
                "instruction": binding.instruction,
                "token": token,
                "issued_at": binding.issued_at.isoformat(),
                "expires_at": binding.expires_at.isoformat(),
            }
        try:
            self._durable_state.put_capability(
                kind="task",
                token_digest=digest,
                tenant_id=binding.tenant_id,
                payload=payload,
                expires_at=binding.expires_at + self._retention,
            )
        except Exception:
            with self._lock:
                self._entries.pop(digest, None)
                self._requests.pop(binding.request_key, None)
            raise
        return challenge

    def consume(self, **values: object) -> task_state.TaskConfirmationResult:
        token = values.get("token")
        message = values.get("message")
        if isinstance(token, str) and isinstance(
            message, (task_state.TextMessage, task_state.CallbackQuery)
        ):
            self._hydrate(token, message.tenant_id)
        return super().consume(**values)  # type: ignore[arg-type]

    def acknowledge(self, token: str, tenant_id: str) -> bool:
        return self._durable_state.delete_capability(
            kind="task",
            token_digest=_digest(token),
            tenant_id=tenant_id,
        )

    def release(self, token: str, tenant_id: str) -> None:
        digest = _digest(token)
        with self._lock:
            self._tombstones.pop(digest, None)
        self._hydrate(token, tenant_id)

    def _hydrate(self, token: str, tenant_id: str) -> None:
        digest = _digest(token)
        with self._lock:
            if digest in self._entries or digest in self._tombstones:
                return
        payload = self._durable_state.read_capability(
            kind="task", token_digest=digest, tenant_id=tenant_id
        )
        if payload is None:
            return
        try:
            prepared_data = payload["prepared"]
            prepared = PreparedTask(
                contract=TaskContract.model_validate(prepared_data["contract"]),
                envelope_revision=prepared_data["envelope_revision"],
            )
            request_key = tuple(payload["request_key"])
            if len(request_key) != 2:
                raise ValueError
            binding = task_state._Binding(
                prepared=PreparedTask.validate(prepared),
                envelope=TrustedIngressEnvelope.model_validate(payload["envelope"]),
                tenant_id=payload["tenant_id"],
                actor_identity=payload["actor_identity"],
                actor_role=payload["actor_role"],
                auth_context_ref=payload["auth_context_ref"],
                user_id=payload["user_id"],
                chat_id=payload["chat_id"],
                request_key=(request_key[0], request_key[1]),
                request_digest=payload["request_digest"],
                instruction=payload["instruction"],
                token=SecretStr(payload["token"]),
                issued_at=datetime.fromisoformat(payload["issued_at"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
            if (
                binding.tenant_id != tenant_id
                or payload["token"] != token
                or binding.envelope.tenant_id != binding.tenant_id
                or binding.envelope.actor_identity != binding.actor_identity
                or binding.envelope.auth_context_ref != binding.auth_context_ref
                or binding.prepared.contract.tenant_id != binding.tenant_id
                or binding.prepared.contract.idempotency_key
                != binding.envelope.idempotency_key
                or binding.prepared.envelope_revision
                != binding.envelope.envelope_revision
            ):
                raise ValueError
        except Exception:
            raise ValueError("durable task confirmation is invalid") from None
        with self._lock:
            self._entries[digest] = binding
            self._requests[binding.request_key] = digest


class DurablePatchConfirmationStore(patch_state.InMemoryPatchConfirmationStore):
    """Persist exact patch proposals encrypted until apply, cancel or expiry."""

    def __init__(self, state: SQLiteTelegramState, **values: object) -> None:
        if not isinstance(state, SQLiteTelegramState):
            raise ValueError("durable patch confirmation state is invalid")
        super().__init__(**values)  # type: ignore[arg-type]
        self._durable_state = state

    def issue(self, **values: object) -> patch_state.PatchConfirmationChallenge:
        challenge = super().issue(**values)  # type: ignore[arg-type]
        token = challenge.confirmation_token.get_secret_value()
        digest = _digest(token)
        with self._lock:
            entry = self._entries[digest]
            payload = {
                "proposal": entry.proposal.model_dump(mode="json"),
                "token": token,
                "tenant_id": entry.tenant_id,
                "actor_identity": entry.actor_identity,
                "actor_role": entry.actor_role,
                "auth_context_ref": entry.auth_context_ref,
                "user_id": entry.user_id,
                "chat_id": entry.chat_id,
                "request_key": list(entry.request_key),
                "request_digest": entry.request_digest,
                "issued_at": entry.issued_at.isoformat(),
                "expires_at": entry.expires_at.isoformat(),
            }
        try:
            self._durable_state.put_capability(
                kind="patch",
                token_digest=digest,
                tenant_id=entry.tenant_id,
                payload=payload,
                expires_at=entry.expires_at,
            )
        except Exception:
            with self._lock:
                self._entries.pop(digest, None)
                self._requests.pop(entry.request_key, None)
            raise
        return challenge

    def consume(self, **values: object) -> patch_state.PatchConfirmationResult:
        token = values.get("token")
        message = values.get("message")
        if isinstance(token, str) and isinstance(
            message, (patch_state.TextMessage, patch_state.CallbackQuery)
        ):
            self._hydrate(token, message.tenant_id)
        result = super().consume(**values)  # type: ignore[arg-type]
        if (
            isinstance(token, str)
            and isinstance(message, (patch_state.TextMessage, patch_state.CallbackQuery))
            and result.status is patch_state.PatchConfirmationStatus.EXPIRED
        ):
            self._durable_state.delete_capability(
                kind="patch",
                token_digest=_digest(token),
                tenant_id=message.tenant_id,
            )
        return result

    def acknowledge(self, token: str, tenant_id: str) -> bool:
        return self._durable_state.delete_capability(
            kind="patch",
            token_digest=_digest(token),
            tenant_id=tenant_id,
        )

    def release(self, token: str, tenant_id: str) -> None:
        digest = _digest(token)
        with self._lock:
            self._tombstones.pop(digest, None)
        self._hydrate(token, tenant_id)

    def _hydrate(self, token: str, tenant_id: str) -> None:
        digest = _digest(token)
        with self._lock:
            if digest in self._entries or digest in self._tombstones:
                return
        payload = self._durable_state.read_capability(
            kind="patch", token_digest=digest, tenant_id=tenant_id
        )
        if payload is None:
            return
        try:
            request_key = tuple(payload["request_key"])
            entry = patch_state._Entry(
                proposal=patch_state.PatchProposal.model_validate(payload["proposal"]),
                token=SecretStr(payload["token"]),
                tenant_id=payload["tenant_id"],
                actor_identity=payload["actor_identity"],
                actor_role=payload["actor_role"],
                auth_context_ref=payload["auth_context_ref"],
                user_id=payload["user_id"],
                chat_id=payload["chat_id"],
                request_key=(request_key[0], request_key[1]),
                request_digest=payload["request_digest"],
                issued_at=datetime.fromisoformat(payload["issued_at"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
            if len(request_key) != 2 or entry.tenant_id != tenant_id or payload["token"] != token:
                raise ValueError
        except Exception:
            raise ValueError("durable patch confirmation is invalid") from None
        with self._lock:
            self._entries[digest] = entry
            self._requests[entry.request_key] = digest


class DurableTelegramActionStore(action_state.InMemoryTelegramActionStore):
    """Restore Telegram callback routing before the gateway claims a token."""

    def __init__(self, state: SQLiteTelegramState) -> None:
        if not isinstance(state, SQLiteTelegramState):
            raise ValueError("durable Telegram action state is invalid")
        super().__init__()
        self._durable_state = state

    def issue(self, **values: object) -> str:
        token = super().issue(**values)  # type: ignore[arg-type]
        with self._lock:
            binding = self._issued[token]
            payload = {
                "token": token,
                "action": binding.action.value,
                "capability_token": binding.capability_token,
                "user_id": binding.user_id,
                "chat_id": binding.chat_id,
                "expires_at": binding.expires_at.isoformat(),
            }
        try:
            self._durable_state.put_capability(
                kind="action",
                token_digest=_digest(token),
                tenant_id="owner",
                payload=payload,
                expires_at=binding.expires_at,
            )
        except Exception:
            with self._lock:
                self._issued.pop(token, None)
            raise
        return token

    def claim(self, token: str, user_id: int, chat_id: int) -> bool:
        self._hydrate(token)
        return super().claim(token, user_id, chat_id)

    def commit(self, callback: CallbackQuery) -> bool:
        committed = super().commit(callback)
        if committed:
            self._durable_state.delete_capability(
                kind="action",
                token_digest=_digest(callback.callback_token),
                tenant_id="owner",
            )
        return committed

    def _hydrate(self, token: str) -> None:
        with self._lock:
            if token in self._issued:
                return
        payload = self._durable_state.read_capability(
            kind="action", token_digest=_digest(token), tenant_id="owner"
        )
        if payload is None:
            return
        try:
            binding = action_state._Binding(
                action=action_state.TelegramAction(payload["action"]),
                capability_token=payload["capability_token"],
                user_id=payload["user_id"],
                chat_id=payload["chat_id"],
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
            if payload["token"] != token:
                raise ValueError
        except Exception:
            raise ValueError("durable Telegram action is invalid") from None
        with self._lock:
            self._issued[token] = binding
