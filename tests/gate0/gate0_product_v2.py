"""Deterministic reconciliation of an existing Gate 0 product to v2 inputs."""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, get_args

from gate0_normative_catalog import (
    load_normative_catalog,
    source_document_inventory,
 )
from normative_models import Action, EffectKind, SourceKind


EXACT_VOCABULARY = {
    "actions": list(get_args(Action)),
    "source_kinds": list(get_args(SourceKind)),
    "effect_kinds": list(get_args(EffectKind)),
}


def _digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def reconcile_product_v2(
    root: pathlib.Path,
    product: dict[str, Any],
) -> dict[str, Any]:
    catalog = load_normative_catalog(root)
    sources = source_document_inventory(root)
    product["contract_version"] = catalog["contract_version"]
    product["normative_input"] = {
        "catalog_ref": (
            "docs/gates/gate-00-product-contract-baseline/product/"
            "normative-catalog.json"
        ),
        "catalog_sha256": catalog["catalog_sha256"],
        "source_count": len(sources),
        "source_set_sha256": _digest(sources),
    }
    vocabularies = product["vocabularies"]
    vocabularies["domains"] = catalog["domains"]
    vocabularies["agent_roles"] = catalog["agent_roles"]
    for field, values in EXACT_VOCABULARY.items():
        vocabularies[field] = values.copy()
    if not any(item["id"] == "PC-13" for item in product["invariants"]):
        product["invariants"].append(
            {
                "id": "PC-13",
                "statement": (
                    "A model or worker cannot expand authority or deploy itself."
                ),
                "owner": "gate2a",
                "fitness_ref": "G0-15",
            }
        )
    families = {item["family"]: item for item in product["contract_families"]}
    family_consumers = {
        "baseline": [1, 2, "2a", 3, 4, 5, 6, 7, 8],
        "intent": [2, "2a", 3, 4, 5, 6, 7, 8],
        "document": ["2a", 3, 5, 6, 7, 8],
    }
    for family, consumers in family_consumers.items():
        families[family]["consumer_gates"] = consumers
    gate2a = {
        "family": "miniapp_development_control",
        "owner_gate": "2a",
        "contracts": [
            "AgentProfile",
            "AgentDispatch",
            "WorkerResultEnvelope",
            "ControlTaskView",
            "ControlEventView",
            "ApprovalChallenge",
            "CodeTaskContract",
            "CodePlan",
            "PatchCandidate",
            "CandidateCommitReceipt",
        ],
        "status": "target",
        "source_ref": (
            "docs/gates/gate-02a-miniapp-development-control/ARCHITECTURE.md"
        ),
        "consumer_gates": [3, 4, 5, 6, 7, 8],
    }
    if "miniapp_development_control" in families:
        families["miniapp_development_control"].update(gate2a)
    else:
        product["contract_families"].insert(3, gate2a)
    return product
