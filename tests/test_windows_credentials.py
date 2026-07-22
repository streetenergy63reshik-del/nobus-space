"""Tests for the Windows Credential Manager boundary."""

from __future__ import annotations

import pytest

from src.security import windows_credentials
from src.security.windows_credentials import (
    CredentialStoreError,
    read_generic_credential,
)


def test_reads_secret_without_exposing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "123456:" + "A" * 32
    monkeypatch.setattr(
        windows_credentials,
        "_read_windows_credential",
        lambda target: ("@bot", secret.encode("utf-16-le")),
    )
    credential = read_generic_credential("safe-target")
    assert credential.username == "@bot"
    assert credential.secret.get_secret_value() == secret
    assert secret not in repr(credential)


def test_raw_failure_is_replaced_without_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "raw-secret"

    def fail(target: str) -> tuple[str, bytes]:
        raise RuntimeError(secret)

    monkeypatch.setattr(windows_credentials, "_read_windows_credential", fail)
    with pytest.raises(CredentialStoreError) as caught:
        read_generic_credential("safe-target")
    assert caught.value.code == "credential_unavailable"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert secret not in str(caught.value)


@pytest.mark.parametrize("target", ["", " ", "bad\x00target", 7])
def test_invalid_target_fails_before_store_access(
    monkeypatch: pytest.MonkeyPatch, target: object
) -> None:
    monkeypatch.setattr(
        windows_credentials,
        "_read_windows_credential",
        lambda value: pytest.fail("store must not be called"),
    )
    with pytest.raises(CredentialStoreError) as caught:
        read_generic_credential(target)  # type: ignore[arg-type]
    assert caught.value.code == "credential_configuration_invalid"


@pytest.mark.parametrize("blob", [b"", b"x", b"\x00\xd8", b"A\x00\x00\x00"])
def test_malformed_blob_fails_closed(blob: bytes) -> None:
    with pytest.raises(CredentialStoreError) as caught:
        windows_credentials._decode_credential_blob(blob)
    assert caught.value.code == "credential_unavailable"
