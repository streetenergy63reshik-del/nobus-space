"""Read-only, sanitized Gate 0 evidence primitives.

The helper writes JSON to stdout only.  It never reads process command lines,
environment values, database payload columns, or owner-library descendants.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import pathlib
import platform
import re
import sqlite3
import stat
import subprocess
import sys
from typing import Any


UTC = dt.timezone.utc
GATE0_CLOSURE_AUTHORITY = "owner-authority:gate0-evidence-closure-2026-07-29"
TELEGRAM_GENESIS_ID = "genesis_baseline:telegram_state_current_schema"
GATE0_OWNED_FILES = {
    ".gitattributes",
    "README.md",
    "docs/04-\u0416\u0443\u0440\u043d\u0430\u043b-ADR.md",
    "docs/07-\u041f\u0440\u0430\u0432\u0438\u043b\u0430-\u0432\u043d\u0435\u0448\u043d\u0435\u0439-\u0437\u0430\u043f\u0438\u0441\u0438.md",
    "docs/12-\u042d\u0442\u0430\u043b\u043e\u043d-MVP-1-\u0438-\u0434\u043e\u0440\u043e\u0436\u043d\u0430\u044f-\u043a\u0430\u0440\u0442\u0430.md",
    "docs/13-\u0418\u043d\u0442\u0435\u0433\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0430\u044f-\u0430\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430-MVP-1.md",
    "docs/README.md",
    "docs/adr/0019-owner-service-filesystem-and-runtime-decisions.md",
    "docs/adr/0020-early-miniapp-and-specialist-workers.md",
    "docs/gates/README.md",
    "docs/gates/gate-01-natural-language-voice/ARCHITECTURE.md",
    "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md",
    "docs/gates/gate-03-google-foundation/ARCHITECTURE.md",
    "docs/gates/gate-04-notes-calendar-tasks/ARCHITECTURE.md",
    "docs/gates/gate-05-document-gateway-windows-bridge/ARCHITECTURE.md",
    "docs/gates/gate-08-hybrid-release-pilot/ARCHITECTURE.md",
    "docs/handoffs/CURRENT-STATUS.md",
    "tests/test_fake_vertical.py",
    "tests/test_telegram_gateway.py",
    "tests/test_trusted_ingress.py",
}
GATE0_OWNED_PREFIXES = (
    "docs/gates/gate-00-product-contract-baseline/",
    "docs/gates/gate-02a-miniapp-development-control/",
    "tests/gate0/",
)


def _unsafe_artifact_reason(relative: str) -> str | None:
    """Classify data-bearing paths before any content or target access."""

    normalized = pathlib.PurePosixPath(relative)
    lowered_parts = tuple(part.lower() for part in normalized.parts)
    name = lowered_parts[-1] if lowered_parts else ""
    if ".runtime" in lowered_parts:
        return "runtime_state_not_read"
    if name == ".env" or name.startswith(".env."):
        return "secret_shaped_not_read"
    if name in {
        "credentials.json",
        "secrets.json",
        "service-account.json",
        "token.json",
    }:
        return "secret_shaped_not_read"
    if name.endswith((
        ".key",
        ".p12",
        ".pem",
        ".pfx",
        ".db",
        ".db3",
        ".sqlite",
        ".sqlite3",
        "-shm",
        "-wal",
        ".local.json",
    )):
        return "secret_or_database_not_read"
    return None


def _safe_repo_regular_file(repo: pathlib.Path, candidate: pathlib.Path) -> bool:
    """Validate lexical containment and reject every link/reparse component."""

    try:
        root = pathlib.Path(os.path.abspath(repo))
        absolute = pathlib.Path(os.path.abspath(candidate))
        relative = absolute.relative_to(root)
        if not relative.parts or ".." in relative.parts:
            return False
        current = root
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for part in relative.parts:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                return False
            if getattr(metadata, "st_file_attributes", 0) & reparse_flag:
                return False
        return stat.S_ISREG(metadata.st_mode)
    except (OSError, ValueError):
        return False


def _read_repo_regular_bytes(
    repo: pathlib.Path,
    candidate: pathlib.Path,
) -> bytes:
    """Open a validated regular-file identity before reading any content."""

    descriptor: int | None = None
    try:
        root = pathlib.Path(os.path.abspath(repo))
        absolute = pathlib.Path(os.path.abspath(candidate))
        relative = absolute.relative_to(root)
        relative_text = relative.as_posix()
        if (
            not relative.parts
            or ".." in relative.parts
            or _unsafe_artifact_reason(relative_text) is not None
        ):
            raise RuntimeError("repository file handle is not authorized")

        current = root
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        leaf_metadata: os.stat_result | None = None
        for part in relative.parts:
            current = current / part
            leaf_metadata = os.lstat(current)
            if (
                stat.S_ISLNK(leaf_metadata.st_mode)
                or getattr(leaf_metadata, "st_file_attributes", 0) & reparse_flag
            ):
                raise RuntimeError("repository file handle has reparse topology")
        if leaf_metadata is None or not stat.S_ISREG(leaf_metadata.st_mode):
            raise RuntimeError("repository file handle is not regular")

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(absolute, flags)
        opened_metadata = os.fstat(descriptor)
        expected_identity = (
            leaf_metadata.st_dev,
            leaf_metadata.st_ino,
            stat.S_IFMT(leaf_metadata.st_mode),
        )
        opened_identity = (
            opened_metadata.st_dev,
            opened_metadata.st_ino,
            stat.S_IFMT(opened_metadata.st_mode),
        )
        if (
            expected_identity != opened_identity
            or not stat.S_ISREG(opened_metadata.st_mode)
            or getattr(opened_metadata, "st_file_attributes", 0) & reparse_flag
            or leaf_metadata.st_size != opened_metadata.st_size
            or leaf_metadata.st_mtime_ns != opened_metadata.st_mtime_ns
        ):
            raise RuntimeError("opened file identity changed before content read")

        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final_metadata = os.fstat(descriptor)
        if (
            final_metadata.st_dev != opened_metadata.st_dev
            or final_metadata.st_ino != opened_metadata.st_ino
            or final_metadata.st_size != opened_metadata.st_size
            or final_metadata.st_mtime_ns != opened_metadata.st_mtime_ns
        ):
            raise RuntimeError("opened file changed during content read")
        content = b"".join(chunks)
        if len(content) != opened_metadata.st_size:
            raise RuntimeError("opened file size did not match content read")
        return content
    except OSError:
        raise RuntimeError("repository file handle could not be validated") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def observed_at() -> str:
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git(repo: pathlib.Path, *args: str, check: bool = True, strip: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", os.fspath(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    return result.stdout.strip() if strip else result.stdout


def _status_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    raw = git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "-z",
        strip=False,
    )
    fields = raw.split("\0")
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(fields) and fields[index]:
        record = fields[index]
        status = record[:2]
        path = record[3:]
        index += 1
        if status[0] in {"R", "C"} and index < len(fields):
            path = fields[index]
            index += 1
        normalized = pathlib.PurePath(path).as_posix()
        gate0_owned = (
            normalized in GATE0_OWNED_FILES or normalized.startswith(GATE0_OWNED_PREFIXES)
        )
        tracked = status != "??"
        safe_hash: str | None = None
        omitted: str | None = None
        candidate = repo / pathlib.PurePosixPath(normalized)
        unsafe_reason = _unsafe_artifact_reason(normalized)
        safe_regular_file = (
            unsafe_reason is None
            and _safe_repo_regular_file(repo, candidate)
        )
        if unsafe_reason is not None:
            omitted = unsafe_reason
        elif not safe_regular_file:
            omitted = "unsafe_file_topology_not_read"
        elif gate0_owned:
            safe_hash = digest_bytes(_read_repo_regular_bytes(repo, candidate))
        elif normalized == ".nobus-quality/cases.ndjson":
            omitted = "not_needed"
        elif normalized.startswith(("docs/", "tests/")):
            safe_hash = digest_bytes(_read_repo_regular_bytes(repo, candidate))
        elif not tracked:
            omitted = "not_needed"
        entries.append(
            {
                "path": normalized,
                "status": status,
                "tracked": tracked,
                "safe_content_sha256": safe_hash,
                "content_omitted_reason": omitted,
                "owner": "gate0" if gate0_owned else "preexisting",
            }
        )
    return sorted(entries, key=lambda item: item["path"])


def collect_repo(repo: pathlib.Path, live: pathlib.Path) -> dict[str, Any]:
    head = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    dirty_entries = _status_entries(repo)

    def ancestor(left: str, right: str) -> bool:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), "merge-base", "--is-ancestor", left, right],
            check=False,
            capture_output=True,
        )
        if result.returncode not in {0, 1}:
            raise RuntimeError("git ancestry check failed")
        return result.returncode == 0

    design_base = "9d816b35d3f419b42e24ad09ae6aadc92c33db43"
    feature = "b69e84687cdce439c42f1bc53e4fe7654e4deaf9"
    return {
        "observed_at": observed_at(),
        "repository": {
            "head_commit": head,
            "branch": branch,
            "dirty_entries": dirty_entries,
        },
        "runtime_release": {
            "head_commit": head,
            "branch": branch,
            "dirty_entries": dirty_entries,
            "design_base_is_ancestor": ancestor(design_base, head),
            "feature_commit_is_ancestor": ancestor(feature, head),
            "repo_is_descendant_of_runtime_release": True,
            "repo_runtime_merge_base": head,
        },
    }


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _safe_status_counts(
    connection: sqlite3.Connection, table: str, columns: set[str]
) -> dict[str, int] | None:
    state_column = next(
        (name for name in ("lifecycle_state", "status", "state") if name in columns),
        None,
    )
    if state_column is None:
        return None
    permitted = {
        "PENDING",
        "ADMITTED",
        "QUEUED",
        "CLAIMED",
        "LEASED",
        "ACKED",
        "RUNNING",
        "IN_PROGRESS",
        "EXECUTING",
        "RECONCILING",
        "WAITING_HUMAN",
        "FAILED",
        "DEAD_LETTER",
        "PROVIDER_UNKNOWN",
        "DELIVERY_PENDING",
        "DELIVERING",
        "DELIVERY_UNKNOWN",
        "SETTLED",
        "COMPLETED",
        "CANCELLED",
        "REJECTED",
    }
    rows = connection.execute(
        f"SELECT upper({_quoted(state_column)}), count(*) "
        f"FROM {_quoted(table)} GROUP BY upper({_quoted(state_column)})"
    )
    result: dict[str, int] = {}
    for value, count in rows:
        key = str(value)
        result[key if key in permitted else "OTHER"] = (
            result.get(key if key in permitted else "OTHER", 0) + int(count)
        )
    return dict(sorted(result.items()))


def _sqlite_files_marker(
    database_path: pathlib.Path,
) -> tuple[tuple[str, bool, int, int], ...]:
    """Return metadata-only markers that diagnose concurrent file activity."""

    markers: list[tuple[str, bool, int, int]] = []
    for suffix in ("", "-wal", "-shm"):
        candidate = pathlib.Path(f"{database_path}{suffix}")
        if candidate.exists():
            stat = candidate.stat()
            markers.append((suffix or "main", True, stat.st_size, stat.st_mtime_ns))
        else:
            markers.append((suffix or "main", False, 0, 0))
    return tuple(markers)


def _snapshot_evidence(
    data_version_before: int,
    data_version_after: int,
    files_before: tuple[tuple[str, bool, int, int], ...],
    files_after: tuple[tuple[str, bool, int, int], ...],
) -> dict[str, Any]:
    """Describe one SQLite read transaction without rejecting WAL churn."""

    data_version_stable = data_version_before == data_version_after
    file_markers_stable = files_before == files_after
    return {
        "mode": "sqlite_read_transaction",
        "wal_aware": True,
        "data_version_stable": data_version_stable,
        "file_markers_stable": file_markers_stable,
        "concurrent_file_activity_observed": not file_markers_stable,
        "consistent": data_version_stable,
    }


def collect_databases(runtime_root: pathlib.Path) -> dict[str, Any]:
    source_path = runtime_root.parent / "src/application/runtime_maintenance.py"
    source_tree = ast.parse(source_path.read_text(encoding="utf-8"), source_path.name)
    expected_schema_digests = None
    for node in source_tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "EXPECTED_SCHEMA_DIGESTS"
        ):
            expected_schema_digests = ast.literal_eval(node.value)
            break
    if not isinstance(expected_schema_digests, dict):
        raise RuntimeError("source schema digest registry is missing or non-literal")

    migration_source_ref = "src/application/durable_telegram_state.py"
    migration_source_path = runtime_root.parent / migration_source_ref
    migration_source_bytes = migration_source_path.read_bytes()
    migration_source_tree = ast.parse(
        migration_source_bytes.decode("utf-8"), migration_source_path.name
    )
    migration_sql = {
        value
        for node in ast.walk(migration_source_tree)
        if isinstance(node, ast.Constant)
        and isinstance((value := node.value), str)
        and re.search(r"\bALTER\s+TABLE\b", value, re.IGNORECASE)
    }
    telegram_legacy_migration_id = (
        "unrecorded_source_migration:telegram_jobs_legacy_to_current"
    )
    telegram_legacy_migration_present = any(
        "telegram_jobs" in sql and "telegram_jobs_legacy" in sql
        for sql in migration_sql
    )
    if not telegram_legacy_migration_present:
        raise RuntimeError("expected in-code Telegram legacy migration was not detected")
    source_migration_evidence = {
        "migration_id": telegram_legacy_migration_id,
        "source_ref": migration_source_ref,
        "source_sha256": digest_bytes(migration_source_bytes),
        "historical_application_recorded": False,
    }

    databases: list[dict[str, Any]] = []
    role_by_name = {
        "task-runtime.sqlite3": "core",
        "telegram-state.sqlite3": "telegram_state",
        "telegram-checkpoint.sqlite3": "checkpoint",
        "business-notes.sqlite3": "business_notes",
    }
    for database_path in sorted(runtime_root.glob("*.sqlite3")):
        files_before = _sqlite_files_marker(database_path)
        uri = f"file:{database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            # This first read establishes the WAL snapshot. Physical WAL/main
            # marker churn after it does not change the transaction's view.
            data_version_before = int(
                connection.execute("PRAGMA data_version").fetchone()[0]
            )
            quick = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
            foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
            schema_rows = list(
                connection.execute(
                    "SELECT type, name, coalesce(sql, '') FROM sqlite_master "
                    "WHERE type IN ('table','index','trigger','view') "
                    "AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY type, name"
                )
            )
            schema_projection = [
                {"type": row[0], "name": row[1], "sql": row[2]} for row in schema_rows
            ]
            source_schema_digests = {
                f"{kind}:{name}": hashlib.sha256(
                    re.sub(r"\s+", " ", str(sql or "").strip())
                    .casefold()
                    .encode()
                ).hexdigest()
                for kind, name, sql in schema_rows
            }
            expected_for_database = expected_schema_digests.get(database_path.name)
            source_schema_match = source_schema_digests == expected_for_database

            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            table_inventory: list[dict[str, Any]] = []
            safe_state_aggregates: dict[str, dict[str, int]] = {}
            migration_tables = [
                table
                for table in tables
                if any(
                    marker in table.casefold()
                    for marker in ("migration", "alembic", "schema_version")
                )
            ]
            for table in tables:
                columns = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({_quoted(table)})")
                }
                count = int(
                    connection.execute(
                        f"SELECT count(*) FROM {_quoted(table)}"
                    ).fetchone()[0]
                )
                table_inventory.append(
                    {
                        "table": table,
                        "columns": sorted(columns),
                        "rows": count,
                        "safe_status_counts": _safe_status_counts(
                            connection, table, columns
                        ),
                    }
                )
                if table == "task_snapshots" and "projection_json" in columns:
                    rows = connection.execute(
                        "SELECT upper(json_extract(projection_json, '$.status')), count(*) "
                        "FROM task_snapshots "
                        "GROUP BY upper(json_extract(projection_json, '$.status'))"
                    )
                    aggregate: dict[str, int] = {}
                    permitted_task_states = {
                        "PENDING",
                        "RUNNING",
                        "COMPLETED",
                        "FAILED",
                        "CANCELLED",
                    }
                    for value, aggregate_count in rows:
                        key = str(value)
                        safe_key = key if key in permitted_task_states else "OTHER"
                        aggregate[safe_key] = (
                            aggregate.get(safe_key, 0) + int(aggregate_count)
                        )
                    safe_state_aggregates["task_snapshots"] = dict(
                        sorted(aggregate.items())
                    )
            source_migrations = (
                [source_migration_evidence]
                if database_path.name == "telegram-state.sqlite3"
                else []
            )
            is_telegram = database_path.name == "telegram-state.sqlite3"
            schema_digest = digest_bytes(canonical_bytes(schema_projection))
            data_version_after = int(
                connection.execute("PRAGMA data_version").fetchone()[0]
            )
            stat = database_path.stat()
            files_after = _sqlite_files_marker(database_path)
            snapshot = _snapshot_evidence(
                data_version_before,
                data_version_after,
                files_before,
                files_after,
            )
            snapshot_consistent = bool(snapshot["consistent"])
            databases.append(
                {
                    "database_role": role_by_name.get(database_path.name, "legacy"),
                    "database_ref": f"runtime-db:{role_by_name.get(database_path.name, 'legacy')}",
                    "source_profile": "scheduler_bound_canonical_runtime_directory",
                    "runtime_binding_status": "verified",
                    "runtime_binding_reason": "SCHEDULER_RUNNER_CONSTANTS_BIND_CANONICAL_RUNTIME_ROOT",
                    "source_schema_match": source_schema_match,
                    "expected_schema_object_count": len(expected_for_database or {}),
                    "migration_inventory": {
                        "applied": [],
                        "pending": [],
                        "unknown": [],
                    },
                    "source_migrations": source_migrations,
                    "migration_lineage_status": (
                        "genesis_baseline_verified"
                        if is_telegram
                        and source_schema_match
                        and not migration_tables
                        and snapshot_consistent
                        else
                        "verified_absent"
                        if source_schema_match
                        and not migration_tables
                        and snapshot_consistent
                        else "contradictory"
                    ),
                    "genesis_baseline": (
                        {
                            "genesis_id": TELEGRAM_GENESIS_ID,
                            "authority_ref": GATE0_CLOSURE_AUTHORITY,
                            "schema_digest": schema_digest,
                            "historical_legacy_migration_proven": False,
                            "durable_ledger_deferred_to_gate": 2,
                            "production_database_mutated": False,
                        }
                        if (
                            is_telegram
                            and source_schema_match
                            and not migration_tables
                            and snapshot_consistent
                        )
                        else None
                    ),
                    "engine": "sqlite",
                    "size_bytes": stat.st_size,
                    "modified_at": dt.datetime.fromtimestamp(
                        stat.st_mtime, UTC
                    ).isoformat().replace("+00:00", "Z"),
                    "journal_mode": str(
                        connection.execute("PRAGMA journal_mode").fetchone()[0]
                    ).lower(),
                    "user_version": int(
                        connection.execute("PRAGMA user_version").fetchone()[0]
                    ),
                    "application_id": int(
                        connection.execute("PRAGMA application_id").fetchone()[0]
                    ),
                    "schema_digest": schema_digest,
                    "snapshot": snapshot,
                    "integrity": {
                        "quick_check": "ok" if quick == ["ok"] else "failed",
                        "foreign_key_check": "ok" if not foreign_keys else "failed",
                    },
                    "safe_state_aggregates": safe_state_aggregates,
                    "tables": table_inventory,
                    "content_exported": False,
                }
            )
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()
    return {"observed_at": observed_at(), "databases": databases}


def _dependency_projection(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item["metadata"]
    expression = metadata.get("license_expression")
    classifiers = metadata.get("classifier") or []
    classifier = next((value for value in classifiers if str(value).startswith("License ::")), None)
    license_id = expression if isinstance(expression, str) and len(expression) <= 128 else classifier
    return {
        "name": str(metadata["name"]),
        "version": str(metadata["version"]),
        "license": str(license_id) if license_id else "UNDECLARED",
        "direct_url_present": item.get("direct_url") is not None,
        "editable": bool((item.get("direct_url") or {}).get("dir_info", {}).get("editable", False)),
        "requested": bool(item.get("requested", False)),
    }


def collect_dependencies() -> dict[str, Any]:
    pip_executable = pathlib.Path(".venv/Scripts/pip.exe")
    completed = subprocess.run(
        [os.fspath(pip_executable), "inspect", "--local"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={"PYTHONUTF8": "1"},
    )
    report = json.loads(completed.stdout)
    packages = sorted(
        (_dependency_projection(item) for item in report["installed"]),
        key=lambda item: item["name"].casefold(),
    )
    installed_names = {item["name"].casefold() for item in packages}
    return {
        "observed_at": observed_at(),
        "os": {
            "family": "windows" if os.name == "nt" else "linux",
            "version": platform.version(),
            "architecture": platform.machine(),
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable_digest": digest_bytes(pathlib.Path(".venv/Scripts/python.exe").read_bytes()),
        },
        "pip": {
            "version": importlib.metadata.version("pip"),
            "inspect_version": str(report.get("version", "unknown")),
            "raw_report_digest": digest_bytes(completed.stdout.encode("utf-8")),
        },
        "packages": packages,
        "required_tools": {
            "pydantic": importlib.metadata.version("pydantic"),
            "pytest": importlib.metadata.version("pytest"),
            "jsonschema": next(
                (
                    item["version"]
                    for item in packages
                    if item["name"].casefold() == "jsonschema"
                ),
                None,
            ),
            "hypothesis": next(
                (
                    item["version"]
                    for item in packages
                    if item["name"].casefold() == "hypothesis"
                ),
                None,
            ),
            "import_linter": next(
                (
                    item["version"]
                    for item in packages
                    if item["name"].casefold() == "import-linter"
                ),
                None,
            ),
        },
        "installed_count": len(packages),
        "pydantic_present": "pydantic" in installed_names,
        "pytest_present": "pytest" in installed_names,
    }


def collect_owner_root(owner_root: pathlib.Path) -> dict[str, Any]:
    counts = {
        "directories": 0,
        "files": 0,
        "reparse_points": 0,
        "hidden": 0,
        "protected_entries_excluded": 0,
    }
    protected = {"VPN данные", "Системные"}
    for entry in owner_root.iterdir():
        if entry.name in protected:
            counts["protected_entries_excluded"] += 1
            continue
        info = entry.lstat()
        if entry.is_symlink():
            counts["reparse_points"] += 1
        elif entry.is_dir():
            counts["directories"] += 1
        elif entry.is_file():
            counts["files"] += 1
        if entry.name.startswith("."):
            counts["hidden"] += 1
        del info
    root_stat = owner_root.stat()
    return {
        "observed_at": observed_at(),
        "mode": "metadata_only_top_level",
        "descendants_read": False,
        "names_persisted": False,
        "root_identity_digest": digest_bytes(str(root_stat.st_dev).encode("ascii")),
        "counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("section", choices=("repo", "databases", "dependencies", "owner"))
    parser.add_argument("--repo", type=pathlib.Path)
    parser.add_argument("--live", type=pathlib.Path)
    parser.add_argument("--runtime-root", type=pathlib.Path)
    parser.add_argument("--owner-root", type=pathlib.Path)
    args = parser.parse_args()
    if args.section == "repo":
        result = collect_repo(args.repo.resolve(), args.live.resolve())
    elif args.section == "databases":
        result = collect_databases(args.runtime_root.resolve())
    elif args.section == "dependencies":
        result = collect_dependencies()
    else:
        result = collect_owner_root(args.owner_root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
