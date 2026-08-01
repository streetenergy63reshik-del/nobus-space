"""Build and verify the separate immutable Gate 0 acceptance commit."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
from typing import Any

from collect_gate0_snapshot import _read_repo_regular_bytes


UTC = dt.timezone.utc
ACCEPTANCE_REL = pathlib.PurePosixPath(
    "docs/gates/gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json"
)
HANDOFF_REL = pathlib.PurePosixPath(
    "docs/gates/gate-00-product-contract-baseline/"
    "fixtures/contracts/valid/gate-handoff.json"
)
STATUS_RELATIVES = (
    pathlib.PurePosixPath("README.md"),
    pathlib.PurePosixPath("docs/gates/README.md"),
    pathlib.PurePosixPath("docs/handoffs/CURRENT-STATUS.md"),
)
ACCEPTANCE_KEYS = {
    "accepted_at",
    "accepted_by",
    "gate",
    "result_commit",
    "result_handoff_ref",
    "result_handoff_sha256",
    "result_tree",
    "schema",
    "status",
}
OID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTITY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")


def _git(
    root: pathlib.Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        check=False,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise RuntimeError("Git object read failed during Gate 0 acceptance")
    return completed


def _git_text(root: pathlib.Path, *args: str) -> str:
    try:
        return _git(root, *args).stdout.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise RuntimeError("Git text was not valid UTF-8") from error


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _strict_json(raw: bytes, *, label: str) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def no_non_finite(value: str) -> None:
        raise RuntimeError(f"{label} contains a non-finite JSON number: {value}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=no_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} is not valid UTF-8 JSON") from error


def _utc_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise RuntimeError("acceptance timestamp is not exact")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError("acceptance timestamp is not exact") from error
    if (
        not value.endswith("Z")
        or parsed.tzinfo is None
        or parsed.utcoffset() != dt.timedelta(0)
    ):
        raise RuntimeError("acceptance timestamp must be UTC")
    return value


def _worktree_paths(root: pathlib.Path) -> list[str]:
    raw = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "-z",
    ).stdout
    try:
        records = raw.decode("utf-8").split("\0")
    except UnicodeDecodeError as error:
        raise RuntimeError("Git working tree status was not valid UTF-8") from error
    paths: list[str] = []
    index = 0
    while index < len(records) and records[index]:
        record = records[index]
        status = record[:2]
        paths.append(record[3:].replace("\\", "/"))
        index += 1
        if status[0] in {"R", "C"} and index < len(records):
            paths.append(records[index].replace("\\", "/"))
            index += 1
    return paths


def _require_clean_acceptance_surface(root: pathlib.Path) -> None:
    unexpected = [
        path for path in _worktree_paths(root)
        if path != ".nobus-quality" and not path.startswith(".nobus-quality/")
    ]
    if unexpected:
        raise RuntimeError("Gate 0 acceptance working tree is not clean")


def _ready_handoff(raw: bytes) -> dict[str, Any]:
    handoff = _strict_json(raw, label="sealed Gate 0 handoff")
    acceptance = handoff.get("acceptance") if isinstance(handoff, dict) else None
    if (
        not isinstance(handoff, dict)
        or handoff.get("status") != "ready"
        or handoff.get("blocking_criteria") != []
        or handoff.get("result_commit") is not None
        or not isinstance(acceptance, list)
        or len(acceptance) != 22
        or [item.get("id") for item in acceptance]
        != [f"G0-{index:02d}" for index in range(1, 23)]
        or any(item.get("status") != "pass" for item in acceptance)
    ):
        raise RuntimeError("result commit does not contain a sealed READY 22/22 handoff")
    return handoff


def _validate_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ACCEPTANCE_KEYS:
        raise RuntimeError("Gate 0 acceptance shape is not exact")
    if (
        value.get("schema") != "nobus.gate0.acceptance.v1"
        or value.get("gate") != 0
        or value.get("status") != "accepted"
        or not isinstance(value.get("result_commit"), str)
        or not OID_PATTERN.fullmatch(value["result_commit"])
        or not isinstance(value.get("result_tree"), str)
        or not OID_PATTERN.fullmatch(value["result_tree"])
        or value.get("result_handoff_ref") != HANDOFF_REL.as_posix()
        or not isinstance(value.get("result_handoff_sha256"), str)
        or not DIGEST_PATTERN.fullmatch(value["result_handoff_sha256"])
        or not isinstance(value.get("accepted_by"), str)
        or not IDENTITY_PATTERN.fullmatch(value["accepted_by"])
    ):
        raise RuntimeError("Gate 0 acceptance values are not exact")
    _utc_timestamp(value.get("accepted_at"))
    return value


def build_acceptance(
    root: pathlib.Path,
    *,
    accepted_at: str,
    accepted_by: str,
) -> dict[str, Any]:
    root = pathlib.Path(os.path.abspath(root))
    _require_clean_acceptance_surface(root)
    result_commit = _git_text(root, "rev-parse", "HEAD")
    result_tree = _git_text(root, "rev-parse", f"{result_commit}^{{tree}}")
    handoff_raw = _git(root, "show", f"{result_commit}:{HANDOFF_REL.as_posix()}").stdout
    _ready_handoff(handoff_raw)
    return _validate_shape(
        {
            "schema": "nobus.gate0.acceptance.v1",
            "gate": 0,
            "status": "accepted",
            "result_commit": result_commit,
            "result_tree": result_tree,
            "result_handoff_ref": HANDOFF_REL.as_posix(),
            "result_handoff_sha256": _sha256(handoff_raw),
            "accepted_at": accepted_at,
            "accepted_by": accepted_by,
        }
    )


def write_acceptance(root: pathlib.Path, value: dict[str, Any]) -> pathlib.Path:
    validated = _validate_shape(value)
    path = pathlib.Path(os.path.abspath(root)) / ACCEPTANCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def validate_acceptance(root: pathlib.Path) -> dict[str, Any]:
    root = pathlib.Path(os.path.abspath(root))
    _require_clean_acceptance_surface(root)
    head = _git_text(root, "rev-parse", "HEAD")
    parents = _git_text(root, "rev-list", "--parents", "-n", "1", head).split()
    if len(parents) != 2:
        raise RuntimeError("Gate 0 acceptance commit must have exactly one parent")
    parent = parents[1]
    working_raw = _read_repo_regular_bytes(root, root / ACCEPTANCE_REL)
    committed_raw = _git(root, "show", f"{head}:{ACCEPTANCE_REL.as_posix()}").stdout
    if working_raw != committed_raw:
        raise RuntimeError("Gate 0 acceptance working tree differs from commit")
    acceptance = _validate_shape(_strict_json(committed_raw, label="Gate 0 acceptance"))
    if acceptance["result_commit"] != parent:
        raise RuntimeError("Gate 0 acceptance parent is not the result commit")
    result_tree = _git_text(root, "rev-parse", f"{parent}^{{tree}}")
    if acceptance["result_tree"] != result_tree:
        raise RuntimeError("Gate 0 acceptance result tree is not exact")
    handoff_raw = _git(root, "show", f"{parent}:{HANDOFF_REL.as_posix()}").stdout
    _ready_handoff(handoff_raw)
    if acceptance["result_handoff_sha256"] != _sha256(handoff_raw):
        raise RuntimeError("Gate 0 acceptance handoff digest is not exact")
    if _git(root, "cat-file", "-e", f"{parent}:{ACCEPTANCE_REL.as_posix()}", check=False).returncode == 0:
        raise RuntimeError("Gate 0 acceptance record already existed in result commit")
    changed = set(
        _git_text(root, "diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines()
    )
    expected_changed = {ACCEPTANCE_REL.as_posix(), *(path.as_posix() for path in STATUS_RELATIVES)}
    if changed != expected_changed:
        raise RuntimeError("Gate 0 acceptance commit changed paths are not exact")
    for relative in STATUS_RELATIVES:
        raw = _git(root, "show", f"{head}:{relative.as_posix()}").stdout
        try:
            status_text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeError("Gate 0 status document is not UTF-8") from error
        if (
            "Gate 0 READY" not in status_text
            or f"result_commit: {parent}" not in status_text
            or f"result_tree: {result_tree}" not in status_text
        ):
            raise RuntimeError("Gate 0 status document is not acceptance-bound")
    return acceptance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--accepted-at")
    parser.add_argument("--accepted-by")
    args = parser.parse_args()
    if args.mode == "build":
        if not args.accepted_at or not args.accepted_by:
            parser.error("build requires --accepted-at and --accepted-by")
        value = build_acceptance(
            args.root,
            accepted_at=args.accepted_at,
            accepted_by=args.accepted_by,
        )
        write_acceptance(args.root, value)
    else:
        value = validate_acceptance(args.root)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
