"""L4-bound artifact creation inside the single Nobus owner workspace."""

from __future__ import annotations

import hashlib
import html
import io
import os
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
_APPROVAL_RE = re.compile(r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$")
_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True, repr=False, slots=True)
class ArtifactProposal:
    relative_path: str
    media_type: str
    content: bytes
    content_digest: str
    current_digest: str | None


class OwnerWorkspace:
    """Render and atomically write only exact approved artifacts under one root."""

    def __init__(
        self,
        root: str | Path,
        *,
        pdf_renderer: Callable[
            [str, tuple[str, ...], tuple[tuple[str, ...], ...]], bytes
        ] | None = None,
    ) -> None:
        configured = Path(root)
        if configured.is_symlink() or (
            hasattr(configured, "is_junction") and configured.is_junction()
        ):
            raise ValueError("owner workspace root is invalid")
        resolved = configured.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("owner workspace root is invalid")
        self._root = resolved
        self._pdf_renderer = pdf_renderer or _pdf_document

    @property
    def root(self) -> Path:
        return self._root

    def propose(
        self,
        relative_path: str,
        *,
        title: str,
        paragraphs: tuple[str, ...] = (),
        rows: tuple[tuple[str, ...], ...] = (),
    ) -> ArtifactProposal:
        target = self._target(relative_path)
        suffix = target.suffix.casefold()
        if suffix not in _TYPES or not _text(title, 256):
            raise ValueError("artifact request is invalid")
        if (
            type(paragraphs) is not tuple
            or len(paragraphs) > 10_000
            or any(not _text(value, 20_000) for value in paragraphs)
            or type(rows) is not tuple
            or len(rows) > 100_000
            or any(
                type(row) is not tuple
                or len(row) > 1_000
                or any(not _text(value, 32_000) for value in row)
                for row in rows
            )
        ):
            raise ValueError("artifact content is invalid")
        renderer = {
            ".html": _html_document,
            ".docx": _docx_document,
            ".xlsx": _xlsx_document,
            ".pdf": self._pdf_renderer,
        }[suffix]
        content = renderer(title.strip(), paragraphs, rows)
        if not content or len(content) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact content is invalid")
        current = _digest_file(target) if target.exists() else None
        return ArtifactProposal(
            relative_path=target.relative_to(self._root).as_posix(),
            media_type=_TYPES[suffix],
            content=content,
            content_digest=_digest(content),
            current_digest=current,
        )

    def recover(self, proposal: ArtifactProposal) -> Path | None:
        if (
            not isinstance(proposal, ArtifactProposal)
            or proposal.content_digest != _digest(proposal.content)
        ):
            raise ValueError("artifact recovery is invalid")
        target = self._target(proposal.relative_path)
        if not target.is_file():
            return None
        _reject_linked_ancestors(self._root, target.parent)
        return target if _digest_file(target) == proposal.content_digest else None

    def apply(self, proposal: ArtifactProposal, *, approval_ref: str) -> Path:
        if (
            not isinstance(proposal, ArtifactProposal)
            or _APPROVAL_RE.fullmatch(approval_ref) is None
            or proposal.content_digest != _digest(proposal.content)
            or len(proposal.content) > MAX_ARTIFACT_BYTES
        ):
            raise ValueError("artifact approval is invalid")
        target = self._target(proposal.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _reject_linked_ancestors(self._root, target.parent)
        parent_identity = _directory_identity(target.parent)
        lock_path = target.parent / f".{target.name}.nobus.lock"
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            raise RuntimeError("artifact write is already in progress") from None
        try:
            current = _digest_file(target) if target.exists() else None
            if current != proposal.current_digest:
                raise RuntimeError("artifact changed after preview")
            identity = _file_identity(target) if target.exists() else None
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temporary = Path(temporary_name)
        except BaseException:
            os.close(lock_descriptor)
            lock_path.unlink(missing_ok=True)
            raise
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(proposal.content)
                stream.flush()
                os.fsync(stream.fileno())
            if _digest_file(temporary) != proposal.content_digest:
                raise RuntimeError("artifact write verification failed")
            _reject_linked_ancestors(self._root, target.parent)
            if (
                _directory_identity(target.parent) != parent_identity
                or self._target(proposal.relative_path).parent.resolve(strict=True)
                != target.parent.resolve(strict=True)
                or (_file_identity(target) if target.exists() else None)
                != identity
            ):
                raise RuntimeError("artifact changed during approved write")
            os.replace(temporary, target)
            if _digest_file(target) != proposal.content_digest:
                raise RuntimeError("artifact write verification failed")
            return target
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            os.close(lock_descriptor)
            lock_path.unlink(missing_ok=True)

    def _target(self, relative_path: str) -> Path:
        if (
            not isinstance(relative_path, str)
            or not relative_path.strip()
            or "\x00" in relative_path
            or len(relative_path) > 1_024
        ):
            raise ValueError("artifact path is invalid")
        relative = Path(relative_path.strip())
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("artifact path is invalid")
        target = self._root / relative
        try:
            target.resolve(strict=False).relative_to(self._root)
        except (OSError, RuntimeError, ValueError):
            raise ValueError("artifact path is invalid") from None
        return target


def _reject_linked_ancestors(root: Path, parent: Path) -> None:
    current = parent
    while current != root:
        if current.is_symlink() or (
            hasattr(current, "is_junction") and current.is_junction()
        ):
            raise ValueError("artifact path is invalid")
        current = current.parent



class EdgePdfRenderer:
    """Render UTF-8 HTML to PDF with a fixed local Edge binary and no web access."""

    def __init__(
        self,
        executable: str | Path,
        *,
        temp_root: str | Path,
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = Path(executable).resolve(strict=True)
        self._temp_root = Path(temp_root).resolve(strict=True)
        if (
            not self._executable.is_file()
            or not self._temp_root.is_dir()
            or type(timeout_seconds) is not int
            or not 10 <= timeout_seconds <= 300
        ):
            raise ValueError("PDF renderer configuration is invalid")
        self._timeout = timeout_seconds

    def __call__(
        self,
        title: str,
        paragraphs: tuple[str, ...],
        rows: tuple[tuple[str, ...], ...],
    ) -> bytes:
        with tempfile.TemporaryDirectory(
            prefix="nobus-pdf-", dir=self._temp_root
        ) as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "source.html"
            output = temporary / "output.pdf"
            profile = temporary / "edge-profile"
            source.write_bytes(_html_document(title, paragraphs, rows))
            result = subprocess.run(
                (
                    str(self._executable),
                    "--headless",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-sync",
                    "--disable-background-networking",
                    "--no-first-run",
                    "--no-pdf-header-footer",
                    f"--user-data-dir={profile}",
                    f"--print-to-pdf={output}",
                    source.as_uri(),
                ),
                cwd=temporary,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self._timeout,
                check=False,
                shell=False,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                ),
                env={
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                    "TEMP": str(temporary),
                    "TMP": str(temporary),
                },
            )
            content = output.read_bytes() if output.is_file() else b""
            if (
                result.returncode != 0
                or not content.startswith(b"%PDF-")
                or len(content) > MAX_ARTIFACT_BYTES
            ):
                raise RuntimeError("PDF rendering failed")
            return content

def _html_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    body = "".join(f"<p>{html.escape(value)}</p>" for value in paragraphs)
    if rows:
        body += "<table>" + "".join(
            "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row) + "</tr>"
            for row in rows
        ) + "</table>"
    return (
        "<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><h1>{html.escape(title)}</h1>{body}</html>"
    ).encode()


def _docx_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    values = (title, *paragraphs, *(value for row in rows for value in row))
    body = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(value)}</w:t></w:r></w:p>"
        for value in values
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}<w:sectPr/></w:body></w:document>"
        ),
    }
    return _zip(files)


def _xlsx_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    data = rows or tuple((value,) for value in (title, *paragraphs))
    sheet_rows = []
    for row_index, row in enumerate(data, 1):
        cells = "".join(
            f'<c r="{_column(index)}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            for index, value in enumerate(row, 1)
        )
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Nobus" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
        ),
    }
    return _zip(files)


def _pdf_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    values = (title, *paragraphs, *(value for row in rows for value in row))
    if any(any(ord(character) > 255 for character in value) for value in values):
        raise ValueError("PDF without an embedded font supports Latin text only")
    lines = ["BT /F1 12 Tf 50 790 Td"]
    for index, value in enumerate(values):
        escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(("" if index == 0 else "0 -18 Td ") + f"({escaped}) Tj")
    stream = "\n".join(lines + ["ET"]).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    start = output.tell()
    output.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return output.getvalue()


def _zip(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, value.encode())
    return output.getvalue()


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _directory_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and not any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in value
        )
    )
