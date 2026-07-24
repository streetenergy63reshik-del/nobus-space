"""Create the bounded owner-write root only after an exact L4 approval."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = ROOT.parents[1] / "NOBUS SPACE BOT"
_APPROVAL = re.compile(r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$")


def initialize(path: Path, *, approval_ref: str) -> Path:
    if _APPROVAL.fullmatch(approval_ref) is None:
        raise ValueError("owner workspace approval is invalid")
    configured = path
    if configured.exists() and (
        configured.is_symlink()
        or (hasattr(configured, "is_junction") and configured.is_junction())
        or not configured.is_dir()
    ):
        raise ValueError("owner workspace path is invalid")
    configured.mkdir(parents=True, exist_ok=True)
    quarantine = configured / "Загрузки"
    if quarantine.exists() and (
        quarantine.is_symlink()
        or (hasattr(quarantine, "is_junction") and quarantine.is_junction())
        or not quarantine.is_dir()
    ):
        raise ValueError("owner quarantine path is invalid")
    quarantine.mkdir(exist_ok=True)
    resolved = configured.resolve(strict=True)
    if not quarantine.resolve(strict=True).is_relative_to(resolved):
        raise ValueError("owner quarantine path is invalid")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--approval-ref", required=True)
    values = parser.parse_args()
    result = initialize(values.path, approval_ref=values.approval_ref)
    print(
        json.dumps(
            {"status": "PASS", "workspace": str(result)},
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
