"""Fail-closed declared code-ownership projection for Code Intelligence.

Git history is deliberately absent from this module.  Contributor history can
explain how code evolved, but it cannot establish current review responsibility.
This adapter reads only a repository-declared ``CODEOWNERS`` file and preserves
the distinction between an observed declaration and platform-enforced authority.
"""

from __future__ import annotations

import os
import re
import stat
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Self

from git import Repo
from pydantic import Field, model_validator

from core.engine.code_intelligence.contracts import (
    ConfidenceBand,
    DerivationKind,
    FrozenContract,
    SourceAnchorV1Alpha1,
    stable_digest,
)

# Conservative, reusable bounds on ownership uncertainty text. A <=1 MiB
# CODEOWNERS source (``GitHubCodeownersAdapter._MAX_SOURCE_BYTES``) must never
# expand into a multi-megabyte uncertainty tuple or a multi-megabyte
# serialized projection just because it contains many malformed lines. These
# bound the *rendered* uncertainty independent of how many diagnostics the
# parser collected, and are enforced by a Pydantic ``model_validator`` so they
# apply on both construction and deserialization (``model_validate``).
OWNERSHIP_MAX_UNCERTAINTY_ITEMS = 6
OWNERSHIP_MAX_UNCERTAINTY_ITEM_CHARS = 4_000
OWNERSHIP_MAX_UNCERTAINTY_TOTAL_CHARS = 6_000


def _bounded_uncertainties(uncertainties: tuple[str, ...]) -> tuple[str, ...]:
    if len(uncertainties) > OWNERSHIP_MAX_UNCERTAINTY_ITEMS:
        raise ValueError(f"uncertainties exceed {OWNERSHIP_MAX_UNCERTAINTY_ITEMS} items")
    if any(len(item) > OWNERSHIP_MAX_UNCERTAINTY_ITEM_CHARS for item in uncertainties):
        raise ValueError(f"uncertainty entries exceed {OWNERSHIP_MAX_UNCERTAINTY_ITEM_CHARS} characters")
    if sum(len(item) for item in uncertainties) > OWNERSHIP_MAX_UNCERTAINTY_TOTAL_CHARS:
        raise ValueError(f"uncertainties exceed {OWNERSHIP_MAX_UNCERTAINTY_TOTAL_CHARS} total characters")
    return uncertainties


class OwnershipProjectionStatus(str, Enum):
    DECLARED = "declared"
    UNASSIGNED = "unassigned"
    UNAVAILABLE = "unavailable"


class DeclaredReviewOwnerV1Alpha1(FrozenContract):
    """One exact reviewer token declared for a matching source path."""

    contract: Literal["ace.code-intelligence.declared-review-owner/v1alpha1"] = (
        "ace.code-intelligence.declared-review-owner/v1alpha1"
    )
    owner_ref: str = Field(min_length=1)
    matched_pattern: str = Field(min_length=1)
    evidence: SourceAnchorV1Alpha1
    confidence: Literal[ConfidenceBand.OBSERVED] = ConfidenceBand.OBSERVED
    uncertainties: tuple[str, ...]
    declared_review_responsibility: Literal[True] = True
    identity_verified: Literal[False] = False
    platform_enforcement_verified: Literal[False] = False
    grants_source_authority: Literal[False] = False
    grants_change_authority: Literal[False] = False
    grants_approval_authority: Literal[False] = False
    grants_delivery_authority: Literal[False] = False
    grants_effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_declared_anchor(self) -> Self:
        if self.evidence.derivation is not DerivationKind.DECLARED:
            raise ValueError("declared review ownership requires a declared source anchor")
        if self.evidence.confidence is not ConfidenceBand.OBSERVED:
            raise ValueError("declared review ownership requires an observed source anchor")
        if not self.uncertainties:
            raise ValueError("declared review ownership must retain uncertainty")
        _bounded_uncertainties(self.uncertainties)
        return self


