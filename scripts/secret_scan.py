#!/usr/bin/env python3
"""Brand-free secret gate for ACE core — the pre-commit line of defense.

ACE core is developed in the open, so a committed credential lands in a public
repo. This scanner blocks that class of mistake and nothing else: API keys,
private-key blocks, tokens, connection strings with embedded credentials, LAN
IPs, absolute home paths, and secret-shaped files. It is deliberately GENERIC —
no company, product, or personal identifiers — because it ships publicly, and a
detector that spelled the private terms it looks for would disclose them.

Usage (pre-commit passes staged files as argv):
    python scripts/secret_scan.py FILE [FILE ...]
    python scripts/secret_scan.py            # no args: scan the staged diff

Suppress a known-safe line (a documented placeholder, a redaction example) with
a trailing ``# secret-scan: allow`` comment on that line.
"""

from __future__ import annotations

import fnmatch
import math
import re
import subprocess
import sys
from pathlib import Path

ALLOW_MARKER = "secret-scan: allow"

# Known-safe occurrences: key-shape DETECTION code, documented placeholder shapes,
# and synthetic test fixtures (fake keys/paths). (path, pattern | None); None = any
# pattern in that file. Mirrors the credential half of the private export scanner's
# allowlist. A NEW real secret elsewhere still fails loud; suppress a one-off with a
# trailing `# secret-scan: allow`.
ALLOWLIST: list[tuple[str, str | None]] = [
    ("scripts/secret_scan.py", None),  # the scanner necessarily contains every detector literal
    ("*.data/data/share/doc/ace/docs/providers.md", "anthropic-key"),  # installed copy of public key-shape docs
    ("core/engine/core/llm.py", "anthropic-key"),  # `key.startswith("sk-ant-...")` — the literal IS the feature
    ("docs/providers.md", "anthropic-key"),  # documents the key shapes
    ("tests/test_llm.py", "anthropic-key"),  # synthetic "sk-ant-" + "r"*40 fixtures
    ("tests/test_llm.py", "openai-key"),  # synthetic "sk-proj-" + "o"*40 fixtures
    ("tests/test_cli_provider.py", "anthropic-key"),  # synthetic key fixtures
    ("tests/test_hardening.py", None),  # tests a secret detector — every fixture is fake by design
    ("tests/test_graph_events.py", "home-path"),  # /home/user/... example paths in event fixtures
    ("tests/test_runtime_bridge.py", "home-path"),  # /home/user/... example stack-trace fixtures
]


def _allowlisted(rel: str, name: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(rel, path) and (pat is None or pat == name) for path, pat in ALLOWLIST)


# --- Secret / credential shapes (shape- and name-gated to avoid false alarms) --
CONTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic-key", re.compile(r"sk-ant-")),
    ("openai-key", re.compile(r"sk-proj-")),
    ("openai-key-classic", re.compile(r"\bsk-[A-Za-z0-9]{48}\b")),
    ("github-token", re.compile(r"\b(?:ghp_|gho_|github_pat_)")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-block", re.compile(r"-----BEGIN .*PRIVATE KEY")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.")),
    ("slack-token", re.compile(r"xox[baprs]-")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    (
        "discord-bot-token",
        re.compile(r"\b[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}\b"),
    ),
    # scheme://user:pass@host, excluding textbook placeholder pairs.
    (
        "connection-string-credentials",
        re.compile(
            r"[a-z][a-z0-9+.-]*://"
            r"(?!(?i:user:pass|user:password|username:password|admin:password|foo:bar)@)"
            r"[^/\s:@]+:[^/\s:@]+@"
        ),
    ),
    # Long hex assigned to a credential-shaped NAME — the one shape entropy
    # cannot see (hex maxes at 4.0 bits/char). Identifier-boundary on the left
    # and a not-a-path-tail guard keep git SHAs / lockfile hashes clean.
    (
        "hex-credential",
        re.compile(
            r"(?:(?<![A-Za-z0-9])|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z]))(?<!/)"
            r"(?i:secret|key|token|password|passwd|pwd|jwt|credential)"
            r"[\"']?\s*[:=]\s*[\"']?"
            r"[0-9a-fA-F]{32,}(?![0-9a-zA-Z])"
        ),
    ),
    # Private infrastructure — generic, never a named person or host.
    ("lan-ip-192", re.compile(r"192\.168\.\d")),
    ("lan-ip-10", re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    ("lan-ip-172", re.compile(r"\b172\.(?:1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}\b")),
    # Any absolute home path (don't commit your local machine's paths).
    ("home-path", re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")),
]

# --- Entropy backstop for unknown-shape secrets, gated to credential-suggestive
# key=value assignments (bare entropy scanning is unusable on a real repo). ----
_ENTROPY_MIN_LENGTH = 32
_ENTROPY_MIN_BITS = 4.0
_ASSIGN_RX = re.compile(
    r"(?i:secret|key|token|password|passwd|pwd|jwt|credential|api[_-]?key|auth)"
    r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9+/_-]{" + str(_ENTROPY_MIN_LENGTH) + r",}={0,2})[\"']?"
)

# Secret-shaped file paths that must never be committed. `.env.example` is the
# sanctioned template and is exempt.
BANNED_PATH_GLOBS = [
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "**/*.pem",
    "*.key",
    "**/*.key",
    "id_rsa*",
    "**/id_rsa*",
    "id_ed25519*",
    "**/id_ed25519*",
    "*.p12",
    "**/*.p12",
    "*.pfx",
    "**/*.pfx",
    "*.keystore",
    "**/*.keystore",
    ".npmrc",
    "**/.npmrc",
    ".pypirc",
    "**/.pypirc",
    "credentials",
    "**/credentials",
    "*.token",
    "**/*.token",
    "token.json",
    "**/token.json",
]
PATH_ALLOW = {".env.example"}

_BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".ttf", ".zip", ".lock"}


def _shannon_bits(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _path_banned(rel: str) -> bool:
    name = Path(rel).name
    if name in PATH_ALLOW:
        return False
    posix = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(posix, g) or fnmatch.fnmatch(name, g) for g in BANNED_PATH_GLOBS)


def scan_file(rel: str) -> list[str]:
    findings: list[str] = []
    if _path_banned(rel):
        findings.append(f"{rel}:0 [secret-file] a secret-shaped file must not be committed")
    if Path(rel).suffix.lower() in _BINARY_EXT:
        return findings
    try:
        text = Path(rel).read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return findings  # unreadable / binary — path check above still applied
    for i, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for name, rx in CONTENT_PATTERNS:
            if rx.search(line) and not _allowlisted(rel, name):
                findings.append(f"{rel}:{i} [{name}] {line.strip()[:120]}")
        m = _ASSIGN_RX.search(line)
        if m and _shannon_bits(m.group(1)) > _ENTROPY_MIN_BITS and not _allowlisted(rel, "high-entropy-secret"):
            findings.append(f"{rel}:{i} [high-entropy-secret] {line.strip()[:120]}")
    return findings


def _staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in out.splitlines() if p.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    files = argv or _staged_files()
    findings: list[str] = []
    for f in files:
        if Path(f).is_file():
            findings.extend(scan_file(f))
    if findings:
        print("secret-scan: BLOCKED — potential secret(s) in staged changes:\n", file=sys.stderr)
        for line in findings:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nRemove the secret (rotate it if it was ever real). If this is a documented\n"
            "placeholder or a redaction example, append '# secret-scan: allow' to the line.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
