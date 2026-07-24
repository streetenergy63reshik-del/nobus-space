from __future__ import annotations

import zipfile

import pytest

from src.application.owner_workspace import OwnerWorkspace


APPROVAL = "telegram-owner-confirmation:sha256:" + "a" * 64


@pytest.mark.parametrize("suffix", [".html", ".docx", ".xlsx", ".pdf"])
def test_propose_and_apply_new_artifact_atomically(tmp_path, suffix):
    root = tmp_path / "NOBUS SPACE BOT"
    root.mkdir()
    workspace = OwnerWorkspace(root)
    proposal = workspace.propose(
        f"reports/result{suffix}",
        title="Nobus report",
        paragraphs=("First paragraph",),
        rows=(("A", "B"),),
    )

    target = workspace.apply(proposal, approval_ref=APPROVAL)

    assert target.read_bytes() == proposal.content
    assert target.resolve().is_relative_to(workspace.root)
    if suffix in {".docx", ".xlsx"}:
        with zipfile.ZipFile(target) as archive:
            assert "[Content_Types].xml" in archive.namelist()


def test_overwrite_is_bound_to_current_digest(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    root.mkdir()
    workspace = OwnerWorkspace(root)
    target = workspace.root / "report.html"
    target.write_text("before", encoding="utf-8")
    proposal = workspace.propose(
        "report.html", title="Nobus", paragraphs=("after",)
    )
    target.write_text("raced", encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed after preview"):
        workspace.apply(proposal, approval_ref=APPROVAL)
    assert target.read_text(encoding="utf-8") == "raced"


@pytest.mark.parametrize(
    "path",
    ["../outside.html", "/absolute.html", "nested/../../escape.docx", "bad.exe"],
)
def test_path_and_type_escape_are_rejected(tmp_path, path):
    root = tmp_path / "NOBUS SPACE BOT"
    root.mkdir()
    workspace = OwnerWorkspace(root)
    with pytest.raises(ValueError):
        workspace.propose(path, title="Nobus")


def test_apply_requires_exact_l4_reference(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    root.mkdir()
    workspace = OwnerWorkspace(root)
    proposal = workspace.propose("report.html", title="Nobus")
    with pytest.raises(ValueError, match="approval"):
        workspace.apply(proposal, approval_ref="approved")
    assert not (workspace.root / "report.html").exists()


def test_artifact_parent_identity_is_rechecked_before_replace(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.application.owner_workspace as owner_workspace

    root = tmp_path / "NOBUS SPACE BOT"
    (root / "reports").mkdir(parents=True)
    workspace = OwnerWorkspace(root)
    proposal = workspace.propose(
        "reports/result.html",
        title="Nobus",
        paragraphs=("safe",),
    )
    real = owner_workspace._directory_identity(root / "reports")
    calls = 0

    def changed(_path):
        nonlocal calls
        calls += 1
        return real if calls == 1 else (real[0], real[1] + 1)

    monkeypatch.setattr(owner_workspace, "_directory_identity", changed)
    with pytest.raises(RuntimeError, match="changed during approved write"):
        workspace.apply(proposal, approval_ref=APPROVAL)
    assert not (root / "reports/result.html").exists()