class CodeOwnershipProjectionV1Alpha1(FrozenContract):
    """Path-scoped ownership result from one bounded declaration adapter."""

    contract: Literal["ace.code-intelligence.ownership-projection/v1alpha1"] = (
        "ace.code-intelligence.ownership-projection/v1alpha1"
    )
    target_path: str = Field(min_length=1)
    status: OwnershipProjectionStatus
    source_path: str | None = None
    searched_source_paths: tuple[str, ...]
    owners: tuple[DeclaredReviewOwnerV1Alpha1, ...] = ()
    uncertainties: tuple[str, ...]
    adapter_profile: Literal["github-codeowners-bounded-v1"] = "github-codeowners-bounded-v1"
    historical_contributors_are_current_owners: Literal[False] = False
    provider_neutral: Literal[True] = True
    grants_source_authority: Literal[False] = False
    grants_change_authority: Literal[False] = False
    grants_approval_authority: Literal[False] = False
    grants_delivery_authority: Literal[False] = False
    grants_effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def status_matches_material(self) -> Self:
        if not self.uncertainties:
            raise ValueError("ownership projection must retain uncertainty")
        _bounded_uncertainties(self.uncertainties)
        if self.status is OwnershipProjectionStatus.DECLARED:
            if self.source_path is None or not self.owners:
                raise ValueError("declared ownership requires a source and at least one owner")
        elif self.owners:
            raise ValueError("non-declared ownership cannot contain owners")
        if self.status is OwnershipProjectionStatus.UNAVAILABLE and self.source_path is not None:
            raise ValueError("unavailable ownership cannot name a usable source")
        return self


