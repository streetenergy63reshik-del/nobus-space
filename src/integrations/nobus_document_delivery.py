"""Adapter to the installed nobus-send-results document delivery owner."""

from __future__ import annotations

import hashlib
import importlib.util
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

from src.contracts.models import canonical_json_digest


class NobusDocumentDeliveryError(RuntimeError):
    """Stable integration error without destination or artifact contents."""


@dataclass(frozen=True, slots=True)
class NobusDocumentDeliveryReceipt:
    status: str
    message_id: int | None
    delivery_key: str


class NobusDocumentDelivery:
    """Use the installed skill runtime and its one shared one-shot ledger."""

    def __init__(self, *, runtime_path: Path, ledger_path: Path) -> None:
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
        self._module = module
        self._ledger = module.SQLiteTelegramDocumentDeliveryLedger(ledger)

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
            or not operation_id.startswith("sha256:")
            or len(operation_id) != 71
            or not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or type(chat_id) is not int
            or chat_id == 0
            or (topic_id is not None and (type(topic_id) is not int or topic_id <= 0))
            or not isinstance(filename, str)
            or type(content) is not bytes
            or not content
        ):
            raise ValueError("Nobus document delivery request is invalid")
        artifact_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        # Existing v1 keying remains unchanged for the skill CLI.  M2 makes the
        # verified destination reference request/operation scoped, so a replay
        # of one operation dedupes while a new request for identical bytes sends.
        destination_ref = canonical_json_digest(
            {
                "schema": "nobus-desktop-document-destination-v1",
                "request_id": str(request_id),
                "operation_id": operation_id,
                "tenant_id": tenant_id.strip(),
                "chat_id": chat_id,
                "topic_id": topic_id,
            }
        )
        delivery_key = self._module.delivery_key_for(destination_ref, artifact_digest)
        existing = self._ledger.status(delivery_key)
        if existing is not None:
            return NobusDocumentDeliveryReceipt(
                status="sent_existing" if existing == "sent" else "unknown_existing",
                message_id=None,
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
            )
        except self._module.TelegramDocumentDeliveryError as error:
            status = self._ledger.status(delivery_key)
            if status is not None:
                return NobusDocumentDeliveryReceipt(
                    status="sent_existing" if status == "sent" else "unknown_existing",
                    message_id=None,
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
