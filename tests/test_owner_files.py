from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest

import src.application.owner_files as owner_files
from src.application.owner_files import (
    OwnerFileSensitiveError,
    OwnerFileService,
)


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


@pytest.mark.asyncio
async def test_markdown_context_is_bounded_and_digest_bound(tmp_path: Path) -> None:
    document = tmp_path / "docs" / "brief.md"
    document.parent.mkdir()
    document.write_text("# Итог\n\nПроверенный текст.", encoding="utf-8")
    service = OwnerFileService(tmp_path)

    selection = await service.context("brief.md")

    assert selection.context is not None
    assert selection.context.relative_path == str(Path("docs") / "brief.md")
    assert "Проверенный текст." in selection.context.text
    assert selection.context.content_digest.startswith("sha256:")
    assert selection.choices == ()


@pytest.mark.asyncio
async def test_docx_context_extracts_text_without_external_dependency(
    tmp_path: Path,
) -> None:
    document = tmp_path / "brief.docx"
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="urn:test"><w:body><w:p>'
                "<w:r><w:t>Безопасный</w:t></w:r>"
                "<w:r><w:t>текст</w:t></w:r>"
                "</w:p></w:body></w:document>"
            ),
        )
    service = OwnerFileService(tmp_path)

    selection = await service.context("brief.docx")

    assert selection.context is not None
    assert selection.context.text == "Безопасный текст"


@pytest.mark.asyncio
async def test_pdf_can_be_delivered_but_not_injected_as_text(tmp_path: Path) -> None:
    (tmp_path / "brief.pdf").write_bytes(b"%PDF-safe")
    service = OwnerFileService(tmp_path)

    delivery = await service.select("brief.pdf")
    assert delivery.document is not None

    with pytest.raises(ValueError, match="owner document text is unavailable"):
        await service.context("brief.pdf")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    (
        "api_key = sk-example-not-real-1234567890",
        "Контакт клиента: owner@example.org",
        "Телефон: +7 (999) 123-45-67",
        "ИНН-подобный идентификатор: 123456789012",
        "-----BEGIN PRIVATE KEY-----",
    ),
)
async def test_neutral_filename_sensitive_content_never_leaves_boundary(
    tmp_path: Path,
    content: str,
) -> None:
    (tmp_path / "brief.md").write_text(content, encoding="utf-8")
    service = OwnerFileService(tmp_path)

    with pytest.raises(
        OwnerFileSensitiveError,
        match="contains protected data",
    ):
        await service.context("brief.md")



@pytest.mark.asyncio
async def test_cp1251_text_is_not_misdecoded_as_utf16(tmp_path: Path) -> None:
    expected = "Отчёт по маркетплейсам"
    (tmp_path / "brief.txt").write_bytes(expected.encode("cp1251"))
    service = OwnerFileService(tmp_path)

    selection = await service.context("brief.txt")

    assert selection.context is not None
    assert selection.context.text == expected


def test_zip_with_excessive_metadata_is_rejected(tmp_path: Path) -> None:
    import io
    import zipfile

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for index in range(513):
            archive.writestr(f"unused/{index}.txt", "")
        archive.writestr("word/document.xml", "<w:t>safe</w:t>")
    (tmp_path / "brief.docx").write_bytes(payload.getvalue())
    service = OwnerFileService(tmp_path)

    with pytest.raises(ValueError, match="text is unavailable"):
        service._read("brief.docx")
        owner_files._extract_text(".docx", payload.getvalue())


def test_sensitive_text_detects_common_tokens_and_separated_card_numbers():
    import src.application.owner_files as owner_files

    assert owner_files._contains_sensitive_text("AKIAIOSFODNN7EXAMPLE")
    assert owner_files._contains_sensitive_text(
        "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    )
    assert owner_files._contains_sensitive_text("4111 1111 1111 1111")


def test_owner_file_answer_rejects_verbatim_but_allows_summary():
    from src.application.owner_files import owner_file_answer_is_safe

    source = " ".join(f"owner-word-{index}" for index in range(80))
    assert not owner_file_answer_is_safe(source, f"Результат: {source}")
    assert owner_file_answer_is_safe(
        source, "Документ содержит последовательный тестовый перечень."
    )


@pytest.mark.parametrize(
    "value",
    (
        "AIzaSyD-EXAMPLE1234567890abcdefghijkl",
        "ASIAIOSFODNN7EXAMPLE",
        "rk_live_51abcdefghijklmnopqrstuvwxyz",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature",
        "4111.1111.1111.1111",
    ),
)
def test_sensitive_text_detects_additional_common_credentials(value):
    import src.application.owner_files as owner_files

    assert owner_files._contains_sensitive_text(value)


def test_owner_file_answer_rejects_transformed_verbatim():
    import base64
    from src.application.owner_files import owner_file_answer_is_safe

    source = " ".join(f"Owner word {index}" for index in range(80))
    assert not owner_file_answer_is_safe(source, source.replace(" ", "  ", 1))
    assert not owner_file_answer_is_safe(source, source[::-1])
    assert not owner_file_answer_is_safe(
        source, base64.b64encode(source.encode()).decode()
    )
    assert not owner_file_answer_is_safe(source, source.encode().hex())


def test_owner_file_answer_rejects_high_coverage_with_inserted_words():
    from src.application.owner_files import owner_file_answer_is_safe

    source_tokens = [f"слово{index}" for index in range(40)]
    answer_tokens = []
    for index, token in enumerate(source_tokens, 1):
        answer_tokens.append(token)
        if index % 7 == 0:
            answer_tokens.append("нейтральное")
    assert not owner_file_answer_is_safe(
        " ".join(source_tokens), " ".join(answer_tokens)
    )


def test_owner_file_answer_rejects_chunked_base64_and_hex():
    import base64
    from src.application.owner_files import owner_file_answer_is_safe

    source = " ".join(f"Owner context word {index}" for index in range(80))
    encoded = base64.b64encode(source.encode()).decode()
    chunked_base64 = " ".join(
        encoded[index : index + 16] for index in range(0, len(encoded), 16)
    )
    hexadecimal = source.encode().hex()
    chunked_hex = " ".join(
        hexadecimal[index : index + 16]
        for index in range(0, len(hexadecimal), 16)
    )
    assert not owner_file_answer_is_safe(source, chunked_base64)
    assert not owner_file_answer_is_safe(source, chunked_hex)


def test_owner_file_answer_padding_cannot_hide_source_coverage():
    from src.application.owner_files import owner_file_answer_is_safe

    source_tokens = [f"слово{index}" for index in range(40)]
    answer_tokens = []
    for index, token in enumerate(source_tokens, 1):
        answer_tokens.append(token)
        if index % 7 == 0:
            answer_tokens.append("нейтральное")
    answer_tokens.extend(f"padding{index}" for index in range(30))
    assert not owner_file_answer_is_safe(
        " ".join(source_tokens), " ".join(answer_tokens)
    )


def test_owner_file_answer_rejects_complete_short_source():
    from src.application.owner_files import owner_file_answer_is_safe

    assert not owner_file_answer_is_safe(
        "Итого миллион", "Ответ: Итого миллион"
    )
