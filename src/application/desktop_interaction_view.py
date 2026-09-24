"""Pure renderer for Desktop pending interaction requests (questions / approvals).

This module converts a display-allowed JSON-like pending request into plain
Russian text blocks for a human operator. It never sends messages, never
approves or denies, never opens URLs, never executes schemas, and never
touches network, filesystem, subprocess, environment, Desktop, or Telegram APIs.

The bridge adds sender, topic, and numeric mentions. A separate formatter
applies Telegram length budgets; this renderer does not truncate for budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import json

__all__ = [
    "InteractionView",
    "render_interaction",
]

_SUPPORTED_KINDS = frozenset(
    {
        "user_input",
        "command_approval",
        "file_approval",
        "permissions_approval",
        "mcp_elicitation",
    }
)

# Top-level keys that are part of the display contract (not "unknown significant").
_TOP_KNOWN = frozenset({"id", "method", "params"})

_PARAMS_KNOWN_BY_KIND: dict[str, frozenset[str]] = {
    "user_input": frozenset(
        {
            "questions",
            "prompt",
            "message",
            "title",
            "text",
            "allow_free_text",
            "allowFreeText",
            "free_text",
            "freeText",
        }
    ),
    "command_approval": frozenset(
        {
            "command",
            "argv",
            "args",
            "shell",
            "cwd",
            "reason",
            "scope",
            "description",
            "path",
            "env",
            "working_directory",
            "workingDirectory",
            "availableDecisions",
            "commandActions",
            "environmentId",
            "kind",
            "proposedExecpolicyAmendment",
            "startedAtMs",
        }
    ),
    "file_approval": frozenset(
        {
            "path",
            "paths",
            "files",
            "file",
            "action",
            "actions",
            "changes",
            "change",
            "diff",
            "diffs",
            "reason",
            "scope",
            "description",
            "cwd",
            "content",
            "old_path",
            "new_path",
            "oldPath",
            "newPath",
        }
    ),
    "permissions_approval": frozenset(
        {
            "network",
            "filesystem",
            "file_system",
            "fileSystem",
            "permissions",
            "permission",
            "extra",
            "extra_permissions",
            "extraPermissions",
            "rights",
            "scope",
            "duration",
            "reason",
            "description",
            "cwd",
            "hosts",
            "domains",
            "paths",
            "path",
            "actions",
            "action",
        }
    ),
    "mcp_elicitation": frozenset(
        {
            "message",
            "mode",
            "requestedSchema",
            "requested_schema",
            "schema",
            "url",
            "URL",
            "uri",
            "link",
            "reason",
            "description",
            "title",
            "prompt",
            "server",
            "serverName",
            "server_name",
            "tool",
            "toolName",
            "tool_name",
        }
    ),
}

_ROUTING_PARAMS = frozenset({"threadId", "turnId", "itemId"})

# Modes / clues that indicate an interactive or URL flow we cannot answer
# through a simple text reply channel.
_MCP_URL_MODE_MARKERS = frozenset(
    {
        "url",
        "uri",
        "link",
        "oauth",
        "o_auth",
        "browser",
        "interactive",
        "web",
        "redirect",
        "external",
        "form_url",
        "form-url",
    }
)


@dataclass(frozen=True)
class InteractionView:
    blocks: tuple[str, ...]
    reply_example: str | None
    requires_manual_review: bool
    issues: tuple[str, ...]


def render_interaction(kind: str, payload: Mapping[str, Any]) -> InteractionView:
    """Render a Desktop pending request into plain-Russian interaction blocks.

    ``kind`` must be one of: user_input, command_approval, file_approval,
    permissions_approval, mcp_elicitation. ``payload`` is a JSON-like mapping
    (optional ``id`` / ``method`` and ``params``). Unexpected non-JSON-like
    objects are never serialized via ``__str__`` / ``repr`` and never have
    methods called; they produce issues and manual review.
    """
    issues: list[str] = []
    blocks: list[str] = []
    reply_example: str | None = None
    manual = False

    if not isinstance(kind, str) or not kind.strip():
        return InteractionView(
            blocks=("Некорректный тип запроса: kind отсутствует или пуст.",),
            reply_example=None,
            requires_manual_review=True,
            issues=("invalid-kind",),
        )

    kind_norm = kind.strip()
    if kind_norm not in _SUPPORTED_KINDS:
        blocks.append(f"Неизвестный тип запроса Desktop: {kind_norm}.")
        blocks.append(
            "Этот renderer не умеет формировать ответ для данного kind. "
            "Требуется ручная проверка."
        )
        _append_payload_overview(blocks, payload, issues)
        return InteractionView(
            blocks=tuple(blocks),
            reply_example=None,
            requires_manual_review=True,
            issues=tuple([*issues, f"unknown-kind:{kind_norm}"]),
        )

    if not isinstance(payload, Mapping):
        return InteractionView(
            blocks=(
                f"Запрос ({kind_norm}): payload имеет некорректный тип "
                f"(ожидался JSON-объект/mapping).",
            ),
            reply_example=None,
            requires_manual_review=True,
            issues=("invalid-payload-type",),
        )

    # Validate / collect JSON-like structure without calling methods on aliens.
    if not _is_json_like(payload, issues, path="$"):
        blocks.append(
            f"Запрос ({kind_norm}): структура payload содержит не-JSON-подобные "
            "значения. Требуется ручная проверка; данные не сериализованы через str/repr."
        )
        return InteractionView(
            blocks=tuple(blocks),
            reply_example=None,
            requires_manual_review=True,
            issues=tuple([*issues, "non-json-like-payload"]),
        )

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params")

    header_lines = [_kind_title(kind_norm)]
    if _is_display_scalar(request_id):
        header_lines.append(f"ID запроса: {_fmt_scalar(request_id)}")
    elif request_id is not None:
        issues.append("request-id-non-scalar")
        manual = True
        header_lines.append("ID запроса: [нескалярное значение — см. issues]")
    if isinstance(method, str) and method.strip():
        header_lines.append(f"Метод: {method}")
    elif method is not None and not isinstance(method, str):
        issues.append("method-non-string")
        manual = True
    blocks.append("\n".join(header_lines))

    if params is None:
        issues.append("missing-params")
        manual = True
        blocks.append("Поле params отсутствует.")
        params_map: Mapping[str, Any] | None = None
    elif not isinstance(params, Mapping):
        issues.append("params-not-mapping")
        manual = True
        blocks.append(
            "Поле params имеет некорректный тип (ожидался JSON-объект). "
            "Содержимое не интерпретировано."
        )
        params_map = None
    else:
        params_map = params

    if params_map is not None:
        if kind_norm == "user_input":
            r_ex, m2 = _render_user_input(blocks, params_map, issues)
            reply_example = r_ex
            manual = manual or m2
        elif kind_norm == "command_approval":
            manual = _render_command(blocks, params_map, issues) or manual
        elif kind_norm == "file_approval":
            manual = _render_file(blocks, params_map, issues) or manual
        elif kind_norm == "permissions_approval":
            manual = _render_permissions(blocks, params_map, issues) or manual
        elif kind_norm == "mcp_elicitation":
            m2 = _render_mcp(blocks, params_map, issues)
            manual = manual or m2

        unknown = _unknown_params(kind_norm, params_map)
        if unknown:
            extra_lines = ["Дополнительные поля params (не из базового контракта):"]
            for key in unknown:
                rendered = _render_json_value(params_map[key], indent=2)
                extra_lines.append(f"• {key}:")
                extra_lines.append(rendered)
                issues.append(f"unknown-param:{key}")
            blocks.append("\n".join(extra_lines))
            # Unknown significant fields must not be silently dropped; flag review
            # so the integrator notices, but do not invent an accept reply.
            manual = True

    # Unknown top-level keys (beyond id/method/params).
    top_unknown = sorted(k for k in payload.keys() if k not in _TOP_KNOWN)
    if top_unknown:
        extra_lines = ["Дополнительные поля верхнего уровня:"]
        for key in top_unknown:
            rendered = _render_json_value(payload[key], indent=2)
            extra_lines.append(f"• {key}:")
            extra_lines.append(rendered)
            issues.append(f"unknown-top:{key}")
        blocks.append("\n".join(extra_lines))
        manual = True

    if manual and reply_example is not None and kind_norm != "user_input":
        # Never ship a fake accept template when structure is invalid.
        reply_example = None

    # For approval / mcp kinds we never invent an approve/deny decision example.
    if kind_norm in {
        "command_approval",
        "file_approval",
        "permissions_approval",
        "mcp_elicitation",
    }:
        # reply_example stays None: bridge documents how to answer.
        reply_example = None

    if manual and "requires-manual-review" not in issues:
        # Keep issues descriptive; manual flag is the contract signal.
        pass

    return InteractionView(
        blocks=tuple(blocks),
        reply_example=reply_example,
        requires_manual_review=manual,
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# Kind titles
# ---------------------------------------------------------------------------


def _kind_title(kind: str) -> str:
    return {
        "user_input": "Codex Desktop просит уточнение (user_input).",
        "command_approval": "Codex Desktop запрашивает разрешение на выполнение команды.",
        "file_approval": "Codex Desktop запрашивает разрешение на файловую операцию.",
        "permissions_approval": "Codex Desktop запрашивает дополнительные полномочия.",
        "mcp_elicitation": "Codex Desktop / MCP elicitation: требуется ввод по схеме.",
    }.get(kind, f"Запрос Desktop: {kind}")


# ---------------------------------------------------------------------------
# user_input
# ---------------------------------------------------------------------------


def _render_user_input(
    blocks: list[str],
    params: Mapping[str, Any],
    issues: list[str],
) -> tuple[str | None, bool]:
    manual = False
    questions = params.get("questions")

    # Optional preamble fields.
    for label, key in (
        ("Заголовок", "title"),
        ("Сообщение", "message"),
        ("Подсказка", "prompt"),
        ("Текст", "text"),
    ):
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            blocks.append(f"{label}:\n{val}")
        elif val is not None and not isinstance(val, str):
            issues.append(f"user_input-{key}-non-string")
            manual = True

    allow_free = _truthy_flag(
        params,
        ("allow_free_text", "allowFreeText", "free_text", "freeText"),
    )

    if questions is None:
        issues.append("missing-questions")
        manual = True
        blocks.append(
            "Список вопросов (params.questions) отсутствует. "
            "Требуется ручная проверка."
        )
        return None, True

    if not isinstance(questions, list):
        issues.append("questions-not-list")
        manual = True
        blocks.append(
            "params.questions имеет некорректный тип (ожидался список). "
            "Требуется ручная проверка."
        )
        return None, True

    if len(questions) == 0:
        issues.append("empty-questions")
        manual = True
        blocks.append("Список вопросов пуст. Требуется ручная проверка.")
        return None, True

    q_ids: list[str] = []
    seen: set[str] = set()
    q_blocks: list[str] = []
    structural_ok = True

    for index, question in enumerate(questions):
        q_lines: list[str] = [f"Вопрос {index + 1}:"]
        if not isinstance(question, Mapping):
            issues.append(f"question[{index}]-not-mapping")
            structural_ok = False
            manual = True
            q_lines.append("  [элемент не является JSON-объектом]")
            q_blocks.append("\n".join(q_lines))
            continue

        qid = question.get("id")
        if not isinstance(qid, str) or not qid.strip():
            issues.append(f"question[{index}]-missing-or-empty-id")
            structural_ok = False
            manual = True
            q_lines.append("  ID: [отсутствует или пуст]")
        else:
            qid_s = qid
            if qid_s in seen:
                issues.append(f"duplicate-question-id:{qid_s}")
                structural_ok = False
                manual = True
                q_lines.append(f"  ID: {qid_s}  ← ПОВТОРЯЮЩИЙСЯ ID")
            else:
                seen.add(qid_s)
                q_ids.append(qid_s)
                q_lines.append(f"  ID: {qid_s}")

        text = question.get("question")
        if text is None:
            text = question.get("text") or question.get("prompt") or question.get("message")
        if isinstance(text, str):
            q_lines.append(f"  Текст: {text}")
        elif text is None:
            issues.append(f"question[{index}]-missing-text")
            q_lines.append("  Текст: [отсутствует]")
            manual = True
        else:
            issues.append(f"question[{index}]-text-non-string")
            q_lines.append("  Текст: [нестроковое значение]")
            manual = True

        # Optional per-question headers/hints.
        for label, key in (("Заголовок", "header"), ("Подсказка", "hint"), ("Описание", "description")):
            v = question.get(key)
            if isinstance(v, str) and v.strip():
                q_lines.append(f"  {label}: {v}")

        options = question.get("options")
        if options is None:
            q_lines.append("  Варианты: не заданы (допустим свободный текст, если разрешён).")
        elif not isinstance(options, list):
            issues.append(f"question[{index}]-options-not-list")
            manual = True
            q_lines.append("  Варианты: [некорректный тип]")
        elif len(options) == 0:
            q_lines.append("  Варианты: пустой список.")
        else:
            q_lines.append("  Варианты ответа:")
            for oi, opt in enumerate(options):
                if not isinstance(opt, Mapping):
                    if isinstance(opt, str):
                        q_lines.append(f"    — {opt}")
                    else:
                        issues.append(f"question[{index}]-option[{oi}]-invalid")
                        manual = True
                        q_lines.append(f"    — [вариант {oi}: некорректный тип]")
                    continue
                label = opt.get("label")
                value = opt.get("value")
                desc = opt.get("description")
                if desc is None:
                    desc = opt.get("desc")
                parts: list[str] = []
                if isinstance(label, str):
                    parts.append(label)
                elif label is not None:
                    issues.append(f"question[{index}]-option[{oi}]-label-non-string")
                    manual = True
                    parts.append("[нестроковый label]")
                if isinstance(value, str) and (
                    not isinstance(label, str) or value != label
                ):
                    parts.append(f"(value: {value})")
                elif value is not None and not isinstance(value, (str, int, float, bool)):
                    issues.append(f"question[{index}]-option[{oi}]-value-non-json")
                    manual = True
                line = "    — " + (" ".join(parts) if parts else f"[вариант {oi}]")
                q_lines.append(line)
                if isinstance(desc, str) and desc.strip():
                    q_lines.append(f"      описание: {desc}")
                # recommended is shown but NEVER pre-selected as the answer.
                recommended = opt.get("recommended")
                if recommended is True:
                    q_lines.append("      (отмечен как recommended — НЕ выбран автоматически)")
                known_option = {"label", "value", "description", "desc", "recommended"}
                for key in sorted(k for k in opt if k not in known_option):
                    q_lines.append(f"      Дополнительное поле {key}:")
                    q_lines.append(_render_json_value(opt[key], indent=8))
                    issues.append(f"unknown-option-field[{index}][{oi}]:{key}")
                    manual = True

        # Answer requirement.
        required = question.get("required")
        multi = question.get("multiple") or question.get("multi") or question.get("allow_multiple")
        req_bits: list[str] = []
        if required is False:
            req_bits.append("ответ необязателен")
        else:
            req_bits.append("ответ обязателен")
        if multi is True:
            req_bits.append("допускается несколько значений (список строк)")
        if allow_free or options is None or (
            isinstance(options, list) and len(options) == 0
        ):
            req_bits.append("допустим свободный текст")
        q_lines.append("  Требование: " + "; ".join(req_bits) + ".")

        # Unknown fields inside the question object.
        q_known = frozenset(
            {
                "id",
                "question",
                "text",
                "prompt",
                "message",
                "header",
                "hint",
                "description",
                "options",
                "required",
                "multiple",
                "multi",
                "allow_multiple",
                "allowFreeText",
                "allow_free_text",
                "type",
            }
        )
        q_unknown = sorted(k for k in question.keys() if k not in q_known)
        if q_unknown:
            q_lines.append("  Дополнительные поля вопроса:")
            for key in q_unknown:
                q_lines.append(f"    • {key}:")
                q_lines.append(_render_json_value(question[key], indent=6))
                issues.append(f"unknown-question-field[{index}]:{key}")
            manual = True

        q_blocks.append("\n".join(q_lines))

    blocks.append("\n\n".join(q_blocks))

    if not structural_ok or not q_ids:
        blocks.append(
            "Структура вопросов некорректна (отсутствующие или повторяющиеся ID). "
            "Шаблон ответа не сформирован — требуется ручная проверка."
        )
        return None, True

    # reply_example
    if len(q_ids) == 1:
        # Single question: free text explicitly allowed (bridge wraps into answers).
        qid = q_ids[0]
        if allow_free or _question_has_no_options(questions[0] if questions else None):
            blocks.append(
                f"Один вопрос (ID «{qid}»). Можно ответить свободным текстом "
                "обычным сообщением (без JSON)."
            )
            reply = None  # free text; no JSON template required
        else:
            blocks.append(
                f"Один вопрос (ID «{qid}»). Можно ответить свободным текстом "
                "или указать label/value выбранного варианта."
            )
            reply = None
        return reply, manual

    # Multi-question: JSON keyed by exact IDs. Values are strings or list of strings.
    # Do NOT pre-select recommended options.
    example_obj: dict[str, Any] = {}
    for qid in q_ids:
        example_obj[qid] = "<ваш ответ>"
    try:
        reply = json.dumps(example_obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        issues.append("reply-example-json-encode-failed")
        return None, True

    blocks.append(
        "Несколько вопросов: ответ должен быть ОДНИМ JSON-объектом, "
        "ключи — точные ID вопросов, значения — строка или список строк "
        "(как ожидает существующий parser _question_answers). "
        "Рекомендованные варианты НЕ подставляются автоматически."
    )
    return reply, manual


def _question_has_no_options(question: Any) -> bool:
    if not isinstance(question, Mapping):
        return True
    options = question.get("options")
    if options is None:
        return True
    if isinstance(options, list) and len(options) == 0:
        return True
    return False


# ---------------------------------------------------------------------------
# command_approval
# ---------------------------------------------------------------------------


def _render_command(
    blocks: list[str],
    params: Mapping[str, Any],
    issues: list[str],
) -> bool:
    manual = False
    lines: list[str] = []

    # shell (if distinct)
    shell = params.get("shell")
    if isinstance(shell, str) and shell.strip():
        lines.append(f"shell:\n{shell}")
    elif shell is not None and not isinstance(shell, str):
        issues.append("command-shell-non-string")
        manual = True

    # command: string OR argv list — never lossy-join an argv list into one string
    command = params.get("command")
    argv = params.get("argv")
    if argv is None:
        argv = params.get("args")

    if isinstance(command, list):
        # Treat list command as argv
        lines.append("command (argv, без объединения):")
        before = len(issues)
        lines.extend(_format_argv_lines(command, issues, "command"))
        manual = manual or len(issues) != before
    elif isinstance(command, str):
        lines.append(f"command:\n{command}")
    elif command is not None:
        issues.append("command-non-json-scalar-or-list")
        manual = True
        lines.append("command: [некорректный тип — не сериализован через str/repr]")

    if argv is not None:
        if isinstance(argv, list):
            lines.append("argv (полный список аргументов, без lossy join):")
            before = len(issues)
            lines.extend(_format_argv_lines(argv, issues, "argv"))
            manual = manual or len(issues) != before
        elif isinstance(argv, str):
            lines.append(f"argv (строка):\n{argv}")
        else:
            issues.append("argv-invalid-type")
            manual = True
            lines.append("argv: [некорректный тип]")

    cwd = params.get("cwd")
    if cwd is None:
        cwd = params.get("working_directory") or params.get("workingDirectory")
    if isinstance(cwd, str):
        lines.append(f"cwd:\n{cwd}")
    elif cwd is not None:
        issues.append("cwd-non-string")
        manual = True

    reason = params.get("reason")
    if isinstance(reason, str):
        lines.append(f"reason:\n{reason}")
    elif reason is not None:
        issues.append("reason-non-string")
        manual = True

    scope = params.get("scope")
    if scope is not None:
        lines.append("scope:")
        lines.append(_render_json_value(scope, indent=2))

    description = params.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"description:\n{description}")

    path = params.get("path")
    if isinstance(path, str) and path.strip():
        lines.append(f"path:\n{path}")

    env = params.get("env")
    if env is not None:
        lines.append("env:")
        lines.append(_render_json_value(env, indent=2))

    # Desktop 26.917 supplies these approval details. Show all of them to the
    # owner; a new unrecognised field still forces manual review above.
    for key in (
        "availableDecisions", "commandActions", "environmentId", "kind",
        "proposedExecpolicyAmendment", "startedAtMs",
    ):
        if key in params:
            lines.append(f"{key}:")
            lines.append(_render_json_value(params[key], indent=2))

    if not lines:
        issues.append("command-approval-empty")
        manual = True
        lines.append("Параметры команды отсутствуют или пусты.")

    blocks.append("\n".join(lines))
    blocks.append(
        "Это только отображение запроса. Решение approve/deny принимает "
        "оператор через bridge; renderer решение не предлагает."
    )
    return manual


def _format_argv_lines(
    argv: list[Any],
    issues: list[str],
    label: str,
) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(argv):
        if isinstance(item, str):
            out.append(f"  [{i}] {item}")
        elif isinstance(item, (int, float, bool)) or item is None:
            out.append(f"  [{i}] {_fmt_scalar(item)}")
        else:
            issues.append(f"{label}[{i}]-non-json-like")
            out.append(f"  [{i}] [не-JSON-подобное значение — пропущено]")
    if not out:
        out.append("  (пустой список)")
    return out


# ---------------------------------------------------------------------------
# file_approval
# ---------------------------------------------------------------------------


def _render_file(
    blocks: list[str],
    params: Mapping[str, Any],
    issues: list[str],
) -> bool:
    manual = False
    lines: list[str] = []
    cwd = params.get("cwd")
    if cwd is None:
        cwd = params.get("working_directory") or params.get("workingDirectory")
    if isinstance(cwd, str):
        lines.append(f"cwd:\n{cwd}")
    elif cwd is not None:
        issues.append("file-cwd-non-string")
        manual = True

    # Paths (single / list / files entries)
    path = params.get("path")
    paths = params.get("paths")
    files = params.get("files")
    file_one = params.get("file")

    path_lines: list[str] = []
    if isinstance(path, str):
        path_lines.append(path)
    elif path is not None:
        issues.append("path-non-string")
        manual = True

    if isinstance(paths, list):
        for i, p in enumerate(paths):
            if isinstance(p, str):
                path_lines.append(p)
            elif isinstance(p, Mapping):
                # nested path object
                inner = p.get("path") or p.get("file") or p.get("name")
                if isinstance(inner, str):
                    path_lines.append(inner)
                path_lines.append(f"  деталь[{i}]:")
                path_lines.append(_render_json_value(p, indent=4))
            else:
                issues.append(f"paths[{i}]-invalid")
                manual = True
    elif paths is not None:
        issues.append("paths-not-list")
        manual = True

    if isinstance(files, list):
        for i, f in enumerate(files):
            if isinstance(f, str):
                path_lines.append(f)
            elif isinstance(f, Mapping):
                inner = f.get("path") or f.get("file") or f.get("name")
                if isinstance(inner, str):
                    path_lines.append(inner)
                path_lines.append(f"  файл[{i}]:")
                path_lines.append(_render_json_value(f, indent=4))
            else:
                issues.append(f"files[{i}]-invalid")
                manual = True
    elif files is not None:
        issues.append("files-not-list")
        manual = True

    if isinstance(file_one, str):
        path_lines.append(file_one)
    elif isinstance(file_one, Mapping):
        path_lines.append(_render_json_value(file_one, indent=2))
    elif file_one is not None:
        issues.append("file-invalid-type")
        manual = True

    for key in ("old_path", "oldPath", "new_path", "newPath"):
        v = params.get(key)
        if isinstance(v, str):
            path_lines.append(f"{key}: {v}")

    if path_lines:
        lines.append("Пути:")
        for p in path_lines:
            if p.startswith("  "):
                lines.append(p)
            else:
                lines.append(f"  • {p}")
    else:
        issues.append("file-paths-missing")
        manual = True
        lines.append("Пути: [не указаны]")

    # Actions / changes
    for key, title in (
        ("action", "Действие"),
        ("actions", "Действия"),
        ("change", "Изменение"),
        ("changes", "Изменения"),
    ):
        val = params.get(key)
        if val is None:
            continue
        lines.append(f"{title}:")
        lines.append(_render_json_value(val, indent=2))

    # Diff(s) — full, no truncation
    for key, title in (("diff", "Diff"), ("diffs", "Diffs"), ("content", "Содержимое")):
        val = params.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            lines.append(f"{title}:")
            lines.append(val)
        else:
            lines.append(f"{title}:")
            lines.append(_render_json_value(val, indent=2))

    reason = params.get("reason")
    if isinstance(reason, str):
        lines.append(f"reason:\n{reason}")
    elif reason is not None:
        issues.append("file-reason-non-string")
        manual = True

    scope = params.get("scope")
    if scope is not None:
        lines.append("scope:")
        lines.append(_render_json_value(scope, indent=2))

    description = params.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"description:\n{description}")

    blocks.append("\n".join(lines))
    blocks.append(
        "Это только отображение запроса на файловую операцию. "
        "Renderer не выполняет файловых действий и не предлагает approve/deny."
    )
    return manual


# ---------------------------------------------------------------------------
# permissions_approval
# ---------------------------------------------------------------------------


def _render_permissions(
    blocks: list[str],
    params: Mapping[str, Any],
    issues: list[str],
) -> bool:
    manual = False
    lines: list[str] = []

    # Concrete permission categories — never replace with vague «дать доступ».
    network = params.get("network")
    if network is not None:
        lines.append("network (конкретный запрос):")
        lines.append(_render_json_value(network, indent=2))

    for key in ("filesystem", "file_system", "fileSystem"):
        fs = params.get(key)
        if fs is not None:
            lines.append(f"{key} (конкретный запрос):")
            lines.append(_render_json_value(fs, indent=2))

    for key in (
        "permissions",
        "permission",
        "extra",
        "extra_permissions",
        "extraPermissions",
        "rights",
    ):
        val = params.get(key)
        if val is not None:
            lines.append(f"{key}:")
            lines.append(_render_json_value(val, indent=2))

    for key in ("hosts", "domains", "paths", "path", "actions", "action"):
        val = params.get(key)
        if val is not None:
            lines.append(f"{key}:")
            lines.append(_render_json_value(val, indent=2))

    scope = params.get("scope")
    if scope is not None:
        lines.append("scope:")
        lines.append(_render_json_value(scope, indent=2))
    else:
        issues.append("permissions-scope-missing")
        lines.append("scope: [не указан]")

    duration = params.get("duration")
    if duration is not None:
        if isinstance(duration, (str, int, float, bool)) or duration is None:
            lines.append(f"duration: {_fmt_scalar(duration)}")
        else:
            lines.append("duration:")
            lines.append(_render_json_value(duration, indent=2))
    else:
        issues.append("permissions-duration-missing")
        lines.append("duration: [не указан]")

    reason = params.get("reason")
    if isinstance(reason, str):
        lines.append(f"reason:\n{reason}")
    elif reason is not None:
        issues.append("permissions-reason-non-string")
        manual = True

    description = params.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"description:\n{description}")

    if not any(
        params.get(k) is not None
        for k in (
            "network",
            "filesystem",
            "file_system",
            "fileSystem",
            "permissions",
            "permission",
            "extra",
            "extra_permissions",
            "extraPermissions",
            "rights",
            "hosts",
            "domains",
            "paths",
            "path",
            "actions",
            "action",
        )
    ):
        issues.append("permissions-details-missing")
        manual = True
        lines.insert(0, "Конкретные полномочия не указаны в известных полях.")

    blocks.append("\n".join(lines))
    blocks.append(
        "Показаны конкретные запрошенные полномочия (network / filesystem / "
        "extra / scope / duration). Формулировка «дать доступ» вместо деталей "
        "не используется. Решение принимает оператор через bridge."
    )
    return manual


# ---------------------------------------------------------------------------
# mcp_elicitation
# ---------------------------------------------------------------------------


def _render_mcp(
    blocks: list[str],
    params: Mapping[str, Any],
    issues: list[str],
) -> bool:
    manual = False
    lines: list[str] = []

    message = params.get("message")
    if message is None:
        message = params.get("prompt") or params.get("description") or params.get("title")
    if isinstance(message, str):
        lines.append(f"message:\n{message}")
    elif message is not None:
        issues.append("mcp-message-non-string")
        manual = True
        lines.append("message: [нестроковое значение]")
    else:
        issues.append("mcp-message-missing")
        lines.append("message: [отсутствует]")

    mode = params.get("mode")
    mode_str: str | None = None
    if isinstance(mode, str):
        mode_str = mode
        lines.append(f"mode: {mode}")
    elif mode is not None:
        issues.append("mcp-mode-non-string")
        manual = True
        lines.append("mode: [нестроковое значение]")
        lines.append(_render_json_value(mode, indent=2))
    else:
        issues.append("mcp-mode-missing")
        lines.append("mode: [отсутствует]")

    # Schema
    schema = None
    schema_key = None
    for key in ("requestedSchema", "requested_schema", "schema"):
        if key in params and params.get(key) is not None:
            schema = params.get(key)
            schema_key = key
            break
    if schema is None:
        issues.append("mcp-schema-missing")
        lines.append("requestedSchema: [отсутствует]")
    else:
        lines.append(f"{schema_key}:")
        before = len(issues)
        lines.extend(_render_schema(schema, issues))
        manual = manual or len(issues) != before

    # URL / URI if present in display-allowed payload — show, do not open.
    url_val = None
    url_key = None
    for key in ("url", "URL", "uri", "link"):
        if key in params and params.get(key) is not None:
            url_val = params.get(key)
            url_key = key
            break
    if url_val is not None:
        if isinstance(url_val, str):
            lines.append(f"{url_key} (только отображение, URL не открывается):\n{url_val}")
        else:
            lines.append(f"{url_key}:")
            lines.append(_render_json_value(url_val, indent=2))
        issues.append("mcp-url-present-manual-review")
        manual = True

    for key in ("server", "serverName", "server_name", "tool", "toolName", "tool_name"):
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            lines.append(f"{key}: {val}")

    # Interactive / URL flow detection.
    if mode_str is not None:
        mode_l = mode_str.strip().lower().replace(" ", "_")
        if mode_l in _MCP_URL_MODE_MARKERS or any(
            m in mode_l for m in ("url", "oauth", "browser", "interactive", "redirect")
        ):
            issues.append(f"mcp-unsupported-interactive-mode:{mode_str}")
            manual = True
            lines.append(
                f"Режим «{mode_str}» относится к интерактивному/URL flow, "
                "который этот renderer не выполняет. Требуется ручная проверка."
            )

    blocks.append("\n".join(lines))
    blocks.append(
        "MCP elicitation: схема и поля показаны полностью. "
        "Renderer не исполняет schema, не открывает URL и не делает auto-accept."
    )
    return manual


def _render_schema(schema: Any, issues: list[str]) -> list[str]:
    """Render requestedSchema with required fields, types, and enums."""
    out: list[str] = []
    if not isinstance(schema, Mapping):
        issues.append("mcp-schema-not-mapping")
        out.append("  [schema не является JSON-объектом]")
        out.append(_render_json_value(schema, indent=2))
        return out

    schema_type = schema.get("type")
    if schema_type is not None:
        out.append(f"  type: {_fmt_scalar(schema_type) if _is_display_scalar(schema_type) else '[сложный type]'}")

    required = schema.get("required")
    if isinstance(required, list):
        req_items = []
        for item in required:
            if isinstance(item, str):
                req_items.append(item)
            elif _is_display_scalar(item):
                req_items.append(_fmt_scalar(item))
            else:
                issues.append("mcp-required-item-non-scalar")
                req_items.append("[нескалярный элемент]")
        out.append("  required: " + (", ".join(req_items) if req_items else "(пусто)"))
    elif required is not None:
        out.append("  required:")
        out.append(_render_json_value(required, indent=4))

    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        out.append("  properties:")
        for pname, pschema in properties.items():
            out.append(f"    • {pname}:")
            out.extend(_render_property_schema(pschema, indent=6, issues=issues, path=str(pname)))
    elif properties is not None:
        issues.append("mcp-properties-not-mapping")
        out.append("  properties: [не объект]")
        out.append(_render_json_value(properties, indent=4))

    # Other schema keys (enum at root, items, additionalProperties, etc.)
    known = frozenset({"type", "required", "properties", "title", "description", "$schema"})
    for key, val in schema.items():
        if key in known:
            continue
        if key in ("title", "description") and isinstance(val, str):
            out.append(f"  {key}: {val}")
            continue
        if key == "enum":
            out.append("  enum:")
            out.append(_render_json_value(val, indent=4))
            continue
        out.append(f"  {key}:")
        out.append(_render_json_value(val, indent=4))
        issues.append(f"mcp-schema-extra:{key}")

    # Also show full JSON for nested fidelity (no truncation).
    out.append("  Полная schema (JSON):")
    out.append(_render_json_value(schema, indent=4))
    return out


def _render_property_schema(
    pschema: Any,
    *,
    indent: int,
    issues: list[str],
    path: str,
) -> list[str]:
    pad = " " * indent
    out: list[str] = []
    if not isinstance(pschema, Mapping):
        if _is_display_scalar(pschema):
            out.append(f"{pad}{_fmt_scalar(pschema)}")
        else:
            issues.append(f"mcp-property-{path}-invalid")
            out.append(f"{pad}[некорректный тип свойства]")
        return out

    ptype = pschema.get("type")
    if ptype is not None:
        if _is_display_scalar(ptype):
            out.append(f"{pad}type: {_fmt_scalar(ptype)}")
        elif isinstance(ptype, list):
            out.append(f"{pad}type: {_render_json_value(ptype, indent=0).strip()}")
        else:
            out.append(f"{pad}type:")
            out.append(_render_json_value(ptype, indent=indent + 2))

    if "enum" in pschema:
        out.append(f"{pad}enum:")
        out.append(_render_json_value(pschema.get("enum"), indent=indent + 2))

    for key in ("description", "title", "default", "format", "minimum", "maximum", "minLength", "maxLength"):
        if key in pschema:
            val = pschema[key]
            if _is_display_scalar(val):
                out.append(f"{pad}{key}: {_fmt_scalar(val)}")
            else:
                out.append(f"{pad}{key}:")
                out.append(_render_json_value(val, indent=indent + 2))

    if "items" in pschema:
        out.append(f"{pad}items:")
        items = pschema["items"]
        if isinstance(items, Mapping):
            out.extend(_render_property_schema(items, indent=indent + 2, issues=issues, path=f"{path}.items"))
        else:
            out.append(_render_json_value(items, indent=indent + 2))

    if "properties" in pschema and isinstance(pschema["properties"], Mapping):
        out.append(f"{pad}properties:")
        nested_req = pschema.get("required")
        if isinstance(nested_req, list):
            out.append(f"{pad}  required: {', '.join(str(x) for x in nested_req if isinstance(x, (str, int, float, bool)) or x is None)}")
        for nname, nschema in pschema["properties"].items():
            out.append(f"{pad}  • {nname}:")
            out.extend(
                _render_property_schema(
                    nschema, indent=indent + 4, issues=issues, path=f"{path}.{nname}"
                )
            )

    if "required" in pschema and "properties" not in pschema:
        out.append(f"{pad}required:")
        out.append(_render_json_value(pschema["required"], indent=indent + 2))

    return out


# ---------------------------------------------------------------------------
# JSON-like helpers (never call methods / __str__ / repr on alien objects)
# ---------------------------------------------------------------------------


def _is_json_like(value: Any, issues: list[str], path: str, *, _depth: int = 0) -> bool:
    if _depth > 64:
        issues.append(f"json-like-too-deep:{path}")
        return False
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, Mapping):
        ok = True
        for k, v in value.items():
            if not isinstance(k, str):
                issues.append(f"non-string-key:{path}")
                ok = False
                continue
            if not _is_json_like(v, issues, f"{path}.{k}", _depth=_depth + 1):
                ok = False
        return ok
    if isinstance(value, list):
        ok = True
        for i, item in enumerate(value):
            if not _is_json_like(item, issues, f"{path}[{i}]", _depth=_depth + 1):
                ok = False
        return ok
    # tuple is uncommon in JSON-like Desktop payloads; treat as non-JSON-like
    # to avoid silently accepting unexpected objects.
    issues.append(f"non-json-like-at:{path}")
    return False


def _is_display_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        # Use json to get stable representation without calling custom __str__.
        return json.dumps(value)
    # Caller must not pass aliens here.
    return "<unprintable>"


def _render_json_value(value: Any, indent: int = 0) -> str:
    """Render a JSON-like value as readable text without truncation.

    Alien objects are replaced with an explicit placeholder (no __str__/repr).
    """
    pad = " " * indent
    try:
        cleaned = _sanitize_for_json(value)
        text = json.dumps(cleaned, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return f"{pad}[значение не сериализуется как JSON]"
    # Indent every line.
    lines = text.split("\n")
    return "\n".join(pad + line if line else pad for line in lines)


def _sanitize_for_json(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 64:
        return "[too-deep]"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = k if isinstance(k, str) else "[non-string-key]"
            out[key] = _sanitize_for_json(v, _depth=_depth + 1)
        return out
    if isinstance(value, list):
        return [_sanitize_for_json(item, _depth=_depth + 1) for item in value]
    return "[non-json-like-value]"


def _unknown_params(kind: str, params: Mapping[str, Any]) -> list[str]:
    known = _PARAMS_KNOWN_BY_KIND.get(kind, frozenset()) | _ROUTING_PARAMS
    return sorted(k for k in params.keys() if k not in known)


def _truthy_flag(params: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        val = params.get(key)
        if val is True:
            return True
        if isinstance(val, str) and val.strip().lower() in {"1", "true", "yes", "да"}:
            return True
    return False


def _append_payload_overview(
    blocks: list[str],
    payload: Any,
    issues: list[str],
) -> None:
    if not isinstance(payload, Mapping):
        issues.append("payload-not-mapping")
        blocks.append("payload: [не JSON-объект]")
        return
    if not _is_json_like(payload, issues, path="$"):
        blocks.append(
            "payload содержит не-JSON-подобные значения и не сериализован через str/repr."
        )
        return
    blocks.append("Содержимое payload (обзор):")
    blocks.append(_render_json_value(payload, indent=2))
