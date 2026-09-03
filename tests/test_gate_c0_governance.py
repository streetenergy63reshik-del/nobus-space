"""Gate C0 contract, governance, and preservation checks."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE = "f5a9119cc0aa1bcce735a3c608f9751747002694"
PACKAGE = ROOT / "docs/gates/gate-c0-mvp1-truth-contract"
SCHEMA_PATH = PACKAGE / "semantic-contract.schema.json"
REGISTRY_PATH = PACKAGE / "capability-registry.v1.json"
CORPUS_PATH = PACKAGE / "semantic-gold-corpus.v1.json"
HANDOFF_PATH = PACKAGE / "HANDOFF.md"
ADR_PATH = ROOT / "docs/adr/0023-modality-neutral-semantic-admission-and-core-decision.md"
ORDER = [
    "TRUST_VIOLATION",
    "POLICY_PROHIBITED",
    "AMBIGUITY",
    "HETEROGENEOUS_CAPABILITIES",
    "IMPLEMENTATION_STATE",
    "APPROVAL_REQUIRED",
    "EXECUTE_ALLOWED",
]
SEMANTIC_KEYS = {
    "schema_version", "interpretation_state", "primary_goal", "deliverables",
    "constraints", "source_material_refs", "input_role", "source_need",
    "output_kind", "operations", "ambiguities", "clarification_question",
}
CONTEXT_KEYS = {
    "schema_version", "context_ref", "intake_ref", "intake_revision",
    "owner_binding", "tenant_binding", "conversation_binding",
    "reference_validation", "operation_provenance", "reference_checks",
    "predicate_evaluation",
}
CORE_KEYS = {
    "schema_version", "proposal_digest", "admission_context_digest", "decision",
    "decision_stage", "predicate_outcome", "selected_capability",
    "policy_reason_code", "policy_evidence", "user_visible_state",
    "task_contract_allowed", "effect_allowed",
}
FORBIDDEN_MODEL_KEYS = {
    "decision", "capability", "approval_required", "authorized", "approved",
    "permissions", "risk", "route", "adapter", "tenant", "actor", "execute",
}
REFERENCE_STATUSES = {
    "VERIFIED", "WRONG_OWNER", "WRONG_TENANT", "WRONG_CONVERSATION",
    "NOT_IN_CURRENT_INTAKE", "BOUNDARY_MISMATCH", "FORGED_REF", "STALE_REF",
}
MATERIAL_REF = re.compile(
    r"material://(?:intake|artifact|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}"
)
TARGET_REF = re.compile(
    r"(?:material|target)://(?:intake|artifact|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}"
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _cases() -> list[dict]:
    return _json(CORPUS_PATH)["cases"]


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _digest(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_predicate(predicate: dict) -> None:
    assert type(predicate) is dict
    assert set(predicate) == {"kind", "subject_ref", "arguments"}
    assert predicate["kind"] == "material_item_state_exists"
    assert MATERIAL_REF.fullmatch(predicate["subject_ref"])
    assert predicate["arguments"] == {"item_state": "overdue"}


def _validate_proposal(proposal: dict) -> None:
    assert type(proposal) is dict and set(proposal) == SEMANTIC_KEYS
    assert not FORBIDDEN_MODEL_KEYS.intersection(proposal)
    assert proposal["schema_version"] == "1.0.0"
    assert proposal["interpretation_state"] in {"understood", "ambiguous"}
    assert isinstance(proposal["primary_goal"], str) and proposal["primary_goal"]
    assert 1 <= len(proposal["deliverables"]) <= 12
    assert len(proposal["constraints"]) <= 24
    assert len(proposal["source_material_refs"]) <= 12
    assert proposal["input_role"] in {
        "direct_request", "material_transformation", "question", "mixed",
    }
    assert proposal["source_need"] in {
        "none", "provided_material", "external_read", "clarification",
    }
    assert proposal["output_kind"] in {
        "answer", "prompt", "document", "data", "action", "status", "artifact",
        "none",
    }
    assert 1 <= len(proposal["operations"]) <= 24
    assert sum(
        item["role"] == "conditional" for item in proposal["operations"]
    ) <= 1
    for source_ref in proposal["source_material_refs"]:
        assert set(source_ref) == {"ref", "boundary"}
        assert MATERIAL_REF.fullmatch(source_ref["ref"])
        assert source_ref["boundary"] in {
            "full_material", "quoted_fragment", "summary_only",
        }
    for operation in proposal["operations"]:
        assert set(operation) == {
            "operation_kind", "role", "target_ref", "predicate",
        }
        assert operation["operation_kind"] in {
            "respond", "transform_material", "cancel_task",
            "read_public_information", "create_file", "write_calendar_event",
            "disclose_secret", "write_marketplace_campaign",
        }
        assert operation["role"] in {
            "requested", "quoted", "mentioned_only", "negated", "conditional",
        }
        assert (
            operation["target_ref"] is None
            or TARGET_REF.fullmatch(operation["target_ref"])
        )
        if operation["role"] == "conditional":
            _validate_predicate(operation["predicate"])
        else:
            assert operation["predicate"] is None
    if proposal["interpretation_state"] == "understood":
        assert proposal["ambiguities"] == []
        assert proposal["clarification_question"] is None
    else:
        assert proposal["ambiguities"]
        assert isinstance(proposal["clarification_question"], str)
        assert proposal["clarification_question"]


def _validate_context(context: dict, proposal: dict) -> None:
    assert type(context) is dict and set(context) == CONTEXT_KEYS
    assert context["schema_version"] == "1.0.0"
    assert re.fullmatch(
        r"context://(?:intake|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}",
        context["context_ref"],
    )
    assert re.fullmatch(
        r"intake://(?:telegram|miniapp|synthetic)/[a-z0-9][a-z0-9._/-]{0,159}",
        context["intake_ref"],
    )
    assert context["intake_revision"] >= 1
    for key in ("owner_binding", "tenant_binding", "conversation_binding"):
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", context[key])
    assert context["reference_validation"] in REFERENCE_STATUSES
    provenance = context["operation_provenance"]
    assert len(provenance) == len(proposal["operations"])
    assert [item["operation_index"] for item in provenance] == list(
        range(len(proposal["operations"]))
    )
    for item in provenance:
        assert set(item) == {
            "operation_index", "span_ref", "trusted_origin", "authority_scope",
        }
        assert item["trusted_origin"] in {
            "DIRECT_OWNER_COMMAND", "PROVIDED_MATERIAL", "QUOTED_MATERIAL",
            "NESTED_MATERIAL", "MENTIONED_CONTEXT",
        }
        assert item["authority_scope"] in {
            "OWNER_REQUESTED", "OWNER_CONDITIONAL", "INERT",
        }
    checks = context["reference_checks"]
    required_refs = {item["ref"] for item in proposal["source_material_refs"]}
    required_refs.update(
        item["target_ref"] for item in proposal["operations"]
        if item["target_ref"] is not None
    )
    required_refs.update(
        item["predicate"]["subject_ref"] for item in proposal["operations"]
        if item["role"] == "conditional"
    )
    assert required_refs <= {item["ref"] for item in checks}
    for check in checks:
        assert set(check) == {"ref", "usages", "trusted_boundary", "status"}
        assert TARGET_REF.fullmatch(check["ref"])
        assert check["status"] in REFERENCE_STATUSES
        assert set(check["usages"]) <= {
            "SOURCE_MATERIAL", "OPERATION_TARGET", "PREDICATE_SUBJECT",
        }
    if context["reference_validation"] == "VERIFIED":
        assert all(item["status"] == "VERIFIED" for item in checks)
    else:
        assert any(
            item["status"] == context["reference_validation"] for item in checks
        )
    predicate = context["predicate_evaluation"]
    assert set(predicate) == {"outcome", "evaluator", "subject_ref"}
    conditional = [
        item for item in proposal["operations"] if item["role"] == "conditional"
    ]
    if conditional:
        assert predicate["outcome"] in {"TRUE", "FALSE", "UNKNOWN"}
        assert predicate["evaluator"] == "MATERIAL_ITEM_STATE_V1"
        assert predicate["subject_ref"] == conditional[0]["predicate"]["subject_ref"]
        subject_check = next(
            item for item in checks if item["ref"] == predicate["subject_ref"]
        )
        assert "PREDICATE_SUBJECT" in subject_check["usages"]
    else:
        assert predicate == {
            "outcome": "NOT_APPLICABLE", "evaluator": "NONE",
            "subject_ref": None,
        }


def _validate_core(decision: dict) -> None:
    assert type(decision) is dict and set(decision) == CORE_KEYS
    assert decision["schema_version"] == "1.0.0"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", decision["proposal_digest"])
    assert re.fullmatch(
        r"sha256:[0-9a-f]{64}", decision["admission_context_digest"]
    )
    assert decision["decision"] in {
        "EXECUTE", "CLARIFY", "APPROVAL", "UNAVAILABLE", "REFUSE",
    }
    assert decision["decision_stage"] in set(ORDER) | {
        "PREDICATE_FALSE", "PREDICATE_UNKNOWN",
    }
    assert decision["predicate_outcome"] in {
        "NOT_APPLICABLE", "TRUE", "FALSE", "UNKNOWN",
    }
    assert set(decision["user_visible_state"]) == {"state", "message_key"}
    stage = decision["decision_stage"]
    if stage == "TRUST_VIOLATION":
        assert decision["decision"] == "REFUSE"
        assert decision["selected_capability"] is None
    elif stage == "POLICY_PROHIBITED":
        assert decision["decision"] == "REFUSE"
        assert isinstance(decision["selected_capability"], str)
    elif stage == "AMBIGUITY":
        assert decision["decision"] == "CLARIFY"
        assert decision["selected_capability"] is None
    elif stage == "HETEROGENEOUS_CAPABILITIES":
        assert decision["decision"] == "UNAVAILABLE"
        assert decision["selected_capability"] is None
        assert decision["policy_reason_code"] == (
            "HETEROGENEOUS_COMPOUND_UNSUPPORTED_V1"
        )
    elif stage == "IMPLEMENTATION_STATE":
        assert decision["decision"] == "UNAVAILABLE"
        assert isinstance(decision["selected_capability"], str)
    elif stage == "APPROVAL_REQUIRED":
        assert decision["decision"] == "APPROVAL"
        assert isinstance(decision["selected_capability"], str)
        assert decision["predicate_outcome"] in {"NOT_APPLICABLE", "TRUE"}
    elif stage == "EXECUTE_ALLOWED":
        assert decision["decision"] == "EXECUTE"
        assert isinstance(decision["selected_capability"], str)
        assert decision["predicate_outcome"] in {"NOT_APPLICABLE", "TRUE"}
    elif stage == "PREDICATE_FALSE":
        assert decision["decision"] == "UNAVAILABLE"
        assert decision["predicate_outcome"] == "FALSE"
        assert decision["user_visible_state"]["state"] == "condition_not_met"
    elif stage == "PREDICATE_UNKNOWN":
        assert decision["decision"] == "CLARIFY"
        assert decision["predicate_outcome"] == "UNKNOWN"
        assert decision["user_visible_state"]["state"] == "condition_unknown"
    expected_allowed = stage == "EXECUTE_ALLOWED"
    assert decision["task_contract_allowed"] is expected_allowed
    assert decision["effect_allowed"] is expected_allowed


def test_schema_closed_versioned_and_separates_three_documents() -> None:
    schema = _json(SCHEMA_PATH)
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["$id"].endswith("/1.0.0")
    assert schema["x-compound-decision-order"] == ORDER
    assert schema["oneOf"] == [
        {"$ref": "#/$defs/SemanticProposal"},
        {"$ref": "#/$defs/TrustedAdmissionContext"},
        {"$ref": "#/$defs/CoreDecision"},
    ]
    proposal = schema["$defs"]["SemanticProposal"]
    context = schema["$defs"]["TrustedAdmissionContext"]
    core = schema["$defs"]["CoreDecision"]
    assert all(
        item["additionalProperties"] is False
        for item in (proposal, context, core)
    )
    assert set(proposal["required"]) == SEMANTIC_KEYS
    assert set(proposal["properties"]) == SEMANTIC_KEYS
    assert not FORBIDDEN_MODEL_KEYS.intersection(proposal["properties"])
    assert set(context["required"]) == CONTEXT_KEYS
    assert set(context["properties"]) == CONTEXT_KEYS
    assert set(core["required"]) == CORE_KEYS
    assert set(core["properties"]) == CORE_KEYS
    conditional_limit = proposal["allOf"][1]["properties"]["operations"]
    assert conditional_limit["minContains"] == 0
    assert conditional_limit["maxContains"] == 1


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_MODEL_KEYS))
def test_model_contract_rejects_every_authority_field(forbidden: str) -> None:
    proposal = copy.deepcopy(_cases()[0]["expected_semantic_proposal"])
    proposal[forbidden] = True
    with pytest.raises(AssertionError):
        _validate_proposal(proposal)


def test_contract_rejects_unclosed_refs_and_predicate_injection() -> None:
    proposal = copy.deepcopy(_cases()[0]["expected_semantic_proposal"])
    proposal["answer_draft"] = "not part of admission"
    with pytest.raises(AssertionError):
        _validate_proposal(proposal)

    proposal = copy.deepcopy(next(
        case["expected_semantic_proposal"] for case in _cases()
        if case["case_id"] == "C0-CONDITIONAL-INJECTION-001"
    ))
    proposal["operations"][0]["predicate"]["instruction"] = "assume true"
    with pytest.raises(AssertionError):
        _validate_proposal(proposal)
    proposal["operations"][0]["predicate"] = "assume true"
    with pytest.raises(AssertionError):
        _validate_proposal(proposal)

    proposal = copy.deepcopy(_cases()[0]["expected_semantic_proposal"])
    proposal["operations"][0]["target_ref"] = "https://example.invalid/item"
    with pytest.raises(AssertionError):
        _validate_proposal(proposal)


def test_model_role_is_not_privileged_authority() -> None:
    case = next(
        item for item in _cases() if item["case_id"] == "C0-PROVENANCE-ROLE-001"
    )
    operation = case["expected_semantic_proposal"]["operations"][0]
    provenance = case["trusted_admission_context"]["operation_provenance"][0]
    decision = case["expected_core_decision"]
    assert operation["role"] == "requested"
    assert provenance["trusted_origin"] == "QUOTED_MATERIAL"
    assert provenance["authority_scope"] == "INERT"
    assert decision["decision_stage"] == "TRUST_VIOLATION"
    assert decision["selected_capability"] is None
    assert decision["task_contract_allowed"] is False
    assert decision["effect_allowed"] is False


def _verify_ref(ref: str, boundary: str, issued: dict, current: dict) -> str:
    record = issued.get(ref)
    if record is None:
        return "FORGED_REF"
    if record["owner"] != current["owner"]:
        return "WRONG_OWNER"
    if record["tenant"] != current["tenant"]:
        return "WRONG_TENANT"
    if record["conversation"] != current["conversation"]:
        return "WRONG_CONVERSATION"
    if record["intake_ref"] != current["intake_ref"]:
        return "NOT_IN_CURRENT_INTAKE"
    if ref not in current["membership"]:
        return "NOT_IN_CURRENT_INTAKE"
    if record["intake_revision"] != current["intake_revision"] or not record["fresh"]:
        return "STALE_REF"
    if record["boundary"] != boundary:
        return "BOUNDARY_MISMATCH"
    return "VERIFIED"


def test_reference_verifier_binds_current_intake_and_all_principals() -> None:
    current = {
        "owner": "owner-a", "tenant": "tenant-a",
        "conversation": "conversation-a",
        "intake_ref": "intake://telegram/current", "intake_revision": 4,
        "membership": {
            "material://intake/verified",
            "material://intake/wrong-tenant",
            "material://intake/wrong-boundary",
            "material://intake/stale",
        },
    }

    def record(**changes):
        value = {
            "owner": "owner-a", "tenant": "tenant-a",
            "conversation": "conversation-a",
            "intake_ref": "intake://telegram/current", "intake_revision": 4,
            "fresh": True, "boundary": "full_material",
        }
        value.update(changes)
        return value

    issued = {
        "material://intake/verified": record(),
        "material://intake/wrong-tenant": record(tenant="tenant-b"),
        "material://intake/not-member": record(),
        "material://intake/wrong-boundary": record(boundary="quoted_fragment"),
        "material://intake/stale": record(intake_revision=3, fresh=False),
    }
    expected = {
        "material://intake/verified": "VERIFIED",
        "material://intake/wrong-tenant": "WRONG_TENANT",
        "material://intake/not-member": "NOT_IN_CURRENT_INTAKE",
        "material://intake/wrong-boundary": "BOUNDARY_MISMATCH",
        "material://intake/forged-valid": "FORGED_REF",
        "material://intake/stale": "STALE_REF",
    }
    for ref, outcome in expected.items():
        assert _verify_ref(ref, "full_material", issued, current) == outcome


def test_reference_rejections_and_no_fragment_targets() -> None:
    cases = {item["case_id"]: item for item in _cases()}
    expected = {
        "C0-REF-WRONG-TENANT-001": "WRONG_TENANT",
        "C0-REF-NOT-MEMBER-001": "NOT_IN_CURRENT_INTAKE",
        "C0-REF-BOUNDARY-001": "BOUNDARY_MISMATCH",
        "C0-REF-FORGED-VALID-001": "FORGED_REF",
        "C0-REF-STALE-001": "STALE_REF",
    }
    for case_id, status in expected.items():
        case = cases[case_id]
        context = case["trusted_admission_context"]
        assert context["reference_validation"] == status
        assert any(item["status"] == status for item in context["reference_checks"])
        assert case["expected_core_decision"]["decision_stage"] == "TRUST_VIOLATION"
    serialized = json.dumps(_json(CORPUS_PATH), ensure_ascii=False)
    assert "#summary" not in serialized and "#checklist" not in serialized


def test_one_decision_order_is_identical_and_first_match_wins() -> None:
    assert _json(SCHEMA_PATH)["x-compound-decision-order"] == ORDER
    assert _json(REGISTRY_PATH)["decision_order"] == ORDER
    assert _json(CORPUS_PATH)["decision_order"] == ORDER
    adr = ADR_PATH.read_text(encoding="utf-8")
    positions = [
        adr.index(f"{index}. " + chr(96) + stage + chr(96))
        for index, stage in enumerate(ORDER, 1)
    ]
    assert positions == sorted(positions)

    def decide(active: set[str]) -> str:
        return next(stage for stage in ORDER if stage in active)

    for offset, stage in enumerate(ORDER):
        assert decide(set(ORDER[offset:])) == stage


def test_heterogeneous_never_creates_partial_contract_or_effect() -> None:
    case = next(
        item for item in _cases()
        if item["case_id"] == "C0-COMPOUND-HETEROGENEOUS-001"
    )
    decision = case["expected_core_decision"]
    assert decision["decision_stage"] == "HETEROGENEOUS_CAPABILITIES"
    assert decision["policy_reason_code"] == (
        "HETEROGENEOUS_COMPOUND_UNSUPPORTED_V1"
    )
    assert decision["selected_capability"] is None
    assert decision["task_contract_allowed"] is False
    assert decision["effect_allowed"] is False


def test_conditional_true_false_unknown_and_injection() -> None:
    cases = {item["case_id"]: item for item in _cases()}
    matrix = {
        "C0-CONDITIONAL-001": ("TRUE", "EXECUTE_ALLOWED", "accepted", True),
        "C0-CONDITIONAL-FALSE-001": (
            "FALSE", "PREDICATE_FALSE", "condition_not_met", False,
        ),
        "C0-CONDITIONAL-UNKNOWN-001": (
            "UNKNOWN", "PREDICATE_UNKNOWN", "condition_unknown", False,
        ),
        "C0-CONDITIONAL-INJECTION-001": (
            "FALSE", "PREDICATE_FALSE", "condition_not_met", False,
        ),
    }
    for case_id, (outcome, stage, state, allowed) in matrix.items():
        case = cases[case_id]
        _validate_predicate(
            case["expected_semantic_proposal"]["operations"][0]["predicate"]
        )
        assert case["trusted_admission_context"]["predicate_evaluation"][
            "outcome"
        ] == outcome
        decision = case["expected_core_decision"]
        assert decision["decision_stage"] == stage
        assert decision["user_visible_state"]["state"] == state
        assert decision["task_contract_allowed"] is allowed
        assert decision["effect_allowed"] is allowed
        facts = case["input"]["trusted_fixture_facts"]
        subject = case["expected_semantic_proposal"]["operations"][0][
            "predicate"
        ]["subject_ref"]
        assert facts["predicate_kind"] == "material_item_state_exists"
        assert facts["subject_ref"] == subject
        calculated = (
            "UNKNOWN"
            if facts["observation_state"] == "UNKNOWN"
            else "TRUE"
            if facts["matching_count"] > 0
            else "FALSE"
        )
        assert calculated == outcome
    assert _json(CORPUS_PATH)["predicate_fixture_contract"]["version"] == "1.0.0"
    injection = cases["C0-CONDITIONAL-INJECTION-001"]
    assert injection["input"]["trusted_fixture_facts"][
        "untrusted_material_claim"
    ] == "TRUE"
    assert injection["trusted_admission_context"]["predicate_evaluation"][
        "outcome"
    ] == "FALSE"
    assert any(
        item["role"] == "quoted"
        for item in injection["expected_semantic_proposal"]["operations"]
    )


def test_core_decision_covers_all_server_outcomes() -> None:
    fixtures = [case["expected_core_decision"] for case in _cases()]
    approval = copy.deepcopy(fixtures[0])
    approval.update(
        decision="APPROVAL", decision_stage="APPROVAL_REQUIRED",
        selected_capability="calendar.event.write",
        policy_reason_code="POLICY_APPROVAL_REQUIRED",
        predicate_outcome="NOT_APPLICABLE",
        task_contract_allowed=False, effect_allowed=False,
        user_visible_state={
            "state": "approval_required",
            "message_key": "calendar.write.approval",
        },
    )
    fixtures.append(approval)
    assert {item["decision"] for item in fixtures} == {
        "EXECUTE", "CLARIFY", "APPROVAL", "UNAVAILABLE", "REFUSE",
    }
    for fixture in fixtures:
        _validate_core(fixture)


@pytest.mark.parametrize("outcome", ["FALSE", "UNKNOWN"])
def test_false_or_unknown_predicate_cannot_reach_approval(outcome: str) -> None:
    decision = copy.deepcopy(_cases()[0]["expected_core_decision"])
    decision.update(
        decision="APPROVAL",
        decision_stage="APPROVAL_REQUIRED",
        predicate_outcome=outcome,
        selected_capability="calendar.event.write",
        policy_reason_code="POLICY_APPROVAL_REQUIRED",
        task_contract_allowed=False,
        effect_allowed=False,
        user_visible_state={
            "state": "approval_required",
            "message_key": "calendar.write.approval",
        },
    )
    with pytest.raises(AssertionError):
        _validate_core(decision)


def test_contract_v1_rejects_multiple_conditional_operations() -> None:
    case = next(
        item for item in _cases() if item["case_id"] == "C0-CONDITIONAL-001"
    )
    proposal = copy.deepcopy(case["expected_semantic_proposal"])
    second = copy.deepcopy(proposal["operations"][0])
    second["target_ref"] = "material://synthetic/conditional/second-subject"
    second["predicate"]["subject_ref"] = second["target_ref"]
    proposal["operations"].append(second)
    with pytest.raises(AssertionError):
        _validate_proposal(proposal)


def test_registry_state_axes_binding_rules_and_complete_entries() -> None:
    registry = _json(REGISTRY_PATH)
    assert registry["registry_version"] == "1.0.0"
    assert registry["status"] == "ACCEPTED_TARGET"
    assert registry["published_base"] == BASE
    assert registry["runtime_binding"] == "UNVERIFIED"
    assert registry["decision_order"] == ORDER
    assert registry["admission_binding_policy"][
        "model_operation_role_authoritative"
    ] is False
    assert "selected_capability=null" in registry["admission_binding_policy"][
        "heterogeneous_task_rule"
    ]
    required = {
        "id", "semantic_operation_kinds", "owner_visible_outcome",
        "implementation_state", "policy_state", "minimum_route_profile",
        "dependencies", "effect_type", "approval_requirement",
        "authoritative_success_evidence", "safe_failure", "owning_gate",
        "evidence_refs", "known_limitations", "privileged_operation",
        "authority_requirement",
    }
    ids, mapped = set(), set()
    operation_kinds = set(
        _json(SCHEMA_PATH)["$defs"]["Operation"]["properties"][
            "operation_kind"
        ]["enum"]
    )
    for capability in registry["capabilities"]:
        assert set(capability) == required
        assert capability["id"] not in ids
        ids.add(capability["id"])
        assert capability["implementation_state"] in {
            "CURRENT", "TARGET", "FROZEN", "UNAVAILABLE",
        }
        assert capability["policy_state"] in {
            "ALLOWED", "REQUIRES_APPROVAL", "PROHIBITED",
        }
        assert set(capability["semantic_operation_kinds"]) <= operation_kinds
        assert mapped.isdisjoint(capability["semantic_operation_kinds"])
        mapped.update(capability["semantic_operation_kinds"])
        if capability["privileged_operation"]:
            assert "direct owner provenance" in capability["authority_requirement"]
    assert mapped == operation_kinds
    compiler = next(
        item for item in registry["capabilities"]
        if item["id"] == "semantic.compile.modality_neutral"
    )
    assert compiler["implementation_state"] == "TARGET"


def test_gold_corpus_is_bound_and_covers_rework() -> None:
    corpus = _json(CORPUS_PATH)
    assert corpus["corpus_version"] == "1.0.0"
    assert corpus["contract_version"] == "1.0.0"
    assert corpus["decision_order"] == ORDER
    cases = corpus["cases"]
    assert len(cases) == 25
    assert len({case["case_id"] for case in cases}) == len(cases)
    required_categories = {
        "direct_task", "material_transformation", "quoted_instruction",
        "nested_instruction", "mentioned_only", "recounted_instruction",
        "negation", "cancel", "conditional", "predicate_true",
        "predicate_false", "predicate_unknown", "predicate_injection",
        "compound_task", "heterogeneous_compound", "unavailable_capability",
        "ambiguity", "clarification", "external_read", "external_write",
        "prompt_injection", "text_voice_pair", "incident_regression",
        "reference_validation", "trust_boundary", "refusal",
    }
    categories = {category for case in cases for category in case["categories"]}
    assert required_categories <= categories
    registry_ids = {
        item["id"] for item in _json(REGISTRY_PATH)["capabilities"]
    }
    for case in cases:
        proposal = case["expected_semantic_proposal"]
        context = case["trusted_admission_context"]
        decision = case["expected_core_decision"]
        _validate_proposal(proposal)
        _validate_context(context, proposal)
        _validate_core(decision)
        assert decision["proposal_digest"] == _digest(proposal)
        assert decision["admission_context_digest"] == _digest(context)
        assert (
            decision["selected_capability"] is None
            or decision["selected_capability"] in registry_ids
        )
        requested = [
            item["operation_kind"] for item in proposal["operations"]
            if item["role"] in {"requested", "conditional"}
        ]
        mentioned = [
            item["operation_kind"] for item in proposal["operations"]
            if item["role"] in {"quoted", "mentioned_only", "negated"}
        ]
        assert case["expected_operation_sets"] == {
            "requested": requested, "mentioned_only": mentioned,
        }
        assert "private" not in json.dumps(case, ensure_ascii=False).lower()


def test_text_voice_pairs_have_identical_semantic_and_route_outcomes() -> None:
    pairs: dict[str, list[dict]] = {}
    for case in _cases():
        pair = case["input"].get("pair_ref")
        if pair:
            pairs.setdefault(pair, []).append(case)
    assert set(pairs) == {"pair-direct-plan", "pair-incident-transform"}
    for cases in pairs.values():
        assert {case["input"]["modality"] for case in cases} == {
            "text", "voice_transcript",
        }
        assert len(cases) == 2
        assert (
            cases[0]["expected_semantic_proposal"]
            == cases[1]["expected_semantic_proposal"]
        )
        for key in (
            "decision", "decision_stage", "predicate_outcome",
            "selected_capability", "policy_reason_code", "user_visible_state",
            "task_contract_allowed", "effect_allowed",
        ):
            assert cases[0]["expected_core_decision"][key] == (
                cases[1]["expected_core_decision"][key]
            )


def test_operation_vocabulary_cannot_smuggle_capability_ids() -> None:
    registry_ids = {
        item["id"] for item in _json(REGISTRY_PATH)["capabilities"]
    }
    operation_kinds = {
        operation["operation_kind"]
        for case in _cases()
        for operation in case["expected_semantic_proposal"]["operations"]
    }
    assert operation_kinds.isdisjoint(registry_ids)


def test_active_status_and_roadmap_are_consistent() -> None:
    active = [
        ROOT / "README.md", ROOT / "docs/README.md",
        ROOT / "docs/01-Единый-документ-проекта.md",
        ROOT / "docs/03-Архитектурный-обзор.md",
        ROOT / "docs/08-Runbook-эксплуатации.md",
        ROOT / "docs/11-Контекст-продукта.md",
        ROOT / "docs/14-Действия-владельца-после-Gate-0-SSH-VPS-и-Gate-1-2.md",
        ROOT / "docs/handoffs/CURRENT-STATUS.md",
    ]
    verdict = (
        "MVP-1 PUBLISHED / LIVE RUNTIME OBSERVED / ACCEPTANCE REOPENED / "
        "PATCH REQUIRED"
    )
    for path in active:
        text_value = path.read_text(encoding="utf-8")
        normalized = " ".join(text_value.replace(">", " ").split())
        assert verdict in normalized and "DEPLOYMENT REVISION UNVERIFIED" in normalized
        assert "MVP-2 HOLD" in normalized
        assert "**MVP-1 READY.**" not in text_value
        assert "имеет статус" not in text_value or "MVP-1 READY" not in text_value
    roadmap = (ROOT / "docs/gates/README.md").read_text(
        encoding="utf-8"
    )
    assert re.findall(
        r"^\| C([0-6]) —", roadmap, flags=re.MULTILINE
    ) == list("0123456")
    assert "Один Gate = одна Codex-задача = один" in roadmap
    assert "R01–R47 — внутренние" in roadmap


def test_adr_number_journal_links_and_single_handoff() -> None:
    journal = (ROOT / "docs/04-Журнал-ADR.md").read_text(encoding="utf-8")
    assert journal.count(
        "[0023](adr/0023-modality-neutral-semantic-admission-and-core-decision.md)"
    ) == 1
    numbers = [
        path.name[:4]
        for path in (ROOT / "docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md")
    ]
    assert len(numbers) == len(set(numbers))
    assert HANDOFF_PATH.is_file()
    assert len(list(PACKAGE.glob("*HANDOFF*.md"))) == 1
    for path in (HANDOFF_PATH, ADR_PATH):
        content = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", content):
            if "://" not in target:
                assert (path.parent / target).resolve().exists(), (path, target)


def test_sealed_gate0_is_byte_identical_to_published_base() -> None:
    prefix = "docs/gates/gate-00-product-contract-baseline"
    tracked = _git(
        "ls-tree", "-r", "--name-only", BASE, "--", prefix
    ).decode().splitlines()
    current = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / prefix).rglob("*") if path.is_file()
    )
    assert current == sorted(tracked)
    assert subprocess.run(
        ["git", "diff", "--quiet", BASE, "--", prefix],
        cwd=ROOT, check=False,
    ).returncode == 0


def test_publication_projection_excludes_held_editorial_docs() -> None:
    held = {
        "docs/15-Продуктовая-дорожная-карта.md",
        "docs/16-Управленческая-карта-разработки.html",
    }
    assert all(not (ROOT / path).exists() for path in held)
    tracked = {
        item.decode("utf-8")
        for item in _git("ls-files", "-z").split(b"\0")
        if item
    }
    assert held.isdisjoint(tracked)


def test_candidate_changes_no_production_code() -> None:
    paths = [
        item.decode("utf-8")
        for item in _git("diff", "--name-only", "-z", BASE, "--").split(b"\0")
        if item
    ]
    assert paths
    assert all(
        path.startswith("docs/")
        or path == "README.md"
        or path == "tests/test_gate_c0_governance.py"
        for path in paths
    )
    assert not any(
        path.startswith(("src/", "scripts/", "frontend/")) for path in paths
    )
