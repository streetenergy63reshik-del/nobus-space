"""Revalidate persisted independent review origin before Gate 0 seal."""

from __future__ import annotations

import os
import pathlib
from typing import Any

from collect_gate0_snapshot import _read_repo_regular_bytes
from gate0_review_submission import (
    CHECK_KEYS,
    DIGEST_PATTERN,
    REVIEW_CHECKS,
    REVIEWER_ID_PATTERN,
    REVIEWER_KEYS,
    REVIEWER_TYPES,
    SUBMISSION_KEYS,
    _decode_review_submission,
    _evidence_refs,
    _sha256,
)

RECEIPT_KEYS = SUBMISSION_KEYS | {"submission_ref", "submission_sha256"}
SUBMISSION_ROOT = pathlib.PurePosixPath(
    "docs/gates/gate-00-product-contract-baseline/verification/submissions"
)

def review_receipts_origin_verified(
    root: pathlib.Path,
    receipts: dict[str, dict[str, Any]],
) -> bool:
    if set(receipts) != {"l1", "l2", "l3"}:
        return False
    reviewer_ids: list[str] = []
    try:
        for level, receipt in receipts.items():
            if not isinstance(receipt, dict):
                return False
            submission_ref = (SUBMISSION_ROOT / f"{level}.json").as_posix()
            raw = _read_repo_regular_bytes(
                pathlib.Path(os.path.abspath(root)),
                pathlib.Path(os.path.abspath(root)) / submission_ref,
            )
            submission = _decode_review_submission(raw)
            if not isinstance(submission, dict) or set(submission) != SUBMISSION_KEYS:
                return False
            expected_receipt = {
                **submission,
                "schema": "nobus.gate0.verification_receipt.v1",
                "submission_ref": submission_ref,
                "submission_sha256": _sha256(raw),
            }
            reviewer = receipt.get("reviewer")
            checks = receipt.get("checks")
            if (
                set(receipt) != RECEIPT_KEYS
                or receipt != expected_receipt
                or receipt.get("schema") != "nobus.gate0.verification_receipt.v1"
                or receipt.get("level") != level
                or not isinstance(receipt.get("submission_sha256"), str)
                or not DIGEST_PATTERN.fullmatch(receipt["submission_sha256"])
                or not isinstance(reviewer, dict)
                or set(reviewer) != REVIEWER_KEYS
                or reviewer.get("reviewer_type") != REVIEWER_TYPES[level]
                or reviewer.get("independence_attested") is not True
                or reviewer.get("executor_separation_attested") is not True
                or not isinstance(reviewer.get("reviewer_id"), str)
                or not REVIEWER_ID_PATTERN.fullmatch(reviewer["reviewer_id"])
                or not isinstance(reviewer.get("method"), str)
                or len(reviewer["method"].strip()) < 12
                or not isinstance(checks, list)
                or len(checks) != len(REVIEW_CHECKS[level])
            ):
                return False
            _evidence_refs(root, reviewer.get("evidence_refs"))
            for check, expected_id in zip(
                checks,
                REVIEW_CHECKS[level],
                strict=True,
            ):
                if (
                    not isinstance(check, dict)
                    or set(check) != CHECK_KEYS
                    or check.get("id") != expected_id
                    or check.get("status") != "pass"
                ):
                    return False
                _evidence_refs(root, check.get("evidence_refs"))
            reviewer_ids.append(reviewer["reviewer_id"])
    except RuntimeError:
        return False
    return len(set(reviewer_ids)) == 3
