"""Meaningful tests for desktop_artifact_refs (block G-B)."""

from __future__ import annotations

import pytest

from src.application.desktop_artifact_refs import (
    ArtifactReference,
    ArtifactReferences,
    extract_artifact_references,
)


def _spans_ok(text: str, result: ArtifactReferences) -> None:
    for ref in result.references:
        assert ref.raw == text[ref.start : ref.end], (
            f"span mismatch: raw={ref.raw!r} slice={text[ref.start:ref.end]!r}"
        )
        assert 0 <= ref.start <= ref.end <= len(text)
        assert ref.kind in {"windows_absolute", "remote_url", "unsupported_local"}


# ---------------------------------------------------------------------------
# Basic Windows absolute forms
# ---------------------------------------------------------------------------


def test_backslash_windows_absolute():
    text = r"See C:\folder\report.txt please"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder\report.txt"
    assert ref.raw == r"C:\folder\report.txt"
    assert ref.label is None
    assert ref.line is None


def test_forward_slash_windows_absolute():
    text = "See C:/folder/report.txt please"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder\report.txt"
    assert ref.raw == "C:/folder/report.txt"


def test_leading_slash_before_drive():
    text = "path=/C:/folder/report.txt done"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder\report.txt"
    assert ref.raw == "/C:/folder/report.txt"


def test_mixed_case_drive_preserved():
    text = r"d:\Data\File.TXT"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"d:\Data\File.TXT"
    assert r.references[0].kind == "windows_absolute"


def test_dotdot_not_resolved():
    text = r"C:\project\..\secret\file.txt"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\project\..\secret\file.txt"
    assert r.references[0].kind == "windows_absolute"


def test_trailing_punctuation_not_in_path():
    text = r"File is C:\folder\report.txt."
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].raw == r"C:\folder\report.txt"
    assert r.references[0].path == r"C:\folder\report.txt"
    assert text[r.references[0].end] == "."


# ---------------------------------------------------------------------------
# Markdown links / images / angle brackets
# ---------------------------------------------------------------------------


def test_markdown_link_with_label():
    text = "Download [report](C:/folder/report.txt) now"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.raw == "[report](C:/folder/report.txt)"
    assert ref.label == "report"
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder\report.txt"


def test_markdown_angle_bracket_address_with_spaces():
    text = "See [doc](<C:/folder with spaces/report.txt>) end"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.raw == "[doc](<C:/folder with spaces/report.txt>)"
    assert ref.label == "doc"
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder with spaces\report.txt"


def test_markdown_image():
    text = "Img ![shot](C:/folder/photo.png) ok"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.raw == "![shot](C:/folder/photo.png)"
    assert ref.label == "shot"
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder\photo.png"


def test_standalone_angle_bracket_path():
    text = "Open <C:/folder with spaces/report.txt> please"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.raw == "<C:/folder with spaces/report.txt>"
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\folder with spaces\report.txt"


# ---------------------------------------------------------------------------
# Backticks, quotes, Cyrillic, spaces, parentheses
# ---------------------------------------------------------------------------


def test_backtick_path_no_leak():
    text = r"Run `C:\folder\report.txt` now"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.raw == r"`C:\folder\report.txt`"
    assert ref.path == r"C:\folder\report.txt"
    assert "`" not in ref.path
    assert ref.kind == "windows_absolute"


def test_double_quoted_path():
    text = r'Open "C:\folder\report.txt" today'
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.raw == r'"C:\folder\report.txt"'
    assert ref.path == r"C:\folder\report.txt"
    assert '"' not in ref.path


def test_single_quoted_path():
    text = r"Open 'C:/folder/report.txt' today"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].raw == "'C:/folder/report.txt'"
    assert r.references[0].path == r"C:\folder\report.txt"


def test_cyrillic_and_spaces_in_markdown():
    text = "[отчёт](<C:/папка с пробелами/файл (1).txt>)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.label == "отчёт"
    assert ref.kind == "windows_absolute"
    assert ref.path == r"C:\папка с пробелами\файл (1).txt"


def test_parentheses_in_filename_markdown():
    text = "[f](C:/folder/file(1).txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\folder\file(1).txt"
    assert r.references[0].kind == "windows_absolute"


def test_nested_parentheses_in_filename():
    text = "[f](C:/folder/file((nested)).txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\folder\file((nested)).txt"
    assert r.references[0].raw == "[f](C:/folder/file((nested)).txt)"


# ---------------------------------------------------------------------------
# Percent encoding
# ---------------------------------------------------------------------------


def test_markdown_percent_encoding_decoded_once():
    text = "[x](C:/folder/report%20file.txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\folder\report file.txt"


def test_percent_25_decoded_once():
    text = "[x](C:/folder/report%25file.txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\folder\report%file.txt"


def test_percent_unicode_decoded_once():
    # %D0%BF = Cyrillic 'п' in UTF-8
    text = "[x](C:/folder/%D0%BF.txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\folder\п.txt"


def test_bare_literal_percent_not_decoded():
    text = r"C:\folder\report%20file.txt"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].path == r"C:\folder\report%20file.txt"


def test_bare_percent_sign_not_silently_decoded():
    text = "[x](C:/folder/100%done.txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    # bare %d is not valid percent-encoding → left intact by unquote
    assert r.references[0].path == r"C:\folder\100%done.txt"


# ---------------------------------------------------------------------------
# Line suffix :12
# ---------------------------------------------------------------------------


def test_codex_line_suffix():
    text = r"C:\folder\report.txt:12"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    ref = r.references[0]
    assert ref.path == r"C:\folder\report.txt"
    assert ref.line == 12
    assert ref.raw == r"C:\folder\report.txt:12"


