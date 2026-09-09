"""Native profile identity and composition are checked without a model or process."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application import codex_runtime as native


def native_fixture(tmp_path, monkeypatch):
    root = tmp_path / "qualified-worktree"
    directory = root / ".runtime" / "native" / ("codex-" + native.CODEX_VERSION)
    directory.mkdir(parents=True)
    expected = {}
    for name in native.NATIVE_FILES:
        content = ("synthetic native fixture " + name).encode()
        (directory / name).write_bytes(content)
        expected[name] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    monkeypatch.setattr(native, "NATIVE_FILES", expected)
    profile = root / native.PROFILE_NAME
    profile.write_text(json.dumps({"schema": "nobus-codex-runtime-1",
        "version": native.CODEX_VERSION, "directory": str(directory)}), encoding="utf-8")
    return root, directory, profile


def test_native_profile_validates_all_exact_bytes(tmp_path, monkeypatch):
    root, directory, _ = native_fixture(tmp_path, monkeypatch)
    assert native.qualified_codex_executable(root) == directory / "codex.exe"


@pytest.mark.parametrize("name", tuple(native.NATIVE_FILES))
@pytest.mark.parametrize("change", ("missing", "tampered"))
def test_native_file_drift_rejected(tmp_path, monkeypatch, name, change):
    root, directory, _ = native_fixture(tmp_path, monkeypatch)
    path = directory / name
    if change == "missing":
        path.unlink()
    else:
        content = path.read_bytes()
        path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    with pytest.raises(RuntimeError, match="^qualified Codex runtime is unavailable$"):
        native.qualified_codex_executable(root)


@pytest.mark.parametrize("change", ("extra", "version", "relative", "outside", "traversal", "duplicate", "oversize", "missing"))
def test_native_profile_rejects_invalid_authority(tmp_path, monkeypatch, change):
    root, directory, profile = native_fixture(tmp_path, monkeypatch)
    value = json.loads(profile.read_text())
    if change == "extra": value["sha256"] = "attacker-supplied-digest"
    if change == "version": value["version"] = "0.144.4"
    if change == "relative": value["directory"] = ".runtime/native/codex-" + native.CODEX_VERSION
    if change == "outside": value["directory"] = str(tmp_path)
    if change == "traversal": value["directory"] = str(directory / ".." / directory.name)
    profile.write_text(json.dumps(value), encoding="utf-8")
    if change == "duplicate": profile.write_text('{"version":"0.153.4","version":"0.153.4"}')
    if change == "oversize": profile.write_text(" " * 4097)
    if change == "missing": profile.unlink()
    with pytest.raises(RuntimeError, match="^qualified Codex runtime is unavailable$"):
        native.qualified_codex_executable(root)


def test_native_profile_rejects_extra_dll_and_hardlink(tmp_path, monkeypatch):
    root, directory, _ = native_fixture(tmp_path, monkeypatch)
    (directory / "unexpected.dll").write_bytes(b"synthetic")
    with pytest.raises(RuntimeError): native.qualified_codex_executable(root)
    (directory / "unexpected.dll").unlink()
    os.link(directory / "codex.exe", tmp_path / "external-link.exe")
    with pytest.raises(RuntimeError): native.qualified_codex_executable(root)


def test_sdk_uses_explicit_executable_and_fallback_keeps_own_path(tmp_path, monkeypatch):
    from src.application import gate5a4 as composition
    from src.workers.codex_sdk import CodexSdkAdapter
    modern = tmp_path / "modern" / "codex.exe"
    bundled = tmp_path / "bundled" / "codex.exe"
    workspace = tmp_path / "worktree"
    temp = workspace / ".runtime" / "temp"
    for path in (modern, bundled):
        path.parent.mkdir(); path.touch()
    temp.mkdir(parents=True)
    seen = {}
    def sdk(**kwargs):
        instance = CodexSdkAdapter(**kwargs)
        seen["sdk_executable"] = instance._config.codex_bin
        return instance
    class BoundaryReached(Exception): pass
    def launcher(**kwargs):
        seen.update(kwargs)
        raise BoundaryReached
    monkeypatch.setattr(composition, "CodexSdkAdapter", sdk)
    monkeypatch.setattr(composition, "bundled_codex_path", lambda: bundled)
    monkeypatch.setattr(composition, "WindowsJobLauncher", launcher)
    with pytest.raises(BoundaryReached):
        composition.build_gate5a4_runtime(gateway=object(), sqlite_path=tmp_path / "unused.sqlite3",
            destination_refs={}, worktree=workspace, codex_executable=modern,
            git_executable=modern, python_executable=modern, codex_home=tmp_path,
            system_root=tmp_path, temp_root=temp, path_entries=(tmp_path, modern.parent))
    assert seen["sdk_executable"] == str(modern.resolve())
    assert seen["target_executable"] == bundled.resolve()
    paths = seen["worker_env"]["PATH"].split(os.pathsep)
    assert str(modern.parent) not in paths
    assert str(bundled.parent) in paths


def test_backup_detects_external_native_drift_with_unchanged_profile(tmp_path, monkeypatch):
    from tests.test_c6_managed_backups import fake_cycle
    from scripts import run_telegram_backup_cycle as cycle
    path, digest, states, events = fake_cycle(tmp_path, monkeypatch)
    config = cycle.load_config(path, digest)
    executable = native.qualified_codex_executable(cycle.ROOT)
    profile_before = (cycle.ROOT / native.PROFILE_NAME).read_bytes()
    executable.write_bytes(b"changed native bytes")
    with pytest.raises(RuntimeError, match="qualified Codex runtime"):
        cycle.cycle(path, digest)
    assert (cycle.ROOT / native.PROFILE_NAME).read_bytes() == profile_before
    assert not any(event.startswith("Start:") for event in events)
