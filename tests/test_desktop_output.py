"""Meaningful tests for desktop_output.format_final_blocks."""

from __future__ import annotations

import re

import pytest

from src.application.desktop_output import (
    FormattedOutput,
    TelegramPart,
    format_final_blocks,
    utf16_len,
)


def _visible(part: TelegramPart) -> str:
    if part.parse_mode is None:
        return part.text
    s = part.text
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&#39;", "'")
    )


def _all_visible(result: FormattedOutput) -> str:
    return "".join(_visible(p) for p in result.parts)


def _assert_budget(result: FormattedOutput, max_units: int) -> None:
    for p in result.parts:
        assert utf16_len(p.text) <= max_units, (
            f"part exceeds budget: {utf16_len(p.text)} > {max_units}"
        )


def _assert_html_self_contained(result: FormattedOutput) -> None:
    for p in result.parts:
        if p.parse_mode != "HTML":
            continue
        assert not p.text.endswith("<")
        assert not p.text.endswith("&")
        # Balanced limited tags.
        stack: list[str] = []
        for m in re.finditer(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", p.text):
            full = m.group(0)
            name = m.group(1).lower()
            if full.startswith("</"):
                assert stack and stack[-1] == name
                stack.pop()
            elif full.endswith("/>"):
                continue
            else:
                stack.append(name)
        assert stack == []


def test_source_blocks_literal_including_empty_and_trailing() -> None:
    blocks = ["привет\n", "", "  spaces  ", "尾\n\n"]
    result = format_final_blocks(blocks)
    assert result.source_blocks == tuple(blocks)
    assert result.source_blocks[0].endswith("\n")
    assert result.source_blocks[1] == ""


def test_cyrillic_and_combining() -> None:
    text = "Привет мир! e\u0301 combining"
    result = format_final_blocks([text])
    assert result.source_blocks == (text,)
    visible = _all_visible(result)
    assert "Привет" in visible
    assert "мир" in visible
    assert "combining" in visible
    assert "e\u0301" in visible or "é" in visible


def test_emoji_outside_bmp_utf16() -> None:
    # U+1F600 😀 is one codepoint, two UTF-16 units.
    text = "hello 😀 world"
    assert utf16_len("😀") == 2
    result = format_final_blocks([text], max_units=64)
    assert "😀" in _all_visible(result)
    _assert_budget(result, 64)
    # Ensure we never split the surrogate pair: each part must be valid.
    for p in result.parts:
        p.text.encode("utf-16-le")  # raises if lone surrogate


def test_amp_lt_gt_quotes_escaped() -> None:
    text = 'Use & <tag> and "quotes" &amp; raw'
    result = format_final_blocks([text])
    assert result.source_blocks == (text,)
    joined = "".join(p.text for p in result.parts)
    if any(p.parse_mode == "HTML" for p in result.parts):
        assert "&amp;" in joined
        assert "&lt;tag&gt;" in joined or "&lt;" in joined
        # Must not contain raw unescaped <tag>
        assert "<tag>" not in joined
    visible = _all_visible(result)
    assert "&" in visible
    assert "<tag>" in visible
    assert '"quotes"' in visible


def test_empty_block_is_preserved_without_sendable_part() -> None:
    result = format_final_blocks([""])
    assert result.source_blocks == ("",)
    assert result.parts == ()


def test_multiple_finals_preserve_order_no_mix() -> None:
    blocks = ["ANSWER-ONE aaa", "ANSWER-TWO bbb", "ANSWER-THREE ccc"]
    result = format_final_blocks(blocks)
    assert result.source_blocks == tuple(blocks)
    visible = _all_visible(result)
    assert visible.index("ANSWER-ONE") < visible.index("ANSWER-TWO")
    assert visible.index("ANSWER-TWO") < visible.index("ANSWER-THREE")
    # No summarization / mixing into one invented blob beyond concatenation.
    for b in blocks:
        assert "aaa" in visible or "ANSWER-ONE" in visible
        assert b.split()[0] in visible


def test_over_20k_chars_split_and_complete() -> None:
    body = ("строка-" + "я" * 80 + "\n") * 300  # > 20k
    assert len(body) > 20_000
    result = format_final_blocks([body], max_units=3500)
    assert result.source_blocks == (body,)
    _assert_budget(result, 3500)
    assert len(result.parts) > 1
    # Full content present across parts (plain or stripped HTML).
    visible = _all_visible(result)
    # Compact whitespace for compare of repeated pattern.
    assert body.replace("\n", "") in visible.replace("\n", "") or all(
        line in visible for line in body.split("\n") if line
    )


def test_one_long_line() -> None:
    line = "X" * 8000
    result = format_final_blocks([line], max_units=500)
    assert result.source_blocks == (line,)
    _assert_budget(result, 500)
    assert "".join(_visible(p) for p in result.parts) == line
    assert len(result.parts) > 1


def test_fenced_code_with_lang() -> None:
    block = "intro\n```python\nprint(1 < 2 & True)\n```\nout"
    result = format_final_blocks([block])
    assert result.source_blocks == (block,)
    html_parts = [p for p in result.parts if p.parse_mode == "HTML"]
    assert html_parts, "expected HTML for supported fence"
    joined = "".join(p.text for p in result.parts)
    assert "<pre>" in joined
    assert "language-python" in joined
    assert "&lt;" in joined  # < escaped inside code
    assert "&amp;" in joined
    visible = _all_visible(result)
    assert "print(1 < 2 & True)" in visible
    assert "intro" in visible
    assert "out" in visible
    _assert_html_self_contained(result)


def test_long_fenced_code_oversized_falls_back_plain() -> None:
    code = "A" * 5000
    block = f"```\n{code}\n```"
    result = format_final_blocks([block], max_units=64)
    assert result.source_blocks == (block,)
    _assert_budget(result, 64)
    visible = _all_visible(result)
    assert code in visible.replace("\n", "") or code in visible
    # Either warning about atomic structure or plain fallback.
    assert result.warnings or all(p.parse_mode is None for p in result.parts)


def test_table_as_monospace_preserves_cells() -> None:
    block = (
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| alpha | 10 |\n"
        "| beta & co | <x> |\n"
    )
    result = format_final_blocks([block])
    assert result.source_blocks == (block,)
    visible = _all_visible(result)
    assert "alpha" in visible
    assert "beta & co" in visible
    assert "<x>" in visible
    assert "10" in visible
    joined = "".join(p.text for p in result.parts)
    if any(p.parse_mode == "HTML" for p in result.parts):
        assert "<pre>" in joined
        assert "&amp;" in joined
        assert "&lt;x&gt;" in joined


def test_unclosed_fence_plain_fallback_warning() -> None:
    block = "before\n```js\nfunction x() {\n  return 1;\n"
    result = format_final_blocks([block])
    assert result.source_blocks == (block,)
    assert any("unclosed" in w or "plain-text" in w for w in result.warnings)
    visible = _all_visible(result)
    assert "before" in visible
    assert "function x()" in visible
    assert "return 1;" in visible
    # Prefer plain for damaged block.
    assert all(p.parse_mode is None for p in result.parts)


def test_nested_or_unsupported_markdown_no_loss() -> None:
    # Raw HTML + odd nesting — must escape, not interpret as Telegram tags.
    block = 'Click <script>alert(1)</script> and **bold *inner* still**'
    result = format_final_blocks([block])
    assert result.source_blocks == (block,)
    joined = "".join(p.text for p in result.parts)
    if any(p.parse_mode == "HTML" for p in result.parts):
        assert "<script>" not in joined
        assert "&lt;script&gt;" in joined
    visible = _all_visible(result)
    assert "alert(1)" in visible
    assert "bold" in visible


def test_malicious_links_and_schemes() -> None:
    block = "\n".join(
        [
            "[ok](https://example.com/a)",
            "[ok2](http://example.com/b)",
            "[tg](tg://resolve?domain=foo)",
            "[bad](javascript:alert(1))",
            "[file](file:///etc/passwd)",
            "[local](./relative/path.md)",
            '[inj](https://example.com/"onclick=alert(1))',
        ]
    )
    result = format_final_blocks([block])
    joined = "".join(p.text for p in result.parts)
    visible = _all_visible(result)
    assert "https://example.com/a" in joined or "example.com/a" in visible
    # javascript / file must not become href.
    assert "javascript:" not in joined.lower() or "href=\"javascript:" not in joined.lower()
    assert 'href="javascript:' not in joined
    assert 'href="file:' not in joined
    assert "alert(1)" in visible
    assert "/etc/passwd" in visible
    assert "relative/path.md" in visible
    # Quote injection must be escaped or link demoted.
    assert 'href="https://example.com/"onclick' not in joined
    _assert_html_self_contained(result)


def test_headings_lists_emphasis_links() -> None:
    block = (
        "# Title\n"
        "## Sub\n"
        "- item *one*\n"
        "1. item **two**\n"
        "See [docs](https://example.com/docs) and `code`.\n"
    )
    result = format_final_blocks([block])
    visible = _all_visible(result)
    assert "Title" in visible
    assert "Sub" in visible
    assert "item" in visible
    assert "one" in visible
    assert "two" in visible
    assert "docs" in visible
    assert "code" in visible
    joined = "".join(p.text for p in result.parts)
    if any(p.parse_mode == "HTML" for p in result.parts):
        assert "<b>" in joined
        assert "<a href=\"https://example.com/docs\">" in joined
        assert "<code>code</code>" in joined


def test_max_units_validation() -> None:
    with pytest.raises(ValueError):
        format_final_blocks(["x"], max_units=0)
    with pytest.raises(ValueError):
        format_final_blocks(["x"], max_units=-1)
    with pytest.raises(ValueError):
        format_final_blocks(["x"], max_units=63)
    with pytest.raises(ValueError):
        format_final_blocks(["x"], max_units=4097)
    with pytest.raises(ValueError):
        format_final_blocks(["x"], max_units=3500.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_final_blocks("not-a-sequence")  # type: ignore[arg-type]


def test_limit_boundary_exact_fit() -> None:
    # Craft plain-ish text whose HTML/plain fits exactly around budget.
    text = "a" * 100
    result = format_final_blocks([text], max_units=64)
    _assert_budget(result, 64)
    assert "".join(_visible(p) for p in result.parts).replace("\n", "") == text


def test_parse_mode_html_vs_none() -> None:
    ok = format_final_blocks(["hello **world**"])
    assert any(p.parse_mode == "HTML" for p in ok.parts) or "world" in _all_visible(ok)
    damaged = format_final_blocks(["```\nno close"])
    assert all(p.parse_mode is None for p in damaged.parts)


def test_no_byte_split_inside_fence_defect() -> None:
    """Regression: must not byte-split raw markdown mid-fence.

    Old bridge split UTF-8 bytes; this module formats first, then splits
    on UTF-16 with fence/entity awareness — or falls back to plain chunks
    that still preserve full content without inventing broken fences.
    """
    inner = ("line-" + "字" * 40 + "\n") * 50
    block = f"preamble\n```\n{inner}```\ntail"
    result = format_final_blocks([block], max_units=200)
    assert result.source_blocks == (block,)
    _assert_budget(result, 200)
    visible = _all_visible(result)
    assert "preamble" in visible
    assert "tail" in visible
    # Every inner line content present.
    for line in inner.split("\n"):
        if line:
            assert line in visible
    # If HTML parts exist, each must be self-contained (no half fence tags).
    _assert_html_self_contained(result)


def test_unicode_trailing_newlines_preserved_in_source() -> None:
    blocks = ["αβγ\n\n", "🎉\n"]
    result = format_final_blocks(blocks)
    assert result.source_blocks == ("αβγ\n\n", "🎉\n")


def test_default_max_units() -> None:
    result = format_final_blocks(["short"])
    _assert_budget(result, 3500)
    assert isinstance(result, FormattedOutput)
