"""Independent contract cases adapted to the integrated modules."""

import json
from html.parser import HTMLParser

from src.application.desktop_artifact_refs import extract_artifact_references
from src.application.desktop_interaction_view import render_interaction
from src.application.desktop_output import format_final_blocks


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _shown(result):
    visible = []
    for part in result.parts:
        if part.parse_mode == "HTML":
            parser = _Visible()
            parser.feed(part.text)
            visible.extend(parser.parts)
        else:
            visible.append(part.text)
    return "".join(visible)


def test_literal_identifier_and_empty_block():
    assert _shown(format_final_blocks(["my_var_name"])) == "my_var_name"
    result = format_final_blocks(["", "visible"])
    assert result.source_blocks == ("", "visible")
    assert all(part.text for part in result.parts)


def test_artifact_invalid_percent_utf8_is_issue():
    result = extract_artifact_references("[file](C:/report%FF.txt)")
    assert result.issues
    assert not any(ref.kind == "windows_absolute" for ref in result.references)


def test_artifact_markdown_windows_backslash_and_remote_port():
    result = extract_artifact_references(r"[file](C:\folder\report.txt)")
    assert [(ref.path, ref.kind) for ref in result.references] == [
        (r"C:\folder\report.txt", "windows_absolute")
    ]
    remote = extract_artifact_references("[site](https://example.test:8443)")
    assert remote.references[0].path == "https://example.test:8443"
    assert remote.references[0].line is None


def test_artifact_ambiguous_bare_spaces_not_guessed():
    result = extract_artifact_references(r"C:\Folder\Annual Report.txt")
    assert result.issues
    assert not any(ref.kind == "windows_absolute" for ref in result.references)


def test_invalid_argv_requires_review():
    view = render_interaction(
        "command_approval", {"params": {"command": [{}], "cwd": r"C:\project"}}
    )
    assert view.requires_manual_review


def test_unknown_nested_option_is_visible_and_requires_review():
    view = render_interaction(
        "user_input",
        {"params": {"questions": [
            {"id": "q", "question": "Select", "options": [
                {"label": "A", "description": "One", "new_policy": "OWNER_ONLY_SENTINEL"}
            ]}
        ]}},
    )
    assert "OWNER_ONLY_SENTINEL" in "\n".join(view.blocks)
    assert view.requires_manual_review and view.issues


def test_exact_question_ids_or_manual_review():
    view = render_interaction(
        "user_input",
        {"params": {"questions": [
            {"id": " q1 ", "question": "First?"},
            {"id": "q2", "question": "Second?"},
        ]}},
    )
    assert view.requires_manual_review or set(json.loads(view.reply_example)) == {
        " q1 ", "q2"
    }


def test_file_cwd_is_visible():
    view = render_interaction(
        "file_approval",
        {"params": {
            "path": "relative.txt", "action": "write", "cwd": r"C:\UNIQUE_CWD_SENTINEL"
        }},
    )
    assert "UNIQUE_CWD_SENTINEL" in "\n".join(view.blocks)


def test_invalid_mcp_schema_requires_review():
    view = render_interaction(
        "mcp_elicitation",
        {"params": {
            "message": "Fill", "mode": "form", "requestedSchema": "invalid-schema"
        }},
    )
    assert view.requires_manual_review
