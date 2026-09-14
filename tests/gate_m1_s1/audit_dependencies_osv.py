"""M1-S1 dependency inventory; network use requires the explicit --query-osv flag."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import urllib.error
import urllib.request


OSV_ENDPOINT = "https://api.osv.dev/v1/querybatch"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _name(value: str) -> str:
    normalized = re.sub(r"[-_.]+", "-", value.strip()).lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", normalized) is None:
        raise ValueError
    return normalized


def inventory(requirements: Path) -> tuple[list[tuple[str, str]], dict[str, object]]:
    installed: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = _name(str(distribution.metadata["Name"]))
        version = str(distribution.version)
        if not version or len(version) > 128 or any(character.isspace() for character in version):
            raise ValueError
        if name in installed and installed[name] != version:
            raise ValueError
        installed[name] = version
    packages = sorted(installed.items())
    direct = {}
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s]+)", line)
        if match is None:
            raise ValueError
        name = _name(match.group(1))
        if name in direct:
            raise ValueError
        direct[name] = match.group(2)
    mismatches = [
        {"name": name, "expected": version, "actual": installed.get(name)}
        for name, version in sorted(direct.items())
        if installed.get(name) != version
    ]
    digest_source = "".join(f"{name}=={version}\n" for name, version in packages).encode("ascii")
    summary = {
        "installed_count": len(packages),
        "direct_pin_count": len(direct),
        "direct_pin_mismatches": mismatches,
        "inventory_digest": "sha256:" + hashlib.sha256(digest_source).hexdigest(),
    }
    return packages, summary


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _decode_osv_response(content: bytes):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    return json.loads(content.decode("utf-8"), object_pairs_hook=unique)


def query_osv(packages: list[tuple[str, str]]) -> list[dict[str, object]]:
    payload = json.dumps(
        {
            "queries": [
                {"package": {"ecosystem": "PyPI", "name": name}, "version": version}
                for name, version in packages
            ]
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    request = urllib.request.Request(
        OSV_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    with opener.open(request, timeout=20) as response:
        if response.status != 200 or response.url != OSV_ENDPOINT:
            raise ValueError
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError
    value = _decode_osv_response(content)
    results = value.get("results") if type(value) is dict else None
    if type(results) is not list or len(results) != len(packages):
        raise ValueError
    matches = []
    for (name, version), result in zip(packages, results, strict=True):
        if type(result) is not dict or result.get("next_page_token") is not None:
            raise ValueError
        vulnerabilities = result.get("vulns", [])
        if type(vulnerabilities) is not list:
            raise ValueError
        identifiers = sorted({
            str(item.get("id"))
            for item in vulnerabilities
            if type(item) is dict and re.fullmatch(r"[A-Za-z0-9-]{3,96}", str(item.get("id")))
        })
        if len(identifiers) != len(vulnerabilities):
            raise ValueError
        if identifiers:
            matches.append({"name": name, "version": version, "vulnerability_ids": identifiers})
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    parser.add_argument("--query-osv", action="store_true")
    values = parser.parse_args(argv)
    try:
        packages, summary = inventory(values.requirements)
        result = {
            "schema": "nobus-m1-dependency-audit-1",
            "status": "INVENTORY_ONLY",
            "service": None,
            **summary,
        }
        code = 0
        if values.query_osv:
            matches = query_osv(packages)
            result.update(
                status="REVIEW" if matches else "PASS_NO_KNOWN_MATCHES",
                service=OSV_ENDPOINT,
                matches=matches,
            )
            code = 2 if matches else 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, urllib.error.URLError):
        result = {
            "schema": "nobus-m1-dependency-audit-1",
            "status": "FAIL",
            "error_class": "dependency_audit_unavailable",
        }
        code = 1
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
