"""Validate independent Gate 0 review submissions without awarding verdicts."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from typing import Any

from collect_gate0_snapshot import _read_repo_regular_bytes

REVIEW_CHECKS = {
    "l1": [
        "bounded_projection",
        "exact_manifest_readback",
        "capture_freshness_and_binding",
        "acceptance_recalculation",
    ],
    "l2": [
        "exact_core_recalculation",
        "contract_and_corpus_consistency",
        "evidence_layer_separation",
        "manifest_and_clean_checkout_binding",
        "gate_1_2a_8_handoff_scope",
    ],
    "l3": [
        "stale_and_false_ready_attack",
        "secret_path_and_real_payload_attack",
        "tenant_unknown_field_and_manifest_attack",
        "eol_clean_checkout_and_tool_lockin_attack",
        "migration_genesis_scope_attack",
        "gate_1_2a_8_drift_attack",
        "independent_review_origin_attack",
    ],
}
REVIEWER_TYPES = {
    "l1": "deterministic_reviewer",
    "l2": "independent_reviewer",
    "l3": "adversarial_reviewer",
}
SUBMISSION_KEYS = {
    "blocking_criteria",
    "candidate_core_digest",
    "capture_digest",
    "checks",
    "findings",
    "frozen_tree_digest",
    "hidden_reasoning_persisted",
    "level",
    "observed_at",
    "release_blockers",
    "review_tree_digest",
    "reviewer",
    "schema",
    "stage",
    "verdict",
}
REVIEWER_KEYS = {
    "evidence_refs",
    "executor_separation_attested",
    "independence_attested",
    "method",
    "reviewer_id",
    "reviewer_type",
}
CHECK_KEYS = {"evidence_refs", "id", "status"}
REVIEWER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,63}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _evidence_refs(root: pathlib.Path, value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RuntimeError("independent review evidence refs are required")
    seen: set[str] = set()
    for relative in value:
        if not isinstance(relative, str) or relative in seen:
            raise RuntimeError("independent review evidence refs are not exact")
        pure = pathlib.PurePosixPath(relative)
        if (
            pure.is_absolute()
            or not pure.parts
            or pure.parts[0] not in {"docs", "tests"}
            or any(part in {"", ".", ".."} for part in pure.parts)
            or "\\" in relative
        ):
            raise RuntimeError("independent review evidence ref escaped repository")
        path = root / pure
        try:
            _read_repo_regular_bytes(root, path)
        except (OSError, RuntimeError) as error:
            raise RuntimeError("independent review evidence ref is unsafe") from error
        seen.add(relative)
    return value

def _decode_review_submission(raw: bytes) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(
                    f"independent review JSON duplicate key: {key}"
                )
            result[key] = value
        return result

    def no_non_finite(value: str) -> None:
        raise RuntimeError(
            f"independent review JSON non-finite value: {value}"
        )

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=no_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "independent review submission is not valid UTF-8 JSON"
        ) from error


def validate_review_submission(
    root: pathlib.Path,
    submission_path: pathlib.Path | None,
    *,
    level: str,
    expected_binding: dict[str, str],
    observed_at: str,
) -> tuple[dict[str, Any], str, bytes]:
    if submission_path is None:
        raise RuntimeError("independent review submission is required")
    root = pathlib.Path(os.path.abspath(root))
    supplied = pathlib.Path(os.path.abspath(submission_path))
    try:
        relative = supplied.relative_to(root)
    except ValueError as error:
        raise RuntimeError("independent review submission escaped repository") from error
    if not relative.parts or relative.parts[0] != "tmp" or supplied.suffix != ".json":
        raise RuntimeError("independent review submission must be an ignored tmp JSON")
    try:
        metadata = os.lstat(supplied)
        if metadata.st_size > 65536:
            raise RuntimeError("independent review submission file is unsafe")
        raw = _read_repo_regular_bytes(root, supplied)
    except (FileNotFoundError, OSError, RuntimeError) as error:
        raise RuntimeError("independent review submission is required") from error
    submission = _decode_review_submission(raw)
    if not isinstance(submission, dict) or set(submission) != SUBMISSION_KEYS:
        raise RuntimeError("independent review submission shape is not exact")
    expected_verdict = "pass" if level == "l1" else "accept"
    if (
        submission.get("schema") != "nobus.gate0.independent_review_submission.v1"
        or submission.get("level") != level
        or submission.get("stage") != "post_capture"
        or submission.get("verdict") != expected_verdict
        or submission.get("observed_at") != observed_at
        or submission.get("hidden_reasoning_persisted") is not False
        or submission.get("findings") != []
        or submission.get("blocking_criteria") != []
        or submission.get("release_blockers") != []
    ):
        raise RuntimeError("independent review submission verdict or stage is not acceptable")
    if any(submission.get(key) != value for key, value in expected_binding.items()):
        raise RuntimeError("independent review submission binding is not exact")
    reviewer = submission.get("reviewer")
    if not isinstance(reviewer, dict) or set(reviewer) != REVIEWER_KEYS:
        raise RuntimeError("independent review identity shape is not exact")
    reviewer_id = reviewer.get("reviewer_id")
    if (
        not isinstance(reviewer_id, str)
        or not REVIEWER_ID_PATTERN.fullmatch(reviewer_id)
        or reviewer.get("reviewer_type") != REVIEWER_TYPES[level]
        or reviewer.get("independence_attested") is not True
        or reviewer.get("executor_separation_attested") is not True
        or not isinstance(reviewer.get("method"), str)
        or len(reviewer["method"].strip()) < 12
    ):
        raise RuntimeError("independent review identity is not acceptable")
    _evidence_refs(root, reviewer.get("evidence_refs"))
    checks = submission.get("checks")
    if not isinstance(checks, list) or len(checks) != len(REVIEW_CHECKS[level]):
        raise RuntimeError("independent review checks are incomplete")
    for check, expected_id in zip(checks, REVIEW_CHECKS[level], strict=True):
        if (
            not isinstance(check, dict)
            or set(check) != CHECK_KEYS
            or check.get("id") != expected_id
            or check.get("status") != "pass"
        ):
            raise RuntimeError("independent review check result is not exact")
        _evidence_refs(root, check.get("evidence_refs"))
    return submission, _sha256(raw), raw
