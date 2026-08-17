#!/usr/bin/env python3
"""Verify frozen Code incident artifacts against their immutable raw URLs.

This is an explicit maintainer verification path, not runtime acquisition and
not evidence of governed adapter delivery.  Network reads are gated behind an
explicit ``--allow-network`` opt-in on the command line: ``--help`` and the
no-argument default invocation never call ``urlopen``.  Only ``--allow-network``
authorizes the four revision-pinned raw.githubusercontent.com reads (the
report, the affected code file, and the two MIT license files) and checks
byte count, raw SHA-256, and Git blob identity for each.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from core.engine.code_intelligence.incident_source import bundled_tbtc_incident_fixture_text

_ALLOWED_HOST = "raw.githubusercontent.com"
_MAX_ARTIFACT_BYTES = 1_000_000


def artifact_facts(payload: bytes) -> dict[str, int | str]:
    """Return independently reproducible raw and Git-blob identities."""

    git_material = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    return {
        "byte_count": len(payload),
        "raw_sha256": f"sha256:{hashlib.sha256(payload).hexdigest()}",
        "git_blob_sha": hashlib.sha1(git_material, usedforsecurity=False).hexdigest(),
    }


def verify_artifact_bytes(*, payload: bytes, expected: dict[str, Any], digest_field: str) -> dict[str, int | str]:
    """Fail unless bytes match all three independently frozen identities."""

    facts = artifact_facts(payload)
    expected_facts = {
        "byte_count": expected["byte_count"],
        "raw_sha256": expected[digest_field],
        "git_blob_sha": expected["git_blob_sha"],
    }
    if facts != expected_facts:
        raise ValueError(f"immutable artifact mismatch: expected {expected_facts!r}, observed {facts!r}")
    return facts


def verify_span(
    *,
    payload: bytes,
    line_start: int,
    line_end: int,
    expected_excerpt: str,
    expected_digest: str,
) -> str:
    """Verify a 1-based inclusive UTF-8 line span with no terminal newline."""

    if line_start < 1 or line_end < line_start or line_end - line_start + 1 > 500:
        raise ValueError("immutable span uses invalid or unbounded line coordinates")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("immutable artifact is not UTF-8") from exc
    if line_end > len(lines):
        raise ValueError("immutable span exceeds artifact line count")
    excerpt = "\n".join(lines[line_start - 1 : line_end])
    digest = f"sha256:{hashlib.sha256(excerpt.encode('utf-8')).hexdigest()}"
    if excerpt != expected_excerpt or digest != expected_digest:
        raise ValueError("immutable source span differs from the frozen excerpt and digest")
    return digest


def _fetch_exact_raw_url(url: str) -> bytes:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _ALLOWED_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("fixture verifier accepts only exact credential-free raw.githubusercontent.com URLs")
    request = Request(url, headers={"User-Agent": "ACE-Code-Incident-Fixture-Verifier/1"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - exact allowlisted HTTPS host above
        if response.geturl() != url:
            raise ValueError("immutable raw URL redirected")
        payload = response.read(_MAX_ARTIFACT_BYTES + 1)
    if len(payload) > _MAX_ARTIFACT_BYTES:
        raise ValueError("immutable artifact exceeds verifier byte bound")
    return payload


def verify_bundled_fixture() -> dict[str, Any]:
    """Fetch and verify the report and affected code artifacts."""

    fixture = json.loads(bundled_tbtc_incident_fixture_text())
    report = fixture["report"]
    coordinate = next(
        section["code_coordinate"]
        for section in fixture["sections"]
        if section["kind"] == "source_declared_code_coordinate"
    )
    report_bytes = _fetch_exact_raw_url(report["raw_url"])
    code_bytes = _fetch_exact_raw_url(coordinate["raw_url"])
    timeline = next(section for section in fixture["sections"] if section["kind"] == "timeline_only")
    declaration = next(
        section for section in fixture["sections"] if section["kind"] == "source_declared_code_coordinate"
    )
    result: dict[str, Any] = {
        "report": verify_artifact_bytes(
            payload=report_bytes,
            expected=report,
            digest_field="content_sha256",
        ),
        "code": verify_artifact_bytes(
            payload=code_bytes,
            expected=coordinate,
            digest_field="file_sha256",
        ),
        "spans": {
            "report_timeline": verify_span(
                payload=report_bytes,
                line_start=timeline["source_line_start"],
                line_end=timeline["source_line_end"],
                expected_excerpt=timeline["excerpt"],
                expected_digest=timeline["excerpt_sha256"],
            ),
            "report_declaration": verify_span(
                payload=report_bytes,
                line_start=declaration["source_line_start"],
                line_end=declaration["source_line_end"],
                expected_excerpt=declaration["excerpt"],
                expected_digest=declaration["excerpt_sha256"],
            ),
            "code_coordinate": verify_span(
                payload=code_bytes,
                line_start=coordinate["line_start"],
                line_end=coordinate["line_end"],
                expected_excerpt=coordinate["excerpt"],
                expected_digest=coordinate["excerpt_sha256"],
            ),
        },
    }
    result["licenses"] = {}
    for license_anchor in fixture["licenses"]:
        license_bytes = _fetch_exact_raw_url(license_anchor["raw_url"])
        facts = verify_artifact_bytes(
            payload=license_bytes,
            expected=license_anchor,
            digest_field="content_sha256",
        )
        license_text = license_bytes.decode("utf-8")
        if (
            license_anchor["copyright_notice"] not in license_text
            or "Permission is hereby granted, free of charge" not in license_text
            or 'THE SOFTWARE IS PROVIDED "AS IS"' not in license_text
        ):
            raise ValueError("immutable license bytes do not contain the frozen MIT notice")
        result["licenses"][license_anchor["scope"]] = facts
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_code_incident_fixture.py",
        description=(
            "Verify the frozen Code incident fixture against its immutable, revision-pinned "
            "raw.githubusercontent.com URLs. This performs live network reads and is an explicit, "
            "opt-in maintainer action, not part of any runtime or default developer workflow."
        ),
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help=(
            "Explicitly authorize the four revision-pinned raw.githubusercontent.com reads "
            "(the report, the affected code file, and the two MIT license files) required to "
            "verify the fixture. Without this flag, no network reads are performed."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.allow_network:
        print(
            "incident fixture verification requires explicit --allow-network opt-in; no network reads were performed",
            file=sys.stderr,
        )
        return 2
    try:
        result = verify_bundled_fixture()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"incident fixture verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
