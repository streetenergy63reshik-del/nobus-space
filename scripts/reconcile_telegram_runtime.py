"""Prepare/read back an exact local-owner plan, or apply its explicit confirmation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.application.runtime_reconciliation import prepare, approve
from src.application.runtime_maintenance import checked_path, write_bytes_durable
from src.contracts.models import canonical_json_digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--original-runtime', type=Path, required=True)
    parser.add_argument('--evidence-manifest', type=Path, required=True)
    parser.add_argument('--owner-binding', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--confirm-digest')
    args = parser.parse_args()
    try:
        path = checked_path(args.plan)
        if args.confirm_digest is None:
            plan = prepare(args.runtime, args.evidence_manifest, args.owner_binding, original_runtime=args.original_runtime)
            write_bytes_durable(path, json.dumps(plan, sort_keys=True, indent=2).encode())
            result = {'status': 'OWNER_CONFIRMATION_PENDING', 'plan_digest': canonical_json_digest(plan),
                'target_binding': plan['target_binding'], 'snapshot': plan['snapshot_manifest_digest'],
                'evidence': plan['evidence_manifest_digest'], 'expires_at': plan['expires_at']}
        else:
            if path.stat().st_size > 65536:
                raise ValueError('operator plan too large')
            plan = json.loads(path.read_text())
            result = approve(args.runtime, args.evidence_manifest, args.owner_binding, plan,
                original_runtime=args.original_runtime, confirmation=args.confirm_digest)
    except Exception:
        print('{"status":"FAIL","code":"reconciliation_required"}')
        return 1
    print(json.dumps(result, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
