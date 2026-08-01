"""Single source of truth for Gate 0 core digest artifacts."""

from __future__ import annotations

import pathlib


CORE_ARTIFACT_RELATIVES = (
    "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json",
    "docs/gates/gate-00-product-contract-baseline/product/product-contract.json",
    "docs/gates/gate-00-product-contract-baseline/corpus/requests.v1.jsonl",
    "docs/gates/gate-00-product-contract-baseline/corpus/coverage.json",
    "docs/gates/gate-00-product-contract-baseline/corpus/corpus-manifest.json",
    "docs/gates/gate-00-product-contract-baseline/evidence/baseline-evidence.json",
)


def core_artifact_paths(root: pathlib.Path) -> list[pathlib.Path]:
    return [root / pathlib.PurePosixPath(relative) for relative in CORE_ARTIFACT_RELATIVES]