def test_line_suffix_not_confused_with_drive_colon():
    text = r"C:\folder\report.txt"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].line is None
    assert r.references[0].path == r"C:\folder\report.txt"


def test_line_suffix_with_colon_in_name_portion():
    # Colon inside filename portion before line suffix
    text = r"C:\folder\report:draft.txt:12"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    ref = r.references[0]
    assert ref.line == 12
    assert ref.path == r"C:\folder\report:draft.txt"


def test_line_suffix_in_backticks():
    text = r"see `C:\src\main.py:42` here"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    ref = r.references[0]
    assert ref.raw == r"`C:\src\main.py:42`"
    assert ref.path == r"C:\src\main.py"
    assert ref.line == 42


def test_line_and_column_suffix():
    text = r"C:\src\main.py:12:5"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].line == 12
    assert r.references[0].path == r"C:\src\main.py"


# ---------------------------------------------------------------------------
# Remote URL / UNC / file://
# ---------------------------------------------------------------------------


def test_http_remote_url():
    text = "See https://example.com/a/b.txt end"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "remote_url"
    assert ref.path == "https://example.com/a/b.txt"
    assert ref.raw == "https://example.com/a/b.txt"


def test_https_in_markdown_still_remote():
    text = "[site](https://example.com/x)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references[0].kind == "remote_url"
    assert r.references[0].path == "https://example.com/x"
    assert r.references[0].label == "site"


def test_file_scheme_is_remote_not_local():
    text = "file:///C:/folder/report.txt"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    assert r.references[0].kind == "remote_url"
    assert r.references[0].path == "file:///C:/folder/report.txt"


def test_unc_is_remote_url():
    text = r"Copy \\server\share\folder\file.txt please"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "remote_url"
    assert ref.path == r"\\server\share\folder\file.txt"
    assert ref.raw == r"\\server\share\folder\file.txt"


# ---------------------------------------------------------------------------
# Relative / incomplete / drive-relative → unsupported_local + issue
# ---------------------------------------------------------------------------


def test_relative_markdown_link_unsupported():
    text = "[rel](./folder/report.txt)"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "unsupported_local"
    assert ref.path == "./folder/report.txt"
    assert ref.label == "rel"
    assert any("unsupported" in x.lower() or "relative" in x.lower() or "./folder" in x for x in r.issues)


def test_incomplete_markdown_link():
    text = "broken [x](C:/folder"
    r = extract_artifact_references(text)
    # Must not vanish: issue and/or unsupported reference
    assert r.issues or r.references
    assert any("incomplete" in x.lower() for x in r.issues)


def test_drive_relative_c_file():
    text = r"bad C:file.txt here"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    ref = r.references[0]
    assert ref.kind == "unsupported_local"
    assert ref.raw == "C:file.txt"
    assert any("drive-relative" in x for x in r.issues)


# ---------------------------------------------------------------------------
# Order, repeats, multi on one line
# ---------------------------------------------------------------------------


def test_two_files_one_line():
    text = r"A C:\a\one.txt and C:\b\two.txt done"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 2
    assert r.references[0].path == r"C:\a\one.txt"
    assert r.references[1].path == r"C:\b\two.txt"
    assert r.references[0].start < r.references[1].start


def test_repeated_link_no_dedup():
    text = "[a](C:/f.txt) then [a](C:/f.txt) again"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 2
    assert r.references[0].path == r"C:\f.txt"
    assert r.references[1].path == r"C:\f.txt"
    assert r.references[0].start != r.references[1].start


# ---------------------------------------------------------------------------
# HTML-like, ambiguity, non-artifacts
# ---------------------------------------------------------------------------


def test_html_like_text_not_confused():
    text = '<a href="http://example.com">link</a> and <div class="x">'
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    # May pick up http URL inside quotes; must NOT invent Windows paths from tags
    for ref in r.references:
        assert ref.kind != "windows_absolute"
        assert not (ref.path and ref.path.startswith("<div"))


def test_phrase_with_dot_not_artifact():
    text = "Please read the final report.txt carefully today."
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert r.references == ()


def test_ambiguous_bare_path_with_spaces_issues():
    text = r"See C:\Users\My Documents\file.txt here"
    r = extract_artifact_references(text)
    # Must produce ambiguity issue and must NOT invent a full spaced filename
    assert any("ambiguous" in x.lower() for x in r.issues)
    for ref in r.references:
        if ref.kind == "windows_absolute":
            assert "Documents" not in (ref.path or "")


def test_quoted_ordinary_phrase_not_artifact():
    text = 'He said "hello world" to me.'
    r = extract_artifact_references(text)
    assert r.references == ()


# ---------------------------------------------------------------------------
# Very long text / stability
# ---------------------------------------------------------------------------


def test_very_long_text():
    pad = "word " * 50000
    text = pad + r" C:\folder\report.txt " + pad + " [x](C:/other/a.txt) " + pad
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 2
    assert r.references[0].path == r"C:\folder\report.txt"
    assert r.references[1].path == r"C:\other\a.txt"
    assert r.references[0].start < r.references[1].start


def test_empty_string():
    r = extract_artifact_references("")
    assert r.references == ()
    assert r.issues == ()


def test_return_types_frozen():
    r = extract_artifact_references(r"C:\a\b.txt")
    assert isinstance(r, ArtifactReferences)
    assert isinstance(r.references[0], ArtifactReference)
    with pytest.raises(Exception):
        r.references[0].path = "no"  # type: ignore[misc]


def test_markdown_forward_slash_not_silently_dropped():
    """Context defect regression: Markdown C:/... must be found."""
    text = "Here is [report](C:/folder/report.txt) for you"
    r = extract_artifact_references(text)
    _spans_ok(text, r)
    assert len(r.references) == 1
    assert r.references[0].kind == "windows_absolute"
    assert r.references[0].path == r"C:\folder\report.txt"
