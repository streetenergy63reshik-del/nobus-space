"""Meaningful tests for desktop_interaction_view.render_interaction.

Protocol proves the renderer only: critical fields preserved, no invented
approve/deny decision, no truncation of long command/diff/schema. Not evidence
of production Desktop approval correctness.
"""

from __future__ import annotations

import json

import pytest

from src.application.desktop_interaction_view import InteractionView, render_interaction


def _joined(view: InteractionView) -> str:
    return "\n".join(view.blocks)


def test_multi_questions_exact_ids_and_json_example() -> None:
    payload = {
        "id": "req-1",
        "method": "item/userInput",
        "params": {
            "questions": [
                {
                    "id": "q_alpha",
                    "question": "Выберите окружение",
                    "options": [
                        {"label": "prod", "description": "боевой контур"},
                        {"label": "stage", "description": "предпрод", "recommended": True},
                    ],
                },
                {
                    "id": "q_beta",
                    "question": "Комментарий",
                    "options": [],
                },
            ]
        },
    }
    view = render_interaction("user_input", payload)
    text = _joined(view)
    assert "q_alpha" in text
    assert "q_beta" in text
    assert "Выберите окружение" in text
    assert "боевой контур" in text
    assert "предпрод" in text
    assert "recommended" in text.lower() or "НЕ выбран" in text
    assert view.reply_example is not None
    decoded = json.loads(view.reply_example)
    assert set(decoded.keys()) == {"q_alpha", "q_beta"}
    # No invented decision / no pre-selected recommended option value.
    assert decoded["q_alpha"] != "stage"
    assert "разрешаю" not in (view.reply_example or "").lower()
    assert "approve" not in (view.reply_example or "").lower()
    for v in decoded.values():
        assert isinstance(v, (str, list))


def test_option_descriptions_preserved() -> None:
    payload = {
        "params": {
            "questions": [
                {
                    "id": "only",
                    "question": "Цвет?",
                    "options": [
                        {"label": "red", "description": "красный #ff0000"},
                        {"label": "blue", "desc": "синий"},
                    ],
                }
            ]
        }
    }
    view = render_interaction("user_input", payload)
    text = _joined(view)
    assert "красный #ff0000" in text
    assert "синий" in text
    assert "only" in text


def test_empty_question_id_manual_review() -> None:
    payload = {
        "params": {
            "questions": [
                {"id": "", "question": "Пустой ID"},
                {"id": "ok", "question": "Норм"},
            ]
        }
    }
    view = render_interaction("user_input", payload)
    assert view.requires_manual_review is True
    assert view.reply_example is None
    assert any("empty-id" in i or "missing-or-empty-id" in i for i in view.issues)


def test_duplicate_question_id_manual_review() -> None:
    payload = {
        "params": {
            "questions": [
                {"id": "dup", "question": "Первый"},
                {"id": "dup", "question": "Второй"},
            ]
        }
    }
    view = render_interaction("user_input", payload)
    assert view.requires_manual_review is True
    assert view.reply_example is None
    assert any("duplicate-question-id:dup" == i for i in view.issues)
    assert "dup" in _joined(view)


def test_single_question_allows_free_text() -> None:
    payload = {
        "params": {
            "questions": [
                {"id": "solo", "question": "Как зовут?", "options": None},
            ],
            "allow_free_text": True,
        }
    }
    view = render_interaction("user_input", payload)
    text = _joined(view)
    assert "solo" in text
    assert "свободн" in text.lower()
    # Single free-text: no multi JSON template required.
    assert view.reply_example is None
    assert view.requires_manual_review is False or "unknown" not in ",".join(view.issues)


def test_command_string_preserved() -> None:
    cmd = "python -m pytest tests/ -q --tb=short"
    payload = {
        "id": 42,
        "params": {
            "command": cmd,
            "cwd": "/workspace/project",
            "reason": "прогон тестов перед релизом",
            "scope": {"session": "local"},
        },
    }
    view = render_interaction("command_approval", payload)
    text = _joined(view)
    assert cmd in text
    assert "/workspace/project" in text
    assert "прогон тестов перед релизом" in text
    assert "session" in text
    assert "local" in text
    assert view.reply_example is None
    assert "разрешаю" not in text.lower() or "не предлагает" in text.lower()


