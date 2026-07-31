from __future__ import annotations

import copy
import datetime as dt
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/gate0"))

from gate0_lifecycle import capture_lifecycle, database_claim


UTC = dt.timezone.utc


def _database() -> dict[str, object]:
    schema_digest = "sha256:" + "a" * 64
    return {
        "database_role": "telegram_state",
        "database_ref": "runtime-db:telegram_state",
        "runtime_binding_status": "verified",
        "source_schema_match": True,
        "schema_digest": schema_digest,
        "migration_inventory": {"applied": [], "pending": [], "unknown": []},
        "migration_lineage_status": "genesis_baseline_verified",
        "snapshot": {
            "mode": "sqlite_read_transaction",
            "wal_aware": True,
            "data_version_stable": True,
            "file_markers_stable": False,
            "concurrent_file_activity_observed": True,
            "consistent": True,
        },
        "integrity": {"quick_check": "ok", "foreign_key_check": "ok"},
        "genesis_baseline": {
            "genesis_id": "genesis_baseline:telegram_state_current_schema",
            "authority_ref": "owner-authority:gate0-evidence-closure-2026-07-29",
            "schema_digest": schema_digest,
            "historical_legacy_migration_proven": False,
            "durable_ledger_deferred_to_gate": 2,
            "production_database_mutated": False,
        },
    }


@pytest.mark.parametrize(
    ("snapshot", "as_of", "expected"),
    [
        (
            {
                "clock": {"trusted": True},
                "observed_at": "2030-01-01T00:00:00Z",
                "fresh_until": "2030-01-01T00:05:00Z",
            },
            dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
            "FRESH",
        ),
        (
            {
                "clock": {"trusted": True},
                "observed_at": "2030-01-01T00:00:00Z",
                "fresh_until": "2030-01-01T00:05:00Z",
            },
            dt.datetime(2030, 1, 1, 0, 6, tzinfo=UTC),
            "STALE",
        ),
        (None, dt.datetime(2030, 1, 1, tzinfo=UTC), "NO_CAPTURE"),
        (
            {
                "clock": {"trusted": True},
                "observed_at": "2030-01-01T00:00:00Z",
            },
            dt.datetime(2030, 1, 1, tzinfo=UTC),
            "UNVERIFIABLE",
        ),
        (
            {
                "status": "CONTRADICTORY",
                "clock": {"trusted": True},
                "observed_at": "2030-01-01T00:00:00Z",
                "fresh_until": "2030-01-01T00:05:00Z",
            },
            dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
            "UNVERIFIABLE",
        ),
        (
            {
                "clock": {"trusted": False},
                "observed_at": "2030-01-01T00:00:00Z",
                "fresh_until": "2030-01-01T00:05:00Z",
            },
            dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
            "UNVERIFIABLE",
        ),
    ],
)
def test_capture_lifecycle_is_explicit(snapshot, as_of, expected) -> None:
    assert capture_lifecycle(snapshot, as_of=as_of) == expected


def test_genesis_requires_complete_fresh_proof() -> None:
    valid = _database()
    claim, status, genesis = database_claim(valid, "FRESH")
    assert status == "VERIFIED"
    assert genesis is True
    assert claim["genesis_baseline"] is not None

    mutations = (
        lambda value: value["snapshot"].update(consistent=False),
        lambda value: value.update(database_ref="candidate-worktree-db:telegram_state"),
        lambda value: value["genesis_baseline"].update(
            schema_digest="sha256:" + "b" * 64
        ),
    )
    for mutate in mutations:
        invalid = copy.deepcopy(valid)
        mutate(invalid)
        claim, status, genesis = database_claim(invalid, "FRESH")
        assert status == "CONTRADICTORY"
        assert genesis is False
        assert claim["migration_lineage_status"] == "contradictory"
        assert claim["genesis_baseline"] is None

    claim, status, genesis = database_claim(valid, "STALE")
    assert status == "STALE"
    assert genesis is False
    assert claim["migration_lineage_status"] == "contradictory"
    assert claim["genesis_baseline"] is None
