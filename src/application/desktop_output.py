"""Pure Markdown → Telegram HTML formatting for desktop final assistant blocks.

No I/O, network, subprocess, env, or secrets. Codex wires send_message later.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TelegramPart",
    "FormattedOutput",
    "format_final_blocks",
    "utf16_len",
]

# Conservative UTF-16 budget bounds (stricter than Telegram's 4096 user limit).
_MIN_UNITS = 64
_MAX_UNITS = 4096
_DEFAULT_UNITS = 3500

_ALLOWED_LINK_SCHEMES = frozenset({"http", "https", "tg"})

_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<lang>[^\s`]*)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_UL_RE = re.compile(r"^([ \t]*)([-*+])\s+(.+)$")
_OL_RE = re.compile(r"^([ \t]*)(\d{1,9})([.)])\s+(.+)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_ITALIC_RE = re.compile(
    r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"
    r"|(?<![\w_])_(?!_)(.+?)(?<!_)_(?![\w_])"
)
_ENTITY_RE = re.compile(r"&(?:#x?[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")
_TAG_RE = re.compile(r"<[^>]+>")
_PH_RE = re.compile(r"\x00([CLBI])(\d+)\x00")


@dataclass(frozen=True)
class TelegramPart:
    text: str
    parse_mode: str | None


@dataclass(frozen=True)
class FormattedOutput:
    source_blocks: tuple[str, ...]
    parts: tuple[TelegramPart, ...]
    warnings: tuple[str, ...]


def utf16_len(text: str) -> int:
    """Telegram counts message length in UTF-16 code units."""
    return sum(1 if ord(ch) < 0x10000 else 2 for ch in text)


def format_final_blocks(
    blocks: Sequence[str],
    *,
    max_units: int = _DEFAULT_UNITS,
) -> FormattedOutput:
    """Format visible final assistant blocks into Telegram-ready parts.

    ``source_blocks`` is a literal copy of the input sequence. This module
    never selects finals/plans/notifiers/secrets and never writes files.
    """
    if not isinstance(blocks, Sequence) or isinstance(blocks, (str, bytes)):
        raise ValueError("blocks must be a sequence of strings")
    source = tuple(blocks)
    for i, block in enumerate(source):
        if not isinstance(block, str):
            raise ValueError(f"block at index {i} must be str")
    if type(max_units) is not int or not (_MIN_UNITS <= max_units <= _MAX_UNITS):
        raise ValueError(
            f"max_units must be an int in [{_MIN_UNITS}, {_MAX_UNITS}]"
        )

    parts: list[TelegramPart] = []
    warnings: list[str] = []

    for index, block in enumerate(source):
        if block == "":
            continue
        block_parts, block_warnings = _format_one_block(block, index, max_units)
        parts.extend(block_parts)
        warnings.extend(block_warnings)

    return FormattedOutput(
        source_blocks=source,
        parts=tuple(parts),
        warnings=tuple(warnings),
    )


def _format_one_block(
    block: str,
    index: int,
    max_units: int,
) -> tuple[list[TelegramPart], list[str]]:
    warnings: list[str] = []
    try:
        html, convert_warnings = _markdown_to_telegram_html(block)
        warnings.extend(f"block[{index}]: {w}" for w in convert_warnings)
        if html is None:
            warnings.append(
                f"block[{index}]: markdown unsafe or damaged; plain-text fallback"
            )
            return _split_plain(block, max_units), warnings
        if not _html_preserves_text(block, html):
            warnings.append(
                f"block[{index}]: HTML conversion would lose text; plain-text fallback"
            )
            return _split_plain(block, max_units), warnings
        return _split_html(html, block, max_units, warnings, index), warnings
    except Exception as exc:  # noqa: BLE001 — never lose text on convert failure
        warnings.append(
            f"block[{index}]: conversion error ({type(exc).__name__}); "
            "plain-text fallback"
        )
        return _split_plain(block, max_units), warnings


# ---------------------------------------------------------------------------
# Markdown → Telegram HTML
# ---------------------------------------------------------------------------


def _markdown_to_telegram_html(text: str) -> tuple[str | None, list[str]]:
    """Return (html, warnings) or (None, warnings) to force plain fallback."""
    warnings: list[str] = []
    if text == "":
        return "", warnings

    lines = text.split("\n")
    out_chunks: list[str] = []
    i = 0
    n = len(lines)
    in_fence = False
    fence_marker = ""
    fence_lang = ""
    fence_body: list[str] = []

    while i < n:
        line = lines[i]

        if in_fence:
            if _is_fence_close(line, fence_marker):
                out_chunks.append(_render_fence(fence_lang, fence_body))
                in_fence = False
                fence_marker = ""
                fence_lang = ""
                fence_body = []
                i += 1
                continue
            fence_body.append(line)
            i += 1
            continue

        fence_match = _FENCE_OPEN_RE.match(line)
        if fence_match:
            in_fence = True
            fence_marker = fence_match.group("fence")[0]
            fence_lang = fence_match.group("lang") or ""
            fence_body = []
            i += 1
            continue

        if _looks_like_table_start(lines, i):
            table_html, consumed, tw = _render_table(lines, i)
            warnings.extend(tw)
            if table_html is None:
                return None, warnings
            out_chunks.append(table_html)
            i += consumed
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            body = _inline_to_html(heading.group(2))
            out_chunks.append(f"<b>{body}</b>")
            i += 1
            continue

        ul = _UL_RE.match(line)
        if ul:
            item = _inline_to_html(ul.group(3))
            indent = ul.group(1).replace("\t", "    ")
            prefix = _escape_text(indent + "• ")
            out_chunks.append(f"{prefix}{item}")
            i += 1
            continue

        ol = _OL_RE.match(line)
        if ol:
            num = ol.group(2)
            item = _inline_to_html(ol.group(4))
            indent = ol.group(1).replace("\t", "    ")
            prefix = _escape_text(f"{indent}{num}. ")
            out_chunks.append(f"{prefix}{item}")
            i += 1
            continue

        if line == "":
            out_chunks.append("")
            i += 1
            continue

        out_chunks.append(_inline_to_html(line))
        i += 1

    if in_fence:
        warnings.append("unclosed fenced code block")
        return None, warnings

    return "\n".join(out_chunks), warnings


def _is_fence_close(line: str, marker_char: str) -> bool:
    if marker_char == "`":
        return bool(re.match(r"^`{3,}\s*$", line))
    return bool(re.match(r"^~{3,}\s*$", line))


def _render_fence(lang: str, body_lines: list[str]) -> str:
    body = _escape_text("\n".join(body_lines))
    lang_clean = re.sub(r"[^A-Za-z0-9_+#.-]", "", lang)[:32]
    if lang_clean:
        return f'<pre><code class="language-{lang_clean}">{body}</code></pre>'
    return f"<pre><code>{body}</code></pre>"


def _looks_like_table_start(lines: list[str], i: int) -> bool:
    if i + 1 >= len(lines):
        return False
    row = lines[i]
    sep = lines[i + 1]
    if not (_TABLE_ROW_RE.match(row) or (row.strip().startswith("|") and "|" in row[1:])):
        return False
    return bool(_TABLE_SEP_RE.match(sep))


def _split_table_cells(row: str) -> list[str]:
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _render_table(
    lines: list[str], start: int
) -> tuple[str | None, int, list[str]]:
    warnings: list[str] = []
    header_cells = _split_table_cells(lines[start])
    if not header_cells:
        warnings.append("empty table header")
        return None, 0, warnings
    consumed = 2
    body_rows: list[list[str]] = []
    j = start + 2
    while j < len(lines):
        line = lines[j]
        if line.strip() == "" or "|" not in line:
            break
        body_rows.append(_split_table_cells(line))
        consumed += 1
        j += 1

    ncols = len(header_cells)
    all_rows = [header_cells] + body_rows
    normalized: list[list[str]] = []
    for row in all_rows:
        if len(row) < ncols:
            row = row + [""] * (ncols - len(row))
        elif len(row) > ncols:
            merged_last = " | ".join(row[ncols - 1 :])
            row = row[: ncols - 1] + [merged_last]
        normalized.append(row)

    widths = [0] * ncols
    for row in normalized:
        for c, cell in enumerate(row):
            widths[c] = max(widths[c], len(cell))

    def fmt_row(row: list[str]) -> str:
        return (
            "| "
            + " | ".join(cell.ljust(widths[c]) for c, cell in enumerate(row))
            + " |"
        )

    rendered_lines = [fmt_row(normalized[0])]
    sep = "| " + " | ".join("-" * widths[c] for c in range(ncols)) + " |"
    rendered_lines.append(sep)
    for row in normalized[1:]:
        rendered_lines.append(fmt_row(row))

    body = _escape_text("\n".join(rendered_lines))
    return f"<pre><code>{body}</code></pre>", consumed, warnings


def _inline_to_html(text: str) -> str:
    """Convert inline Markdown to Telegram HTML; always escape raw HTML."""
    store: dict[str, list[str]] = {"C": [], "L": [], "B": [], "I": []}

    def ph(kind: str, html_fragment: str) -> str:
        store[kind].append(html_fragment)
        return f"\x00{kind}{len(store[kind]) - 1}\x00"

    def save_code(m: re.Match[str]) -> str:
        return ph("C", f"<code>{_escape_text(m.group(1))}</code>")

    work = _INLINE_CODE_RE.sub(save_code, text)

    def save_link(m: re.Match[str]) -> str:
        label = m.group(1)
        url = m.group(2).strip()
        # Resolve code placeholders inside label, then escape the rest.
        label_html = _materialize_placeholders(
            _escape_preserving_ph(_INLINE_CODE_RE.sub(save_code, label)),
            store,
        )
        return ph("L", _render_link_html(label_html, url))

    work = _LINK_RE.sub(save_link, work)

    def save_bold(m: re.Match[str]) -> str:
        inner = _materialize_placeholders(
            _escape_preserving_ph(m.group(2)), store
        )
        return ph("B", f"<b>{inner}</b>")

    work = _BOLD_RE.sub(save_bold, work)

    def save_italic(m: re.Match[str]) -> str:
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        inner = _materialize_placeholders(_escape_preserving_ph(raw), store)
        return ph("I", f"<i>{inner}</i>")

    work = _ITALIC_RE.sub(save_italic, work)

    work = _escape_preserving_ph(work)
    return _materialize_placeholders(work, store)


def _escape_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape_preserving_ph(text: str) -> str:
    """Escape &, <, > but leave \\x00K#\\x00 placeholders untouched."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\x00":
            m = _PH_RE.match(text, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        ch = text[i]
        if ch == "&":
            out.append("&amp;")
        elif ch == "<":
            out.append("&lt;")
        elif ch == ">":
            out.append("&gt;")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _materialize_placeholders(text: str, store: dict[str, list[str]]) -> str:
    def repl(m: re.Match[str]) -> str:
        kind = m.group(1)
        idx = int(m.group(2))
        return store[kind][idx]

    # Multiple passes for any residual nesting.
    s = text
    for _ in range(8):
        nxt = _PH_RE.sub(repl, s)
        if nxt == s:
            break
        s = nxt
    return s


def _render_link_html(label_html: str, url: str) -> str:
    scheme = _link_scheme(url)
    if scheme in _ALLOWED_LINK_SCHEMES and _valid_href(url):
        return f'<a href="{_escape_attr(url)}">{label_html}</a>'
    plain_label = _strip_html_to_text(label_html)
    return _escape_text(f"{plain_label} ({url})")


def _link_scheme(url: str) -> str | None:
    if ":" not in url:
        return None  # relative / local path
    scheme = url.split(":", 1)[0].lower()
    if not re.fullmatch(r"[a-z][a-z0-9+.-]*", scheme):
        return None
    return scheme


def _valid_href(url: str) -> bool:
    if not url or any(c in url for c in ' \t\r\n"\'<>'):
        return False
    if len(url) > 2048:
        return False
    return True


def _escape_attr(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _strip_html_to_text(html: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    s = _TAG_RE.sub("", s)
    s = (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&#39;", "'")
    )
    return s


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _html_preserves_text(source: str, html: str) -> bool:
    visible = _strip_html_to_text(html)
    visible_norm = _normalize_ws(visible)
    # URLs for allowed links live in href attributes, not necessarily visible text.
    hrefs = set(re.findall(r'href="([^"]*)"', html))
    hrefs_unesc = {
        h.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        for h in hrefs
    }
    for tok in _content_tokens(source):
        if tok in visible or tok in visible_norm:
            continue
        if _normalize_ws(tok) in visible_norm:
            continue
        if tok in hrefs or tok in hrefs_unesc:
            continue
        return False
    return True


def _content_tokens(source: str) -> list[str]:
    tokens: list[str] = []
    lines = source.split("\n")
    in_fence = False
    fence_char = ""
    for line in lines:
        if in_fence:
            if _is_fence_close(line, fence_char):
                in_fence = False
                continue
            if line != "":
                tokens.append(line)
            continue
        fm = _FENCE_OPEN_RE.match(line)
        if fm:
            in_fence = True
            fence_char = fm.group("fence")[0]
            continue
        if _TABLE_SEP_RE.match(line):
            continue
        if "|" in line and line.strip().startswith("|"):
            for cell in _split_table_cells(line):
                if cell:
                    tokens.append(cell)
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            tokens.append(hm.group(2))
            continue
        um = _UL_RE.match(line)
        if um:
            tokens.append(um.group(3))
            continue
        om = _OL_RE.match(line)
        if om:
            tokens.append(om.group(4))
            continue
        for m in _INLINE_CODE_RE.finditer(line):
            tokens.append(m.group(1))
        for m in _LINK_RE.finditer(line):
            tokens.append(m.group(1))
            tokens.append(m.group(2).strip())
        stripped = _INLINE_CODE_RE.sub(" ", line)
        stripped = _LINK_RE.sub(r"\1 \2", stripped)
        stripped = _BOLD_RE.sub(r"\2", stripped)
        stripped = _ITALIC_RE.sub(
            lambda m: (m.group(1) or m.group(2) or ""), stripped
        )
        for piece in re.findall(r"\S+", stripped):
            if piece not in {"-", "*", "+", "|", ">", "`", "#"}:
                # Drop pure heading markers already handled.
                if re.fullmatch(r"#+", piece):
                    continue
                tokens.append(piece)
    return tokens


# ---------------------------------------------------------------------------
# Splitting (UTF-16, entity/tag/surrogate aware)
# ---------------------------------------------------------------------------


def _split_plain(text: str, max_units: int) -> list[TelegramPart]:
    if text == "":
        return [TelegramPart(text="", parse_mode=None)]
    chunks = _split_utf16_plain(text, max_units)
    if "".join(chunks) != text:
        raise RuntimeError("plain split lost content")
    return [TelegramPart(text=c, parse_mode=None) for c in chunks]


def _split_html(
    html: str,
    source: str,
    max_units: int,
    warnings: list[str],
    index: int,
) -> list[TelegramPart]:
    if html == "":
        return [TelegramPart(text="", parse_mode="HTML")]
    if utf16_len(html) <= max_units:
        return [TelegramPart(text=html, parse_mode="HTML")]

    pieces = _split_html_safe(html, max_units)
    if pieces is not None:
        return [TelegramPart(text=p, parse_mode="HTML") for p in pieces]

    warnings.append(
        f"block[{index}]: atomic HTML structure exceeds max_units; "
        "plain-text chunk fallback"
    )
    return _split_plain(source, max_units)


def _split_utf16_plain(text: str, max_units: int) -> list[str]:
    if utf16_len(text) <= max_units:
        return [text]
    parts: list[str] = []
    remaining = text
    guard = 0
    max_guard = len(text) + 8
    while remaining:
        guard += 1
        if guard > max_guard:
            raise RuntimeError("plain split failed to make progress")
        if utf16_len(remaining) <= max_units:
            parts.append(remaining)
            break
        cut = _fit_utf16_prefix(remaining, max_units)
        if cut <= 0:
            raise ValueError("max_units too small to encode a character")
        candidate = remaining[:cut]
        nl = candidate.rfind("\n")
        if nl >= max(1, len(candidate) // 2):
            cut = nl + 1
            candidate = remaining[:cut]
        else:
            sp = candidate.rfind(" ")
            if sp >= max(1, len(candidate) // 2):
                cut = sp + 1
                candidate = remaining[:cut]
        parts.append(candidate)
        remaining = remaining[cut:]
    return parts


def _fit_utf16_prefix(text: str, max_units: int) -> int:
    units = 0
    i = 0
    n = len(text)
    while i < n:
        ch_units = 1 if ord(text[i]) < 0x10000 else 2
        if units + ch_units > max_units:
            break
        units += ch_units
        i += 1
    return i


def _split_html_safe(html: str, max_units: int) -> list[str] | None:
    atoms = _html_atoms(html)
    if not atoms:
        return [html] if utf16_len(html) <= max_units else None

    parts: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            parts.append(buf)
            buf = ""

    for atom in atoms:
        atom_len = utf16_len(atom)
        if atom_len > max_units:
            if _is_pre_atom(atom):
                return None
            sub = _split_html_by_lines(atom, max_units)
            if sub is None:
                return None
            for piece in sub:
                if buf and utf16_len(buf) + utf16_len(piece) > max_units:
                    flush()
                buf = buf + piece if buf else piece
                if utf16_len(buf) > max_units:
                    return None
            continue

        sep = ""
        if buf and not buf.endswith("\n") and not atom.startswith("\n"):
            sep = "\n"
        needed = utf16_len(sep) + atom_len
        if buf and utf16_len(buf) + needed > max_units:
            flush()
            buf = atom
        else:
            buf = (buf + sep + atom) if buf else atom
    flush()

    for p in parts:
        if utf16_len(p) > max_units:
            return None
        if not _html_part_self_contained(p):
            return None
    return parts


def _is_pre_atom(atom: str) -> bool:
    s = atom.lstrip()
    return s.startswith("<pre>") or s.startswith("<pre ")


def _html_atoms(html: str) -> list[str]:
    atoms: list[str] = []
    pos = 0
    n = len(html)
    pre_re = re.compile(r"<pre(?:\s[^>]*)?>[\s\S]*?</pre>")
    while pos < n:
        m = pre_re.search(html, pos)
        if not m:
            atoms.extend(_split_keep_newlines(html[pos:]))
            break
        if m.start() > pos:
            atoms.extend(_split_keep_newlines(html[pos : m.start()]))
        atoms.append(m.group(0))
        pos = m.end()
    return atoms


def _split_keep_newlines(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    start = 0
    while start < len(text):
        nl = text.find("\n", start)
        if nl < 0:
            out.append(text[start:])
            break
        out.append(text[start : nl + 1])
        start = nl + 1
    return out


def _split_html_by_lines(html: str, max_units: int) -> list[str] | None:
    lines = _split_keep_newlines(html)
    parts: list[str] = []
    buf = ""
    for line in lines:
        if utf16_len(line) > max_units:
            if _TAG_RE.search(line) or (_ENTITY_RE.search(line) and "&" in line):
                # Check for incomplete-cut risk: if line has tags, refuse.
                if _TAG_RE.search(line):
                    return None
            # No tags: soft-split like plain, still avoid mid-entity.
            safe_chunks = _split_utf16_avoiding_entities(line, max_units)
            if safe_chunks is None:
                return None
            for sub in safe_chunks:
                if buf and utf16_len(buf) + utf16_len(sub) > max_units:
                    parts.append(buf)
                    buf = sub
                else:
                    buf = buf + sub if buf else sub
            continue
        if buf and utf16_len(buf) + utf16_len(line) > max_units:
            parts.append(buf)
            buf = line
        else:
            buf = buf + line if buf else line
    if buf:
        parts.append(buf)
    for p in parts:
        if utf16_len(p) > max_units or not _html_part_self_contained(p):
            return None
    return parts


def _split_utf16_avoiding_entities(text: str, max_units: int) -> list[str] | None:
    """Split text that may contain entities but no tags."""
    parts: list[str] = []
    remaining = text
    guard = 0
    while remaining:
        guard += 1
        if guard > len(text) + 8:
            return None
        if utf16_len(remaining) <= max_units:
            parts.append(remaining)
            break
        cut = _fit_utf16_prefix(remaining, max_units)
        if cut <= 0:
            return None
        # Do not cut inside an entity &...;
        candidate = remaining[:cut]
        amp = candidate.rfind("&")
        if amp >= 0 and ";" not in candidate[amp:]:
            # Might be cutting inside entity — pull cut back before &.
            if amp == 0:
                # Entity itself longer than budget.
                return None
            cut = amp
            candidate = remaining[:cut]
        # Prefer newline / space.
        nl = candidate.rfind("\n")
        if nl >= max(1, len(candidate) // 2):
            cut = nl + 1
        else:
            sp = candidate.rfind(" ")
            if sp >= max(1, len(candidate) // 2):
                cut = sp + 1
        if cut <= 0:
            return None
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    return parts


def _html_part_self_contained(part: str) -> bool:
    if part.endswith("<") or part.endswith("&"):
        return False
    amp = part.rfind("&")
    if amp >= 0:
        frag = part[amp:]
        if ";" not in frag:
            # Bare trailing & is invalid in our escaped output.
            return False
        if not _ENTITY_RE.match(part, amp) and not frag.startswith("&amp;"):
            # Could still be &amp;... matched above; check properly.
            if _ENTITY_RE.match(part[amp:]) is None:
                # Allow if a complete entity exists starting at amp.
                m = re.match(r"&[^;]*;", frag)
                if not m:
                    return False
    last_lt = part.rfind("<")
    if last_lt >= 0 and part.find(">", last_lt) < 0:
        return False

    stack: list[str] = []
    for m in re.finditer(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", part):
        full = m.group(0)
        name = m.group(1).lower()
        if full.startswith("</"):
            if not stack or stack[-1] != name:
                return False
            stack.pop()
        elif full.endswith("/>"):
            continue
        else:
            stack.append(name)
    return not stack