class GitHubCodeownersAdapter:
    """Project supported ``CODEOWNERS`` rules into exact, non-authorizing evidence.

    The adapter intentionally supports a bounded subset of GitHub's CODEOWNERS
    matcher, not universal parity with it: root-relative and basename patterns
    using ``*``, ``**``, and ``?``.  Unsupported negation, character classes,
    escapes, malformed owner tokens, or invalid UTF-8 fail closed rather than
    producing a partial ownership claim.

    Every input dimension that feeds the parser, the wildcard matcher, or the
    owner projection is bounded by an explicit finite limit below, checked
    before that dimension's expensive work runs.  A declaration outside any
    limit — or otherwise malformed — returns ``UNAVAILABLE`` with an honest
    uncertainty; it never yields a partial owner projection.
    """

    SEARCH_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
    _OWNER = re.compile(r"^(?:@[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?|[^@\s]+@[^@\s]+)$")
    _WILDCARD_TOKEN = re.compile(r"\*\*|\*|\?")

    # Exact HEAD blob size in bytes, enforced by reading at most one byte past
    # the limit (see ``_tracked_source`` / ``project``) so an oversized
    # declaration is never fully materialized in memory.
    _MAX_SOURCE_BYTES = 1_048_576
    # One physical CODEOWNERS line, measured in UTF-8 bytes, before tokenizing.
    _MAX_LINE_BYTES = 4_096
    # Non-comment, non-blank declaration lines accepted from one source file.
    _MAX_RULES = 5_000
    # Characters permitted in one rule's pattern column.
    _MAX_PATTERN_LENGTH = 512
    # ``*``, ``**``, and ``?`` tokens permitted in one pattern.  This bounds
    # the alternating wildcard/literal regex segments ``_matches`` can ever
    # compile for one pattern, so a pathological pattern such as repeated
    # ``*a`` segments is rejected here — before any regex is built or run —
    # rather than relying on a wall-clock timeout after the fact.
    _MAX_PATTERN_WILDCARDS = 8
    # Owner tokens permitted on one rule line.
    _MAX_OWNERS_PER_RULE = 64
    # Owner tokens permitted summed across every accepted rule in the file.
    _MAX_TOTAL_OWNERS = 20_000
    # Malformed-rule diagnostics retained verbatim from one parse pass, and
    # the per-item character length each retained diagnostic is truncated to.
    # These bound the *rendering* of individual line/path errors independent
    # of how many malformed lines the (already size-capped) source contains:
    # once the cap is reached, remaining malformed lines are still counted so
    # the omission is exact, but their text is never stored or rendered.
    _MAX_DIAGNOSTIC_ITEMS = 20
    _MAX_DIAGNOSTIC_ITEM_CHARS = 160

    def __init__(self, repository: str | Path):
        self.root = Path(repository).resolve()
        if not self.root.is_dir():
            raise ValueError(f"repository does not exist: {self.root}")
        self.repo = Repo(self.root, search_parent_directories=False)

    def project(self, target_path: str) -> CodeOwnershipProjectionV1Alpha1:
        normalized_target = self._safe_target(target_path)
        source, blob, source_error = self._tracked_source()
        if source_error is not None:
            return self._unsupported(normalized_target, source_error)
        if source is None:
            return CodeOwnershipProjectionV1Alpha1(
                target_path=normalized_target,
                status=OwnershipProjectionStatus.UNAVAILABLE,
                searched_source_paths=self.SEARCH_PATHS,
                uncertainties=(
                    "No tracked regular path-owner declaration exists at a supported CODEOWNERS location in HEAD.",
                    "Repository governance, package authorship, and Git contributors do not establish target-path ownership.",
                ),
            )

        source_file = self.root / source
        if self._contains_symlink(source_file) or not self._is_regular_file(source_file):
            return self._unsupported(
                normalized_target,
                f"{source} is not a current regular file without symlink traversal",
            )
        # The declaration is the tracked HEAD blob, read by its immutable object
        # id.  A dirty or racing working tree can only make the adapter refuse
        # above; its bytes are never mixed into a HEAD-proved declaration.  The
        # read is bounded to one byte past the size limit so an oversized blob
        # is never fully pulled into memory before being rejected.
        try:
            payload = blob.data_stream.read(self._MAX_SOURCE_BYTES + 1)
        except OSError:
            return self._unsupported(normalized_target, f"{source} could not be read as a stable regular file")
        if len(payload) > self._MAX_SOURCE_BYTES:
            return self._unsupported(
                normalized_target, f"{source} exceeds the {self._MAX_SOURCE_BYTES}-byte declaration size limit"
            )
        try:
            lines = payload.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            return self._unsupported(normalized_target, f"{source} is not valid UTF-8")

        rules: list[tuple[int, str, tuple[str, ...], str]] = []
        errors: list[str] = []
        omitted_diagnostics = 0

        def record(message: str) -> None:
            nonlocal omitted_diagnostics
            if len(errors) < self._MAX_DIAGNOSTIC_ITEMS:
                errors.append(message[: self._MAX_DIAGNOSTIC_ITEM_CHARS])
            else:
                omitted_diagnostics += 1

        total_owners = 0
        for line_number, raw_line in enumerate(lines, 1):
            if len(raw_line.encode("utf-8")) > self._MAX_LINE_BYTES:
                record(f"line {line_number}: exceeds the {self._MAX_LINE_BYTES}-byte line limit")
                break
            parsed = self._parse_rule(raw_line)
            if parsed is None:
                continue
            if isinstance(parsed, str):
                record(f"line {line_number}: {parsed}")
                continue
            pattern, owners = parsed
            if len(rules) + 1 > self._MAX_RULES:
                record(f"line {line_number}: exceeds the {self._MAX_RULES}-rule count limit")
                break
            total_owners += len(owners)
            if total_owners > self._MAX_TOTAL_OWNERS:
                record(f"line {line_number}: exceeds the {self._MAX_TOTAL_OWNERS}-owner total limit")
                break
            rules.append((line_number, pattern, owners, raw_line))
        if omitted_diagnostics:
            errors.append(f"additional_malformed_rules:{omitted_diagnostics}")
        if errors:
            return self._unsupported(
                normalized_target, f"{source} has unsupported or malformed rules: {'; '.join(errors)}"
            )

        matched = next(
            (
                (line_number, pattern, owners, raw_line)
                for line_number, pattern, owners, raw_line in reversed(rules)
                if self._matches(pattern, normalized_target)
            ),
            None,
        )
        if matched is None:
            return CodeOwnershipProjectionV1Alpha1(
                target_path=normalized_target,
                status=OwnershipProjectionStatus.UNASSIGNED,
                source_path=source,
                searched_source_paths=self.SEARCH_PATHS,
                uncertainties=(
                    "A canonical CODEOWNERS file was observed, but no supported rule matches the target path.",
                    "No current path owner is inferred from repository governance, package authorship, or Git history.",
                ),
            )

        line_number, pattern, owner_refs, raw_line = matched
        anchor = SourceAnchorV1Alpha1(
            path=source,
            line_start=line_number,
            line_end=line_number,
            content_digest=stable_digest(raw_line),
            derivation=DerivationKind.DECLARED,
            confidence=ConfidenceBand.OBSERVED,
            explanation="Exact last matching CODEOWNERS declaration for the target path.",
        )
        uncertainty = (
            "Owner tokens are observed declarations; account identity and current team membership were not resolved.",
            "Branch protection and platform review enforcement were not inspected.",
            "The declaration grants no source, change, approval, delivery, or effect authority through ACE.",
        )
        owners = tuple(
            DeclaredReviewOwnerV1Alpha1(
                owner_ref=owner_ref,
                matched_pattern=pattern,
                evidence=anchor,
                uncertainties=uncertainty,
            )
            for owner_ref in owner_refs
        )
        return CodeOwnershipProjectionV1Alpha1(
            target_path=normalized_target,
            status=OwnershipProjectionStatus.DECLARED,
            source_path=source,
            searched_source_paths=self.SEARCH_PATHS,
            owners=owners,
            uncertainties=uncertainty,
        )

    def _unsupported(self, target_path: str, reason: str) -> CodeOwnershipProjectionV1Alpha1:
        return CodeOwnershipProjectionV1Alpha1(
            target_path=target_path,
            status=OwnershipProjectionStatus.UNAVAILABLE,
            searched_source_paths=self.SEARCH_PATHS,
            uncertainties=(
                reason,
                "The adapter failed closed; no owner was inferred from a partial parse or Git history.",
            ),
        )

    def _safe_target(self, target_path: str) -> str:
        if not target_path or Path(target_path).is_absolute():
            raise ValueError("target path must be a non-empty repository-relative path")
        lexical = self.root / target_path
        candidate = lexical.resolve()
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("target path escapes repository") from exc
        canonical = relative.as_posix()
        if target_path != canonical:
            raise ValueError("target path must use one canonical repository-relative spelling")
        if self._contains_symlink(lexical):
            raise ValueError("target path must not traverse a symlink")
        self._require_exact_component_spelling(canonical)
        if not self._is_regular_file(candidate):
            raise ValueError(f"target file does not exist: {target_path}")
        return canonical

    def _require_exact_component_spelling(self, canonical: str) -> None:
        """Reject case aliases that a case-insensitive filesystem would accept."""
        current = self.root
        for part in Path(canonical).parts:
            try:
                entries = os.listdir(current)
            except OSError as exc:
                raise ValueError(f"target file does not exist: {canonical}") from exc
            if part not in entries:
                if any(entry.casefold() == part.casefold() for entry in entries):
                    raise ValueError("target path must use the exact component spelling recorded in the repository")
                raise ValueError(f"target file does not exist: {canonical}")
            current = current / part

    def _tracked_source(self) -> tuple[str | None, Any | None, str | None]:
        """Select the first canonical location that exists as a regular HEAD blob.

        The proved entry itself is returned so the later read uses that exact
        immutable object rather than re-resolving the path after the check.
        """

        try:
            tree = self.repo.head.commit.tree
        except (TypeError, ValueError):
            return None, None, "Repository HEAD is unavailable for exact CODEOWNERS provenance"
        for source in self.SEARCH_PATHS:
            try:
                entry = tree / source
            except KeyError:
                continue
            if entry.type != "blob" or stat.S_IFMT(entry.mode) != stat.S_IFREG:
                return None, None, f"{source} is not a tracked regular file in HEAD"
            return source, entry, None
        return None, None, None

    def _contains_symlink(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return True
        current = self.root
        for part in relative.parts:
            current = current / part
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    return True
            except OSError:
                return False
        return False

    @staticmethod
    def _is_regular_file(path: Path) -> bool:
        try:
            return stat.S_ISREG(os.lstat(path).st_mode)
        except OSError:
            return False

    @classmethod
    def _parse_rule(cls, raw_line: str) -> tuple[str, tuple[str, ...]] | str | None:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            return None
        tokens = stripped.split()
        tokens = tokens[: next((index for index, token in enumerate(tokens) if token.startswith("#")), len(tokens))]
        if len(tokens) < 2:
            return "rule does not declare an owner"
        pattern, *owners = tokens
        if len(pattern) > cls._MAX_PATTERN_LENGTH:
            return f"pattern exceeds the {cls._MAX_PATTERN_LENGTH}-character pattern length limit"
        if len(owners) > cls._MAX_OWNERS_PER_RULE:
            return f"rule declares more than the {cls._MAX_OWNERS_PER_RULE}-owner-per-rule limit"
        if pattern.startswith("!") or any(character in pattern for character in "[]\\"):
            return f"unsupported pattern {pattern!r}"
        if any(segment != "**" and "**" in segment for segment in pattern.split("/")):
            return f"unsupported pattern {pattern!r}: ** must be a whole path segment"
        # Reject pathological wildcard density before any regex is compiled or
        # matched: bounding this count keeps ``_matches`` worst-case
        # backtracking cost bounded, deterministically, regardless of the
        # target path length being matched against.
        if len(cls._WILDCARD_TOKEN.findall(pattern)) > cls._MAX_PATTERN_WILDCARDS:
            return f"pattern exceeds the {cls._MAX_PATTERN_WILDCARDS}-wildcard complexity limit"
        if not all(cls._OWNER.fullmatch(owner) for owner in owners):
            return "rule contains an unsupported owner token"
        return pattern, tuple(owners)

    @staticmethod
    def _tokenize(normalized: str) -> list[tuple[str, str] | tuple[str]]:
        """Split a slash-stripped pattern body into deterministic match tokens.

        ``_parse_rule`` already rejects any ``**`` that is not a whole path
        segment, so the only multi-character token this loop ever forms is a
        canonical ``**`` (optionally followed by ``/``); every other
        character becomes its own single-character token.
        """
        tokens: list[tuple[str, str] | tuple[str]] = []
        index = 0
        while index < len(normalized):
            character = normalized[index]
            if character == "*":
                if index + 1 < len(normalized) and normalized[index + 1] == "*":
                    if index + 2 < len(normalized) and normalized[index + 2] == "/":
                        tokens.append(("dstar_slash",))
                        index += 3
                    else:
                        tokens.append(("dstar",))
                        index += 2
                else:
                    tokens.append(("star",))
                    index += 1
            elif character == "?":
                tokens.append(("qmark",))
                index += 1
            else:
                tokens.append(("lit", character))
                index += 1
        return tokens

    @classmethod
    def _match_with_state_count(cls, pattern: str, target_path: str) -> tuple[bool, int]:
        """Deterministically evaluate one CODEOWNERS pattern against one path.

        This is a reachable-position dynamic-programming walk equivalent to
        the documented matcher grammar, not a backtracking regex: at every
        token it tracks the finite *set* of target-path positions still
        consistent with the pattern seen so far, so a pathological legal
        pattern (bounded by ``_MAX_PATTERN_WILDCARDS``) cannot force
        exponential re-exploration of the same positions the way alternation
        inside a compiled regex can. ``states_visited`` sums the size of that
        position set at every token step, so it is bounded above by
        ``(len(pattern) + 1) * (len(target_path) + 1)`` regardless of input
        shape -- a fact the test suite checks directly instead of trusting a
        wall-clock timeout.
        """
        anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
        normalized = pattern.lstrip("/")
        directory_rule = normalized.endswith("/")
        normalized = normalized.rstrip("/")
        tokens = cls._tokenize(normalized)

        length = len(target_path)
        # Component-boundary positions: index 0, and every index immediately
        # after a "/" in the target path. A non-anchored (basename) pattern
        # may begin matching only at one of these positions.
        boundaries = [k for k in range(1, length + 1) if target_path[k - 1] == "/"]
        positions = {0} if anchored else {0, *boundaries}
        states_visited = len(positions)

        for token in tokens:
            if not positions:
                break
            kind = token[0]
            if kind == "lit":
                character = token[1]
                positions = {p + 1 for p in positions if p < length and target_path[p] == character}
            elif kind == "qmark":
                positions = {p + 1 for p in positions if p < length and target_path[p] != "/"}
            elif kind == "star":
                # Zero or more non-slash characters: from each position, every
                # index up to (and including) the next "/" or end of string.
                expanded: set[int] = set()
                for p in positions:
                    end = p
                    while end < length and target_path[end] != "/":
                        end += 1
                    expanded.update(range(p, end + 1))
                positions = expanded
            elif kind == "dstar":
                # Bare "**": zero or more characters of any kind, including
                # "/". The reachable set from any start is every position
                # from that start through the end of the string, so the union
                # across all current positions collapses to one range.
                start = min(positions)
                positions = set(range(start, length + 1))
            else:  # "dstar_slash": "**/" — zero or more whole directories.
                start = min(positions)
                positions = set(positions)
                positions.update(k for k in boundaries if k > start)
            states_visited += len(positions)

        if directory_rule:
            matched = any(p < length and target_path[p] == "/" for p in positions)
        else:
            matched = length in positions or any(p < length and target_path[p] == "/" for p in positions)
        return matched, states_visited

    @classmethod
    def _matches(cls, pattern: str, target_path: str) -> bool:
        matched, _states_visited = cls._match_with_state_count(pattern, target_path)
        return matched


__all__ = [
    "CodeOwnershipProjectionV1Alpha1",
    "DeclaredReviewOwnerV1Alpha1",
    "GitHubCodeownersAdapter",
    "OwnershipProjectionStatus",
]
