"""Pure extraction of artifact path references from assistant/Codex text.

This module performs string transformation only. It never touches the
filesystem, network, environment, subprocesses, or Desktop/Telegram APIs.

Span contract
-------------
``start`` / ``end`` form a half-open interval into the original Python ``str``
such that ``raw == text[start:end]`` always holds.

* Markdown links and images: ``raw`` spans the **entire** link/image fragment
  (e.g. ``[label](dest)``, ``![alt](<dest>)``), including brackets.
* Backtick- or quote-delimited forms: ``raw`` spans the **entire** delimited
  fragment, including the opening and closing delimiters.
* Bare Windows paths, angle-bracket autolinks, UNC shares, and remote URLs:
  ``raw`` spans exactly the matched reference text (no surrounding punctuation
  invented beyond what was matched).

``kind`` is exactly one of: ``windows_absolute``, ``remote_url``,
``unsupported_local``.

For ``windows_absolute``, ``path`` is a normalized absolute Windows drive path
using backslashes (one optional leading ``/`` before ``C:`` is stripped;
forward slashes become backslashes). ``..`` segments are preserved as written —
they are never resolved and never make a path "proven safe". For other kinds,
``path`` is the original recognized link/path string (after a single Markdown
percent-decode when applicable). Codex ``:N`` / ``:N:M`` line suffixes are
separated from the drive colon and from colons that belong to the filename
portion of the matched text.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote
import re

__all__ = [
    "ArtifactReference",
    "ArtifactReferences",
    "extract_artifact_references",
]


@dataclass(frozen=True)
class ArtifactReference:
    raw: str
    path: str | None
    kind: str
    start: int
    end: int
    label: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class ArtifactReferences:
    references: tuple[ArtifactReference, ...]
    issues: tuple[str, ...]


# Trailing punctuation commonly attached to bare paths in prose.
_TRAILING_PUNCT = ".,;:!?)]}\"'"

# Characters that end a bare (non-delimited) path segment run.
_BARE_STOP = set(" \t\r\n\"'`<>") | set(_TRAILING_PUNCT)


def extract_artifact_references(text: str) -> ArtifactReferences:
    """Extract ordered artifact references from ``text``.

    Preserves occurrence order. Does not deduplicate, casefold, or resolve
    through the filesystem. Explicitly file-like Markdown destinations that
    are relative or incomplete yield ``unsupported_local`` plus an issue —
    they never vanish silently. Ambiguous bare paths with spaces produce an
    exact ambiguity issue instead of inventing a filename.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")

    references: list[ArtifactReference] = []
    issues: list[str] = []
    n = len(text)
    i = 0
    # Tracks spans already claimed so nested/overlapping bare matches are skipped.
    claimed: list[tuple[int, int]] = []

    def _is_claimed(pos: int) -> bool:
        for a, b in claimed:
            if a <= pos < b:
                return True
        return False

    while i < n:
        if _is_claimed(i):
            i += 1
            continue

        matched = (
            _try_markdown(text, i, references, issues, claimed)
            or _try_angle_bracket(text, i, references, issues, claimed)
            or _try_backtick(text, i, references, issues, claimed)
            or _try_quotes(text, i, references, issues, claimed)
            or _try_unc(text, i, references, issues, claimed)
            or _try_remote_url(text, i, references, issues, claimed)
            or _try_bare_windows(text, i, references, issues, claimed)
        )
        if matched:
            i = matched
        else:
            i += 1

    return ArtifactReferences(tuple(references), tuple(issues))


# ---------------------------------------------------------------------------
# Matchers (each returns new cursor end on success, else None)
# ---------------------------------------------------------------------------


