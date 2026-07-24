"""Durable, owner-bound L4 effects for documents, downloads and network commands."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.network_commands import (
    NetworkCommandProposal,
    NetworkCommandRunner,
)
from src.application.network_tools import DownloadProposal, Quarantine, SafeDownloader
from src.application.owner_workspace import ArtifactProposal, OwnerWorkspace
from src.contracts.models import canonical_json_digest
from src.integrations import (
    CalendarAction,
    CalendarActionKind,
    CalendarEvent,
    GoogleTaskAction,
    GoogleTaskActionKind,
    GoogleTaskItem,
)


class ProductEffectKind(str, Enum):
    ARTIFACT = "artifact"
    DOWNLOAD = "download"
    NETWORK = "network"
    CALENDAR_DELETE = "calendar_delete"
    CALENDAR = "calendar"
    GOOGLE_TASK = "google_task"
    GOOGLE_TASK_DELETE = "google_task_delete"


@dataclass(frozen=True, slots=True)
class ProductEffectChallenge:
    token: str
    kind: ProductEffectKind
    preview: str


@dataclass(frozen=True, slots=True)
class ProductEffectResult:
    message: str
    filename: str | None = None
    content: bytes | None = None
    delivery_required: bool = True


@dataclass(frozen=True, slots=True)
class _EffectBinding:
    token: str
    kind: ProductEffectKind
    tenant_id: str
    user_id: int
    chat_id: int
    payload: dict[str, Any]
    effect_digest: str
    state: str
    result: dict[str, Any] | None


class DurableProductEffectVault:
    """Store exact effect bytes encrypted until one owner decision."""

    def __init__(self, state: SQLiteTelegramState) -> None:
        if not isinstance(state, SQLiteTelegramState):
            raise ValueError("product effect vault is invalid")
        self._state = state

    def issue(
        self,
        *,
        kind: ProductEffectKind,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        ttl_seconds: int = 604_800,
    ) -> str:
        if (
            type(kind) is not ProductEffectKind
            or not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or type(user_id) is not int
            or type(chat_id) is not int
            or type(ttl_seconds) is not int
            or not 60 <= ttl_seconds <= 604_800
        ):
            raise ValueError("product effect binding is invalid")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str)
            or not idempotency_key.startswith("sha256:")
            or len(idempotency_key) != 71
        ):
            raise ValueError("product effect idempotency key is invalid")
        effect_digest = canonical_json_digest(payload)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        deterministic_token = (
            None
            if idempotency_key is None
            else hashlib.sha256(
                canonical_json_digest(
                    {
                        "idempotency_key": idempotency_key,
                        "kind": kind.value,
                        "tenant_id": tenant_id.strip(),
                    }
                ).encode()
            ).hexdigest()
        )
        for token in (
            (deterministic_token,)
            if deterministic_token is not None
            else tuple(secrets.token_urlsafe(32) for _ in range(8))
        ):
            token_digest = _digest(token)
            values = {
                "token": token,
                "kind": kind.value,
                "tenant_id": tenant_id.strip(),
                "user_id": user_id,
                "chat_id": chat_id,
                "payload": payload,
                "effect_digest": effect_digest,
                "state": "pending",
                "result": None,
            }
            try:
                self._state.put_capability(
                    kind="action",
                    token_digest=token_digest,
                    tenant_id=tenant_id.strip(),
                    payload=values,
                    expires_at=expires_at,
                )
                return token
            except Exception:
                if deterministic_token is None:
                    continue
                existing = self.read(
                    token,
                    tenant_id=tenant_id.strip(),
                    user_id=user_id,
                    chat_id=chat_id,
                )
                if (
                    existing is not None
                    and existing.kind is kind
                    and existing.payload == payload
                    and existing.effect_digest == effect_digest
                ):
                    return token
                break
        raise RuntimeError("product effect capability is unavailable")

    def read(
        self,
        token: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
    ) -> _EffectBinding | None:
        if not isinstance(token, str) or not token:
            return None
        values = self._state.read_capability(
            kind="action",
            token_digest=_digest(token),
            tenant_id=tenant_id,
        )
        if values is None:
            return None
        try:
            binding = _EffectBinding(
                token=values["token"],
                kind=ProductEffectKind(values["kind"]),
                tenant_id=values["tenant_id"],
                user_id=values["user_id"],
                chat_id=values["chat_id"],
                payload=values["payload"],
                effect_digest=values["effect_digest"],
                state=values["state"],
                result=values["result"],
            )
            if (
                binding.token != token
                or binding.state
                not in {"pending", "executing", "completed", "unknown", "delivered"}
                or (
                    binding.result is not None
                    and not isinstance(binding.result, dict)
                )
                or canonical_json_digest(binding.payload)
                != binding.effect_digest
            ):
                raise ValueError
            if (
                binding.tenant_id != tenant_id
                or binding.user_id != user_id
                or binding.chat_id != chat_id
            ):
                return None
            return binding
        except Exception:
            raise ValueError("durable product effect is invalid") from None

    def transition(
        self,
        binding: _EffectBinding,
        *,
        state: str,
        result: dict[str, Any] | None = None,
    ) -> _EffectBinding:
        if state not in {"executing", "completed", "unknown", "delivered"}:
            raise ValueError("product effect transition is invalid")
        current = self._values(binding)
        updated = {**current, "state": state, "result": result}
        if not self._state.replace_capability(
            kind="action",
            token_digest=_digest(binding.token),
            tenant_id=binding.tenant_id,
            expected_payload=current,
            payload=updated,
        ):
            raise RuntimeError("product effect transition conflict")
        return _EffectBinding(
            binding.token,
            binding.kind,
            binding.tenant_id,
            binding.user_id,
            binding.chat_id,
            binding.payload,
            binding.effect_digest,
            state,
            result,
        )

    @staticmethod
    def _values(binding: _EffectBinding) -> dict[str, Any]:
        return {
            "token": binding.token,
            "kind": binding.kind.value,
            "tenant_id": binding.tenant_id,
            "user_id": binding.user_id,
            "chat_id": binding.chat_id,
            "payload": binding.payload,
            "effect_digest": binding.effect_digest,
            "state": binding.state,
            "result": binding.result,
        }

    def delete(self, binding: _EffectBinding) -> bool:
        return self._state.delete_capability(
            kind="action",
            token_digest=_digest(binding.token),
            tenant_id=binding.tenant_id,
        )


class ProductEffectService:
    """Prepare effects without authority and execute only an exact L4 binding."""

    def __init__(
        self,
        *,
        vault: DurableProductEffectVault,
        workspace: OwnerWorkspace,
        downloader: SafeDownloader,
        quarantine: Quarantine,
        network_runner: NetworkCommandRunner,
        calendar: Any | None = None,
        google_tasks: Any | None = None,
    ) -> None:
        self._vault = vault
        self._workspace = workspace
        self._downloader = downloader
        self._quarantine = quarantine
        self._network = network_runner
        self._calendar = calendar
        self._google_tasks = google_tasks

    async def close(self) -> None:
        await self._downloader.aclose()

    def prepare_document(
        self,
        argument: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str | None = None,
    ) -> ProductEffectChallenge:
        parts = tuple(part.strip() for part in argument.split("|", 2))
        if len(parts) != 3 or not all(parts):
            raise ValueError("document syntax is invalid")
        path, title, body = parts
        if Path(path).suffix.casefold() == ".xlsx":
            rows = tuple(
                tuple(cell.strip() for cell in line.split("\t"))
                for line in body.splitlines()
                if line.strip()
            )
            paragraphs: tuple[str, ...] = ()
        else:
            paragraphs = tuple(
                line.strip() for line in body.splitlines() if line.strip()
            )
            rows = ()
        proposal = self._workspace.propose(
            path, title=title, paragraphs=paragraphs, rows=rows
        )
        token = self._vault.issue(
            kind=ProductEffectKind.ARTIFACT,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=_artifact_payload(proposal),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(
            token,
            ProductEffectKind.ARTIFACT,
            (
                "Создать документ?\n\n"
                f"Файл: {proposal.relative_path}\n"
                f"Размер: {len(proposal.content)} байт\n"
                "Запись произойдёт только после подтверждения."
            ),
        )

    async def prepare_download(
        self,
        argument: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str | None = None,
    ) -> ProductEffectChallenge:
        proposal = await self._downloader.preview(argument.strip())
        token = self._vault.issue(
            kind=ProductEffectKind.DOWNLOAD,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=_download_payload(proposal),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(
            token,
            ProductEffectKind.DOWNLOAD,
            (
                "Сохранить и отправить загруженный файл?\n\n"
                f"Файл: {proposal.filename}\n"
                f"Тип: {proposal.media_type}\n"
                f"Размер: {len(proposal.content)} байт"
            ),
        )

    def prepare_network(
        self,
        argument: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str | None = None,
    ) -> ProductEffectChallenge:
        parts = tuple(part.strip() for part in argument.split("|"))
        if len(parts) == 4 and parts[0] == "git-fetch":
            proposal = self._network.propose_git_fetch(
                repository_directory=parts[1],
                remote=parts[2],
                revision=parts[3],
            )
        elif len(parts) == 3 and parts[0] == "pip-install":
            proposal = self._network.propose_pip_install(
                repository_directory=parts[1],
                requirement_file=parts[2],
            )
        else:
            raise ValueError("network command syntax is invalid")
        token = self._vault.issue(
            kind=ProductEffectKind.NETWORK,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=_network_payload(proposal),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(
            token,
            ProductEffectKind.NETWORK,
            (
                "Выполнить сетевую команду?\n\n"
                f"Инструмент: {proposal.tool}\n"
                f"Каталог: {proposal.working_directory}\n"
                f"Аргументы: {' '.join(proposal.argv)}"
            ),
        )

    async def prepare_google_task_delete(
        self,
        action: GoogleTaskAction,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str,
    ) -> ProductEffectChallenge:
        if self._google_tasks is None:
            raise RuntimeError("Google Tasks integration is unavailable")
        item = await self._google_tasks.resolve_delete(action)
        token = self._vault.issue(
            kind=ProductEffectKind.GOOGLE_TASK_DELETE,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=item.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(
            token,
            ProductEffectKind.GOOGLE_TASK_DELETE,
            (
                "Удалить задачу из Google Tasks?\n\n"
                f"Задача: {item.title}\n"
                f"Список: {item.tasklist_title}\n\n"
                "Удаление необратимо и будет выполнено только после нажатия кнопки."
            ),
        )

    def prepare_google_task(
        self,
        action: GoogleTaskAction,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str,
    ) -> ProductEffectChallenge:
        if self._google_tasks is None:
            raise RuntimeError("Google Tasks integration is unavailable")
        action = GoogleTaskAction.model_validate(action.model_dump())
        if action.kind in {
            GoogleTaskActionKind.NONE,
            GoogleTaskActionKind.DELETE,
        }:
            raise ValueError("Google Task action is not directly executable")
        token = self._vault.issue(
            kind=ProductEffectKind.GOOGLE_TASK,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=action.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(token, ProductEffectKind.GOOGLE_TASK, "")

    async def prepare_calendar_delete(
        self,
        action: CalendarAction,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str,
    ) -> ProductEffectChallenge:
        if self._calendar is None:
            raise RuntimeError("calendar integration is unavailable")
        event = await self._calendar.resolve_delete(action)
        token = self._vault.issue(
            kind=ProductEffectKind.CALENDAR_DELETE,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=_calendar_payload(event),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(
            token,
            ProductEffectKind.CALENDAR_DELETE,
            (
                "Удалить событие из календаря?\n\n"
                f"Событие: {event.title}\n"
                f"Начало: {event.start.astimezone():%d.%m.%Y %H:%M}\n\n"
                "Удаление необратимо и будет выполнено только после нажатия кнопки."
            ),
        )

    def prepare_calendar(
        self,
        action: CalendarAction,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        idempotency_key: str,
    ) -> ProductEffectChallenge:
        if self._calendar is None:
            raise RuntimeError("calendar integration is unavailable")
        action = CalendarAction.model_validate(action.model_dump())
        if action.kind in {CalendarActionKind.NONE, CalendarActionKind.DELETE}:
            raise ValueError("calendar action is not directly executable")
        token = self._vault.issue(
            kind=ProductEffectKind.CALENDAR,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            payload=action.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return ProductEffectChallenge(token, ProductEffectKind.CALENDAR, "")

    async def resolve(
        self,
        token: str,
        *,
        expected_kind: ProductEffectKind,
        approve: bool,
        tenant_id: str,
        user_id: int,
        chat_id: int,
        approval_ref: str,
    ) -> ProductEffectResult:
        binding = self._vault.read(
            token,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
        )
        if binding is None or binding.kind is not expected_kind:
            raise ValueError("product effect confirmation is invalid")
        if not approve:
            if binding.state == "pending":
                binding = self._vault.transition(
                    binding,
                    state="completed",
                    result={"message": "Действие отменено.", "filename": None},
                )
            return self._completed_result(binding)
        if binding.state in {"completed", "delivered"}:
            return self._completed_result(binding)
        if binding.state == "unknown":
            return ProductEffectResult(
                "Состояние сетевой команды требует ручной проверки; "
                "повторный запуск заблокирован."
            )
        recovered = binding.state == "executing"
        if binding.state == "pending":
            binding = self._vault.transition(binding, state="executing")
        if binding.kind is ProductEffectKind.NETWORK and recovered:
            binding = self._vault.transition(
                binding,
                state="unknown",
                result={"message": "network_result_unknown"},
            )
            return self._completed_result(binding)
        if binding.kind is ProductEffectKind.ARTIFACT:
            proposal = _artifact(binding.payload)
            target = self._workspace.recover(proposal)
            if target is None:
                target = self._workspace.apply(
                    proposal, approval_ref=approval_ref
                )
            result = ProductEffectResult(
                "Документ создан.", target.name, target.read_bytes()
            )
        elif binding.kind is ProductEffectKind.DOWNLOAD:
            proposal = _download(binding.payload)
            target = self._quarantine.recover(proposal)
            if target is None:
                target = self._quarantine.store(
                    proposal, approval_ref=approval_ref
                )
            result = ProductEffectResult(
                "Файл сохранён.", target.name, target.read_bytes()
            )
        elif binding.kind is ProductEffectKind.NETWORK:
            proposal = _network(binding.payload)
            completed = await asyncio.to_thread(
                self._network.run,
                proposal,
                approval_ref=approval_ref,
            )
            result = ProductEffectResult(
                "Сетевая команда выполнена."
                if completed.returncode == 0
                else "Сетевая команда завершилась с ошибкой."
            )
        elif binding.kind is ProductEffectKind.CALENDAR_DELETE:
            if self._calendar is None:
                raise RuntimeError("calendar integration is unavailable")
            event = _calendar_event(binding.payload)
            await self._calendar.delete_event(event.event_id)
            result = ProductEffectResult(f"Событие «{event.title}» удалено.")
        elif binding.kind is ProductEffectKind.CALENDAR:
            if self._calendar is None:
                raise RuntimeError("calendar integration is unavailable")
            action = CalendarAction.model_validate(binding.payload)
            calendar_result = await self._calendar.execute(
                action,
                idempotency_key=canonical_json_digest(
                    {
                        "effect_digest": binding.effect_digest,
                        "tenant_id": binding.tenant_id,
                    }
                ),
            )
            result = ProductEffectResult(calendar_result.message)
        elif binding.kind is ProductEffectKind.GOOGLE_TASK_DELETE:
            if self._google_tasks is None:
                raise RuntimeError("Google Tasks integration is unavailable")
            item = GoogleTaskItem.model_validate(binding.payload)
            await self._google_tasks.delete_task(
                item.tasklist_id, item.task_id
            )
            result = ProductEffectResult(f"Задача «{item.title}» удалена.")
        elif binding.kind is ProductEffectKind.GOOGLE_TASK:
            if self._google_tasks is None:
                raise RuntimeError("Google Tasks integration is unavailable")
            action = GoogleTaskAction.model_validate(binding.payload)
            task_result = await self._google_tasks.execute(
                action,
                idempotency_key=canonical_json_digest(
                    {
                        "effect_digest": binding.effect_digest,
                        "tenant_id": binding.tenant_id,
                    }
                ),
            )
            result = ProductEffectResult(task_result.message)
        else:
            raise RuntimeError("product effect kind is unsupported")
        binding = self._vault.transition(
            binding,
            state="completed",
            result={
                "message": result.message,
                "filename": result.filename,
                "approval_ref": approval_ref,
            },
        )
        return self._completed_result(binding)

    def delivery_pending(
        self,
        token: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
    ) -> bool:
        binding = self._vault.read(
            token,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
        )
        return binding is not None and binding.state in {
            "completed",
            "unknown",
        }

    def record_terminal_failure(
        self,
        token: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
    ) -> bool:
        """Persist a safe owner-visible result after deterministic retries end."""
        binding = self._vault.read(
            token,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
        )
        if binding is None:
            return False
        if binding.state in {"completed", "unknown", "delivered"}:
            return True
        self._vault.transition(
            binding,
            state="completed",
            result={
                "message": (
                    "Не удалось завершить действие после нескольких попыток. "
                    "Внешняя система не подтвердила результат; повторите команду позже."
                ),
                "filename": None,
                "approval_ref": "system:terminal-failure",
            },
        )
        return True

    def acknowledge_delivery(
        self,
        token: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
    ) -> bool:
        binding = self._vault.read(
            token,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
        )
        if binding is None:
            return False
        if binding.state == "delivered":
            return True
        if binding.state not in {"completed", "unknown"}:
            return False
        self._vault.transition(
            binding,
            state="delivered",
            result=binding.result,
        )
        return True

    def finalize_delivery(
        self,
        token: str,
        *,
        tenant_id: str,
        user_id: int,
        chat_id: int,
    ) -> bool:
        binding = self._vault.read(
            token,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
        )
        return (
            binding is not None
            and binding.state == "delivered"
            and self._vault.delete(binding)
        )

    @staticmethod
    def _completed_result(binding: _EffectBinding) -> ProductEffectResult:
        if binding.state == "unknown":
            return ProductEffectResult(
                "Состояние сетевой команды требует ручной проверки; "
                "повторный запуск заблокирован.",
                delivery_required=binding.state != "delivered",
            )
        if binding.result is None:
            raise RuntimeError("product effect result is unavailable")
        filename = binding.result.get("filename")
        content: bytes | None = None
        if filename is not None:
            content = base64.b64decode(
                binding.payload["content"], validate=True
            )
        return ProductEffectResult(
            str(binding.result["message"]),
            str(filename) if filename is not None else None,
            content,
            binding.state != "delivered",
        )


def approval_reference(
    *, actor_identity: str, query_id: str, effect_token: str
) -> str:
    digest = hashlib.sha256(
        canonical_json_digest(
            {
                "actor_identity": actor_identity,
                "query_id": query_id,
                "effect_token_digest": _digest(effect_token),
            }
        ).encode()
    ).hexdigest()
    return f"telegram-owner-confirmation:sha256:{digest}"


def _artifact_payload(value: ArtifactProposal) -> dict[str, Any]:
    return {
        "relative_path": value.relative_path,
        "media_type": value.media_type,
        "content": base64.b64encode(value.content).decode("ascii"),
        "content_digest": value.content_digest,
        "current_digest": value.current_digest,
    }


def _artifact(value: dict[str, Any]) -> ArtifactProposal:
    return ArtifactProposal(
        relative_path=value["relative_path"],
        media_type=value["media_type"],
        content=base64.b64decode(value["content"], validate=True),
        content_digest=value["content_digest"],
        current_digest=value["current_digest"],
    )


def _download_payload(value: DownloadProposal) -> dict[str, Any]:
    return {
        "source_url": value.source_url,
        "final_url": value.final_url,
        "filename": value.filename,
        "media_type": value.media_type,
        "content": base64.b64encode(value.content).decode("ascii"),
        "content_digest": value.content_digest,
    }


def _download(value: dict[str, Any]) -> DownloadProposal:
    return DownloadProposal(
        source_url=value["source_url"],
        final_url=value["final_url"],
        filename=value["filename"],
        media_type=value["media_type"],
        content=base64.b64decode(value["content"], validate=True),
        content_digest=value["content_digest"],
    )


def _network_payload(value: NetworkCommandProposal) -> dict[str, Any]:
    return {
        "tool": value.tool,
        "argv": list(value.argv),
        "working_directory": value.working_directory,
        "input_digest": value.input_digest,
        "source": value.source,
        "destination": value.destination,
        "digest": value.digest,
    }


def _network(value: dict[str, Any]) -> NetworkCommandProposal:
    return NetworkCommandProposal(
        value["tool"],
        tuple(value["argv"]),
        value["working_directory"],
        value["input_digest"],
        value.get("source"),
        value.get("destination"),
        value["digest"],
    )


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _calendar_payload(value: CalendarEvent) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _calendar_event(value: dict[str, Any]) -> CalendarEvent:
    return CalendarEvent.model_validate_json(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
