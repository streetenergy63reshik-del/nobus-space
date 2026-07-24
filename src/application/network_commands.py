"""Exact L4 proposals for the small set of supported network commands."""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_APPROVAL_RE = re.compile(r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_HTTPS_GIT_RE = re.compile(
    r"^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/[A-Za-z0-9._~!$&\'()*+,;=:@%/-]+$"
)
_PYPI_INDEX = "https://pypi.org/simple"
_REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?"
    r"==[A-Za-z0-9][A-Za-z0-9_.+!-]*"
    r"(?:\s+--hash=sha256:[0-9a-fA-F]{64})+$"
)


@dataclass(frozen=True, slots=True)
class NetworkCommandProposal:
    tool: str
    argv: tuple[str, ...]
    working_directory: str
    input_digest: str
    source: str | None
    destination: str | None
    digest: str


class NetworkCommandRunner:
    """Run only an exact reviewed argv, never a shell command."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        git_executable: str | Path,
        python_executable: str | Path,
    ) -> None:
        self._root = Path(workspace_root).resolve(strict=True)
        self._executables = {
            "git-fetch": Path(git_executable).resolve(strict=True),
            "pip-install": Path(python_executable).resolve(strict=True),
        }
        if not self._root.is_dir() or any(
            not value.is_file() for value in self._executables.values()
        ):
            raise ValueError("network command configuration is invalid")

    def propose_git_fetch(
        self, *, repository_directory: str, remote: str, revision: str
    ) -> NetworkCommandProposal:
        cwd = self._directory(repository_directory)
        if (
            not re.fullmatch(r"^[A-Za-z0-9._-]{1,64}$", remote)
            or _REVISION_RE.fullmatch(revision) is None
        ):
            raise ValueError("git fetch request is invalid")
        url, input_digest = self._git_remote(cwd, remote)
        argv = ("fetch", "--no-tags", "--", url, revision)
        return self._proposal(
            "git-fetch",
            argv,
            cwd,
            input_digest,
            source=revision,
            destination=url,
        )

    def propose_pip_install(
        self, *, repository_directory: str, requirement_file: str
    ) -> NetworkCommandProposal:
        cwd = self._directory(repository_directory)
        requirement = Path(requirement_file)
        if (
            requirement.is_absolute()
            or requirement.parts != (requirement.name,)
            or requirement.name not in {"requirements.txt", "requirements-dev.txt"}
        ):
            raise ValueError("pip install request is invalid")
        path = cwd / requirement
        self._validate_requirements(path)
        argv = (
            "-m",
            "pip",
            "--isolated",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--index-url",
            _PYPI_INDEX,
            "--require-hashes",
            "--only-binary=:all:",
            "-r",
            requirement.name,
        )
        return self._proposal(
            "pip-install",
            argv,
            cwd,
            self._file_digest(path),
            source=requirement.name,
            destination=_PYPI_INDEX,
        )

    def run(
        self,
        proposal: NetworkCommandProposal,
        *,
        approval_ref: str,
        timeout_seconds: int = 900,
    ) -> subprocess.CompletedProcess[bytes]:
        if (
            not isinstance(proposal, NetworkCommandProposal)
            or _APPROVAL_RE.fullmatch(approval_ref) is None
            or proposal.digest
            != self._digest(
                proposal.tool,
                proposal.argv,
                proposal.working_directory,
                proposal.input_digest,
                proposal.source,
                proposal.destination,
            )
            or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 3_600
        ):
            raise ValueError("network command approval is invalid")
        executable = self._executables.get(proposal.tool)
        if executable is None:
            raise ValueError("network command is invalid")
        cwd = self._directory(proposal.working_directory)
        if proposal.tool == "git-fetch":
            if proposal.destination is None or proposal.source is None:
                raise ValueError("network command is invalid")
            remote = self._remote_name_for_url(cwd, proposal.destination)
            url, current_input = self._git_remote(cwd, remote)
            if url != proposal.destination:
                raise ValueError("network command input changed after approval")
        else:
            if (
                proposal.source is None
                or proposal.destination != _PYPI_INDEX
            ):
                raise ValueError("network command is invalid")
            requirement = cwd / proposal.source
            self._validate_requirements(requirement)
            current_input = self._file_digest(requirement)
        if current_input != proposal.input_digest:
            raise ValueError("network command input changed after approval")
        return subprocess.run(
            (str(executable), *proposal.argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=timeout_seconds,
            check=False,
            env={
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "PIP_CONFIG_FILE": os.devnull,
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_INPUT": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONUTF8": "1",
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            },
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def _proposal(
        self,
        tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        input_digest: str,
        *,
        source: str | None,
        destination: str | None,
    ) -> NetworkCommandProposal:
        relative = cwd.relative_to(self._root).as_posix() or "."
        return NetworkCommandProposal(
            tool,
            argv,
            relative,
            input_digest,
            source,
            destination,
            self._digest(tool, argv, relative, input_digest, source, destination),
        )

    def _directory(self, value: str) -> Path:
        candidate = Path(value)
        resolved = (
            candidate.resolve(strict=True)
            if candidate.is_absolute()
            else (self._root / candidate).resolve(strict=True)
        )
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise ValueError("network command path is invalid") from None
        if not resolved.is_dir() or resolved.is_symlink():
            raise ValueError("network command path is invalid")
        return resolved

    def _git_remote(self, cwd: Path, remote: str) -> tuple[str, str]:
        config_path = self._git_config(cwd)
        raw = config_path.read_text(encoding="utf-8")
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(raw)
        self._validate_git_config(parser)
        section = f'remote "{remote}"'
        if not parser.has_option(section, "url"):
            raise ValueError("git remote is unavailable")
        url = parser.get(section, "url").strip()
        if _HTTPS_GIT_RE.fullmatch(url) is None:
            raise ValueError("git remote URL is not approved")
        return url, self._digest_value(
            {
                "remote": remote,
                "url": url,
                "config_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }
        )

    @staticmethod
    def _validate_git_config(parser: configparser.ConfigParser) -> None:
        """Allow only inert repository metadata needed by an explicit HTTPS fetch."""
        if parser.defaults():
            raise ValueError("git config contains forbidden settings")
        core_options = {
            "bare",
            "filemode",
            "ignorecase",
            "logallrefupdates",
            "repositoryformatversion",
            "symlinks",
            "worktree",
        }
        branch_options = {"merge", "remote"}
        remote_options = {"fetch", "url"}
        for section in parser.sections():
            folded = section.casefold()
            options = {option.casefold() for option in parser.options(section)}
            if folded == "core":
                allowed = core_options
            elif re.fullmatch(r'branch "[A-Za-z0-9._/-]{1,200}"', section):
                allowed = branch_options
            elif re.fullmatch(r'remote "[A-Za-z0-9._-]{1,64}"', section):
                allowed = remote_options
                url = parser.get(section, "url", fallback="").strip()
                if _HTTPS_GIT_RE.fullmatch(url) is None:
                    raise ValueError("git remote URL is not approved")
            else:
                raise ValueError("git config contains forbidden settings")
            if not options <= allowed:
                raise ValueError("git config contains forbidden settings")

    def _remote_name_for_url(self, cwd: Path, expected_url: str) -> str:
        config_path = self._git_config(cwd)
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(config_path.read_text(encoding="utf-8"))
        matches = []
        for section in parser.sections():
            match = re.fullmatch(r'remote "([A-Za-z0-9._-]{1,64})"', section)
            if match and parser.get(section, "url", fallback="").strip() == expected_url:
                matches.append(match.group(1))
        if len(matches) != 1:
            raise ValueError("git remote binding changed after approval")
        return matches[0]

    def _git_config(self, cwd: Path) -> Path:
        metadata = cwd / ".git"
        if metadata.is_file():
            line = metadata.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir: "):
                raise ValueError("git repository metadata is invalid")
            git_dir = (cwd / line[8:]).resolve(strict=True)
        else:
            git_dir = metadata.resolve(strict=True)
        try:
            git_dir.relative_to(self._root)
        except ValueError:
            raise ValueError("git repository metadata is outside workspace") from None
        config_path = git_dir / "config"
        if not config_path.is_file():
            common = git_dir / "commondir"
            if not common.is_file():
                raise ValueError("git repository config is unavailable")
            config_path = (
                git_dir / common.read_text(encoding="utf-8").strip() / "config"
            ).resolve(strict=True)
        try:
            config_path.relative_to(self._root)
        except ValueError:
            raise ValueError("git repository config is outside workspace") from None
        if not config_path.is_file() or config_path.is_symlink():
            raise ValueError("git repository config is unavailable")
        return config_path

    @staticmethod
    def _validate_requirements(path: Path) -> None:
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size > 2 * 1024 * 1024
        ):
            raise ValueError("network command input is invalid")
        text = path.read_text(encoding="utf-8")
        if "\\\n" in text or "\\\r\n" in text or "${" in text or "%" in text:
            raise ValueError("nested or mutable pip requirement is forbidden")
        for line in text.splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if _REQUIREMENT_RE.fullmatch(value) is None:
                raise ValueError("nested or mutable pip requirement is forbidden")

    @staticmethod
    def _file_digest(path: Path) -> str:
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size > 2 * 1024 * 1024
        ):
            raise ValueError("network command input is invalid")
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

    @staticmethod
    def _digest(
        tool: str,
        argv: tuple[str, ...],
        cwd: str,
        input_digest: str,
        source: str | None,
        destination: str | None,
    ) -> str:
        return NetworkCommandRunner._digest_value(
            {
                "tool": tool,
                "argv": argv,
                "working_directory": cwd,
                "input_digest": input_digest,
                "source": source,
                "destination": destination,
            }
        )

    @staticmethod
    def _digest_value(value: object) -> str:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return f"sha256:{hashlib.sha256(raw).hexdigest()}"
