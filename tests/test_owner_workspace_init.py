from __future__ import annotations

import pytest

from scripts.initialize_owner_workspace import initialize


APPROVAL = "telegram-owner-confirmation:sha256:" + "a" * 64


def test_owner_workspace_is_created_only_after_exact_l4(tmp_path):
    root = tmp_path / "NOBUS SPACE BOT"
    with pytest.raises(ValueError, match="approval"):
        initialize(root, approval_ref="approved")
    assert not root.exists()

    resolved = initialize(root, approval_ref=APPROVAL)

    assert resolved == root.resolve()
    assert (root / "Загрузки").is_dir()
