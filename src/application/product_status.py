"""Channel-neutral product projection of internal task states."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.models.task import TaskStatus


class ProductTaskStatus(str, Enum):
    QUEUED = "queued"
    WORKING = "working"
    WAITING = "waiting"
    READY = "ready"
    ATTENTION = "attention"
    FAILED = "failed"


class ProductReason(str, Enum):
    ACCEPTED = "accepted"
    WORKING = "working"
    CHECKING_RESULT = "checking_result"
    NEEDS_CLARIFICATION = "needs_clarification"
    APPROVAL_REQUIRED = "approval_required"
    RESULT_READY = "result_ready"
    DELIVERY_PENDING = "delivery_pending"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    TASK_FAILED = "task_failed"
    RECOVERY_REQUIRED = "recovery_required"
    REQUEST_REFUSED = "request_refused"
    CONDITION_NOT_MET = "condition_not_met"
    VOICE_RECEIVED = "voice_received"
    VOICE_RECOGNIZING = "voice_recognizing"
    VOICE_CONFIRMATION = "voice_confirmation"
    VOICE_INTERRUPTED = "voice_interrupted"
    INPUT_CANCELLED = "input_cancelled"


class ProductAction(str, Enum):
    NONE = "none"
    WAIT = "wait"
    ANSWER = "answer"
    CONFIRM = "confirm"
    OPEN_RESULT = "open_result"
    CHECK_STATUS = "check_status"
    REOPEN = "reopen"
    NEW_REQUEST = "new_request"


class ProductTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProductTaskStatus
    label: str
    terminal: bool
    reason: ProductReason
    reason_label: str
    action: ProductAction


_STATE = {
    ProductTaskStatus.QUEUED: ProductTaskState(
        status=ProductTaskStatus.QUEUED,
        label="В очереди",
        terminal=False,
        reason=ProductReason.ACCEPTED,
        reason_label="Задача принята и ждёт выполнения.",
        action=ProductAction.WAIT,
    ),
    ProductTaskStatus.WORKING: ProductTaskState(
        status=ProductTaskStatus.WORKING,
        label="В работе",
        terminal=False,
        reason=ProductReason.WORKING,
        reason_label="Выполняю задачу.",
        action=ProductAction.WAIT,
    ),
    ProductTaskStatus.WAITING: ProductTaskState(
        status=ProductTaskStatus.WAITING,
        label="Ожидает действия",
        terminal=False,
        reason=ProductReason.NEEDS_CLARIFICATION,
        reason_label="Нужен ваш ответ, чтобы продолжить.",
        action=ProductAction.ANSWER,
    ),
    ProductTaskStatus.READY: ProductTaskState(
        status=ProductTaskStatus.READY,
        label="Готово",
        terminal=True,
        reason=ProductReason.RESULT_READY,
        reason_label="Результат готов.",
        action=ProductAction.OPEN_RESULT,
    ),
    ProductTaskStatus.ATTENTION: ProductTaskState(
        status=ProductTaskStatus.ATTENTION,
        label="Требует внимания",
        terminal=True,
        reason=ProductReason.RECOVERY_REQUIRED,
        reason_label="Нужно сверить состояние задачи. Откройте её в Mini App или проверьте /status; не отправляйте её заново до сверки.",
        action=ProductAction.CHECK_STATUS,
    ),
    ProductTaskStatus.FAILED: ProductTaskState(
        status=ProductTaskStatus.FAILED,
        label="Не выполнено",
        terminal=True,
        reason=ProductReason.TASK_FAILED,
        reason_label="Не удалось выполнить задачу. Откройте её состояние перед новым запросом.",
        action=ProductAction.CHECK_STATUS,
    ),
}


# These are projections of existing Core/intake/delivery states, never transitions.
_REASONS = {state.reason: state for state in _STATE.values()}
for reason, status, label, text, action, terminal in (
    (ProductReason.CHECKING_RESULT, ProductTaskStatus.WORKING, "В работе", "Проверяю результат перед выдачей.", ProductAction.WAIT, False),
    (ProductReason.APPROVAL_REQUIRED, ProductTaskStatus.WAITING, "Нужно подтверждение", "Для действия требуется точное подтверждение. До него действие не запускается.", ProductAction.CONFIRM, False),
    (ProductReason.DELIVERY_PENDING, ProductTaskStatus.READY, "Результат готов", "Результат готов. Доставка ответа или файла ещё не подтверждена; повторять задачу не нужно.", ProductAction.OPEN_RESULT, True),
    (ProductReason.CAPABILITY_UNAVAILABLE, ProductTaskStatus.FAILED, "Возможность недоступна", "Запрошенная возможность сейчас недоступна; никаких действий не выполнялось.", ProductAction.NEW_REQUEST, True),
    (ProductReason.TEMPORARILY_UNAVAILABLE, ProductTaskStatus.ATTENTION, "Временно недоступно", "Не удалось обновить состояние. Повторите проверку; не отправляйте задачу заново.", ProductAction.CHECK_STATUS, False),
    (ProductReason.REQUEST_REFUSED, ProductTaskStatus.FAILED, "Запрос отклонён", "Запрос отклонён политикой безопасности; никаких действий не выполнялось.", ProductAction.NEW_REQUEST, True),
    (ProductReason.CONDITION_NOT_MET, ProductTaskStatus.FAILED, "Условие не выполнено", "Условие сейчас не выполнено; действие не запускалось.", ProductAction.NONE, True),
    (ProductReason.VOICE_RECEIVED, ProductTaskStatus.QUEUED, "Запись получена", "Голосовая запись сохранена и ждёт распознавания. Задача ещё не запущена.", ProductAction.WAIT, False),
    (ProductReason.VOICE_RECOGNIZING, ProductTaskStatus.WORKING, "Распознаю запись", "Распознаю запись на русском языке. Задача ещё не запущена.", ProductAction.WAIT, False),
    (ProductReason.VOICE_CONFIRMATION, ProductTaskStatus.WAITING, "Проверьте запись", "Ответьте на исходное голосовое сообщение: «да», «нет» или исправленным текстом. До подтверждения задача не запускается.", ProductAction.CONFIRM, False),
    (ProductReason.VOICE_INTERRUPTED, ProductTaskStatus.ATTENTION, "Распознавание прервано", "Ответьте на исходное голосовое сообщение «повторить» или исправленным текстом. Задача ещё не запущена.", ProductAction.ANSWER, False),
    (ProductReason.INPUT_CANCELLED, ProductTaskStatus.FAILED, "Ввод отменён", "Голосовая запись отменена; задача не запускалась.", ProductAction.NONE, True),
):
    _REASONS[reason] = ProductTaskState(status=status, label=label, terminal=terminal,
        reason=reason, reason_label=text, action=action)

if set(_REASONS) != set(ProductReason):  # pragma: no cover
    raise RuntimeError("product reason mapping is incomplete")

_TASK_STATUS = {
    TaskStatus.PENDING: ProductTaskStatus.QUEUED,
    # Core records STARTED/PARSING before entering the provider.
    TaskStatus.PARSING: ProductTaskStatus.WORKING,
    TaskStatus.ROUTING: ProductTaskStatus.QUEUED,
    TaskStatus.IN_PROGRESS: ProductTaskStatus.WORKING,
    TaskStatus.DRAFT: ProductTaskStatus.WORKING,
    TaskStatus.L1_VALIDATED: ProductTaskStatus.WORKING,
    TaskStatus.L2_VERIFIED: ProductTaskStatus.WORKING,
    TaskStatus.L3_APPROVED: ProductTaskStatus.WORKING,
    TaskStatus.HUMAN_APPROVED: ProductTaskStatus.WORKING,
    TaskStatus.EXECUTING: ProductTaskStatus.WORKING,
    TaskStatus.REWORK: ProductTaskStatus.WORKING,
    TaskStatus.WAITING_INPUT: ProductTaskStatus.WAITING,
    TaskStatus.WAITING_HUMAN: ProductTaskStatus.WAITING,
    TaskStatus.DEFERRED: ProductTaskStatus.WAITING,
    TaskStatus.COMPLETED: ProductTaskStatus.READY,
    TaskStatus.ANSWERED: ProductTaskStatus.READY,
    TaskStatus.ESCALATE: ProductTaskStatus.ATTENTION,
    TaskStatus.REJECTED: ProductTaskStatus.FAILED,
    TaskStatus.FAILED: ProductTaskStatus.FAILED,
}

if set(_TASK_STATUS) != set(TaskStatus):  # pragma: no cover - import-time guard
    raise RuntimeError("product task status mapping is incomplete")


def product_task_state(status: TaskStatus) -> ProductTaskState:
    """Return one safe product state for an exact internal enum value."""
    if not isinstance(status, TaskStatus):
        raise ValueError("product task status is invalid")
    if status is TaskStatus.WAITING_HUMAN:
        return product_reason_state(ProductReason.APPROVAL_REQUIRED)
    return _STATE[_TASK_STATUS[status]]


def product_reason_state(reason: ProductReason) -> ProductTaskState:
    if not isinstance(reason, ProductReason):
        raise ValueError("product reason is invalid")
    return _REASONS[reason]


def product_semantic_state(decision: object) -> ProductTaskState:
    from src.application.semantic_admission import CoreDecision

    if not isinstance(decision, CoreDecision):
        raise ValueError("product semantic decision is invalid")
    reasons = {
        "accepted": ProductReason.ACCEPTED,
        "needs_clarification": ProductReason.NEEDS_CLARIFICATION,
        "condition_unknown": ProductReason.NEEDS_CLARIFICATION,
        "approval_required": ProductReason.APPROVAL_REQUIRED,
        "unavailable": ProductReason.CAPABILITY_UNAVAILABLE,
        "refused": ProductReason.REQUEST_REFUSED,
        "condition_not_met": ProductReason.CONDITION_NOT_MET,
    }
    return product_reason_state(reasons[decision.user_visible_state.state])


class RuntimeAdmissionPaused(RuntimeError):
    """Planned maintenance: keep ingress unacknowledged until orderly shutdown."""


class ProductAdmissionStopped(RuntimeError):
    """One Core-owned semantic decision that created no task or effect."""

    def __init__(self, decision: object) -> None:
        self.state = product_semantic_state(decision)
        if self.state.reason in {ProductReason.ACCEPTED, ProductReason.NEEDS_CLARIFICATION}:
            raise ValueError("product admission stop is invalid")
        super().__init__(self.state.reason.value)


def product_progress_state(stage: str) -> ProductTaskState:
    reasons = {
        "Проверяю контекст и границы доступа": ProductReason.WORKING,
        "Codex выполняет задачу": ProductReason.WORKING,
        "Проверяю результат": ProductReason.CHECKING_RESULT,
        "Независимо перепроверяю результат": ProductReason.CHECKING_RESULT,
        "Провожу финальную проверку": ProductReason.CHECKING_RESULT,
    }
    return product_reason_state(reasons.get(stage, ProductReason.WORKING))


def product_event_label(kind: str) -> str:
    labels = {
        "started": "Выполнение началось",
        "progress": "Задача выполняется",
        "waiting_input": "Нужен ваш ответ",
        "artifact_ready": "Файл подготовлен",
        "result_ready": "Результат подготовлен",
        "failed": "Выполнение не удалось",
        "stopped": "Выполнение остановлено",
    }
    if kind not in labels:
        raise ValueError("product event is invalid")
    return labels[kind]