def test_command_argv_no_lossy_join() -> None:
    argv = ["git", "commit", "-m", "fix: a b\nc"]
    payload = {"params": {"argv": argv, "shell": "/bin/bash"}}
    view = render_interaction("command_approval", payload)
    text = _joined(view)
    assert "/bin/bash" in text
    assert "[0] git" in text
    assert "[1] commit" in text
    assert "[2] -m" in text
    assert "[3] fix: a b\nc" in text
    # Must not collapse argv into a single shell-joined string as the only form.
    assert "argv" in text.lower() or "список аргументов" in text.lower()


def test_long_command_no_truncation() -> None:
    long_cmd = "x" * 5000 + "ENDMARKER"
    payload = {"params": {"command": long_cmd, "cwd": "/tmp", "reason": "r" * 2000}}
    view = render_interaction("command_approval", payload)
    text = _joined(view)
    assert long_cmd in text
    assert "ENDMARKER" in text
    assert ("r" * 2000) in text
    assert len(text) >= 7000


def test_file_changes_and_diff_preserved() -> None:
    diff = "--- a/foo\n+++ b/foo\n@@ -1 +1 @@\n-old\n+new LINE_UNIQUE_99\n" + ("z" * 3000)
    payload = {
        "params": {
            "paths": ["/tmp/a.txt", "/tmp/b.txt"],
            "actions": ["write", "chmod"],
            "changes": [{"path": "/tmp/a.txt", "op": "modify"}],
            "diff": diff,
            "reason": "правка конфига",
        }
    }
    view = render_interaction("file_approval", payload)
    text = _joined(view)
    assert "/tmp/a.txt" in text
    assert "/tmp/b.txt" in text
    assert "write" in text
    assert "chmod" in text
    assert "LINE_UNIQUE_99" in text
    assert ("z" * 3000) in text
    assert "правка конфига" in text
    assert view.reply_example is None


def test_permissions_network_filesystem_scope() -> None:
    payload = {
        "params": {
            "network": {"hosts": ["api.example.com:443"], "protocols": ["https"]},
            "filesystem": {"paths": ["/var/data"], "mode": "read-write"},
            "extra_permissions": ["clipboard"],
            "scope": {"workspace": "/proj", "level": "session"},
            "duration": "1h",
            "reason": "нужен доступ к API и каталогу данных",
        }
    }
    view = render_interaction("permissions_approval", payload)
    text = _joined(view)
    assert "api.example.com:443" in text
    assert "/var/data" in text
    assert "read-write" in text
    assert "clipboard" in text
    assert "session" in text
    assert "1h" in text
    assert "нужен доступ к API и каталогу данных" in text
    # Must not replace concrete action with vague phrase alone.
    assert "api.example.com" in text
    assert view.reply_example is None


def test_permissions_no_vague_only_access_phrase() -> None:
    payload = {
        "params": {
            "network": {"allow": ["10.0.0.1"]},
            "scope": "agent",
            "duration": 60,
        }
    }
    view = render_interaction("permissions_approval", payload)
    text = _joined(view)
    assert "10.0.0.1" in text
    # Vague-only replacement must not be the sole description of the action.
    assert "network" in text.lower()


def test_missing_params_manual_review() -> None:
    view = render_interaction("command_approval", {"id": "x"})
    assert view.requires_manual_review is True
    assert any("missing-params" == i for i in view.issues)
    assert view.reply_example is None


