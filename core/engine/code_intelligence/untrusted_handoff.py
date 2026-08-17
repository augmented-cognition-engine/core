"""Bounded admission for Code Intelligence handoffs from untrusted Git trees.

Repository bytes are evidence, never controller instructions.  This additive
profile reads immutable ``HEAD`` blobs, creates a filtered disposable Git tree,
then wraps the settled Code Intelligence journey without changing its contracts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from git import Actor, Repo
from pydantic import Field, field_validator, model_validator

from core.engine.code_intelligence.contracts import (
    CodeIntelligenceJourneyV1Alpha1,
    CodingAgentReturnV1Alpha1,
    FrozenContract,
    raw_digest,
    stable_digest,
    stable_id,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return
from core.engine.code_intelligence.journey import CodeIntelligenceJourney
from core.engine.intelligence.graph_builder import GraphBuilder

UNTRUSTED_TREE_ENTRY_LIMIT = 20_000
UNTRUSTED_CANDIDATE_FILE_LIMIT = 2_000
UNTRUSTED_CANDIDATE_TOTAL_BYTES_LIMIT = 32 * 1024 * 1024
UNTRUSTED_BLOB_BYTES_LIMIT = 500_000
UNTRUSTED_PATH_BYTES_LIMIT = 1_024
UNTRUSTED_PATH_DEPTH_LIMIT = 32
UNTRUSTED_PATH_SEGMENT_BYTES_LIMIT = 255
UNTRUSTED_CONTEXT_FILE_LIMIT = 8
UNTRUSTED_CONTEXT_BYTES_LIMIT = 24_000
UNTRUSTED_RETURN_JSON_BYTES_LIMIT = 128 * 1024

_SCOPE_ITEM_LIMIT = 64
_WRITE_PATH_LIMIT = 8
_DECISION_LIMIT = 2_000
_HEX_OBJECT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GLOB_CHARS = frozenset("*?[]{}")
_SUPPORTED_SUFFIXES = frozenset({".py", ".pyi", ".md", ".txt", ".toml", ".json", ".yaml", ".yml"})
_SKIP_SEGMENTS = frozenset(
    {
        ".git",
        ".hg",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
        "egg-info",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        ".cargo",
        "coverage",
        ".coverage",
        "generated",
        ".claude",
        "claude-repo",
    }
)
_LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"
_LFS_POINTER = re.compile(rb"^version https://git-lfs\.github\.com/spec/v1\r?\n")
_FILTERED_COMMIT_MESSAGE = "ACE deterministic filtered untrusted repository"
_FILTERED_ACTOR = "ACE Deterministic Admission <admission@invalid>"
_FILTERED_TIMESTAMP = "946684800 +0000"
_FILTERED_GENERATED_AT = datetime(2000, 1, 1, tzinfo=timezone.utc)
_ISOLATED_JOURNEY_REQUEST_BYTES_LIMIT = 64 * 1024
_ISOLATED_JOURNEY_RESPONSE_BYTES_LIMIT = 4 * 1024 * 1024
_ISOLATED_JOURNEY_TIMEOUT_SECONDS = 60
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pem_private_key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("github_token", re.compile(r"\b(?:ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("aws_access_key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    (
        "aws_secret_key",
        re.compile(r"(?im)\baws[_-]?secret[_-]?(?:access[_-]?)?key\b\s*[:=]\s*['\"]?([^\s'\"#,;]{12,})"),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?im)\b(?:api[_-]?key|access[_-]?token|secret|password|anthropic[_-]?api[_-]?key)\b"
            r"\s*[:=]\s*['\"]?([^\s'\"#,;]{8,})"
        ),
    ),
)
_PLACEHOLDERS = frozenset(
    {
        "placeholder",
        "changeme",
        "example",
        "dummy",
        "redacted",
        "test-only",
        "your-key-here",
        "not-a-secret",
    }
)

MaterialReason = Literal[
    "outside_controller_read_scope",
    "generated_or_vendor",
    "unsupported_extension",
    "binary_or_nul",
    "invalid_utf8",
    "control_text",
    "recognized_secret",
    "symlink",
    "submodule",
    "special_mode",
    "lfs_pointer",
    "resource_limit",
    "path_invalid",
]


def _canonical_path(value: str) -> str:
    if not value or value != unicodedata.normalize("NFC", value):
        raise ValueError("repository scope contains a non-canonical path")
    if "\\" in value or any(char in value for char in _GLOB_CHARS):
        raise ValueError("repository scope contains a forbidden path form")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ValueError("repository scope contains a control path")
    path = PurePosixPath(value)
    parts = path.parts
    if path.is_absolute() or not parts or value != path.as_posix() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("repository scope path is not canonical relative POSIX")
    encoded = value.encode("utf-8", errors="strict")
    if len(encoded) > UNTRUSTED_PATH_BYTES_LIMIT or len(parts) > UNTRUSTED_PATH_DEPTH_LIMIT:
        raise ValueError("repository scope path exceeds its fixed bound")
    if any(len(part.encode("utf-8")) > UNTRUSTED_PATH_SEGMENT_BYTES_LIMIT for part in parts):
        raise ValueError("repository scope path segment exceeds its fixed bound")
    return value


def _in_read_scope(path: str, scope: ControllerRepositoryScopeV1Alpha1) -> bool:
    return path in scope.read_paths or any(
        path == prefix or path.startswith(prefix + "/") for prefix in scope.read_prefixes
    )


class UntrustedRepositoryPolicyV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.untrusted-repository-policy/v1alpha1"] = (
        "ace.code-intelligence.untrusted-repository-policy/v1alpha1"
    )
    tree_entry_limit: Literal[20_000] = UNTRUSTED_TREE_ENTRY_LIMIT
    candidate_file_limit: Literal[2_000] = UNTRUSTED_CANDIDATE_FILE_LIMIT
    candidate_total_bytes_limit: Literal[33_554_432] = UNTRUSTED_CANDIDATE_TOTAL_BYTES_LIMIT
    blob_bytes_limit: Literal[500_000] = UNTRUSTED_BLOB_BYTES_LIMIT
    path_bytes_limit: Literal[1_024] = UNTRUSTED_PATH_BYTES_LIMIT
    path_depth_limit: Literal[32] = UNTRUSTED_PATH_DEPTH_LIMIT
    path_segment_bytes_limit: Literal[255] = UNTRUSTED_PATH_SEGMENT_BYTES_LIMIT
    context_file_limit: Literal[8] = UNTRUSTED_CONTEXT_FILE_LIMIT
    context_bytes_limit: Literal[24_000] = UNTRUSTED_CONTEXT_BYTES_LIMIT
    return_json_bytes_limit: Literal[131_072] = UNTRUSTED_RETURN_JSON_BYTES_LIMIT
    head_only: Literal[True] = True
    clean_required: Literal[True] = True
    strict_utf8: Literal[True] = True
    working_tree_material_permitted: Literal[False] = False
    generated_vendor_material_permitted: Literal[False] = False
    binary_material_permitted: Literal[False] = False
    recognized_secret_policy: Literal["ace.code-intelligence.recognized-secret-patterns/v1"] = (
        "ace.code-intelligence.recognized-secret-patterns/v1"
    )

    @property
    def policy_id(self) -> str:
        return stable_id("untrusted_repository_policy", self)


class ControllerRepositoryScopeV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.controller-repository-scope/v1alpha1"] = (
        "ace.code-intelligence.controller-repository-scope/v1alpha1"
    )
    repository_ref: str = Field(min_length=1, max_length=256)
    query: str = Field(min_length=1, max_length=4_000)
    target_path: str
    receiver_ref: str = Field(min_length=1, max_length=256)
    read_prefixes: tuple[str, ...]
    read_paths: tuple[str, ...] = ()
    write_paths: tuple[str, ...]

    @field_validator("target_path")
    @classmethod
    def target_is_canonical(cls, value: str) -> str:
        return _canonical_path(value)

    @field_validator("read_prefixes", "read_paths", "write_paths")
    @classmethod
    def paths_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_canonical_path(value) for value in values)

    @model_validator(mode="after")
    def bounded_and_closed(self) -> Self:
        for label, values, limit in (
            ("read_prefixes", self.read_prefixes, _SCOPE_ITEM_LIMIT),
            ("read_paths", self.read_paths, _SCOPE_ITEM_LIMIT),
            ("write_paths", self.write_paths, _WRITE_PATH_LIMIT),
        ):
            if len(values) > limit or len(set(values)) != len(values):
                raise ValueError(f"controller {label} is duplicate or exceeds its fixed bound")
        if not self.read_prefixes and not self.read_paths:
            raise ValueError("controller read scope is empty")
        if not self.write_paths or self.target_path not in self.write_paths:
            raise ValueError("target path must be an exact permitted write path")
        if any(not _in_read_scope(path, self) for path in self.write_paths):
            raise ValueError("every write path must fall within controller read scope")
        return self

    @property
    def scope_id(self) -> str:
        return stable_id("controller_repository_scope", self)


class UntrustedRepositoryMaterialDecisionV1Alpha1(FrozenContract):
    path: str
    git_blob_id: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    body_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_TOTAL_BYTES_LIMIT)
    disposition: Literal["admitted", "excluded", "blocked"]
    reason: MaterialReason | None = None
    recognized_secret_categories: tuple[str, ...] = ()
    body_exposed: Literal[False] = False

    @field_validator("path")
    @classmethod
    def canonical_material_path(cls, value: str) -> str:
        return _canonical_path(value)

    @model_validator(mode="after")
    def exact_disposition(self) -> Self:
        if (self.disposition == "admitted") != (self.reason is None):
            raise ValueError("material decision reason differs from disposition")
        if self.disposition == "admitted" and self.body_digest is None:
            raise ValueError("admitted material requires an exact body digest")
        if self.recognized_secret_categories and self.reason != "recognized_secret":
            raise ValueError("secret categories require recognized-secret disposition")
        if len(self.recognized_secret_categories) > len(_SECRET_PATTERNS):
            raise ValueError("recognized-secret category list exceeds policy bound")
        return self


class UntrustedRepositoryMaterialReceiptV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.untrusted-repository-material/v1alpha1"] = (
        "ace.code-intelligence.untrusted-repository-material/v1alpha1"
    )
    repository_ref: str
    source_head_revision: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    source_head_tree: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    source_clean: Literal[True] = True
    policy_id: str
    scope_id: str
    tree_entry_count: int = Field(ge=0, le=UNTRUSTED_TREE_ENTRY_LIMIT)
    candidate_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_FILE_LIMIT)
    candidate_byte_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_TOTAL_BYTES_LIMIT)
    admitted_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_FILE_LIMIT)
    admitted_byte_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_TOTAL_BYTES_LIMIT)
    excluded_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_FILE_LIMIT)
    blocked_count: int = Field(ge=0, le=UNTRUSTED_CANDIDATE_FILE_LIMIT)
    decisions: tuple[UntrustedRepositoryMaterialDecisionV1Alpha1, ...]
    admitted_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    excluded_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    recognized_secret_findings: int = Field(ge=0)
    raw_secret_material_retained: Literal[False] = False
    working_tree_body_read: Literal[False] = False

    @model_validator(mode="after")
    def exact_counts(self) -> Self:
        if len(self.decisions) > _DECISION_LIMIT:
            raise ValueError("material decisions exceed fixed bound")
        decision_paths = tuple(item.path for item in self.decisions)
        if len(set(decision_paths)) != len(decision_paths):
            raise ValueError("material decision paths must be unique")
        if decision_paths != tuple(sorted(decision_paths)):
            raise ValueError("material decision paths must be in canonical order")
        if self.candidate_count > self.tree_entry_count:
            raise ValueError("material candidate count exceeds source tree entries")
        admitted = tuple(item for item in self.decisions if item.disposition == "admitted")
        excluded = tuple(item for item in self.decisions if item.disposition == "excluded")
        blocked = tuple(item for item in self.decisions if item.disposition == "blocked")
        if (len(admitted), len(excluded), len(blocked)) != (
            self.admitted_count,
            self.excluded_count,
            self.blocked_count,
        ):
            raise ValueError("material receipt decision counts differ")
        if sum(item.byte_count for item in admitted) != self.admitted_byte_count:
            raise ValueError("material receipt admitted byte count differs")
        if self.candidate_count != len(self.decisions):
            raise ValueError("material receipt candidate count differs from decisions")
        if self.candidate_byte_count != sum(item.byte_count for item in self.decisions):
            raise ValueError("material receipt candidate byte count differs from decisions")
        admitted_rows = tuple(item.model_dump(mode="json") for item in admitted)
        excluded_rows = tuple(item.model_dump(mode="json") for item in excluded)
        if self.admitted_manifest_digest != stable_digest(admitted_rows):
            raise ValueError("material receipt admitted manifest digest differs")
        if self.excluded_manifest_digest != stable_digest(excluded_rows):
            raise ValueError("material receipt excluded manifest digest differs")
        if sum(len(item.recognized_secret_categories) for item in self.decisions) != self.recognized_secret_findings:
            raise ValueError("material receipt secret finding count differs")
        return self

    @property
    def receipt_id(self) -> str:
        return stable_id("untrusted_repository_material", self)


class UntrustedRepositoryEvidenceRoleV1Alpha1(FrozenContract):
    block_id: str
    path: str
    body_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    block_body_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_role: Literal["untrusted_repository_evidence"] = "untrusted_repository_evidence"
    may_supply_instructions: Literal[False] = False
    may_change_controller_scope: Literal[False] = False


class UntrustedRepositoryHandoffV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.untrusted-repository-handoff/v1alpha1"] = (
        "ace.code-intelligence.untrusted-repository-handoff/v1alpha1"
    )
    policy: UntrustedRepositoryPolicyV1Alpha1
    controller_scope: ControllerRepositoryScopeV1Alpha1
    material_receipt: UntrustedRepositoryMaterialReceiptV1Alpha1
    journey: CodeIntelligenceJourneyV1Alpha1
    source_head_revision: str
    source_head_tree: str
    filtered_workspace_revision: str
    filtered_workspace_tree: str
    filtered_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    base_index_id: str
    base_lens_id: str
    base_manifest_id: str
    base_handoff_id: str
    evidence_roles: tuple[UntrustedRepositoryEvidenceRoleV1Alpha1, ...]
    delivered_read_paths: tuple[str, ...]
    permitted_write_paths: tuple[str, ...]
    repository_text_is_evidence: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    effect_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    execution_authority_revalidation_required: Literal[True] = True

    @model_validator(mode="after")
    def exact_chain(self) -> Self:
        lens = self.journey.lens
        handoff = self.journey.handoff
        expected = (
            lens.index.index_id,
            lens.lens_id,
            handoff.manifest.manifest_id,
            handoff.receipt.handoff_id,
        )
        if expected != (self.base_index_id, self.base_lens_id, self.base_manifest_id, self.base_handoff_id):
            raise ValueError("untrusted handoff base identities are crossed")
        if self.policy.policy_id != self.material_receipt.policy_id:
            raise ValueError("untrusted handoff policy identity differs")
        if self.controller_scope.scope_id != self.material_receipt.scope_id:
            raise ValueError("untrusted handoff controller scope differs")
        if self.controller_scope.repository_ref != self.material_receipt.repository_ref:
            raise ValueError("untrusted handoff repository reference differs")
        expected_repository = "repository/" + stable_digest(self.controller_scope.repository_ref).split(":", 1)[1]
        if self.journey.lens.index.repository != expected_repository:
            raise ValueError("untrusted handoff journey repository identity differs")
        if self.journey.lens.query != self.controller_scope.query:
            raise ValueError("untrusted handoff query differs from controller scope")
        if self.journey.lens.target_path != self.controller_scope.target_path:
            raise ValueError("untrusted handoff target differs from controller scope")
        if self.journey.handoff.receipt.receiver_ref != self.controller_scope.receiver_ref:
            raise ValueError("untrusted handoff receiver differs from controller scope")
        if self.journey.handoff.receipt.requested_change != self.controller_scope.query:
            raise ValueError("untrusted handoff requested change differs from controller scope")
        if (self.source_head_revision, self.source_head_tree) != (
            self.material_receipt.source_head_revision,
            self.material_receipt.source_head_tree,
        ):
            raise ValueError("untrusted handoff source identity differs")
        admitted_digests = {
            item.path: item.body_digest for item in self.material_receipt.decisions if item.disposition == "admitted"
        }
        expected_roles = tuple(
            UntrustedRepositoryEvidenceRoleV1Alpha1(
                block_id=block.block_id,
                path=block.path,
                body_digest=admitted_digests[block.path],
                block_body_digest=block.body_digest,
            )
            for block in handoff.blocks
            if block.path in admitted_digests
        )
        if self.evidence_roles != expected_roles:
            raise ValueError("untrusted handoff evidence roles differ from exact blocks")
        paths = tuple(block.path for block in handoff.blocks)
        if self.delivered_read_paths != paths:
            raise ValueError("untrusted handoff delivered paths differ from exact blocks")
        if any(not _in_read_scope(path, self.controller_scope) for path in paths):
            raise ValueError("untrusted handoff delivered a path outside controller read scope")
        admitted = {item.path for item in self.material_receipt.decisions if item.disposition == "admitted"}
        if self.material_receipt.blocked_count != 0:
            raise ValueError("successful untrusted handoff cannot contain blocked material")
        if any(path not in admitted for path in self.controller_scope.write_paths):
            raise ValueError("untrusted handoff write targets must be admitted material")
        if any(path not in admitted for path in paths):
            raise ValueError("untrusted handoff delivered material that was not admitted")
        if any(admitted_digests.get(role.path) != role.body_digest for role in self.evidence_roles):
            raise ValueError("untrusted handoff evidence digest differs from admitted material")
        if self.permitted_write_paths != self.controller_scope.write_paths:
            raise ValueError("untrusted handoff write scope differs from controller scope")
        if self.filtered_manifest_digest != self.material_receipt.admitted_manifest_digest:
            raise ValueError("untrusted handoff filtered manifest differs from admitted material")
        if self.journey.lens.index.revision != self.filtered_workspace_revision:
            raise ValueError("untrusted handoff journey revision differs from filtered workspace")
        if self.journey.lens.index.dirty or self.journey.lens.index.working_tree_digest != "clean":
            raise ValueError("untrusted handoff journey index is not the clean filtered workspace")
        if self.filtered_workspace_revision != _filtered_commit_id(self.filtered_workspace_tree):
            raise ValueError("untrusted handoff filtered revision does not bind its exact tree")
        return self

    @property
    def packet_id(self) -> str:
        return stable_id("untrusted_repository_handoff", self)


@dataclass(frozen=True)
class PreparedUntrustedRepositoryHandoff:
    packet: UntrustedRepositoryHandoffV1Alpha1
    workspace_root: Path


class UntrustedRepositoryReturnReceiptV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.untrusted-repository-return/v1alpha1"] = (
        "ace.code-intelligence.untrusted-repository-return/v1alpha1"
    )
    packet_id: str
    policy_id: str
    scope_id: str
    material_receipt_id: str
    source_head_revision: str
    source_head_tree: str
    filtered_workspace_revision: str
    filtered_workspace_tree: str
    base_index_id: str
    base_lens_id: str
    base_manifest_id: str
    base_handoff_id: str
    return_id: str
    base_return_receipt_id: str
    consumed_block_ids: tuple[str, ...]
    changed_paths: tuple[str, ...]
    disposition: Literal["change_proposed", "no_change_recommended", "blocked"]
    validated_at: datetime
    strict_return_validated: Literal[True] = True
    persistence_performed: Literal[False] = False
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @property
    def receipt_id(self) -> str:
        return stable_id(
            "untrusted_repository_return",
            self.model_dump(exclude={"validated_at", "base_return_receipt_id"}),
        )


def _repo_is_clean(repo: Repo, *, entry_limit: int = UNTRUSTED_TREE_ENTRY_LIMIT) -> bool:
    """Fail closed from HEAD, index, and filesystem metadata only.

    No Git status/diff/config operation is used, so repository or host filters,
    diff drivers, fsmonitor hooks, credentials, and config includes cannot run.
    Working-tree bodies are never opened. A tracked metadata mismatch rejects;
    immutable HEAD objects remain the only source of delivered bytes.
    """

    try:
        index_entries = repo.index.entries
        if any(stage != 0 for _path, stage in index_entries):
            return False
        indexed = {str(path): entry for (path, _stage), entry in index_entries.items()}
        headed: dict[str, tuple[str, int, int]] = {}
        for number, item in enumerate(repo.head.commit.tree.traverse(), start=1):
            if number > entry_limit:
                return False
            if getattr(item, "type", "") != "tree":
                size = int(getattr(item, "size", 0))
                headed[str(item.path)] = (str(item.hexsha), int(item.mode), size)
        if set(indexed) != set(headed):
            return False

        root = Path(repo.working_tree_dir or "")
        for path, entry in indexed.items():
            head_sha, head_mode, head_size = headed[path]
            if entry.hexsha != head_sha or int(entry.mode) != head_mode:
                return False
            try:
                observed = (root / path).lstat()
            except OSError:
                return False
            expected_mode = int(entry.mode)
            if expected_mode == 0o120000:
                if not stat.S_ISLNK(observed.st_mode):
                    return False
            elif expected_mode == 0o160000:
                if not stat.S_ISDIR(observed.st_mode):
                    return False
            elif not stat.S_ISREG(observed.st_mode):
                return False
            if expected_mode not in {0o120000, 0o160000}:
                if bool(observed.st_mode & stat.S_IXUSR) != bool(expected_mode & 0o100):
                    return False
            if expected_mode != 0o160000 and observed.st_size != head_size:
                return False
            if expected_mode != 0o160000:
                if entry.mtime == (0, 0) or entry.ctime == (0, 0):
                    return False
                indexed_mtime_ns = entry.mtime[0] * 1_000_000_000 + entry.mtime[1]
                indexed_ctime_ns = entry.ctime[0] * 1_000_000_000 + entry.ctime[1]
                if observed.st_mtime_ns != indexed_mtime_ns or observed.st_ctime_ns != indexed_ctime_ns:
                    return False

        seen = 0
        pending = [root]
        while pending:
            directory = pending.pop()
            for item in os.scandir(directory):
                if directory == root and item.name == ".git":
                    continue
                seen += 1
                if seen > entry_limit:
                    return False
                path = Path(item.path)
                relative = path.relative_to(root).as_posix()
                if item.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif relative not in indexed:
                    return False
        return True
    except (OSError, ValueError):
        return False


def _secret_categories(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for category, pattern in _SECRET_PATTERNS:
        matches = tuple(pattern.finditer(text))
        if not matches:
            continue
        if category in {"aws_secret_key", "assigned_secret"}:
            matches = tuple(
                match for match in matches if match.group(1).strip().lower().replace("_", "-") not in _PLACEHOLDERS
            )
        if matches:
            found.append(category)
    return tuple(found)


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("untrusted repository return contains a duplicate JSON key")
        document[key] = value
    return document


def _contains_recognized_secret(value: object) -> bool:
    if isinstance(value, str):
        return bool(_secret_categories(value))
    if isinstance(value, dict):
        return any(_contains_recognized_secret(key) or _contains_recognized_secret(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_recognized_secret(item) for item in value)
    return False


class _IsolatedJourneyRequestV1(FrozenContract):
    contract: Literal["ace.code-intelligence.isolated-journey-request/v1"] = (
        "ace.code-intelligence.isolated-journey-request/v1"
    )
    workspace_root: str = Field(min_length=1, max_length=4_096)
    query: str = Field(min_length=1, max_length=4_000)
    target_path: str
    receiver_ref: str = Field(min_length=1, max_length=256)
    max_context_files: Literal[8] = UNTRUSTED_CONTEXT_FILE_LIMIT
    max_context_bytes: Literal[24_000] = UNTRUSTED_CONTEXT_BYTES_LIMIT

    @field_validator("target_path")
    @classmethod
    def exact_target_path(cls, value: str) -> str:
        return _canonical_path(value)

    @model_validator(mode="after")
    def absolute_workspace(self) -> Self:
        workspace = Path(self.workspace_root)
        if not workspace.is_absolute() or workspace.resolve() != workspace:
            raise ValueError("isolated journey workspace must be an exact absolute path")
        return self


def _build_isolated_journey(request: _IsolatedJourneyRequestV1) -> CodeIntelligenceJourneyV1Alpha1:
    workspace = Path(request.workspace_root)
    journey_builder = CodeIntelligenceJourney(
        workspace,
        max_context_files=request.max_context_files,
        max_context_bytes=request.max_context_bytes,
    )
    graph = GraphBuilder(str(workspace))
    graph.phase1_treesitter()
    fixed_index = journey_builder.index_identity(graph).model_copy(update={"generated_at": _FILTERED_GENERATED_AT})
    return journey_builder.run(
        query=request.query,
        target_path=request.target_path,
        receiver_ref=request.receiver_ref,
        builder=graph,
        expected_index=fixed_index,
    )


def _isolated_journey_helper_main() -> int:
    raw_request = sys.stdin.buffer.read(_ISOLATED_JOURNEY_REQUEST_BYTES_LIMIT + 1)
    if len(raw_request) > _ISOLATED_JOURNEY_REQUEST_BYTES_LIMIT:
        return 2
    try:
        request = _IsolatedJourneyRequestV1.model_validate(
            json.loads(raw_request.decode("utf-8", errors="strict"), object_pairs_hook=_reject_duplicate_pairs)
        )
        journey = _build_isolated_journey(request)
        response = json.dumps(
            {
                "contract": "ace.code-intelligence.isolated-journey-response/v1",
                "module_origin": Path(__file__).resolve().as_posix(),
                "journey": journey.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    except Exception:
        return 2
    if len(response) > _ISOLATED_JOURNEY_RESPONSE_BYTES_LIMIT:
        return 2
    sys.stdout.buffer.write(response)
    return 0


def _run_isolated_journey(
    workspace: Path,
    *,
    query: str,
    target_path: str,
    receiver_ref: str,
) -> CodeIntelligenceJourneyV1Alpha1:
    request = _IsolatedJourneyRequestV1(
        workspace_root=workspace.resolve().as_posix(),
        query=query,
        target_path=target_path,
        receiver_ref=receiver_ref,
    )
    raw_request = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    if len(raw_request) > _ISOLATED_JOURNEY_REQUEST_BYTES_LIMIT:
        raise ValueError("isolated journey request exceeds its fixed bound")
    git_executable = shutil.which("git", path="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")
    if git_executable is None:
        raise ValueError("isolated journey requires the fixed local Git dependency")
    with tempfile.TemporaryDirectory(prefix="ace-isolated-journey-", dir=workspace.parent) as temporary:
        isolation_root = Path(temporary)
        home = isolation_root / "home"
        xdg = isolation_root / "xdg"
        process_tmp = isolation_root / "tmp"
        for directory in (home, xdg, process_tmp):
            directory.mkdir()
        output_path = isolation_root / "response.json"
        environment = {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": "0",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": home.as_posix(),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": str(Path(git_executable).parent),
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": process_tmp.as_posix(),
            "TZ": "UTC",
            "XDG_CONFIG_HOME": xdg.as_posix(),
        }
        try:
            with output_path.open("wb") as output:
                completed = subprocess.run(
                    [sys.executable, "-I", "-m", __name__, "--isolated-journey-helper-v1"],
                    input=raw_request,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    cwd=isolation_root,
                    env=environment,
                    timeout=_ISOLATED_JOURNEY_TIMEOUT_SECONDS,
                    check=False,
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("isolated journey helper failed closed") from exc
        if completed.returncode != 0 or output_path.stat().st_size > _ISOLATED_JOURNEY_RESPONSE_BYTES_LIMIT:
            raise ValueError("isolated journey helper failed closed")
        try:
            document = json.loads(
                output_path.read_bytes().decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_pairs,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("isolated journey helper returned invalid bounded JSON") from exc
    if set(document) != {"contract", "module_origin", "journey"}:
        raise ValueError("isolated journey helper returned an invalid envelope")
    if document["contract"] != "ace.code-intelligence.isolated-journey-response/v1":
        raise ValueError("isolated journey helper returned an invalid contract")
    if document["module_origin"] != Path(__file__).resolve().as_posix():
        raise ValueError("isolated journey helper module origin differs")
    return CodeIntelligenceJourneyV1Alpha1.model_validate(document["journey"])


def _read_head_blob(blob: object) -> bytes:
    size = int(getattr(blob, "size"))
    if size > UNTRUSTED_BLOB_BYTES_LIMIT:
        raise ValueError("resource_limit")
    payload = getattr(blob, "data_stream").read(UNTRUSTED_BLOB_BYTES_LIMIT + 1)
    if len(payload) != size or len(payload) > UNTRUSTED_BLOB_BYTES_LIMIT:
        raise ValueError("resource_limit")
    return payload


def _mode_exclusion(mode: int, entry_type: str) -> MaterialReason | None:
    if mode == 0o160000 or entry_type == "submodule":
        return "submodule"
    if mode == 0o120000:
        return "symlink"
    if mode not in {0o100644, 0o100755}:
        return "special_mode"
    return None


def _classify_text(payload: bytes) -> tuple[str | None, str | None, tuple[str, ...]]:
    digest = raw_digest(payload)
    if _LFS_POINTER.match(payload):
        return "lfs_pointer", digest, ()
    if b"\x00" in payload:
        return "binary_or_nul", digest, ()
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return "invalid_utf8", digest, ()
    if any((ord(char) < 32 and char not in "\t\n\r") or 127 <= ord(char) <= 159 for char in text):
        return "control_text", digest, ()
    secrets = _secret_categories(text)
    if secrets:
        return "recognized_secret", digest, secrets
    return None, digest, ()


def _filtered_commit_id(tree_id: str) -> str:
    body = (
        f"tree {tree_id}\n"
        f"author {_FILTERED_ACTOR} {_FILTERED_TIMESTAMP}\n"
        f"committer {_FILTERED_ACTOR} {_FILTERED_TIMESTAMP}\n"
        f"\n{_FILTERED_COMMIT_MESSAGE}"
    ).encode()
    return hashlib.sha1(b"commit " + str(len(body)).encode() + b"\0" + body).hexdigest()


def _write_filtered_repository(
    workspace: Path,
    admitted: dict[str, bytes],
    write_paths: tuple[str, ...],
    repository_ref: str,
) -> Repo:
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("disposable filtered workspace must be new or empty")
    workspace.mkdir(parents=True, exist_ok=True)
    for relative, payload in sorted(admitted.items()):
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError("short filtered-workspace write")
        finally:
            os.close(descriptor)
    # An explicit empty template prevents host/global ``init.templateDir`` from
    # copying hooks or other material into the disposable repository.  The
    # template lives briefly inside the controller-owned workspace and is
    # removed before any inventory, index, or journey operation.
    empty_template = workspace / ".ace-empty-git-template"
    empty_template.mkdir()
    repo = Repo.init(
        workspace,
        mkdir=False,
        allow_unsafe_options=True,
        template=str(empty_template),
        initial_branch="main",
        object_format="sha1",
    )
    empty_template.rmdir()
    # GitPython's IndexFile.add stores the already-admitted working bytes
    # directly in the object database; it does not invoke Git clean filters.
    # Local values close the remaining identity inputs from host/global config.
    with repo.config_writer() as config:
        config.set_value("core", "hooksPath", os.devnull)
        config.set_value("core", "autocrlf", "false")
        config.set_value("commit", "gpgSign", "false")
        config.set_value("i18n", "commitEncoding", "UTF-8")
        repository_identity = stable_digest(repository_ref).split(":", 1)[1]
        config.set_value('remote "origin"', "url", f"https://ace.invalid/repository/{repository_identity}.git")
        config.set_value('remote "origin"', "fetch", "+refs/heads/*:refs/remotes/origin/*")
    repo.index.add(sorted(admitted))
    actor = Actor("ACE Deterministic Admission", "admission@invalid")
    repo.index.commit(
        _FILTERED_COMMIT_MESSAGE,
        author=actor,
        committer=actor,
        author_date="2000-01-01 00:00:00 +0000",
        commit_date="2000-01-01 00:00:00 +0000",
        parent_commits=[],
        skip_hooks=True,
    )
    if repo.head.commit.hexsha != _filtered_commit_id(repo.head.commit.tree.hexsha):
        raise ValueError("filtered workspace commit identity is not deterministic")
    writable = set(write_paths)
    for relative in admitted:
        os.chmod(workspace / relative, 0o600 if relative in writable else 0o400)
    with repo.git.custom_environment(
        GIT_ATTR_NOSYSTEM="1",
        GIT_CONFIG_COUNT="0",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_SYSTEM=os.devnull,
    ):
        repo.git.update_index("--refresh")
    return repo


def prepare_untrusted_repository_handoff(
    repository: str | Path,
    workspace_root: str | Path,
    *,
    repository_ref: str,
    query: str,
    target_path: str,
    receiver_ref: str,
    read_prefixes: tuple[str, ...],
    read_paths: tuple[str, ...] = (),
    write_paths: tuple[str, ...],
    policy: UntrustedRepositoryPolicyV1Alpha1 | None = None,
) -> PreparedUntrustedRepositoryHandoff:
    """Admit immutable HEAD evidence and prepare one filtered, bounded journey."""

    selected_policy = policy or UntrustedRepositoryPolicyV1Alpha1()
    scope = ControllerRepositoryScopeV1Alpha1(
        repository_ref=repository_ref,
        query=query,
        target_path=target_path,
        receiver_ref=receiver_ref,
        read_prefixes=read_prefixes,
        read_paths=read_paths,
        write_paths=write_paths,
    )
    controller_metadata = (
        repository_ref,
        query,
        receiver_ref,
        scope.target_path,
        *scope.read_prefixes,
        *scope.read_paths,
        *scope.write_paths,
    )
    if any(_secret_categories(value) for value in controller_metadata):
        raise ValueError("untrusted repository preparation blocked: recognized_secret")
    root = Path(repository).resolve()
    workspace = Path(workspace_root).resolve()
    repo = Repo(root, search_parent_directories=False)
    if repo.bare or Path(repo.working_tree_dir or "").resolve() != root:
        raise ValueError("untrusted repository must be an exact non-bare Git root")
    if root == workspace or root in workspace.parents or workspace in root.parents:
        raise ValueError("filtered workspace must be outside the source repository")
    if not _repo_is_clean(repo, entry_limit=selected_policy.tree_entry_limit):
        raise ValueError("untrusted repository is not a clean tracked HEAD")
    source_commit = repo.head.commit
    source_revision = source_commit.hexsha
    source_tree = source_commit.tree.hexsha
    if not _HEX_OBJECT.fullmatch(source_revision) or not _HEX_OBJECT.fullmatch(source_tree):
        raise ValueError("untrusted repository uses an unsupported object identity")

    entries: list[object] = []
    for entry in source_commit.tree.traverse():
        if len(entries) >= selected_policy.tree_entry_limit:
            raise ValueError("untrusted repository preparation blocked: resource_limit")
        entries.append(entry)
    blobs: list[object] = []
    collision_keys: dict[str, str] = {}
    for entry in entries:
        entry_type = getattr(entry, "type", "")
        if entry_type == "tree":
            continue
        path = getattr(entry, "path", "")
        try:
            path = _canonical_path(path)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("untrusted repository preparation blocked: path_invalid") from exc
        if not _in_read_scope(path, scope):
            continue
        if _secret_categories(path):
            raise ValueError("untrusted repository preparation blocked: recognized_secret")
        collision_key = unicodedata.normalize("NFC", path).casefold()
        if collision_key in collision_keys and collision_keys[collision_key] != path:
            raise ValueError("untrusted repository preparation blocked: path_invalid")
        collision_keys[collision_key] = path
        blobs.append(entry)
    if len(blobs) > selected_policy.candidate_file_limit:
        raise ValueError("untrusted repository preparation blocked: resource_limit")
    if sum(int(getattr(item, "size", 0)) for item in blobs) > selected_policy.candidate_total_bytes_limit:
        raise ValueError("untrusted repository preparation blocked: resource_limit")

    admitted: dict[str, bytes] = {}
    decisions: list[UntrustedRepositoryMaterialDecisionV1Alpha1] = []
    blocked_reasons: list[str] = []
    required = set(scope.write_paths)
    for blob in sorted(blobs, key=lambda item: getattr(item, "path")):
        path = getattr(blob, "path")
        blob_id = getattr(blob, "hexsha")
        mode = int(getattr(blob, "mode", 0))
        reason: MaterialReason | None = None
        payload: bytes | None = None
        digest: str | None = None
        secrets: tuple[str, ...] = ()
        reason = _mode_exclusion(mode, str(getattr(blob, "type", "")))
        if reason is None and any(segment in _SKIP_SEGMENTS for segment in PurePosixPath(path).parts):
            reason = "generated_or_vendor"
        elif (
            reason is None
            and PurePosixPath(path).name != "CODEOWNERS"
            and PurePosixPath(path).suffix.lower() not in _SUPPORTED_SUFFIXES
        ):
            reason = "unsupported_extension"
        elif reason is None and int(getattr(blob, "size")) > selected_policy.blob_bytes_limit:
            reason = "resource_limit"
        elif reason is None:
            try:
                payload = _read_head_blob(blob)
                reason, digest, secrets = _classify_text(payload)
            except ValueError:
                reason = "resource_limit"
        disposition: Literal["admitted", "excluded", "blocked"]
        if reason is None and payload is not None and digest is not None:
            disposition = "admitted"
            admitted[path] = payload
        elif path in required:
            disposition = "blocked"
            blocked_reasons.append(reason or "resource_limit")
        else:
            disposition = "excluded"
        decisions.append(
            UntrustedRepositoryMaterialDecisionV1Alpha1(
                path=path,
                git_blob_id=blob_id,
                body_digest=digest,
                byte_count=int(getattr(blob, "size")),
                disposition=disposition,
                reason=reason,
                recognized_secret_categories=secrets,
            )
        )
    observed = {item.path for item in decisions}
    if required - observed:
        raise ValueError("untrusted repository preparation blocked: path_invalid")
    if blocked_reasons:
        raise ValueError(f"untrusted repository preparation blocked: {sorted(set(blocked_reasons))[0]}")
    if len(decisions) > _DECISION_LIMIT:
        raise ValueError("untrusted repository preparation blocked: resource_limit")

    admitted_rows = tuple(item.model_dump(mode="json") for item in decisions if item.disposition == "admitted")
    excluded_rows = tuple(item.model_dump(mode="json") for item in decisions if item.disposition == "excluded")
    material = UntrustedRepositoryMaterialReceiptV1Alpha1(
        repository_ref=repository_ref,
        source_head_revision=source_revision,
        source_head_tree=source_tree,
        policy_id=selected_policy.policy_id,
        scope_id=scope.scope_id,
        tree_entry_count=len(entries),
        candidate_count=len(blobs),
        candidate_byte_count=sum(int(getattr(item, "size")) for item in blobs),
        admitted_count=len(admitted_rows),
        admitted_byte_count=sum(len(payload) for payload in admitted.values()),
        excluded_count=len(excluded_rows),
        blocked_count=0,
        decisions=tuple(decisions),
        admitted_manifest_digest=stable_digest(admitted_rows),
        excluded_manifest_digest=stable_digest(excluded_rows),
        recognized_secret_findings=sum(len(item.recognized_secret_categories) for item in decisions),
    )
    filtered_repo = _write_filtered_repository(workspace, admitted, scope.write_paths, repository_ref)
    filtered_revision = filtered_repo.head.commit.hexsha
    filtered_tree = filtered_repo.head.commit.tree.hexsha
    if not _repo_is_clean(filtered_repo, entry_limit=selected_policy.tree_entry_limit):
        raise ValueError("filtered workspace is not a clean deterministic Git tree")
    journey = _run_isolated_journey(
        workspace,
        query=query,
        target_path=target_path,
        receiver_ref=receiver_ref,
    )
    for block in journey.handoff.blocks:
        if block.path not in admitted or not _in_read_scope(block.path, scope):
            raise ValueError("filtered journey escaped admitted controller read scope")
    if (
        not _repo_is_clean(repo, entry_limit=selected_policy.tree_entry_limit)
        or repo.head.commit.hexsha != source_revision
        or repo.head.commit.tree.hexsha != source_tree
    ):
        raise ValueError("untrusted repository HEAD changed during preparation")
    roles = tuple(
        UntrustedRepositoryEvidenceRoleV1Alpha1(
            block_id=block.block_id,
            path=block.path,
            body_digest=next(
                item.body_digest
                for item in material.decisions
                if item.path == block.path and item.disposition == "admitted"
            ),
            block_body_digest=block.body_digest,
        )
        for block in journey.handoff.blocks
    )
    packet = UntrustedRepositoryHandoffV1Alpha1(
        policy=selected_policy,
        controller_scope=scope,
        material_receipt=material,
        journey=journey,
        source_head_revision=source_revision,
        source_head_tree=source_tree,
        filtered_workspace_revision=filtered_revision,
        filtered_workspace_tree=filtered_tree,
        filtered_manifest_digest=material.admitted_manifest_digest,
        base_index_id=journey.lens.index.index_id,
        base_lens_id=journey.lens.lens_id,
        base_manifest_id=journey.handoff.manifest.manifest_id,
        base_handoff_id=journey.handoff.receipt.handoff_id,
        evidence_roles=roles,
        delivered_read_paths=tuple(block.path for block in journey.handoff.blocks),
        permitted_write_paths=scope.write_paths,
    )
    return PreparedUntrustedRepositoryHandoff(packet=packet, workspace_root=workspace)


def validate_untrusted_repository_return(
    packet: UntrustedRepositoryHandoffV1Alpha1,
    raw_return: bytes,
    *,
    validated_at: datetime | None = None,
) -> UntrustedRepositoryReturnReceiptV1Alpha1:
    """Strictly validate one bounded return without executing or persisting it."""

    if len(raw_return) > UNTRUSTED_RETURN_JSON_BYTES_LIMIT:
        raise ValueError("untrusted repository return exceeds fixed JSON byte bound")
    try:
        text = raw_return.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("untrusted repository return is not strict UTF-8") from exc
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ValueError("untrusted repository return is not valid JSON") from exc
    if _contains_recognized_secret(document):
        raise ValueError("untrusted repository return blocked: recognized_secret")
    returned = CodingAgentReturnV1Alpha1.model_validate(document)
    base = validate_coding_agent_return(packet.journey.handoff, returned)
    expected_blocks = tuple(block.block_id for block in packet.journey.handoff.blocks)
    if returned.consumed_block_ids != expected_blocks:
        raise ValueError("untrusted repository return must consume exact ordered evidence blocks")
    if any(path not in packet.permitted_write_paths for path in returned.changed_paths):
        raise ValueError("untrusted repository return names a path outside controller write scope")
    when = validated_at or datetime.now(timezone.utc)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("validated_at must be timezone-aware")
    return UntrustedRepositoryReturnReceiptV1Alpha1(
        packet_id=packet.packet_id,
        policy_id=packet.policy.policy_id,
        scope_id=packet.controller_scope.scope_id,
        material_receipt_id=packet.material_receipt.receipt_id,
        source_head_revision=packet.source_head_revision,
        source_head_tree=packet.source_head_tree,
        filtered_workspace_revision=packet.filtered_workspace_revision,
        filtered_workspace_tree=packet.filtered_workspace_tree,
        base_index_id=packet.base_index_id,
        base_lens_id=packet.base_lens_id,
        base_manifest_id=packet.base_manifest_id,
        base_handoff_id=packet.base_handoff_id,
        return_id=returned.return_id,
        base_return_receipt_id=base.receipt_id,
        consumed_block_ids=returned.consumed_block_ids,
        changed_paths=returned.changed_paths,
        disposition=returned.disposition,
        validated_at=when,
    )


if __name__ == "__main__":
    if sys.argv[1:] != ["--isolated-journey-helper-v1"]:
        raise SystemExit(2)
    raise SystemExit(_isolated_journey_helper_main())
