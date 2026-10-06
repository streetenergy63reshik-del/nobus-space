"""Read-only snapshot of the installed Codex Desktop project and task index.

The Desktop IPC does not expose list operations in the pinned protocol.  This
adapter reads Desktop's own local index afresh for each menu transition; it is
never used as authority to dispatch a turn.  The bridge still proves the exact
thread owner and cwd through Desktop IPC before mutation.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_THREAD_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


class DesktopCatalogError(RuntimeError):
    """Desktop's private list index is unavailable or incompatible."""


@dataclass(frozen=True, slots=True)
class CatalogProject:
    project_id: str
    name: str
    cwd: Path


@dataclass(frozen=True, slots=True)
class CatalogTask:
    thread_id: str
    title: str
    project_id: str
    updated_at_ms: int


class CodexDesktopCatalog:
    """Pin the observed local-index schema and fail closed on a changed shape."""

    def __init__(self, codex_home: Path, *, owner_root: Path) -> None:
        self._home = Path(codex_home).resolve(strict=True)
        self._owner_root = Path(owner_root).resolve(strict=True)

    def projects(self) -> tuple[CatalogProject, ...]:
        state = self._read_state()
        raw_projects = state.get("local-projects")
        order = state.get("project-order")
        if not isinstance(raw_projects, dict) or not isinstance(order, list):
            raise DesktopCatalogError("desktop-catalog-schema")
        if len(raw_projects) > 128 or len(order) > 128:
            raise DesktopCatalogError("desktop-catalog-limit")
        projects: list[CatalogProject] = []
        seen_roots: set[Path] = set()
        seen_names: set[str] = set()
        for project_id in order:
            if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
                raise DesktopCatalogError("desktop-catalog-schema")
            # ChatGPT cloud projects cannot be resumed through this local Desktop owner.
            if project_id.startswith("g-p-"):
                continue
            item = raw_projects.get(project_id)
            if not isinstance(item, dict) or item.get("id") != project_id:
                raise DesktopCatalogError("desktop-catalog-schema")
            name, roots = item.get("name"), item.get("rootPaths")
            if (
                not isinstance(name, str) or not name.strip() or len(name) > 256
                or not isinstance(roots, list) or len(roots) != 1
                or not isinstance(roots[0], str) or "\x00" in roots[0]
            ):
                raise DesktopCatalogError("desktop-catalog-schema")
            root = Path(roots[0])
            if not root.is_absolute() or not root.is_dir():
                raise DesktopCatalogError("desktop-catalog-root")
            current = root
            while current != self._owner_root and current != current.parent:
                if current.is_symlink() or current.is_junction():
                    raise DesktopCatalogError("desktop-catalog-reparse")
                current = current.parent
            resolved = root.resolve(strict=True)
            if not resolved.is_relative_to(self._owner_root):
                raise DesktopCatalogError("desktop-catalog-root")
            folded = name.strip().casefold()
            if resolved in seen_roots or folded in seen_names:
                raise DesktopCatalogError("desktop-catalog-ambiguous")
            projects.append(CatalogProject(project_id, name.strip(), resolved))
            seen_roots.add(resolved)
            seen_names.add(folded)
        if not projects:
            raise DesktopCatalogError("desktop-catalog-empty")
        return tuple(projects)

    def tasks(self, project_id: str) -> tuple[CatalogTask, ...]:
        if _PROJECT_ID.fullmatch(project_id) is None:
            raise DesktopCatalogError("desktop-catalog-project")
        projects = {item.project_id: item for item in self.projects()}
        if project_id not in projects:
            raise DesktopCatalogError("desktop-catalog-project")
        state = self._read_state()
        assignments = state.get("thread-project-assignments")
        host_ids = state.get("thread-project-membership-host-ids", {})
        if not isinstance(assignments, dict) or len(assignments) > 100_000:
            raise DesktopCatalogError("desktop-catalog-schema")
        if not isinstance(host_ids, dict):
            raise DesktopCatalogError("desktop-catalog-schema")
        ids = [
            thread_id for thread_id, binding in assignments.items()
            if isinstance(binding, dict)
            and binding.get("projectKind") == "local"
            and binding.get("projectId") == project_id
            and isinstance(thread_id, str)
            and _THREAD_ID.fullmatch(thread_id) is not None
            and host_ids.get(thread_id, "local") == "local"
        ]
        if not ids:
            return ()
        try:
            database = self._home / "state_5.sqlite"
            if database.is_symlink() or not database.is_file():
                raise DesktopCatalogError("desktop-catalog-tasks-unavailable")
            uri = database.as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2) as connection:
                # Bounded chunks avoid SQLite's parameter limit and never read content.
                rows = []
                for start in range(0, len(ids), 500):
                    chunk = ids[start:start + 500]
                    rows.extend(connection.execute(
                        "SELECT id,name,recency_at_ms,thread_source,agent_path "
                        "FROM threads WHERE archived=0 AND id IN ("
                        + ",".join("?" for _ in chunk) + ")", chunk,
                    ))
        except (OSError, sqlite3.Error, ValueError):
            raise DesktopCatalogError("desktop-catalog-tasks-unavailable") from None
        found: list[CatalogTask] = []
        for thread_id, name, updated, source, agent_path in rows:
            if source not in {"user", "agent_created_thread"} or agent_path is not None:
                continue
            display = name if isinstance(name, str) and name.strip() else "Задача " + thread_id[:8]
            if type(updated) is not int:
                updated = 0
            found.append(CatalogTask(thread_id, display.strip()[:256], project_id, updated))
        found.sort(key=lambda item: (-item.updated_at_ms, item.thread_id))
        return tuple(found)

    def _read_state(self) -> dict[str, Any]:
        path = self._home / ".codex-global-state.json"
        try:
            if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
                raise DesktopCatalogError("desktop-catalog-state-unavailable")
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            raise DesktopCatalogError("desktop-catalog-state-unavailable") from None
        if not isinstance(state, dict):
            raise DesktopCatalogError("desktop-catalog-schema")
        return state