def test_unknown_keys_preserved_with_issue() -> None:
    payload = {
        "params": {
            "command": "echo hi",
            "customWidget": {"foo": 1},
            "mystery": "keep-me-VISIBLE",
        },
        "extraTop": {"a": 2},
    }
    view = render_interaction("command_approval", payload)
    text = _joined(view)
    assert "keep-me-VISIBLE" in text
    assert "customWidget" in text
    assert "extraTop" in text
    assert any(i.startswith("unknown-param:customWidget") for i in view.issues)
    assert any(i.startswith("unknown-param:mystery") for i in view.issues)
    assert any(i.startswith("unknown-top:extraTop") for i in view.issues)
    assert view.requires_manual_review is True
    assert view.reply_example is None


def test_unknown_kind_manual_review_no_accept_template() -> None:
    view = render_interaction("quantum_approval", {"params": {"x": 1}})
    assert view.requires_manual_review is True
    assert view.reply_example is None
    assert any("unknown-kind" in i for i in view.issues)
    assert "разрешаю" not in _joined(view).lower()


def test_mcp_nested_schema_required_enum() -> None:
    schema = {
        "type": "object",
        "required": ["name", "env"],
        "properties": {
            "name": {"type": "string", "description": "имя сервиса"},
            "env": {
                "type": "string",
                "enum": ["dev", "prod", "тест"],
            },
            "nested": {
                "type": "object",
                "required": ["port"],
                "properties": {
                    "port": {"type": "integer", "minimum": 1},
                },
            },
        },
    }
    payload = {
        "params": {
            "message": "Заполните форму MCP",
            "mode": "form",
            "requestedSchema": schema,
            "serverName": "demo-mcp",
        }
    }
    view = render_interaction("mcp_elicitation", payload)
    text = _joined(view)
    assert "Заполните форму MCP" in text
    assert "mode: form" in text
    assert "name" in text
    assert "env" in text
    assert "dev" in text and "prod" in text and "тест" in text
    assert "имя сервиса" in text
    assert "port" in text
    assert "integer" in text
    assert "demo-mcp" in text
    assert view.reply_example is None


def test_mcp_url_requires_manual_review() -> None:
    payload = {
        "params": {
            "message": "Авторизуйтесь",
            "mode": "url",
            "url": "https://example.com/oauth?x=1",
            "requestedSchema": {"type": "object", "properties": {}},
        }
    }
    view = render_interaction("mcp_elicitation", payload)
    assert view.requires_manual_review is True
    text = _joined(view)
    assert "https://example.com/oauth?x=1" in text
    assert any("url" in i.lower() or "interactive" in i.lower() or "manual" in i.lower() for i in view.issues)
    # Must not look like auto-accept.
    assert view.reply_example is None
    assert "auto-accept" not in text.lower() or "не делает auto-accept" in text.lower()


def test_mcp_interactive_mode_manual_review() -> None:
    payload = {
        "params": {
            "message": "interactive flow",
            "mode": "browser_oauth",
            "requested_schema": {"type": "object", "required": ["token"], "properties": {"token": {"type": "string"}}},
        }
    }
    view = render_interaction("mcp_elicitation", payload)
    assert view.requires_manual_review is True
    assert "token" in _joined(view)


def test_unicode_cyrillic_emoji() -> None:
    payload = {
        "params": {
            "questions": [
                {
                    "id": "юникод_id",
                    "question": "Привет 👋 мир — проверка «кавычек»",
                    "options": [{"label": "да ✅", "description": "подтверждение ✨"}],
                },
                {
                    "id": "второй",
                    "question": "Ещё вопрос",
                },
            ]
        }
    }
    view = render_interaction("user_input", payload)
    text = _joined(view)
    assert "юникод_id" in text
    assert "👋" in text
    assert "✨" in text
    assert "«кавычек»" in text
    decoded = json.loads(view.reply_example or "{}")
    assert "юникод_id" in decoded and "второй" in decoded


def test_wrong_types_manual_review() -> None:
    view = render_interaction("user_input", {"params": {"questions": "not-a-list"}})
    assert view.requires_manual_review is True
    assert view.reply_example is None
    assert any("questions-not-list" == i for i in view.issues)

    view2 = render_interaction("command_approval", {"params": "oops"})
    assert view2.requires_manual_review is True
    assert any("params-not-mapping" == i for i in view2.issues)


