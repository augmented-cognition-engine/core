"""Inspectable contracts for the first bounded Code Intelligence journey."""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
import textwrap
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _canonical(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def stable_digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{stable_digest(value).split(':', 1)[1][:32]}"


def raw_digest(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def deterministic_code_patch(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


_GIT_COMMIT_EVIDENCE = re.compile(r"git:[0-9a-f]{40}")


def logical_line_count(body: str) -> int:
    """Return the exact number of logical lines a bounded body represents.

    A body is always ``"\\n".join(lines)`` over an inclusive span, so the count
    is the exact inverse of that join: an empty body is one empty line, and a
    trailing newline means the final line is empty and still counted.
    """
    return body.count("\n") + 1


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DerivationKind(str, Enum):
    PARSER = "parser"
    GRAPH = "graph"
    GIT = "git"
    DECLARED = "declared"
    HEURISTIC = "heuristic"


class ConfidenceBand(str, Enum):
    OBSERVED = "observed"
    SUPPORTED = "supported"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class CodeArtifactKind(str, Enum):
    REPOSITORY = "repository"
    SERVICE = "service"
    MODULE = "module"
    FILE = "file"
    SYMBOL = "symbol"
    FEATURE = "feature"
    TEST = "test"
    API = "api"
    OWNERSHIP = "ownership"
    CONTRIBUTOR = "contributor"
    ADR = "adr"
    INCIDENT = "incident"
    DECISION = "decision"


class SourceAnchorV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.source-anchor/v1alpha1"] = "ace.code-intelligence.source-anchor/v1alpha1"
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    derivation: DerivationKind
    confidence: ConfidenceBand
    explanation: str

    @model_validator(mode="after")
    def ordered_lines(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("source anchor line range is reversed")
        return self

    @property
    def anchor_id(self) -> str:
        return stable_id("code_anchor", self)


class RepositoryIndexIdentityV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.repository-index/v1alpha1"] = (
        "ace.code-intelligence.repository-index/v1alpha1"
    )
    repository: str
    revision: str
    dirty: bool
    working_tree_digest: str = Field(pattern=r"^(clean|sha256:[a-f0-9]{64})$")
    scanner_contract: str
    analysis_profile: Literal["python-local-static-v1"] = "python-local-static-v1"
    topology: Literal["single-local-git-repository"] = "single-local-git-repository"
    supported_languages: tuple[Literal["python"], ...] = ("python",)
    observed_languages: tuple[str, ...]
    generated_at: datetime

    @property
    def index_id(self) -> str:
        material = self.model_dump(mode="json", exclude={"generated_at"})
        return stable_id("code_index", material)


class CodeNodeV1Alpha1(FrozenContract):
    node_id: str
    kind: CodeArtifactKind
    label: str
    path: str | None = None
    symbol: str | None = None
    derivation: DerivationKind
    confidence: ConfidenceBand
    evidence_refs: tuple[str, ...] = ()
    detail: str | None = None


class CodeEdgeV1Alpha1(FrozenContract):
    source: str
    target: str
    relation: str
    derivation: DerivationKind
    confidence: ConfidenceBand
    evidence_refs: tuple[str, ...] = ()


class ChangeImpactV1Alpha1(FrozenContract):
    target_path: str
    direct_dependents: tuple[str, ...]
    transitive_dependents: tuple[str, ...]
    affected_tests: tuple[str, ...]
    known_coverage_gaps: tuple[str, ...]
    confidence: ConfidenceBand
    basis: str


class DisconnectedSymbolCandidateV1Alpha1(FrozenContract):
    symbol_id: str
    path: str
    symbol: str
    line_start: int = Field(ge=1)
    reason: str
    confidence: Literal[ConfidenceBand.INFERRED] = ConfidenceBand.INFERRED
    evidence_ref: str


# Conservative, reusable contract-level bounds on lens omission metadata.
# Mirrors ``CONTEXT_MANIFEST_MAX_OMISSIONS*`` below: a repository with a huge
# untracked-symlink set, a large malformed-CODEOWNERS diagnostic tail, or many
# skipped lexical candidates must never grow the lens's own omissions tuple
# proportionally to repository size. The journey composing this lens is
# responsible for aggregating any such disclosure by deterministic count
# before appending it here; this validator is the last-line contract bound
# that also applies on deserialization, not just at construction.
LENS_MAX_OMISSIONS = 24
LENS_MAX_OMISSION_CHARS = 320
LENS_MAX_OMISSIONS_TOTAL_CHARS = 3_200


class AtriumCodeLensV1Alpha1(FrozenContract):
    """Read-only, Atrium-ready projection over one exact repository index."""

    contract: Literal["ace.code-intelligence.atrium-code-lens/v1alpha1"] = (
        "ace.code-intelligence.atrium-code-lens/v1alpha1"
    )
    index: RepositoryIndexIdentityV1Alpha1
    query: str
    target_path: str
    nodes: tuple[CodeNodeV1Alpha1, ...]
    edges: tuple[CodeEdgeV1Alpha1, ...]
    impact: ChangeImpactV1Alpha1
    disconnected_symbols: tuple[DisconnectedSymbolCandidateV1Alpha1, ...]
    evidence: tuple[SourceAnchorV1Alpha1, ...]
    omissions: tuple[str, ...]
    degraded_reasons: tuple[str, ...]
    read_only: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_internal_closure(self) -> Self:
        """Every projected identity is unique and every claim names its evidence."""
        if self.impact.target_path != self.target_path:
            raise ValueError("lens impact describes a different target path")
        node_ids = [item.node_id for item in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("lens repeats a node identity")
        edge_keys = [(item.source, item.target, item.relation) for item in self.edges]
        if len(set(edge_keys)) != len(edge_keys):
            raise ValueError("lens repeats an edge identity")
        symbol_ids = [item.symbol_id for item in self.disconnected_symbols]
        if len(set(symbol_ids)) != len(symbol_ids):
            raise ValueError("lens repeats a disconnected symbol identity")
        known_nodes = set(node_ids)
        anchors = {item.anchor_id for item in self.evidence}
        for edge in self.edges:
            if edge.source not in known_nodes or edge.target not in known_nodes:
                raise ValueError("lens edge names a node outside the exact projection")
        for node in self.nodes:
            if not set(node.evidence_refs) <= anchors:
                raise ValueError("lens node evidence does not resolve to an exact source anchor")
        for candidate in self.disconnected_symbols:
            if candidate.evidence_ref not in anchors:
                raise ValueError("lens disconnected symbol evidence does not resolve to an exact source anchor")
        for edge in self.edges:
            for reference in edge.evidence_refs:
                if reference in anchors:
                    continue
                # A historical Git contributor edge is the one relation whose
                # evidence is a commit rather than a scanned source span.
                if (
                    edge.derivation is DerivationKind.GIT
                    and edge.relation == "historical_contributor"
                    and _GIT_COMMIT_EVIDENCE.fullmatch(reference) is not None
                ):
                    continue
                raise ValueError("lens edge evidence does not resolve to an exact source anchor or commit")
        return self

    @model_validator(mode="after")
    def bounded_omissions(self) -> Self:
        """Reject lens omission metadata whose size could scale with repository size.

        Mirrors ``CodeContextManifestV1Alpha1.bounded_omissions``.
        """
        if len(self.omissions) > LENS_MAX_OMISSIONS:
            raise ValueError(f"lens omissions exceed {LENS_MAX_OMISSIONS} items")
        if len(set(self.omissions)) != len(self.omissions):
            raise ValueError("lens omissions contains a duplicate entry")
        if any(not item or len(item) > LENS_MAX_OMISSION_CHARS for item in self.omissions):
            raise ValueError(f"lens omissions entries must contain 1..{LENS_MAX_OMISSION_CHARS} characters")
        total_chars = sum(len(item) for item in self.omissions)
        if total_chars > LENS_MAX_OMISSIONS_TOTAL_CHARS:
            raise ValueError(f"lens omissions total characters exceed {LENS_MAX_OMISSIONS_TOTAL_CHARS}")
        return self

    @property
    def lens_id(self) -> str:
        return stable_id("atrium_code_lens", self)


class CodeContextBlockV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.context-block/v1alpha1"] = "ace.code-intelligence.context-block/v1alpha1"
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    body: str
    body_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    byte_count: int = Field(ge=0)
    token_estimate: int = Field(ge=0)
    reason: str
    evidence_ref: str
    symbol: str | None = None
    symbol_line_start: int | None = Field(default=None, ge=1)
    symbol_line_end: int | None = Field(default=None, ge=1)
    symbol_body_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def exact_body(self) -> Self:
        encoded = self.body.encode()
        if self.body_digest != stable_digest(self.body):
            raise ValueError("code context body digest differs from body")
        if self.byte_count != len(encoded):
            raise ValueError("code context byte count differs from body")
        if self.line_end < self.line_start:
            raise ValueError("code context line range is reversed")
        if logical_line_count(self.body) != self.line_end - self.line_start + 1:
            raise ValueError("code context inclusive line span differs from the exact body line count")
        symbol_fields = (self.symbol, self.symbol_line_start, self.symbol_line_end, self.symbol_body_digest)
        if any(item is not None for item in symbol_fields) and not all(item is not None for item in symbol_fields):
            raise ValueError("code context symbol identity and span must be present together")
        if self.symbol_line_start is not None and self.symbol_line_end is not None:
            if self.symbol_line_end < self.symbol_line_start:
                raise ValueError("code context symbol line range is reversed")
            if self.symbol_line_start < self.line_start or self.symbol_line_end > self.line_end:
                raise ValueError("code context symbol span falls outside the bounded body")
            body_lines = self.body.splitlines()
            relative_start = self.symbol_line_start - self.line_start
            relative_end = self.symbol_line_end - self.line_start + 1
            symbol_body = "\n".join(body_lines[relative_start:relative_end])
            if self.symbol_body_digest != stable_digest(symbol_body):
                raise ValueError("code context symbol body digest differs from its exact body span")
            try:
                parsed = ast.parse(textwrap.dedent(symbol_body))
            except SyntaxError as exc:
                raise ValueError("code context symbol body is not parseable Python") from exc
            definitions = (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            )
            expected_name = self.symbol.rsplit(".", 1)[-1]
            if (
                len(parsed.body) != 1
                or not isinstance(parsed.body[0], definitions)
                or parsed.body[0].name != expected_name
            ):
                raise ValueError("code context symbol body is not the sole top-level named Python definition")
        return self

    @property
    def block_id(self) -> str:
        return stable_id("code_context_block", self.model_dump(exclude={"body"}))


class CodeContextBlockReceiptV1Alpha1(FrozenContract):
    block_id: str
    path: str
    line_start: int
    line_end: int
    body_digest: str
    byte_count: int
    token_estimate: int
    reason: str
    evidence_ref: str
    symbol: str | None = None
    symbol_line_start: int | None = None
    symbol_line_end: int | None = None
    symbol_body_digest: str | None = None


# Conservative, reusable contract-level bounds on manifest omission metadata.
# These hold independent of ``max_bytes``/``total_bytes`` so a large context
# body budget can never license unbounded omission metadata growth, and a
# planner over a large repository cannot emit one entry per candidate file.
CONTEXT_MANIFEST_MAX_OMISSIONS = 16
CONTEXT_MANIFEST_MAX_OMISSION_CHARS = 160
CONTEXT_MANIFEST_MAX_OMISSIONS_TOTAL_CHARS = 1_200


class CodeContextManifestV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.context-manifest/v1alpha1"] = (
        "ace.code-intelligence.context-manifest/v1alpha1"
    )
    index_id: str
    lens_id: str
    blocks: tuple[CodeContextBlockReceiptV1Alpha1, ...]
    total_bytes: int
    total_token_estimate: int
    max_files: int
    max_bytes: int
    omissions: tuple[str, ...]
    degraded_reasons: tuple[str, ...]
    execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_totals(self) -> Self:
        if self.total_bytes != sum(item.byte_count for item in self.blocks):
            raise ValueError("manifest byte total differs from exact blocks")
        if self.total_token_estimate != sum(item.token_estimate for item in self.blocks):
            raise ValueError("manifest token total differs from exact blocks")
        if len(self.blocks) > self.max_files or self.total_bytes > self.max_bytes:
            raise ValueError("manifest exceeds declared bounds")
        if len({item.block_id for item in self.blocks}) != len(self.blocks):
            raise ValueError("manifest contains duplicate blocks")
        return self

    @model_validator(mode="after")
    def bounded_omissions(self) -> Self:
        """Reject omission metadata whose size could scale with repository size.

        These bounds apply regardless of ``max_bytes``/``total_bytes``: the
        omission list is bounded on its own terms, not as a fraction of the
        context body budget.
        """
        if len(self.omissions) > CONTEXT_MANIFEST_MAX_OMISSIONS:
            raise ValueError(f"manifest omissions exceed {CONTEXT_MANIFEST_MAX_OMISSIONS} items")
        if len(set(self.omissions)) != len(self.omissions):
            raise ValueError("manifest omissions contains a duplicate entry")
        if any(not item or len(item) > CONTEXT_MANIFEST_MAX_OMISSION_CHARS for item in self.omissions):
            raise ValueError(
                f"manifest omissions entries must contain 1..{CONTEXT_MANIFEST_MAX_OMISSION_CHARS} characters"
            )
        total_chars = sum(len(item) for item in self.omissions)
        if total_chars > CONTEXT_MANIFEST_MAX_OMISSIONS_TOTAL_CHARS:
            raise ValueError(f"manifest omissions total characters exceed {CONTEXT_MANIFEST_MAX_OMISSIONS_TOTAL_CHARS}")
        return self

    @property
    def manifest_id(self) -> str:
        return stable_id("code_context_manifest", self)


class CodingAgentHandoffReceiptV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.coding-agent-handoff/v1alpha1"] = (
        "ace.code-intelligence.coding-agent-handoff/v1alpha1"
    )
    receiver_ref: str
    requested_change: str
    requested_outputs: tuple[str, ...]
    index_id: str
    lens_id: str
    manifest_id: str
    included_paths: tuple[str, ...]
    provider_neutral: Literal[True] = True
    grants_source_authority: Literal[False] = False
    grants_reasoning_authority: Literal[False] = False
    grants_delivery_authority: Literal[False] = False
    grants_effect_authority: Literal[False] = False
    execution_authority_revalidation_required: Literal[True] = True

    @property
    def handoff_id(self) -> str:
        return stable_id("coding_agent_handoff", self)


class BoundedCodeHandoffV1Alpha1(FrozenContract):
    manifest: CodeContextManifestV1Alpha1
    receipt: CodingAgentHandoffReceiptV1Alpha1
    blocks: tuple[CodeContextBlockV1Alpha1, ...]

    @model_validator(mode="after")
    def exact_chain(self) -> Self:
        if self.receipt.manifest_id != self.manifest.manifest_id:
            raise ValueError("handoff receipt names a different manifest")
        if self.receipt.index_id != self.manifest.index_id:
            raise ValueError("handoff receipt names a different index than the manifest")
        if self.receipt.lens_id != self.manifest.lens_id:
            raise ValueError("handoff receipt names a different lens than the manifest")
        manifest_paths = tuple(item.path for item in self.manifest.blocks)
        if len(set(manifest_paths)) != len(manifest_paths):
            raise ValueError("handoff manifest repeats a bounded context path")
        if self.receipt.included_paths != manifest_paths:
            raise ValueError("handoff receipt included paths differ from the exact ordered manifest block paths")
        if tuple(item.block_id for item in self.blocks) != tuple(item.block_id for item in self.manifest.blocks):
            raise ValueError("handoff body blocks differ from manifest receipts")
        expected_receipts = tuple(
            CodeContextBlockReceiptV1Alpha1(
                block_id=item.block_id,
                path=item.path,
                line_start=item.line_start,
                line_end=item.line_end,
                body_digest=item.body_digest,
                byte_count=item.byte_count,
                token_estimate=item.token_estimate,
                reason=item.reason,
                evidence_ref=item.evidence_ref,
                symbol=item.symbol,
                symbol_line_start=item.symbol_line_start,
                symbol_line_end=item.symbol_line_end,
                symbol_body_digest=item.symbol_body_digest,
            )
            for item in self.blocks
        )
        if self.manifest.blocks != expected_receipts:
            raise ValueError("handoff manifest receipts differ from exact body blocks")
        return self


class CodingAgentReturnV1Alpha1(FrozenContract):
    """A provider-neutral agent's attributable answer to one exact handoff."""

    contract: Literal["ace.code-intelligence.coding-agent-return/v1alpha1"] = (
        "ace.code-intelligence.coding-agent-return/v1alpha1"
    )
    receiver_ref: str = Field(min_length=1, max_length=256)
    handoff_id: str = Field(min_length=1, max_length=128)
    index_id: str = Field(min_length=1, max_length=128)
    lens_id: str = Field(min_length=1, max_length=128)
    manifest_id: str = Field(min_length=1, max_length=128)
    disposition: Literal["change_proposed", "no_change_recommended", "blocked"]
    summary: str = Field(min_length=1, max_length=4_000)
    consumed_block_ids: tuple[str, ...]
    changed_paths: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    submitted_at: datetime
    claims_source_authority: Literal[False] = False
    claims_reasoning_authority: Literal[False] = False
    claims_delivery_authority: Literal[False] = False
    claims_effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if not self.consumed_block_ids:
            raise ValueError("coding-agent return must identify consumed context blocks")
        if len(set(self.consumed_block_ids)) != len(self.consumed_block_ids):
            raise ValueError("coding-agent return repeats a consumed block")
        if len(set(self.changed_paths)) != len(self.changed_paths):
            raise ValueError("coding-agent return repeats a changed path")
        if self.disposition != "change_proposed" and self.changed_paths:
            raise ValueError("only change_proposed may name changed paths")
        bounded_lists = (
            ("consumed_block_ids", self.consumed_block_ids, 64, 128),
            ("changed_paths", self.changed_paths, 64, 1_024),
            ("verification_refs", self.verification_refs, 64, 2_048),
            ("uncertainties", self.uncertainties, 64, 4_000),
        )
        for label, values, max_items, max_chars in bounded_lists:
            if len(values) > max_items:
                raise ValueError(f"coding-agent return {label} exceeds {max_items} items")
            if any(not value or len(value) > max_chars for value in values):
                raise ValueError(f"coding-agent return {label} entries must contain 1..{max_chars} characters")
        return self

    @property
    def return_id(self) -> str:
        return stable_id("coding_agent_return", self)


class CodingAgentReturnReceiptV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.coding-agent-return-receipt/v1alpha1"] = (
        "ace.code-intelligence.coding-agent-return-receipt/v1alpha1"
    )
    return_id: str
    receiver_ref: str
    handoff_id: str
    index_id: str
    lens_id: str
    manifest_id: str
    disposition: Literal["change_proposed", "no_change_recommended", "blocked"]
    consumed_block_ids: tuple[str, ...]
    changed_paths: tuple[str, ...]
    verification_refs: tuple[str, ...]
    warnings: tuple[str, ...]
    validated_at: datetime
    chain_validated: Literal[True] = True
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    effect_authority: Literal[False] = False
    execution_authority_revalidation_required: Literal[True] = True

    @property
    def receipt_id(self) -> str:
        return stable_id("coding_agent_return_receipt", self)


class CodeFileMutationObservationV1Alpha1(FrozenContract):
    """Exact bounded before/after bytes and deterministic patch for one path."""

    contract: Literal["ace.code-intelligence.file-mutation-observation/v1alpha1"] = (
        "ace.code-intelligence.file-mutation-observation/v1alpha1"
    )
    path: str = Field(min_length=1, max_length=1_024)
    before_body: str = Field(max_length=64_000)
    after_body: str = Field(max_length=64_000)
    before_byte_count: int = Field(ge=0, le=64_000)
    after_byte_count: int = Field(ge=0, le=64_000)
    before_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    after_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    patch: str = Field(max_length=128_000)
    patch_byte_count: int = Field(ge=0, le=128_000)
    patch_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observed_from_repository_diff: Literal[True] = True
    harness_applied_mutation: Literal[True] = True
    external_delivery_observed: Literal[False] = False

    @model_validator(mode="after")
    def exact_bytes_and_patch(self) -> Self:
        before = self.before_body.encode()
        after = self.after_body.encode()
        patch = self.patch.encode()
        if self.before_byte_count != len(before) or self.before_digest != raw_digest(before):
            raise ValueError("mutation before-byte receipt differs from exact body")
        if self.after_byte_count != len(after) or self.after_digest != raw_digest(after):
            raise ValueError("mutation after-byte receipt differs from exact body")
        expected_patch = deterministic_code_patch(self.path, self.before_body, self.after_body)
        if self.patch != expected_patch:
            raise ValueError("mutation patch differs from deterministic before/after diff")
        if self.patch_byte_count != len(patch) or self.patch_digest != raw_digest(patch):
            raise ValueError("mutation patch receipt differs from exact patch bytes")
        if self.before_digest == self.after_digest:
            raise ValueError("mutation before and after bodies are identical")
        return self

    @property
    def mutation_id(self) -> str:
        return stable_id("code_file_mutation", self)


class CodeVerificationObservationV1Alpha1(FrozenContract):
    """An independently observed check over one exact coding-agent return."""

    contract: Literal["ace.code-intelligence.verification-observation/v1alpha1"] = (
        "ace.code-intelligence.verification-observation/v1alpha1"
    )
    observer_ref: str = Field(min_length=1, max_length=256)
    return_id: str = Field(min_length=1, max_length=128)
    changed_paths: tuple[str, ...]
    mutation: CodeFileMutationObservationV1Alpha1
    command: tuple[str, ...]
    status: Literal["passed", "failed"]
    exit_code: int
    stdout_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    stderr_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observed_at: datetime
    independent_of_coding_agent_claims: Literal[True] = True
    self_authenticates_command_execution: Literal[False] = False
    verifier_replay_required: Literal[True] = True
    provider_neutral: Literal[True] = True
    grants_source_authority: Literal[False] = False
    grants_reasoning_authority: Literal[False] = False
    grants_change_authority: Literal[False] = False
    grants_approval_authority: Literal[False] = False
    grants_delivery_authority: Literal[False] = False
    grants_execution_authority: Literal[False] = False
    grants_effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def bounded_exact_observation(self) -> Self:
        if not self.command or len(self.command) > 32:
            raise ValueError("verification command must contain 1..32 arguments")
        if any(not item or len(item) > 2_048 for item in self.command):
            raise ValueError("verification command arguments must contain 1..2048 characters")
        if len(self.changed_paths) > 64 or len(set(self.changed_paths)) != len(self.changed_paths):
            raise ValueError("verification changed paths must be unique and bounded to 64")
        if any(not item or len(item) > 1_024 for item in self.changed_paths):
            raise ValueError("verification changed paths must contain 1..1024 characters")
        if (self.status == "passed") != (self.exit_code == 0):
            raise ValueError("verification status differs from the observed exit code")
        if self.changed_paths != (self.mutation.path,):
            raise ValueError("verification changed paths differ from exact mutation material")
        return self

    @property
    def verification_id(self) -> str:
        return stable_id("code_verification", self)


class CodeIntelligenceLivingUpdateV1Alpha1(FrozenContract):
    """Exact generation and restart closure after one bounded code return."""

    contract: Literal["ace.code-intelligence.living-update/v1alpha1"] = "ace.code-intelligence.living-update/v1alpha1"
    return_id: str
    return_receipt_id: str
    verification_id: str
    mutation_id: str
    changed_paths: tuple[str, ...]
    before_source_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    after_source_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    patch_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    initial_index_id: str
    initial_lens_id: str
    initial_snapshot_id: str
    initial_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    initial_generation: Literal[1] = 1
    updated_index_id: str
    updated_snapshot_id: str
    updated_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    updated_generation: Literal[2] = 2
    parent_snapshot_id: str
    parent_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    fresh_process_reopen: Literal[True] = True
    full_rescan_permitted: Literal[False] = False
    provider_invocation_permitted: Literal[False] = False
    post_restart_index_id: str
    post_restart_lens_id: str
    post_restart_source_block_id: str
    post_restart_source_body_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    post_restart_source_path: str
    post_restart_source_file_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    post_restart_source_symbol: str
    post_restart_symbol_line_start: int = Field(ge=1)
    post_restart_symbol_line_end: int = Field(ge=1)
    old_snapshot_still_readable: Literal[True] = True
    old_snapshot_id: str
    old_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observed_at: datetime
    provider_neutral: Literal[True] = True
    grants_source_authority: Literal[False] = False
    grants_reasoning_authority: Literal[False] = False
    grants_change_authority: Literal[False] = False
    grants_approval_authority: Literal[False] = False
    grants_delivery_authority: Literal[False] = False
    grants_execution_authority: Literal[False] = False
    grants_effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_parent_restart_and_history(self) -> Self:
        if not self.changed_paths or len(self.changed_paths) > 64:
            raise ValueError("living update must name 1..64 exact changed paths")
        if len(set(self.changed_paths)) != len(self.changed_paths):
            raise ValueError("living update repeats a changed path")
        if self.parent_snapshot_id != self.initial_snapshot_id:
            raise ValueError("generation two does not name the initial snapshot as parent")
        if self.parent_snapshot_digest != self.initial_snapshot_digest:
            raise ValueError("generation two parent digest differs from the initial snapshot")
        if self.old_snapshot_id != self.initial_snapshot_id or self.old_snapshot_digest != self.initial_snapshot_digest:
            raise ValueError("immutable-history receipt differs from the initial snapshot")
        if self.post_restart_index_id != self.updated_index_id:
            raise ValueError("post-restart index differs from generation two")
        if self.post_restart_source_file_digest != self.after_source_digest:
            raise ValueError("post-restart source digest differs from exact mutation after bytes")
        if self.post_restart_symbol_line_end < self.post_restart_symbol_line_start:
            raise ValueError("post-restart source symbol span is reversed")
        return self

    @property
    def update_id(self) -> str:
        return stable_id("code_living_update", self)


class CodeIntelligenceSingleChainLivingRunV1Alpha1(FrozenContract):
    """One inspectable chain from lens context through update and restart."""

    contract: Literal["ace.code-intelligence.single-chain-living-run/v1alpha1"] = (
        "ace.code-intelligence.single-chain-living-run/v1alpha1"
    )
    status: Literal["candidate_local_observed"] = "candidate_local_observed"
    receiver_ref: str
    initial_index_id: str
    initial_lens_id: str
    initial_manifest_id: str
    initial_handoff_id: str
    initial_snapshot_id: str
    agent_return: CodingAgentReturnV1Alpha1
    return_receipt: CodingAgentReturnReceiptV1Alpha1
    verification: CodeVerificationObservationV1Alpha1
    living_update: CodeIntelligenceLivingUpdateV1Alpha1
    limitations: tuple[str, ...]
    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_end_to_end_chain(self) -> Self:
        returned = self.agent_return
        receipt = self.return_receipt
        verification = self.verification
        update = self.living_update
        if returned.receiver_ref != self.receiver_ref or receipt.receiver_ref != self.receiver_ref:
            raise ValueError("living run receiver differs across handoff return chain")
        if returned.handoff_id != self.initial_handoff_id or receipt.handoff_id != self.initial_handoff_id:
            raise ValueError("living run handoff identity differs across return chain")
        if returned.index_id != self.initial_index_id or receipt.index_id != self.initial_index_id:
            raise ValueError("living run initial index differs across return chain")
        if returned.lens_id != self.initial_lens_id or receipt.lens_id != self.initial_lens_id:
            raise ValueError("living run initial lens differs across return chain")
        if returned.manifest_id != self.initial_manifest_id or receipt.manifest_id != self.initial_manifest_id:
            raise ValueError("living run manifest differs across return chain")
        if receipt.return_id != returned.return_id:
            raise ValueError("living run return receipt names a different return")
        if verification.return_id != returned.return_id or update.return_id != returned.return_id:
            raise ValueError("living run verification or update names a different return")
        if tuple(returned.changed_paths) != tuple(receipt.changed_paths):
            raise ValueError("living run receipt changed paths differ from agent return")
        if tuple(returned.changed_paths) != tuple(verification.changed_paths):
            raise ValueError("living run verification changed paths differ from agent return")
        if tuple(returned.changed_paths) != tuple(update.changed_paths):
            raise ValueError("living run update changed paths differ from agent return")
        if update.return_receipt_id != receipt.receipt_id:
            raise ValueError("living update names a different return receipt")
        if update.verification_id != verification.verification_id:
            raise ValueError("living update names a different verification observation")
        if update.mutation_id != verification.mutation.mutation_id:
            raise ValueError("living update names a different file mutation")
        if update.before_source_digest != verification.mutation.before_digest:
            raise ValueError("living update before-source digest differs from file mutation")
        if update.after_source_digest != verification.mutation.after_digest:
            raise ValueError("living update after-source digest differs from file mutation")
        if update.patch_digest != verification.mutation.patch_digest:
            raise ValueError("living update patch digest differs from file mutation")
        if update.initial_index_id != self.initial_index_id or update.initial_lens_id != self.initial_lens_id:
            raise ValueError("living update initial identities differ from the run")
        if update.initial_snapshot_id != self.initial_snapshot_id:
            raise ValueError("living update initial snapshot differs from the run")
        if verification.status != "passed":
            raise ValueError("living run requires an independently observed passing verification")
        return self

    @property
    def run_id(self) -> str:
        return stable_id("code_living_run", self)


class CodeIntelligenceReplayExpectationV1Alpha1(FrozenContract):
    """Externally recorded coordinates for paired archive-envelope validation."""

    contract: Literal["ace.code-intelligence.replay-expectation/v1alpha1"] = (
        "ace.code-intelligence.replay-expectation/v1alpha1"
    )
    raw_member_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    run_id: str
    return_receipt_id: str
    return_receipt_validated_at: datetime
    initial_snapshot_id: str
    initial_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    updated_snapshot_id: str
    updated_snapshot_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    post_restart_lens_id: str


class CodeIntelligenceJourneyV1Alpha1(FrozenContract):
    contract: Literal["ace.code-intelligence.repository-journey/v1alpha1"] = (
        "ace.code-intelligence.repository-journey/v1alpha1"
    )
    lens: AtriumCodeLensV1Alpha1
    handoff: BoundedCodeHandoffV1Alpha1
    scanner_stats: dict[str, int]
    limitations: tuple[str, ...]

    @field_validator("scanner_stats", mode="before")
    @classmethod
    def reject_non_exact_int_scanner_stat_values(cls, value: Any) -> Any:
        # ``int`` field coercion happily accepts ``bool`` (a subtype of
        # ``int``), numeric strings, and integral floats, silently narrowing
        # each into a plain ``int``. Every value must already be exactly
        # ``int`` (``type(value) is int``, not merely ``isinstance``) and
        # nonnegative here, before that coercion runs, or the after-validator's
        # own type check would only ever see values coercion already fixed up.
        if isinstance(value, dict):
            for item in value.values():
                if type(item) is not int or item < 0:
                    raise ValueError(f"journey scanner_stats values must be nonnegative int, not {item!r}")
        return value

    @model_validator(mode="after")
    def exact_scanner_stats(self) -> Self:
        expected_keys = {"files", "functions", "classes", "imports"}
        if set(self.scanner_stats) != expected_keys:
            raise ValueError("journey scanner_stats must contain exactly the keys files, functions, classes, imports")
        for key, value in self.scanner_stats.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"journey scanner_stats {key} must be a nonnegative int, not {value!r}")
        return self

    @model_validator(mode="after")
    def exact_cross_contract_closure(self) -> Self:
        """The lens, manifest, receipt, and bounded bodies name one exact index."""
        manifest = self.handoff.manifest
        receipt = self.handoff.receipt
        index_id = self.lens.index.index_id
        if manifest.index_id != index_id or receipt.index_id != index_id:
            raise ValueError("journey manifest or receipt names a different repository index")
        if manifest.lens_id != self.lens.lens_id or receipt.lens_id != self.lens.lens_id:
            raise ValueError("journey manifest or receipt names a different lens")
        if receipt.requested_change != self.lens.query:
            raise ValueError("journey handoff requests a change the lens did not examine")
        anchors_by_id = {item.anchor_id: item for item in self.lens.evidence}
        for block in self.handoff.blocks:
            anchor = anchors_by_id.get(block.evidence_ref)
            if anchor is None:
                raise ValueError("journey context block evidence does not resolve to an exact lens anchor")
            if block.symbol is None:
                if (
                    anchor.path != block.path
                    or anchor.line_start != block.line_start
                    or anchor.line_end != block.line_end
                    or anchor.content_digest != block.body_digest
                ):
                    raise ValueError("journey context block evidence anchor differs from its exact bounded body span")
            elif (
                anchor.path != block.path
                or anchor.line_start != block.symbol_line_start
                or anchor.line_end != block.symbol_line_end
                or anchor.content_digest != block.symbol_body_digest
            ):
                raise ValueError("journey context block evidence anchor differs from its exact named-symbol span")
        return self
