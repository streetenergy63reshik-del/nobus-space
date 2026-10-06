"""Adapter to the installed nobus-send-results document delivery owner."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

from src.contracts.models import canonical_json_digest


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class NobusDocumentDeliveryError(RuntimeError):
    """Stable integration error without destination or artifact contents."""


@dataclass(frozen=True, slots=True)
class NobusDocumentDeliveryReceipt:
    status: str
    message_id: int | None
    delivery_key: str


class NobusDocumentDelivery:
    """Use the installed skill runtime and its one shared one-shot ledger."""

    def __init__(
        self, *, runtime_path: Path, ledger_path: Path,
        bot_id: int, bot_username: str, group_binding_ref: str,
        group_chat_id: int, group_tenant_id: str,
    ) -> None:
        path = Path(runtime_path).resolve(strict=True)
        ledger = Path(ledger_path).resolve(strict=False)
        if (
            not _regular_unlinked_file(path)
            or path.name != "telegram_delivery_runtime.py"
            or not ledger.is_absolute()
            or not ledger.parent.is_dir()
            or ledger.parent.is_symlink()
        ):
            raise ValueError("Nobus document delivery configuration is invalid")
        module = _load_runtime(path)
        required = (
            "SQLiteTelegramDocumentDeliveryLedger",
            "TelegramDocumentDestination",
            "TelegramDocumentDeliveryError",
            "deliver_document_once",
            "delivery_key_for",
        )
        if not all(hasattr(module, name) for name in required):
            raise ValueError("Nobus document delivery runtime is incompatible")
        if (
            "operation_key" not in inspect.signature(module.delivery_key_for).parameters
            or "operation_key" not in inspect.signature(module.deliver_document_once).parameters
            or not hasattr(module.SQLiteTelegramDocumentDeliveryLedger, "receipt")
        ):
            raise ValueError("Nobus document delivery runtime lacks operation receipts")
        if (
            type(bot_id) is not int or bot_id <= 0
            or not isinstance(bot_username, str) or not bot_username.strip()
            or not isinstance(group_binding_ref, str)
            or _DIGEST.fullmatch(group_binding_ref) is None
            or type(group_chat_id) is not int or group_chat_id >= 0
            or not isinstance(group_tenant_id, str) or not group_tenant_id.strip()
        ):
            raise ValueError("Nobus document destination proof is invalid")
        self._module = module
        self._ledger = module.SQLiteTelegramDocumentDeliveryLedger(ledger)
        self._bot_id = bot_id
        self._bot_username = bot_username
        self._group_binding_ref = group_binding_ref
        self._group_chat_id = group_chat_id
        self._group_tenant_id = group_tenant_id

    async def deliver(
        self,
        *,
        api: object,
        request_id: UUID,
        operation_id: str,
        tenant_id: str,
        chat_id: int,
        topic_id: int | None,
        filename: str,
        content: bytes,
    ) -> NobusDocumentDeliveryReceipt:
        if (
            not isinstance(request_id, UUID)
            or not isinstance(operation_id, str)
            or _DIGEST.fullmatch(operation_id) is None
            or not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or tenant_id != self._group_tenant_id
            or type(chat_id) is not int
            or chat_id != self._group_chat_id
            or (topic_id is not None and (type(topic_id) is not int or topic_id <= 0))
            or not isinstance(filename, str)
            or type(content) is not bytes
            or not content
        ):
            raise ValueError("Nobus document delivery request is invalid")
        artifact_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        # Match the established proof-bound alias semantics: destination_ref
        # identifies only the bot, verified group binding and exact topic.
        destination_payload = {
            "alias": "business_notes.prostranstvo",
            "binding_auth_context_ref": self._group_binding_ref,
            "binding_purpose": "business_notes",
            "bot_id": self._bot_id,
            "bot_username": self._bot_username,
            "message_thread_id": topic_id,
            "schema_version": 1,
            "tenant_id": tenant_id,
        }
        destination_ref = "sha256:" + hashlib.sha256(
            json.dumps(
                destination_payload, ensure_ascii=True, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        scoped_operation = canonical_json_digest({
            "schema": "nobus-desktop-delivery-operation-v1",
            "request_id": str(request_id),
            "operation_id": operation_id,
        })
        delivery_key = self._module.delivery_key_for(
            destination_ref, artifact_digest, operation_key=scoped_operation
        )
        existing = self._ledger.receipt(delivery_key)
        if existing is not None:
            return NobusDocumentDeliveryReceipt(
                status="sent_existing" if existing[0] == "sent" and type(existing[1]) is int else "unknown_existing",
                message_id=existing[1] if existing[0] == "sent" and type(existing[1]) is int else None,
                delivery_key=delivery_key,
            )
        destination = self._module.TelegramDocumentDestination(
            alias="business_notes.prostranstvo",
            tenant_id=tenant_id.strip(),
            chat_id=chat_id,
            message_thread_id=topic_id,
            destination_ref=destination_ref,
        )
        try:
            message_id = await self._module.deliver_document_once(
                api=api,
                ledger=self._ledger,
                destination=destination,
                filename=filename,
                content=content,
                artifact_digest=artifact_digest,
                operation_key=scoped_operation,
            )
        except self._module.TelegramDocumentDeliveryError as error:
            outcome = self._ledger.receipt(delivery_key)
            if outcome is not None:
                return NobusDocumentDeliveryReceipt(
                    status="sent_existing" if outcome[0] == "sent" and type(outcome[1]) is int else "unknown_existing",
                    message_id=outcome[1] if outcome[0] == "sent" and type(outcome[1]) is int else None,
                    delivery_key=delivery_key,
                )
            raise NobusDocumentDeliveryError(getattr(error, "code", "delivery-failed")) from None
        return NobusDocumentDeliveryReceipt(
            status="sent", message_id=message_id, delivery_key=delivery_key
        )


def _load_runtime(path: Path) -> ModuleType:
    name = "nobus_send_results_delivery_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Nobus document delivery runtime is unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(name, None)
        raise ValueError("Nobus document delivery runtime is incompatible") from exc
    return module


def _regular_unlinked_file(path: Path) -> bool:
    try:
        metadata = path.stat()
        return (
            path.is_file()
            and not path.is_symlink()
            and not (getattr(path, "is_junction", lambda: False)())
            and stat.S_ISREG(metadata.st_mode)
            and metadata.st_nlink == 1
            and not (
                getattr(metadata, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
        )
    except OSError:
        return False