def test_non_json_like_object_no_str_repr() -> None:
    class Alien:
        def __str__(self) -> str:  # pragma: no cover - must not be called
            raise AssertionError("str must not be called")

        def __repr__(self) -> str:  # pragma: no cover
            raise AssertionError("repr must not be called")

        def dangerous(self) -> None:  # pragma: no cover
            raise AssertionError("methods must not be called")

    payload = {"params": {"command": Alien()}}
    view = render_interaction("command_approval", payload)
    assert view.requires_manual_review is True
    assert any("non-json-like" in i for i in view.issues)
    text = _joined(view)
    assert "Alien" not in text  # no repr leak


def test_command_list_as_argv() -> None:
    payload = {"params": {"command": ["echo", "hello", "world"], "cwd": "C:\\Work"}}
    view = render_interaction("command_approval", payload)
    text = _joined(view)
    assert "[0] echo" in text
    assert "[1] hello" in text
    assert "[2] world" in text
    assert "C:\\Work" in text


def test_no_approve_deny_decision_in_examples() -> None:
    for kind, params in (
        ("command_approval", {"command": "ls", "cwd": "/"}),
        ("file_approval", {"path": "/tmp/x", "diff": "+a"}),
        ("permissions_approval", {"network": {"hosts": ["h"]}, "scope": "s", "duration": "d"}),
        ("mcp_elicitation", {"message": "m", "mode": "form", "requestedSchema": {"type": "object"}}),
    ):
        view = render_interaction(kind, {"params": params})
        assert view.reply_example is None
        blob = _joined(view).lower()
        # May mention that operator decides, but must not ship accept template.
        assert "«разрешаю»" not in blob
        assert '"decision": "approve"' not in blob


def test_invalid_kind_empty() -> None:
    view = render_interaction("", {"params": {}})
    assert view.requires_manual_review is True
    assert view.reply_example is None


def test_request_id_and_method_shown() -> None:
    view = render_interaction(
        "command_approval",
        {"id": "abc-123", "method": "item/commandExecution/requestApproval", "params": {"command": "true"}},
    )
    text = _joined(view)
    assert "abc-123" in text
    assert "item/commandExecution/requestApproval" in text


def test_multi_question_json_keys_match_parser_contract() -> None:
    """reply_example must be dict keyed by question IDs → str or list[str]."""
    ids = ("id-1", "id-2", "id-3")
    payload = {
        "params": {
            "questions": [
                {"id": ids[0], "question": "A", "options": [{"label": "x"}]},
                {"id": ids[1], "question": "B"},
                {"id": ids[2], "question": "C", "multiple": True, "options": [{"label": "1"}, {"label": "2"}]},
            ]
        }
    }
    view = render_interaction("user_input", payload)
    assert view.reply_example is not None
    decoded = json.loads(view.reply_example)
    assert set(decoded) == set(ids)
    # Simulate existing _question_answers acceptance shape.
    for qid in ids:
        value = decoded[qid]
        values = value if isinstance(value, list) else [value]
        assert values and all(isinstance(item, str) and item.strip() for item in values)


def test_interaction_view_frozen() -> None:
    view = render_interaction("command_approval", {"params": {"command": "x"}})
    assert isinstance(view, InteractionView)
    with pytest.raises(Exception):
        view.requires_manual_review = False  # type: ignore[misc]


def test_long_schema_no_hidden_cap() -> None:
    big_enum = [f"value_{i}_UNIQUE" for i in range(200)]
    payload = {
        "params": {
            "message": "schema",
            "mode": "form",
            "requestedSchema": {
                "type": "object",
                "required": ["field"],
                "properties": {
                    "field": {"type": "string", "enum": big_enum},
                },
            },
        }
    }
    view = render_interaction("mcp_elicitation", payload)
    text = _joined(view)
    assert "value_0_UNIQUE" in text
    assert "value_199_UNIQUE" in text
