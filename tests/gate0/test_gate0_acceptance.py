from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/gate0"))

from gate0_acceptance import (  # noqa: E402
    ACCEPTANCE_REL,
    STATUS_RELATIVES,
    build_acceptance,
    validate_acceptance,
    write_acceptance,
)


def _git(repo: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _write_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _result_repo(tmp_path: pathlib.Path, *, ready: bool = True) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "gate0-tests@example.invalid")
    _git(repo, "config", "user.name", "Gate 0 Tests")
    handoff = {
        "schema": "nobus.gate0.handoff.v1",
        "status": "ready" if ready else "blocked",
        "blocking_criteria": [] if ready else ["G0-19"],
        "result_commit": None,
        "acceptance": [
            {
                "id": f"G0-{index:02d}",
                "status": "pass" if ready else "blocked",
            }
            for index in range(1, 23)
        ],
    }
    handoff_path = repo / (
        "docs/gates/gate-00-product-contract-baseline/"
        "fixtures/contracts/valid/gate-handoff.json"
    )
    _write_json(handoff_path, handoff)
    for relative in STATUS_RELATIVES:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Gate 0 sealed candidate; acceptance pending.\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feat(gate0): seal result")
    return repo


def _accept(repo: pathlib.Path, *, extra_path: str | None = None) -> dict[str, object]:
    acceptance = build_acceptance(
        repo,
        accepted_at="2030-01-10T00:00:00Z",
        accepted_by="owner:synthetic",
    )
    write_acceptance(repo, acceptance)
    marker = (
        "Gate 0 READY\n"
        f"result_commit: {acceptance['result_commit']}\n"
        f"result_tree: {acceptance['result_tree']}\n"
    )
    for relative in STATUS_RELATIVES:
        (repo / relative).write_text(marker, encoding="utf-8", newline="\n")
    if extra_path is not None:
        path = repo / extra_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not allowed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore(gate0): accept sealed baseline")
    return acceptance


def test_acceptance_binds_exact_parent_commit_tree_and_handoff(
    tmp_path: pathlib.Path,
) -> None:
    repo = _result_repo(tmp_path)
    acceptance = _accept(repo)

    assert validate_acceptance(repo) == acceptance
    assert acceptance["result_commit"] == _git(repo, "rev-parse", "HEAD^")
    assert acceptance["result_tree"] == _git(
        repo, "rev-parse", f"{acceptance['result_commit']}^{{tree}}"
    )


def test_acceptance_rejects_worktree_tamper(tmp_path: pathlib.Path) -> None:
    repo = _result_repo(tmp_path)
    acceptance = _accept(repo)
    attacked = copy.deepcopy(acceptance)
    attacked["result_tree"] = "0" * 40
    _write_json(repo / ACCEPTANCE_REL, attacked)

    with pytest.raises(RuntimeError, match="working tree"):
        validate_acceptance(repo)


def test_acceptance_rejects_wrong_result_tree(tmp_path: pathlib.Path) -> None:
    repo = _result_repo(tmp_path)
    acceptance = build_acceptance(
        repo,
        accepted_at="2030-01-10T00:00:00Z",
        accepted_by="owner:synthetic",
    )
    acceptance["result_tree"] = "0" * 40
    write_acceptance(repo, acceptance)
    marker = (
        "Gate 0 READY\n"
        f"result_commit: {acceptance['result_commit']}\n"
        f"result_tree: {acceptance['result_tree']}\n"
    )
    for relative in STATUS_RELATIVES:
        (repo / relative).write_text(marker, encoding="utf-8", newline="\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore(gate0): invalid acceptance")

    with pytest.raises(RuntimeError, match="result tree"):
        validate_acceptance(repo)


def test_acceptance_rejects_unapproved_commit_path(tmp_path: pathlib.Path) -> None:
    repo = _result_repo(tmp_path)
    _accept(repo, extra_path="src/unauthorized.py")

    with pytest.raises(RuntimeError, match="changed paths"):
        validate_acceptance(repo)


def test_acceptance_rejects_result_that_is_not_ready(tmp_path: pathlib.Path) -> None:
    repo = _result_repo(tmp_path, ready=False)

    with pytest.raises(RuntimeError, match="sealed READY"):
        build_acceptance(
            repo,
            accepted_at="2030-01-10T00:00:00Z",
            accepted_by="owner:synthetic",
        )
