from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

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



def test_overwrite_requires_and_creates_verified_snapshot(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "reports" / "report.html"
    target.parent.mkdir()
    original = b"before"
    target.write_bytes(original)

    without_snapshot = OwnerWorkspace(root)
    proposal = without_snapshot.propose(
        "reports/report.html",
        title="Nobus",
        paragraphs=("after",),
    )
    with pytest.raises(RuntimeError, match="snapshot is unavailable"):
        without_snapshot.apply(proposal, approval_ref=APPROVAL)
    assert target.read_bytes() == original

    workspace = OwnerWorkspace(root, snapshot_root=snapshots)
    proposal = workspace.propose(
        "reports/report.html",
        title="Nobus",
        paragraphs=("after",),
    )
    workspace.apply(proposal, approval_ref=APPROVAL)

    backups = tuple(snapshots.rglob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert target.read_bytes() == proposal.content


def test_verified_snapshot_can_restore_with_cas_and_exact_approval(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "reports" / "report.html"
    target.parent.mkdir()
    original = b"before"
    target.write_bytes(original)
    original_digest = "sha256:" + hashlib.sha256(original).hexdigest()
    workspace = OwnerWorkspace(root, snapshot_root=snapshots)
    proposal = workspace.propose(
        "reports/report.html", title="Nobus", paragraphs=("after",)
    )
    workspace.apply(proposal, approval_ref=APPROVAL)

    restored = workspace.restore_snapshot(
        "reports/report.html",
        snapshot_digest=original_digest,
        expected_current_digest=proposal.content_digest,
        approval_ref=APPROVAL,
    )

    assert restored == target
    assert target.read_bytes() == original

    with pytest.raises(RuntimeError, match="changed before restore"):
        workspace.restore_snapshot(
            "reports/report.html",
            snapshot_digest=original_digest,
            expected_current_digest=proposal.content_digest,
            approval_ref=APPROVAL,
        )



def test_snapshot_parent_identity_is_rechecked_before_replace(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.application.owner_workspace as owner_workspace

    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "reports" / "report.html"
    target.parent.mkdir()
    target.write_bytes(b"before")
    workspace = OwnerWorkspace(root, snapshot_root=snapshots)
    proposal = workspace.propose(
        "reports/report.html", title="Nobus", paragraphs=("after",)
    )
    expected_parent = snapshots / "reports" / "report.html"
    real_identity = owner_workspace._directory_identity
    parent_calls = 0

    def identity(path):
        nonlocal parent_calls
        value = real_identity(path)
        if Path(path) == expected_parent:
            parent_calls += 1
            if parent_calls > 1:
                return (value[0], value[1] + 1)
        return value

    monkeypatch.setattr(owner_workspace, "_directory_identity", identity)
    with pytest.raises(RuntimeError, match="snapshot root changed"):
        workspace.apply(proposal, approval_ref=APPROVAL)
    assert target.read_bytes() == b"before"


def test_overwrite_preview_contains_digest_and_size_diff(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    root.mkdir()
    target = root / "report.html"
    target.write_bytes(b"before")
    workspace = OwnerWorkspace(root)
    proposal = workspace.propose(
        "report.html", title="Nobus", paragraphs=("after",)
    )

    summary = workspace.diff_summary(proposal)

    assert proposal.current_digest in summary
    assert proposal.content_digest in summary
    assert "(6 bytes)" in summary


def test_startup_recovers_crash_between_target_and_source_rename(tmp_path):
    import json

    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "reports" / "report.html"
    target.parent.mkdir()
    original = b"before-crash"
    target.write_bytes(original)
    previous_digest = "sha256:" + hashlib.sha256(original).hexdigest()
    new_digest = "sha256:" + hashlib.sha256(b"after-crash").hexdigest()
    rollback_name = ".report.html.nobus-rollback-0011223344556677"
    rollback = target.parent / rollback_name
    target.replace(rollback)
    journal = snapshots / "artifact-replace-00112233445566778899aabb.json"
    journal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "relative_path": "reports/report.html",
                "rollback_name": rollback_name,
                "previous_digest": previous_digest,
                "new_digest": new_digest,
            }
        ),
        encoding="utf-8",
    )

    OwnerWorkspace(root, snapshot_root=snapshots)

    assert target.read_bytes() == original
    assert not rollback.exists()
    assert not journal.exists()



def test_committed_artifact_survives_journal_cleanup_error(
    tmp_path, monkeypatch
):
    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "report.html"
    target.write_bytes(b"before")
    workspace = OwnerWorkspace(root, snapshot_root=snapshots)
    proposal = workspace.propose(
        "report.html", title="Nobus", paragraphs=("after",)
    )
    real_unlink = Path.unlink
    failed = False

    def fail_journal_cleanup_once(path, *args, **kwargs):
        nonlocal failed
        if Path(path).name.startswith("artifact-replace-") and not failed:
            failed = True
            raise PermissionError("journal cleanup unavailable")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_journal_cleanup_once)
    result = workspace.apply(proposal, approval_ref=APPROVAL)

    assert result == target
    assert target.read_bytes() == proposal.content
    assert failed
    monkeypatch.undo()
    OwnerWorkspace(root, snapshot_root=snapshots)
    assert not tuple(snapshots.glob("artifact-replace-*.json"))


def test_stale_lock_file_does_not_block_next_write(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "report.html"
    target.write_bytes(b"before")
    (root / ".report.html.nobus.lock").write_text("stale", encoding="utf-8")
    workspace = OwnerWorkspace(root, snapshot_root=snapshots)
    proposal = workspace.propose(
        "report.html", title="Nobus", paragraphs=("after",)
    )

    workspace.apply(proposal, approval_ref=APPROVAL)

    assert target.read_bytes() == proposal.content


def test_active_artifact_lock_rejects_concurrent_write(tmp_path):
    import threading
    import src.application.owner_workspace as owner_workspace

    root = tmp_path / "NOBUS SPACE BOT"
    snapshots = tmp_path / "snapshots"
    root.mkdir()
    snapshots.mkdir()
    target = root / "report.html"
    target.write_bytes(b"before")
    workspace = OwnerWorkspace(root, snapshot_root=snapshots)
    proposal = workspace.propose(
        "report.html", title="Nobus", paragraphs=("after",)
    )
    ready = threading.Event()
    release = threading.Event()

    def hold_lock():
        lock = owner_workspace._acquire_artifact_lock(
            root / ".report.html.nobus.lock"
        )
        ready.set()
        release.wait(timeout=5)
        owner_workspace._release_artifact_lock(lock)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    assert ready.wait(timeout=5)
    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            workspace.apply(proposal, approval_ref=APPROVAL)
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert target.read_bytes() == b"before"
