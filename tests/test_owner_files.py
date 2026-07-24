from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.application.owner_files as owner_files
from src.application.owner_files import OwnerFileService


@pytest.mark.asyncio
async def test_exact_supported_document_is_read_with_relative_metadata(
    tmp_path: Path,
) -> None:
    document = tmp_path / "docs" / "roadmap.html"
    document.parent.mkdir()
    document.write_bytes(b"<html>safe</html>")
    service = OwnerFileService(tmp_path)

    selection = await service.select("roadmap.html")

    assert selection.document is not None
    assert selection.document.relative_path == str(Path("docs") / "roadmap.html")
    assert selection.document.filename == "roadmap.html"
    assert selection.document.content == b"<html>safe</html>"
    assert selection.choices == ()


@pytest.mark.asyncio
async def test_ambiguous_documents_return_paths_without_reading(
    tmp_path: Path,
) -> None:
    for folder in ("a", "b"):
        path = tmp_path / folder / "report.pdf"
        path.parent.mkdir()
        path.write_bytes(b"safe")
    service = OwnerFileService(tmp_path)

    selection = await service.select("report.pdf")

    assert selection.document is None
    assert set(selection.choices) == {
        str(Path("a") / "report.pdf"),
        str(Path("b") / "report.pdf"),
    }


@pytest.mark.asyncio
async def test_sensitive_hidden_and_unsupported_files_are_not_returned(
    tmp_path: Path,
) -> None:
    (tmp_path / ".secret.pdf").write_bytes(b"secret")
    (tmp_path / "credentials-report.pdf").write_bytes(b"secret")
    (tmp_path / "report.exe").write_bytes(b"unsafe")
    service = OwnerFileService(tmp_path)

    for query in (".secret.pdf", "credentials-report.pdf", "report.exe"):
        selection = await service.select(query)
        assert selection.document is None
        assert selection.choices == ()


@pytest.mark.asyncio
async def test_oversized_document_fails_without_returning_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"oversized")
    monkeypatch.setattr(owner_files, "MAX_OWNER_DOCUMENT_BYTES", 4)
    service = OwnerFileService(tmp_path)

    with pytest.raises(ValueError, match="owner document is unavailable"):
        await service.select("report.pdf")


@pytest.mark.asyncio
async def test_opened_handle_outside_root_is_rejected_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    candidate = root / "report.pdf"
    candidate.write_bytes(b"inside")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    monkeypatch.setattr(
        owner_files, "_opened_final_path", lambda stream: outside
    )
    service = OwnerFileService(root)

    with pytest.raises(ValueError, match="owner document is unavailable"):
        await service.select("report.pdf")


@pytest.mark.asyncio
async def test_projected_escape_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.pdf").write_bytes(b"outside")
    monkeypatch.setattr(
        owner_files,
        "find_owner_file_paths",
        lambda selected_root, query: (str(Path("..") / "outside.pdf"),),
    )
    service = OwnerFileService(root)

    with pytest.raises(ValueError, match="owner document is unavailable"):
        await service.select("outside.pdf")


def test_root_and_query_are_fail_closed(tmp_path: Path) -> None:
    file_root = tmp_path / "file"
    file_root.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="owner file root is invalid"):
        OwnerFileService(file_root)

    service = OwnerFileService(tmp_path)
    with pytest.raises(ValueError, match="owner file query is invalid"):
        asyncio.run(service.select("\x00"))