def _try_markdown(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    """Match ``![alt](dest)`` or ``[label](dest)`` starting at ``i``."""
    n = len(text)
    pos = i
    is_image = False
    if text.startswith("![", pos):
        is_image = True
        pos += 2
    elif text.startswith("[", pos):
        pos += 1
    else:
        return None

    # Parse label / alt until unescaped ']'
    label_start = pos
    label, pos = _read_until_unescaped(text, pos, "]")
    if label is None or pos >= n or text[pos] != "]":
        return None
    pos += 1  # skip ]
    if pos >= n or text[pos] != "(":
        # Not a link — bare [label] reference; ignore.
        return None
    pos += 1  # skip (

    dest_start = pos
    dest, dest_end, incomplete = _read_markdown_destination(text, pos)
    if incomplete:
        # Explicitly file-like incomplete link must not vanish.
        frag_end = _find_line_end(text, i)
        raw = text[i:frag_end]
        issues.append(
            f"incomplete Markdown {'image' if is_image else 'link'} "
            f"at {i}:{frag_end}: {raw!r}"
        )
        # Try to salvage a destination fragment for unsupported_local.
        salvage = text[dest_start:frag_end].rstrip(")\n\r")
        kind, path, line = _classify_destination(salvage, from_markdown=True)
        if kind is None and salvage.strip():
            kind, path, line = "unsupported_local", salvage.strip(), None
        if kind is not None:
            refs.append(
                ArtifactReference(
                    raw=raw,
                    path=path,
                    kind=kind,
                    start=i,
                    end=frag_end,
                    label=label if not is_image else (label or None),
                    line=line,
                )
            )
            claimed.append((i, frag_end))
            return frag_end
        claimed.append((i, frag_end))
        return frag_end

    if dest is None:
        return None

    # Require closing ')'
    if dest_end >= n or text[dest_end] != ")":
        frag_end = _find_line_end(text, i)
        raw = text[i:frag_end]
        issues.append(
            f"incomplete Markdown {'image' if is_image else 'link'} "
            f"at {i}:{frag_end}: {raw!r}"
        )
        kind, path, line = _classify_destination(dest, from_markdown=True)
        if kind is None and dest.strip():
            kind, path, line = "unsupported_local", dest.strip(), None
        if kind is not None:
            refs.append(
                ArtifactReference(
                    raw=raw,
                    path=path,
                    kind=kind,
                    start=i,
                    end=frag_end,
                    label=label if label else None,
                    line=line,
                )
            )
        claimed.append((i, frag_end))
        return frag_end

    end = dest_end + 1
    raw = text[i:end]
    kind, path, line = _classify_destination(dest, from_markdown=True)
    if kind is None:
        # Destination is not file-like and not a remote URL — skip silently
        # (ordinary Markdown web-style short refs without scheme/path cues).
        # But if it looks path-ish (slash or drive), keep as unsupported.
        if _looks_file_like(dest):
            kind, path, line = "unsupported_local", dest, None
        else:
            return None

    if kind == "unsupported_local":
        issues.append(
            f"unsupported local path in Markdown "
            f"{'image' if is_image else 'link'} at {i}:{end}: {dest!r}"
        )

    refs.append(
        ArtifactReference(
            raw=raw,
            path=path,
            kind=kind,
            start=i,
            end=end,
            label=label if label else None,
            line=line,
        )
    )
    claimed.append((i, end))
    return end


def _try_angle_bracket(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    """Match ``<destination>`` autolink-style angle brackets."""
    if i >= len(text) or text[i] != "<":
        return None
    # Avoid HTML tags: require path/URL-like first character after '<'
    if i + 1 >= len(text):
        return None
    nxt = text[i + 1]
    if not (
        nxt.isalpha()
        or nxt in "/\\"
        or nxt == "."
    ):
        return None

    end_idx = text.find(">", i + 1)
    if end_idx < 0:
        return None
    # Angle content cannot span newlines (CommonMark autolink rule-ish).
    inner = text[i + 1 : end_idx]
    if "\n" in inner or "\r" in inner:
        return None
    # Reject obvious HTML tags like <a href=...> / <div ...>
    if re.match(r"^[A-Za-z]+(\s|/|>|$)", inner) and not _looks_path_or_url(inner):
        return None

    raw = text[i : end_idx + 1]
    # Angle-bracket autolinks must look like a path/URL; reject HTML crumbs
    # such as </a> or <div ...> (already partially filtered above).
    if not _looks_path_or_url(inner):
        return None
    kind, path, line = _classify_destination(inner, from_markdown=True)
    if kind is None:
        return None
    if kind == "unsupported_local":
        issues.append(
            f"unsupported local path in angle brackets at {i}:{end_idx + 1}: {inner!r}"
        )

    refs.append(
        ArtifactReference(
            raw=raw,
            path=path,
            kind=kind,
            start=i,
            end=end_idx + 1,
            label=None,
            line=line,
        )
    )
    claimed.append((i, end_idx + 1))
    return end_idx + 1


def _try_backtick(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    if text[i] != "`":
        return None
    # Single backtick span (not fenced ```).
    if text.startswith("```", i):
        return None
    close = text.find("`", i + 1)
    if close < 0:
        return None
    # Do not span newlines for inline code paths.
    inner = text[i + 1 : close]
    if "\n" in inner or "\r" in inner:
        return None
    raw = text[i : close + 1]
    stripped = inner.strip()
    kind, path, line = _classify_destination(stripped, from_markdown=False)
    if kind is None:
        if _looks_file_like(stripped):
            kind, path, line = "unsupported_local", stripped, None
        else:
            return None
    if kind == "unsupported_local":
        issues.append(
            f"unsupported local path in backticks at {i}:{close + 1}: {path!r}"
        )

    refs.append(
        ArtifactReference(
            raw=raw,
            path=path,
            kind=kind,
            start=i,
            end=close + 1,
            label=None,
            line=line,
        )
    )
    claimed.append((i, close + 1))
    return close + 1


def _try_quotes(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    q = text[i]
    if q not in "'\"":
        return None
    close = text.find(q, i + 1)
    if close < 0:
        return None
    inner = text[i + 1 : close]
    if "\n" in inner or "\r" in inner:
        return None
    # Only treat as artifact if content looks like a path/URL — avoid
    # capturing ordinary quoted English phrases.
    stripped = inner.strip()
    if not _looks_path_or_url(stripped) and not _looks_file_like(stripped):
        return None
    raw = text[i : close + 1]
    kind, path, line = _classify_destination(stripped, from_markdown=False)
    if kind is None:
        if _looks_file_like(stripped):
            kind, path, line = "unsupported_local", stripped, None
        else:
            return None
    if kind == "unsupported_local":
        issues.append(
            f"unsupported local path in quotes at {i}:{close + 1}: {path!r}"
        )

    refs.append(
        ArtifactReference(
            raw=raw,
            path=path,
            kind=kind,
            start=i,
            end=close + 1,
            label=None,
            line=line,
        )
    )
    claimed.append((i, close + 1))
    return close + 1


def _try_unc(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    """Match UNC ``\\\\server\\share\\...`` or ``//server/share/...``."""
    del issues  # UNC is always remote_url; issues unused
    prefix = None
    if text.startswith("\\\\", i):
        prefix = "\\"
    elif text.startswith("//", i) and not text.startswith("///", i):
        # Avoid matching http:// — those are handled by remote_url.
        # //server requires the next char not to be /
        # But http:// also has // — only match if NOT preceded by scheme.
        if i >= 1 and text[i - 1] == ":":
            return None
        prefix = "/"
    else:
        return None

    # Read until whitespace / trailing punctuation.
    j = i + 2
    n = len(text)
    if j >= n or text[j] in " \t\r\n/\\":
        return None
    while j < n and text[j] not in " \t\r\n<>\"'`":
        j += 1
    # Strip trailing punctuation (but keep path separators).
    while j > i + 2 and text[j - 1] in ".,;:!?)]}:":
        # Keep if it looks like part of share (unlikely); strip prose punct.
        j -= 1
    raw = text[i:j]
    # Must look like \\server\share at minimum (two more segments).
    body = raw[2:]
    sep = "\\" if prefix == "\\" else "/"
    parts = [p for p in body.split(sep) if p]
    if len(parts) < 2:
        return None

    refs.append(
        ArtifactReference(
            raw=raw,
            path=raw,
            kind="remote_url",
            start=i,
            end=j,
            label=None,
            line=None,
        )
    )
    claimed.append((i, j))
    return j


def _try_remote_url(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    del issues
    lower = text[i : i + 8].lower()
    scheme = None
    if lower.startswith("https://"):
        scheme = "https://"
    elif lower.startswith("http://"):
        scheme = "http://"
    elif lower.startswith("file://"):
        scheme = "file://"
    else:
        return None

    j = i + len(scheme)
    n = len(text)
    if j >= n:
        return None
    while j < n and text[j] not in " \t\r\n<>\"'`":
        j += 1
    while j > i + len(scheme) and text[j - 1] in ".,;:!?)]}:":
        # Don't strip : from URL ports — only strip if trailing prose punct.
        # Heuristic: strip . , ; ! ? ) ] } and a colon only if not \d before port-like.
        ch = text[j - 1]
        if ch == ":" and j < n and text[j : j + 1].isdigit():
            break
        if ch in ".,;!?)]}" or (ch == ":" and (j >= n or not text[j].isdigit())):
            j -= 1
        else:
            break
    # Simpler trailing strip for URLs: .,;!?)]}>'
    while j > i + len(scheme) and text[j - 1] in ".,;!?)]}>'":
        j -= 1
    raw = text[i:j]
    if len(raw) <= len(scheme):
        return None

    refs.append(
        ArtifactReference(
            raw=raw,
            path=raw,
            kind="remote_url",
            start=i,
            end=j,
            label=None,
            line=None,
        )
    )
    claimed.append((i, j))
    return j


def _try_bare_windows(
    text: str,
    i: int,
    refs: list[ArtifactReference],
    issues: list[str],
    claimed: list[tuple[int, int]],
) -> int | None:
    """Match bare ``C:\\...``, ``C:/...``, ``/C:/...`` without delimiters."""
    m = _WINDOWS_ABS_START.match(text, i)
    if not m:
        # Drive-relative C:file (no slash) — explicit unsupported if clear.
        m2 = re.match(r"([A-Za-z]:)(?![\\/])([^\s\"'`<>]+)", text[i:])
        if m2:
            # Avoid matching inside words: require start or non-path boundary.
            if i > 0 and (text[i - 1].isalnum() or text[i - 1] in ":\\/"):
                return None
            raw = m2.group(0)
            # Skip if this looks like a URL scheme (http: already handled).
            end = i + len(raw)
            refs.append(
                ArtifactReference(
                    raw=raw,
                    path=raw,
                    kind="unsupported_local",
                    start=i,
                    end=end,
                    label=None,
                    line=None,
                )
            )
            issues.append(
                f"drive-relative path is not absolute at {i}:{end}: {raw!r}"
            )
            claimed.append((i, end))
            return end
        return None

    # Boundary: must not be mid-token (e.g. xC:\...)
    if i > 0:
        prev = text[i - 1]
        if prev.isalnum() or prev in ":\\_":
            return None

    start = i
    # Optional leading /
    pos = i
    if text[pos] == "/":
        pos += 1
    # Drive letter + :
    pos += 2
    # Must have separator
    if pos >= len(text) or text[pos] not in "\\/":
        return None

    # Consume path characters until bare-stop. Spaces are NOT allowed in bare
    # paths — if a space appears mid-path looking continuation, emit ambiguity.
    j = pos
    n = len(text)
    while j < n:
        ch = text[j]
        if ch in " \t\r\n":
            break
        if ch in "\"'`<>":
            break
        j += 1

    # Strip trailing punctuation from the match (not part of path).
    path_end = j
    while path_end > pos and text[path_end - 1] in ".,;!?)]}\"'" :
        path_end -= 1

    # Line suffix :N or :N:M — keep temporarily then split.
    # First, if we stripped a colon that began :digits, re-evaluate.
    # Re-extend to include :digits if present right after path body.
    # Actually the while loop stopped at whitespace; :digits would be included
    # unless : is in stop set. ':' is in _TRAILING_PUNCT but we only strip at end.
    # Digits after colon stay in the consumed run because ':' isn't a stop char
    # during consumption — good. We'll split_line_suffix later.

    # However trailing strip may have removed the line-suffix colon. Fix:
    # After initial consume, try to peel trailing prose punct that is NOT
    # part of :digits line suffix.
    consumed = text[start:j]
    # If a clear short extension is glued to trailing word characters
    # (e.g. report.txtword), trim back to the extension. Separators abort.
    # Peel trailing punct except preserve :digits / :digits:digits
    body, line = _split_line_suffix_from_end(consumed)
    # Now peel remaining trailing punct from body
    while body and body[-1] in ".,;!?)]}\"'" :
        body = body[:-1]
    # Recompute end based on body (+ line suffix if any)
    suffix_len = 0
    if line is not None:
        # Find how much of consumed after body is the :N(:M) suffix
        rest = consumed[len(body) :]
        m_suf = re.match(r":(\d+)(?::\d+)?", rest)
        if m_suf:
            suffix_len = m_suf.end()
    end = start + len(body) + suffix_len
    raw = text[start:end]

    # Ambiguity: bare path followed by space + continuation that looks like
    # more path (e.g. "C:\Users\My Documents\file.txt").
    if end < n and text[end] in " \t":
        after = text[end:].lstrip(" \t")
        if after and (
            after[0] in "\\/"
            or re.match(r"[^\s\"'`<>]+[\\/]", after)
            or re.match(r"[^\s\"'`<>]+\.\w{1,8}\b", after)
        ):
            peek = after.split("\n", 1)[0]
            if "\\" in peek or "/" in peek or (
                "." not in raw.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                and re.match(r"[^\s\"'`<>]+\.\w{1,8}\b", after)
            ):
                issues.append(
                    f"ambiguous bare Windows path boundaries at {start}:{end}: "
                    f"cannot establish end of {raw!r} before {peek[:40]!r}"
                )
                claimed.append((start, end))
                return end

    kind, path, line2 = _classify_destination(raw, from_markdown=False)
    if line is not None and line2 is None:
        line2 = line
    if kind is None:
        return None

    refs.append(
        ArtifactReference(
            raw=raw,
            path=path,
            kind=kind,
            start=start,
            end=end,
            label=None,
            line=line2,
        )
    )
    claimed.append((start, end))
    return end


_WINDOWS_ABS_START = re.compile(
    r"/(?=[A-Za-z]:[\\/])|(?=[A-Za-z]:[\\/])"
)


# ---------------------------------------------------------------------------
# Classification & normalization
# ---------------------------------------------------------------------------


def _classify_destination(
    dest: str, *, from_markdown: bool
) -> tuple[str | None, str | None, int | None]:
    """Return ``(kind, path, line)`` or ``(None, None, None)`` if unrecognized."""
    if not dest:
        return None, None, None

    original = dest
    # Angle brackets already stripped by callers; strip once more if nested.
    if dest.startswith("<") and dest.endswith(">") and len(dest) >= 2:
        dest = dest[1:-1]

    decoded = dest
    if from_markdown:
        try:
            decoded = _percent_decode_once(dest)
        except UnicodeDecodeError:
            return "unsupported_local", original, None

    # Remote URLs
    lower = decoded.lower()
    if lower.startswith(("http://", "https://", "file://")):
        return "remote_url", decoded, None

    # UNC
    if decoded.startswith("\\\\") or (
        decoded.startswith("//") and not lower.startswith("///")
    ):
        return "remote_url", decoded, None

    # Line suffixes are meaningful only for local file references.
    body, line = _split_line_suffix(decoded)

    # Windows absolute: C:\... C:/... /C:/... /C:\...
    win = _normalize_windows_absolute(body)
    if win is not None:
        return "windows_absolute", win, line

    # Drive-relative C:file
    if re.match(r"^[A-Za-z]:(?![\\/]).+", body):
        return "unsupported_local", body, line

    # Relative / incomplete paths — only when caller indicated file context
    # (markdown) or content looks file-like.
    if from_markdown and _looks_file_like(body):
        return "unsupported_local", body, line

    if _looks_file_like(body) and (
        body.startswith(("./", ".\\", "../", "..\\"))
        or "/" in body
        or "\\" in body
    ):
        return "unsupported_local", body, line

    return None, None, None


def _normalize_windows_absolute(body: str) -> str | None:
    s = body
    if len(s) >= 3 and s[0] == "/" and s[1].isalpha() and s[2] == ":":
        s = s[1:]
    if len(s) < 3:
        return None
    if not (s[0].isalpha() and s[1] == ":" and s[2] in "\\/"):
        return None
    # Normalize separators to backslash; do not resolve .. or casefold.
    normalized = s[0] + ":" + s[2:].replace("/", "\\")
    # Require something after the root separator to be useful, OR allow root.
    # C:\ alone is absolute but rarely an artifact — still accept if length > 3
    # or exactly C:\ / C:/
    return normalized


def _percent_decode_once(s: str) -> str:
    """Decode Markdown percent-encoding once; leave bare ``%`` alone."""
    # unquote leaves incomplete/invalid sequences intact.
    return unquote(s, encoding="utf-8", errors="strict")




def _split_line_suffix(s: str) -> tuple[str, int | None]:
    """Split Codex ``:line`` / ``:line:col`` from ``s`` without touching drive colon."""
    m = re.search(r":(\d+)(?::\d+)?$", s)
    if not m:
        return s, None
    colon_at = m.start()
    # Drive colon positions: index 1 for ``C:...``, index 2 for ``/C:...``
    drive_positions = set()
    if len(s) >= 2 and s[0].isalpha() and s[1] == ":":
        drive_positions.add(1)
    if len(s) >= 3 and s[0] == "/" and s[1].isalpha() and s[2] == ":":
        drive_positions.add(2)
    if colon_at in drive_positions:
        return s, None
    return s[:colon_at], int(m.group(1))


def _split_line_suffix_from_end(s: str) -> tuple[str, int | None]:
    return _split_line_suffix(s)


def _looks_file_like(s: str) -> bool:
    if not s or s.isspace():
        return False
    t = s.strip()
    if t.startswith(("http://", "https://", "file://", "\\\\", "//")):
        return True
    if re.match(r"^[A-Za-z]:", t):
        return True
    if t.startswith(("./", ".\\", "../", "..\\", "~/")):
        return True
    if "/" in t or "\\" in t:
        return True
    # filename.ext with a short extension — only when explicitly delimited
    # callers already gate on delimiters; still require a dot+ext cue.
    if re.match(r"^[^/\\]+?\.[A-Za-z0-9]{1,8}$", t):
        return True
    return False


def _looks_path_or_url(s: str) -> bool:
    t = s.strip()
    if not t:
        return False
    lower = t.lower()
    if lower.startswith(("http://", "https://", "file://")):
        return True
    if t.startswith(("\\\\", "//")):
        return True
    if re.match(r"^/?[A-Za-z]:[\\/]", t):
        return True
    if re.match(r"^[A-Za-z]:(?![\\/])", t):  # drive-relative
        return True
    return False


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


def _read_until_unescaped(text: str, pos: int, closer: str) -> tuple[str | None, int]:
    n = len(text)
    out: list[str] = []
    i = pos
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        if ch == closer:
            return "".join(out), i
        if ch in "\r\n":
            return None, pos
        out.append(ch)
        i += 1
    return None, pos


def _read_markdown_destination(
    text: str, pos: int
) -> tuple[str | None, int, bool]:
    """Read a Markdown link destination starting at ``pos``.

    Returns ``(dest, end_pos, incomplete)``.
    ``end_pos`` points at the closing ``)`` when successful.
    """
    n = len(text)
    if pos >= n:
        return None, pos, True

    # Angle-bracket destination
    if text[pos] == "<":
        end = text.find(">", pos + 1)
        if end < 0:
            return None, pos, True
        inner = text[pos + 1 : end]
        if "\n" in inner or "\r" in inner:
            return None, pos, True
        j = end + 1
        # Optional title whitespace — skip to )
        while j < n and text[j] in " \t":
            j += 1
        if j < n and text[j] in "\"'(":
            # title present — skip until matching close then )
            title_q = text[j]
            close_t = "'" if title_q == "'" else ('"' if title_q == '"' else ")")
            if title_q == "(":
                close_t = ")"
            k = text.find(close_t, j + 1)
            if k < 0:
                return inner, end + 1, True
            j = k + 1
            while j < n and text[j] in " \t":
                j += 1
        return inner, j, False

    # Non-angle destination: no spaces, balanced parentheses.
    depth = 0
    i = pos
    out: list[str] = []
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] in r"\\()[]<>*_!`":
            out.append(text[i + 1])
            i += 2
            continue
        if ch in " \t\r\n":
            # End of destination; optional title may follow.
            break
        if ch == "(":
            depth += 1
            out.append(ch)
            i += 1
            continue
        if ch == ")":
            if depth == 0:
                break
            depth -= 1
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1

    dest = "".join(out)
    if not dest:
        return None, pos, True
    # Skip optional title
    j = i
    while j < n and text[j] in " \t":
        j += 1
    if j < n and text[j] in "\"'(":
        title_q = text[j]
        close_t = ")" if title_q == "(" else title_q
        k = text.find(close_t, j + 1)
        if k < 0:
            return dest, i, True
        j = k + 1
        while j < n and text[j] in " \t":
            j += 1
    return dest, j, False


def _find_line_end(text: str, start: int) -> int:
    n = len(text)
    j = start
    while j < n and text[j] not in "\r\n":
        j += 1
    return j
