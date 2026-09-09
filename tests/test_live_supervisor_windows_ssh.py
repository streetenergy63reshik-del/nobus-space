"""Actual Windows OpenSSH must start inside the restricted supervisor Job."""
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows runtime integration")
def test_owned_ssh_starts_with_restricted_environment(monkeypatch):
    script = Path(__file__).parents[1] / "scripts/run_nobus_space_live.py"
    spec = importlib.util.spec_from_file_location("nobus_ssh_environment_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SSH.is_file(), "Windows OpenSSH is a production prerequisite"
    monkeypatch.setenv("C6_TEST_PRIVATE_VALUE", "synthetic-must-not-be-inherited")
    original = subprocess.Popen
    seen = []

    def spawn(*args, **kwargs):
        seen.append({key.upper() for key in kwargs["env"]})
        return original(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    api = module._job_api()
    job = api.create_job()
    child = None
    try:
        child = module.spawn_owned(api, job, [str(module.SSH), "-V"])
        assert child.wait(timeout=15) == 0
        assert len(seen) == 1
        assert "C6_TEST_PRIVATE_VALUE" not in seen[0]
    finally:
        api.terminate(job)
        empty = module.wait_job_empty(job)
        api.close(job)
        if child is not None:
            module.close_owned(api, child)
        assert empty, "Supervisor Job must be empty after the integration probe"
