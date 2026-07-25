from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.application.network_commands import NetworkCommandRunner
from src.application.network_tools import NetworkBoundaryError, Quarantine, SafeDownloader
from src.application.task_profiles import (
    PROFILE_POLICIES,
    TaskProfile,
    profile_for_command,
)


PUBLIC = [(None, None, None, None, ("93.184.216.34", 443))]
PRIVATE = [(None, None, None, None, ("127.0.0.1", 443))]
APPROVAL = "telegram-owner-confirmation:sha256:" + "a" * 64


@pytest.mark.asyncio
async def test_download_preview_is_https_public_bounded_and_not_written(tmp_path):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/pdf",
                "content-disposition": 'attachment; filename="report.pdf"',
            },
            content=b"%PDF-1.4\nsafe",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = SafeDownloader(client=client, resolver=lambda *a, **k: PUBLIC)
    proposal = await downloader.preview("https://example.com/report")

    assert proposal.filename == "report.pdf"
    assert proposal.content.startswith(b"%PDF-")
    assert list(tmp_path.iterdir()) == []
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,resolver",
    [
        ("http://example.com/file.pdf", lambda *a, **k: PUBLIC),
        ("https://127.0.0.1/file.pdf", lambda *a, **k: PRIVATE),
        ("file:///etc/passwd", lambda *a, **k: PUBLIC),
    ],
)
async def test_download_rejects_non_https_and_private_targets(url, resolver):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    downloader = SafeDownloader(client=client, resolver=resolver)
    with pytest.raises(NetworkBoundaryError):
        await downloader.preview(url)
    await client.aclose()


def test_quarantine_requires_l4_and_never_overwrites(tmp_path):
    from src.application.network_tools import DownloadProposal

    content = b"%PDF-1.4\nsafe"
    import hashlib

    proposal = DownloadProposal(
        "https://example.com/a.pdf",
        "https://example.com/a.pdf",
        "a.pdf",
        "application/pdf",
        content,
        "sha256:" + hashlib.sha256(content).hexdigest(),
    )
    quarantine = Quarantine(tmp_path)
    with pytest.raises(ValueError):
        quarantine.store(proposal, approval_ref="yes")
    target = quarantine.store(proposal, approval_ref=APPROVAL)
    assert target.read_bytes() == content
    with pytest.raises(FileExistsError):
        quarantine.store(proposal, approval_ref=APPROVAL)


def test_task_profiles_never_infer_write_authority_from_prose():
    assert profile_for_command("/research") is TaskProfile.RESEARCH_WEB
    assert PROFILE_POLICIES[TaskProfile.ANSWER_READ].permissions == (
        "model.inference",
        "owner.library.read",
    )
    assert PROFILE_POLICIES[TaskProfile.RESEARCH_WEB].permissions == (
        "model.inference",
        "owner.library.read",
        "web.search",
    )
    for profile in (TaskProfile.ANSWER_READ, TaskProfile.RESEARCH_WEB):
        assert "artifact.write" not in PROFILE_POLICIES[profile].permissions
        assert "filesystem.delete" not in PROFILE_POLICIES[profile].permissions
    assert profile_for_command("создай документ") is None
    assert not PROFILE_POLICIES[TaskProfile.RESEARCH_WEB].requires_l4
    assert not PROFILE_POLICIES[TaskProfile.ARTIFACT_CREATE].requires_l4
    assert not PROFILE_POLICIES[TaskProfile.DOWNLOAD_QUARANTINE].requires_l4
    assert not PROFILE_POLICIES[TaskProfile.NETWORK_COMMAND].requires_l4


def test_network_command_proposal_is_exact_and_path_bound(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    metadata = root / ".git"
    metadata.mkdir()
    config = metadata / "config"
    config.write_text(
        '[remote "origin"]\n\turl = https://example.com/repo.git\n',
        encoding="utf-8",
    )
    requirements = root / "requirements.txt"
    requirements.write_text("x==1 --hash=sha256:" + "0" * 64)
    git = tmp_path / "git.exe"
    python = tmp_path / "python.exe"
    git.touch()
    python.touch()
    runner = NetworkCommandRunner(
        workspace_root=root,
        git_executable=git,
        python_executable=python,
    )

    proposal = runner.propose_git_fetch(
        repository_directory=".", remote="origin", revision="main"
    )
    assert proposal.argv == (
        "fetch",
        "--no-tags",
        "--",
        "https://example.com/repo.git",
        "main",
    )
    assert proposal.destination == "https://example.com/repo.git"
    config.write_text(
        '[remote "origin"]\n\turl = https://evil.example/repo.git\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="changed after approval"):
        runner.run(proposal, approval_ref=APPROVAL)

    pip_proposal = runner.propose_pip_install(
        repository_directory=".", requirement_file="requirements.txt"
    )
    requirements.write_text("x==2 --hash=sha256:" + "1" * 64)
    with pytest.raises(ValueError, match="changed after approval"):
        runner.run(pip_proposal, approval_ref=APPROVAL)

    with pytest.raises(ValueError):
        runner.propose_git_fetch(
            repository_directory="..", remote="origin", revision="main"
        )


def test_quarantine_revalidates_root_identity_before_link(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib
    import src.application.network_tools as network_tools
    from src.application.network_tools import DownloadProposal

    content = b"%PDF-1.4\nsafe"
    proposal = DownloadProposal(
        "https://example.com/a.pdf",
        "https://example.com/a.pdf",
        "a.pdf",
        "application/pdf",
        content,
        "sha256:" + hashlib.sha256(content).hexdigest(),
    )
    quarantine = Quarantine(tmp_path)
    monkeypatch.setattr(network_tools, "_directory_identity", lambda path: (9, 9))
    with pytest.raises(RuntimeError, match="quarantine root changed"):
        quarantine.store(proposal, approval_ref=APPROVAL)
    assert not (tmp_path / "a.pdf").exists()
