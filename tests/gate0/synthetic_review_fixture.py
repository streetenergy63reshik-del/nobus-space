"""Synthetic external review submissions for isolated Gate 0 tests only."""

from __future__ import annotations

import json
import pathlib

from gate0_review_submission import REVIEW_CHECKS, REVIEWER_TYPES


def write_synthetic_review_submission(
    candidate: pathlib.Path,
    *,
    level: str,
    observed_at: str,
) -> pathlib.Path:
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    template = json.loads(
        (gate / "verification" / f"{level}.json").read_text(encoding="utf-8")
    )
    evidence_refs = ["tests/gate0/test_gate0_precapture.py"]
    submission = {
        "schema": "nobus.gate0.independent_review_submission.v1",
        "level": level,
        "stage": "post_capture",
        "verdict": "pass" if level == "l1" else "accept",
        "observed_at": observed_at,
        "candidate_core_digest": template["candidate_core_digest"],
        "frozen_tree_digest": template["frozen_tree_digest"],
        "capture_digest": template["capture_digest"],
        "review_tree_digest": template["review_tree_digest"],
        "reviewer": {
            "reviewer_id": f"synthetic-{level}-reviewer",
            "reviewer_type": REVIEWER_TYPES[level],
            "method": "independent synthetic reproduction for lifecycle test",
            "independence_attested": True,
            "executor_separation_attested": True,
            "evidence_refs": evidence_refs,
        },
        "checks": [
            {"id": check, "status": "pass", "evidence_refs": evidence_refs}
            for check in REVIEW_CHECKS[level]
        ],
        "findings": [],
        "blocking_criteria": [],
        "release_blockers": [],
        "hidden_reasoning_persisted": False,
    }
    path = candidate / "tmp" / f"synthetic-{level}-review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(submission, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
