from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def run_powershell(body: str) -> subprocess.CompletedProcess[str]:
    helper = str(HELPER).replace("'", "''")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{helper}'; {body}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def assert_closed_failure(
    completed: subprocess.CompletedProcess[str],
    *,
    expected_stage: str,
) -> None:
    assert completed.returncode == 0, completed.stderr
    assert "token=" not in completed.stdout.lower()
    assert "token=" not in completed.stderr.lower()
    assert json.loads(completed.stdout) == {
        "schema": "nobus.gate0.runtime_maintenance.v1",
        "result": "blocked",
        "error_stage": expected_stage,
    }


def test_scheduler_discovery_failure_emits_only_closed_stage() -> None:
    completed = run_powershell(
        r"""
function Get-ScheduledTask { throw 'token=must-not-escape' }
try {
  $null = Get-LiveMaintenanceState `
    -CanonicalRepoRoot $script:MaintenanceCanonicalRepoRoot
}
catch {
  Write-SanitizedMaintenanceFailure
}
"""
    )

    assert_closed_failure(completed, expected_stage="scheduler_task")


def test_candidate_discovery_failure_emits_only_closed_stage() -> None:
    completed = run_powershell(
        r"""
function Get-RegisteredRuntimeDefinition {
  return [pscustomobject]@{ SchedulerState='running' }
}
function Get-RunnerCandidates { throw 'token=must-not-escape' }
try {
  $null = Get-LiveMaintenanceState -CanonicalRepoRoot 'C:\repo'
}
catch {
  Write-SanitizedMaintenanceFailure
}
"""
    )

    assert_closed_failure(completed, expected_stage="runner_candidates")


def test_unknown_internal_stage_fails_closed_without_echoing_it() -> None:
    completed = run_powershell(
        r"""
$script:MaintenanceFailureStage = 'token=must-not-escape'
Write-SanitizedMaintenanceFailure
"""
    )

    assert_closed_failure(completed, expected_stage="unknown")


def test_task_contract_failure_emits_only_closed_boolean_bitmap() -> None:
    completed = run_powershell(
        r"""
$profile = [ordered]@{}
foreach ($field in $script:TaskContractProfileFields) {
  $profile[$field] = $true
}
$profile['restart_count'] = $false
$script:MaintenanceTaskContractProfile = $profile
$script:MaintenanceFailureStage = 'task_contract'
Write-SanitizedMaintenanceFailure
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "token=" not in completed.stdout.lower()
    result = json.loads(completed.stdout)
    assert result["schema"] == "nobus.gate0.runtime_maintenance.v1"
    assert result["result"] == "blocked"
    assert result["error_stage"] == "task_contract"
    bitmap = result["task_contract_profile"]
    assert set(bitmap) == {
        "task_name", "task_path", "description", "enabled",
        "multiple_instances", "start_when_available", "disallow_battery",
        "stop_on_battery", "restart_count", "restart_interval",
        "execution_limit", "principal_user", "logon_type", "run_level",
        "trigger_count", "trigger_type", "trigger_user", "action_arguments",
        "working_directory", "executable",
    }
    assert bitmap["restart_count"] is False
    assert all(isinstance(value, bool) for value in bitmap.values())
    assert set(result) == {
        "schema", "result", "error_stage", "task_contract_profile"
    }


def test_action_contract_failure_emits_only_fixed_structural_bitmap() -> None:
    completed = run_powershell(
        r"""
$taskProfile = [ordered]@{}
foreach ($field in $script:TaskContractProfileFields) {
  $taskProfile[$field] = $true
}
$taskProfile['action_arguments'] = $false
$actionProfile = [ordered]@{}
foreach ($field in $script:ActionContractProfileFields) {
  $actionProfile[$field] = $true
}
$actionProfile['launcher_path_exact'] = $false
$script:MaintenanceTaskContractProfile = $taskProfile
$script:MaintenanceActionContractProfile = $actionProfile
$script:MaintenanceFailureStage = 'task_contract'
Write-SanitizedMaintenanceFailure
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "token=" not in completed.stdout.lower()
    result = json.loads(completed.stdout)
    profile = result["action_contract_profile"]
    assert set(profile) == {
        "nonempty", "secret_shape_absent", "control_chars_absent", "parse_ok",
        "statement_count_one", "statement_is_pipeline",
        "pipeline_element_count_one", "element_is_command",
        "redirection_count_zero", "command_element_count_eight",
        "token_count_eight", "shell_token", "nologo_token", "noprofile_token",
        "noninteractive_token", "execution_policy_token", "bypass_token",
        "file_token", "launcher_quote_shape", "launcher_path_exact",
    }
    assert profile["launcher_path_exact"] is False
    assert all(isinstance(value, bool) for value in profile.values())
    assert set(result) == {
        "schema", "result", "error_stage", "task_contract_profile",
        "action_contract_profile",
    }


def test_file_entrypoint_rejects_invalid_mode_without_raw_binding_error() -> None:
    raw_mode = "token=must-not-escape"
    raw_root = r"C:\synthetic-root-must-not-escape"
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HELPER),
            "-Mode",
            raw_mode,
            "-RepoRoot",
            raw_root,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stderr == ""
    serialized = completed.stdout.casefold()
    assert raw_mode.casefold() not in serialized
    assert raw_root.casefold() not in serialized
    assert str(HELPER).casefold() not in serialized
    assert json.loads(completed.stdout) == {
        "schema": "nobus.gate0.runtime_maintenance.v1",
        "result": "blocked",
        "error_stage": "entry",
    }
