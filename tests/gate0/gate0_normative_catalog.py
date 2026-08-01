"""Closed, digest-bound normative input catalog for Gate 0."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from typing import Any

from collect_gate0_snapshot import _read_repo_regular_bytes


CATALOG_REL = pathlib.PurePosixPath(
    "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json"
)
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CATALOG_KEYS = {
    "agent_roles",
    "contract_version",
    "corpus_version",
    "development_requirements",
    "domains",
    "gate_ids",
    "required_sources",
    "schema",
}
DEVELOPMENT_REQUIREMENT_KEYS = {
    "minimum_cases",
    "required_error_codes",
    "required_modalities",
}
EXACT_SEMANTIC_SETS = {
    "domains": [
        "notes", "calendar", "tasks", "documents", "research",
        "development", "general",
    ],
    "gate_ids": ["0", "1", "2", "2a", "3", "4", "5", "6", "7", "8"],
    "agent_roles": [
        "general_orchestrator_worker",
        "google_workspace_specialist",
        "research_analytics_specialist",
        "content_studio_specialist",
        "development_specialist",
        "verification_specialist",
    ],
}
SOURCE_KEYS = {"path", "sha256"}


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _strict_json(raw: bytes) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"normative catalog duplicate key: {key}")
            result[key] = value
        return result

    def no_non_finite(value: str) -> None:
        raise ValueError(f"normative catalog non-finite value: {value}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=no_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("normative catalog is not valid UTF-8 JSON") from error

def _closed_string_list(value: Any, *, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"normative catalog {field} must be a non-empty unique string list")
    return value


def load_normative_catalog(root: pathlib.Path) -> dict[str, Any]:
    root = pathlib.Path(os.path.abspath(root))
    path = root / CATALOG_REL
    raw = _read_repo_regular_bytes(root, path)
    catalog = _strict_json(raw)
    if not isinstance(catalog, dict) or set(catalog) != CATALOG_KEYS:
        raise ValueError("normative catalog shape is not exact")
    if catalog.get("schema") != "nobus.gate0.normative_catalog.v1":
        raise ValueError("normative catalog schema is not supported")
    if catalog.get("contract_version") != "2.0.0" or catalog.get(
        "corpus_version"
    ) != "2.0.0":
        raise ValueError("normative catalog versions are not exact")
    for field, expected in EXACT_SEMANTIC_SETS.items():
        actual = _closed_string_list(catalog.get(field), field=field)
        if actual != expected:
            raise ValueError(
                f"normative catalog {field} semantic set is not exact"
            )
    requirements = catalog.get("development_requirements")
    if (
        not isinstance(requirements, dict)
        or set(requirements) != DEVELOPMENT_REQUIREMENT_KEYS
        or type(requirements.get("minimum_cases")) is not int
        or requirements["minimum_cases"] < 8
    ):
        raise ValueError("normative catalog development requirements are not exact")
    _closed_string_list(
        requirements.get("required_error_codes"),
        field="development_requirements.required_error_codes",
    )
    _closed_string_list(
        requirements.get("required_modalities"),
        field="development_requirements.required_modalities",
    )
    sources = catalog.get("required_sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("normative catalog required_sources must be non-empty")
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
            raise ValueError("normative catalog source shape is not exact")
        relative = source.get("path")
        expected = source.get("sha256")
        if not isinstance(relative, str) or relative in seen:
            raise ValueError("normative catalog source path is invalid or duplicated")
        pure = pathlib.PurePosixPath(relative)
        if (
            pure.is_absolute()
            or not pure.parts
            or pure.parts[0] != "docs"
            or any(part in {"", ".", ".."} for part in pure.parts)
            or "\\" in relative
        ):
            raise ValueError("normative catalog source path escaped docs")
        if not isinstance(expected, str) or not DIGEST_PATTERN.fullmatch(expected):
            raise ValueError("normative catalog source digest is invalid")
        seen.add(relative)
    return {**catalog, "catalog_sha256": _sha256(raw)}


def source_document_inventory(root: pathlib.Path) -> list[dict[str, str]]:
    root = pathlib.Path(os.path.abspath(root))
    catalog = load_normative_catalog(root)
    records: list[dict[str, str]] = []
    for source in catalog["required_sources"]:
        relative = source["path"]
        path = root / pathlib.PurePosixPath(relative)
        try:
            os.lstat(path)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"required Gate 0 source document missing: {relative}"
            ) from error
        try:
            raw = _read_repo_regular_bytes(root, path)
        except RuntimeError as error:
            raise RuntimeError(
                f"required Gate 0 source topology is unsafe: {relative}"
            ) from error
        actual = _sha256(raw)
        if actual != source["sha256"]:
            raise RuntimeError(
                f"required Gate 0 source digest mismatch: {relative}"
            )
        records.append(
            {"path": relative, "sha256": actual, "status": "VERIFIED"}
        )
    return records
