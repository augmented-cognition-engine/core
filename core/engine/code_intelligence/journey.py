"""Compose the first bounded Code Intelligence journey from existing assets."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from git import Repo

from core.engine.code_intelligence.contracts import (
    AtriumCodeLensV1Alpha1,
    BoundedCodeHandoffV1Alpha1,
    ChangeImpactV1Alpha1,
    CodeArtifactKind,
    CodeContextBlockReceiptV1Alpha1,
    CodeContextBlockV1Alpha1,
    CodeContextManifestV1Alpha1,
    CodeEdgeV1Alpha1,
    CodeIntelligenceJourneyV1Alpha1,
    CodeNodeV1Alpha1,
    CodingAgentHandoffReceiptV1Alpha1,
    ConfidenceBand,
    DerivationKind,
    DisconnectedSymbolCandidateV1Alpha1,
    RepositoryIndexIdentityV1Alpha1,
    SourceAnchorV1Alpha1,
    stable_digest,
)
from core.engine.code_intelligence.ownership import (
    CodeOwnershipProjectionV1Alpha1,
    GitHubCodeownersAdapter,
    OwnershipProjectionStatus,
)
from core.engine.intelligence.graph_builder import GraphBuilder
from core.engine.intelligence.queries import blast_radius, code_context, find_dead_code
from core.engine.scanner.ast_parser import LANG_MAP

_TEST_PATH = re.compile(r"(^|/)(tests?|test_[^/]+)(/|$)")
_API_PATH = re.compile(r"/(api|mcp)/|(^|/)ace_mcp_client/")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _node_id(kind: CodeArtifactKind, value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    digest = hashlib.sha256(value.encode()).hexdigest()[:10]
    return f"{kind.value}:{slug[:64]}:{digest}"


class CodeIntelligenceJourney:
    """Build an inspectable lens and bounded handoff for one local Python repository.

    The journey deliberately uses the existing phase-one Tree-sitter/import graph.
    It labels graph relationships as static evidence, treats disconnected symbols as
    candidates rather than unreachable code, and records every known coverage gap.
    """

    def __init__(self, repository: str | Path, *, max_context_files: int = 8, max_context_bytes: int = 24_000):
        self.root = Path(repository).resolve()
        self.max_context_files = max_context_files
        self.max_context_bytes = max_context_bytes
        if not self.root.is_dir():
            raise ValueError(f"repository does not exist: {self.root}")
        self.repo = Repo(self.root, search_parent_directories=False)

    def run(
        self,
        *,
        query: str,
        target_path: str,
        receiver_ref: str = "coding-agent:provider-neutral",
        builder: GraphBuilder | None = None,
        expected_index: RepositoryIndexIdentityV1Alpha1 | None = None,
    ) -> CodeIntelligenceJourneyV1Alpha1:
        target = self._safe_path(target_path)
        if target.suffix not in {".py", ".pyi"}:
            raise ValueError("python-local-static-v1 accepts only Python target files")

        if builder is None:
            builder = GraphBuilder(str(self.root))
            scanner_stats = {key: int(value) for key, value in builder.phase1_treesitter().items()}
        else:
            symbols = builder.get_symbols()
            scanner_stats = {
                "files": len(builder.get_files()),
                "functions": sum(item.get("kind") != "class" for item in symbols),
                "classes": sum(item.get("kind") == "class" for item in symbols),
                "imports": len(builder.get_imports()),
            }
        observed_index = self.index_identity(builder)
        if expected_index is not None and observed_index.index_id != expected_index.index_id:
            raise ValueError("repository changed after the exact index snapshot was reopened")
        index = expected_index or observed_index
        context = code_context(query, builder)
        target_symbols = [item for item in builder.get_symbols() if item["file"] == target_path]
        selected_symbols = self._selected_symbols(query, target_symbols)
        impact, skipped_symlink_tests = self._impact(target_path, builder, selected_symbols)
        evidence: list[SourceAnchorV1Alpha1] = []
        nodes: list[CodeNodeV1Alpha1] = []
        edges: list[CodeEdgeV1Alpha1] = []

        target_anchor = self._anchor(
            target_path,
            1,
            min(80, self._line_count(target_path)),
            DerivationKind.PARSER,
            ConfidenceBand.OBSERVED,
            "Exact target file in the scanned repository revision.",
        )
        evidence.append(target_anchor)

        repository_node = CodeNodeV1Alpha1(
            node_id=_node_id(CodeArtifactKind.REPOSITORY, index.repository),
            kind=CodeArtifactKind.REPOSITORY,
            label=index.repository,
            derivation=DerivationKind.GIT,
            confidence=ConfidenceBand.OBSERVED,
            detail=f"revision {index.revision[:12]} ({'dirty' if index.dirty else 'clean'})",
        )
        module_path = str(Path(target_path).parent)
        module_node = CodeNodeV1Alpha1(
            node_id=_node_id(CodeArtifactKind.MODULE, module_path),
            kind=CodeArtifactKind.MODULE,
            label=module_path,
            path=module_path,
            derivation=DerivationKind.PARSER,
            confidence=ConfidenceBand.OBSERVED,
        )
        target_node = CodeNodeV1Alpha1(
            node_id=_node_id(self._kind(target_path), target_path),
            kind=self._kind(target_path),
            label=Path(target_path).name,
            path=target_path,
            derivation=DerivationKind.PARSER,
            confidence=ConfidenceBand.OBSERVED,
            evidence_refs=(target_anchor.anchor_id,),
        )
        feature_node = CodeNodeV1Alpha1(
            node_id=_node_id(CodeArtifactKind.FEATURE, query),
            kind=CodeArtifactKind.FEATURE,
            label=query,
            derivation=DerivationKind.DECLARED,
            confidence=ConfidenceBand.OBSERVED,
            detail="User-declared change question; not inferred product truth.",
        )
        nodes.extend((repository_node, module_node, target_node, feature_node))
        edges.extend(
            (
                CodeEdgeV1Alpha1(
                    source=repository_node.node_id,
                    target=module_node.node_id,
                    relation="contains",
                    derivation=DerivationKind.PARSER,
                    confidence=ConfidenceBand.OBSERVED,
                ),
                CodeEdgeV1Alpha1(
                    source=module_node.node_id,
                    target=target_node.node_id,
                    relation="contains",
                    derivation=DerivationKind.PARSER,
                    confidence=ConfidenceBand.OBSERVED,
                    evidence_refs=(target_anchor.anchor_id,),
                ),
                CodeEdgeV1Alpha1(
                    source=feature_node.node_id,
                    target=target_node.node_id,
                    relation="examines_change_to",
                    derivation=DerivationKind.DECLARED,
                    confidence=ConfidenceBand.OBSERVED,
                    evidence_refs=(target_anchor.anchor_id,),
                ),
            )
        )

        service_path = self._service_path(target_path)
        service_node = CodeNodeV1Alpha1(
            node_id=_node_id(CodeArtifactKind.SERVICE, service_path),
            kind=CodeArtifactKind.SERVICE,
            label=f"{service_path} service boundary",
            path=service_path,
            derivation=DerivationKind.HEURISTIC,
            confidence=ConfidenceBand.INFERRED,
            detail="Directory-derived service boundary; no deployment descriptor asserts this identity.",
        )
        nodes.append(service_node)
        edges.append(
            CodeEdgeV1Alpha1(
                source=service_node.node_id,
                target=module_node.node_id,
                relation="contains_module",
                derivation=DerivationKind.HEURISTIC,
                confidence=ConfidenceBand.INFERRED,
            )
        )

        dependencies = (
            sorted(node for node in builder.graph.successors(target_path) if isinstance(node, str) and "::" not in node)
            if target_path in builder.graph
            else []
        )
        connected_paths = _unique(
            [
                *impact.direct_dependents,
                *dependencies,
                *impact.affected_tests,
                *(item.get("path", "") for item in context.get("context_files", [])),
            ]
        )
        for path in connected_paths[:40]:
            if not self._exists(path):
                continue
            anchor = self._anchor(
                path,
                1,
                min(40, self._line_count(path)),
                DerivationKind.GRAPH,
                ConfidenceBand.SUPPORTED,
                "Static graph or lexical feature connection.",
            )
            evidence.append(anchor)
            node = CodeNodeV1Alpha1(
                node_id=_node_id(self._kind(path), path),
                kind=self._kind(path),
                label=Path(path).name,
                path=path,
                derivation=DerivationKind.GRAPH,
                confidence=ConfidenceBand.SUPPORTED,
                evidence_refs=(anchor.anchor_id,),
            )
            nodes.append(node)
            if path in impact.direct_dependents:
                source_node = node.node_id
                target_node_id = target_node.node_id
                relation = "imports"
            elif path in dependencies:
                source_node = target_node.node_id
                target_node_id = node.node_id
                relation = "imports"
            else:
                source_node = target_node.node_id
                target_node_id = node.node_id
                relation = "affected_test" if self._kind(path) is CodeArtifactKind.TEST else "connected_code"
            edges.append(
                CodeEdgeV1Alpha1(
                    source=source_node,
                    target=target_node_id,
                    relation=relation,
                    derivation=DerivationKind.GRAPH,
                    confidence=ConfidenceBand.SUPPORTED,
                    evidence_refs=(anchor.anchor_id,),
                )
            )

        ordered_symbols = [*selected_symbols, *(item for item in target_symbols if item not in selected_symbols)]
        for symbol in ordered_symbols[:30]:
            anchor = self._anchor(
                target_path,
                int(symbol["line_start"]),
                int(symbol["line_end"]),
                DerivationKind.PARSER,
                ConfidenceBand.OBSERVED,
                "Tree-sitter symbol definition.",
            )
            evidence.append(anchor)
            symbol_node = CodeNodeV1Alpha1(
                node_id=_node_id(CodeArtifactKind.SYMBOL, f"{target_path}::{symbol['name']}"),
                kind=CodeArtifactKind.SYMBOL,
                label=symbol["name"],
                path=target_path,
                symbol=symbol["name"],
                derivation=DerivationKind.PARSER,
                confidence=ConfidenceBand.OBSERVED,
                evidence_refs=(anchor.anchor_id,),
            )
            nodes.append(symbol_node)
            edges.append(
                CodeEdgeV1Alpha1(
                    source=target_node.node_id,
                    target=symbol_node.node_id,
                    relation="defines",
                    derivation=DerivationKind.PARSER,
                    confidence=ConfidenceBand.OBSERVED,
                    evidence_refs=(anchor.anchor_id,),
                )
            )

        decision_nodes, decision_edges, decision_evidence, skipped_symlink_decisions = self._decision_connections(
            query=query,
            target_path=target_path,
            feature_node=feature_node,
        )
        nodes.extend(decision_nodes)
        edges.extend(decision_edges)
        evidence.extend(decision_evidence)

        historical_ownership_nodes, historical_ownership_edges = self._historical_ownership(target_path, target_node)
        nodes.extend(historical_ownership_nodes)
        edges.extend(historical_ownership_edges)

        ownership_projection = GitHubCodeownersAdapter(self.root).project(target_path)
        declared_ownership_nodes, declared_ownership_edges, declared_ownership_evidence = self._declared_ownership(
            ownership_projection,
            target_node,
        )
        nodes.extend(declared_ownership_nodes)
        edges.extend(declared_ownership_edges)
        evidence.extend(declared_ownership_evidence)

        disconnected, disconnected_evidence = self._disconnected(builder)
        evidence.extend(disconnected_evidence)

        omissions = [
            "Runtime dispatch, reflection, monkey-patching, generated code, and dynamic imports are not resolved.",
            "Static import reachability does not prove runtime reachability or safe deletion.",
            "Historical Git contributors are not treated as current ownership authority.",
            "No declared incident source is connected unless it exists in the scanned public repository.",
            "The first packet does not run an LSP, model inference, compiler, test suite, or external coding agent.",
        ]
        non_python = sorted(set(index.observed_languages) - {"python"})
        if non_python:
            omissions.append(
                "Observed non-Python languages are inventory-only in this acceptance profile: " + ", ".join(non_python)
            )
        if index.dirty:
            _, untracked_symlinks = self._untracked_digests()
            if untracked_symlinks:
                # Aggregated by deterministic count, never by joining every
                # untracked path: a working tree with thousands of untracked
                # symlinks must not grow this single omission entry
                # proportionally to that count.
                omissions.append(
                    "Untracked symlinks contribute only their link target text; their targets were never read or "
                    f"scanned: {len(untracked_symlinks)} symlink(s)."
                )
        if skipped_symlink_tests:
            omissions.append(
                "Symlinked test candidates were skipped by repository containment policy and were never read: "
                f"{skipped_symlink_tests} candidate(s)."
            )
        if skipped_symlink_decisions:
            omissions.append(
                "Symlinked decision-document candidates were skipped by repository containment policy and were "
                f"never read: {skipped_symlink_decisions} candidate(s)."
            )
        if not decision_nodes:
            omissions.append("No matching ADR or evidence record was found for the bounded query terms.")
        if not historical_ownership_nodes:
            omissions.append("No historical Git contributor record was available for the target path.")
        if ownership_projection.status is OwnershipProjectionStatus.UNAVAILABLE:
            # The ownership adapter's own uncertainty bound (``OWNERSHIP_MAX_
            # UNCERTAINTY_ITEMS`` items up to ``OWNERSHIP_MAX_UNCERTAINTY_ITEM_
            # CHARS`` characters each) is far larger than one lens omission
            # entry may be, so this reports a bounded count plus a bounded
            # excerpt of the first reason rather than joining every retained
            # uncertainty verbatim.
            first_uncertainty = ownership_projection.uncertainties[0][:160]
            omissions.append(
                "Declared path ownership unavailable: "
                f"{len(ownership_projection.uncertainties)} uncertainty note(s); first: {first_uncertainty} "
                "Git contributors do not establish target-path ownership."
            )
        elif ownership_projection.status is OwnershipProjectionStatus.UNASSIGNED:
            omissions.append(
                "Declared path ownership unassigned: "
                f"{ownership_projection.source_path} contains no supported rule matching {target_path}; "
                "no owner is inferred from repository governance, package authorship, or Git history."
            )

        degraded = []
        if index.dirty:
            degraded.append("dirty_working_tree")
        if not impact.affected_tests:
            degraded.append("affected_tests_not_found")
        if scanner_stats.get("files", 0) == 0:
            degraded.append("empty_index")

        # Context blocks are planned before the lens is frozen so that every
        # anchor a block cites is published as exact lens evidence.
        blocks, omitted = self._plan_context_blocks(
            target_path=target_path,
            target_symbols=selected_symbols,
            candidate_paths=[
                target_path,
                *(path for path in impact.direct_dependents if self._kind(path) is not CodeArtifactKind.TEST),
                *impact.affected_tests,
                *dependencies,
                *connected_paths,
            ],
            evidence=evidence,
        )

        lens = AtriumCodeLensV1Alpha1(
            index=index,
            query=query,
            target_path=target_path,
            nodes=tuple(self._dedupe_nodes(nodes)),
            edges=tuple(self._dedupe_edges(edges)),
            impact=impact,
            disconnected_symbols=disconnected,
            evidence=tuple(self._dedupe_evidence(evidence)),
            omissions=tuple(omissions),
            degraded_reasons=tuple(degraded),
        )
        handoff = self._bounded_handoff(
            lens=lens,
            blocks=blocks,
            omitted=omitted,
            receiver_ref=receiver_ref,
        )
        if self.index_identity(builder).index_id != index.index_id:
            raise ValueError("repository changed while the bounded Code journey was being composed")
        return CodeIntelligenceJourneyV1Alpha1(
            lens=lens,
            handoff=handoff,
            scanner_stats=scanner_stats,
            limitations=(
                "Supported target language: Python 3 source parsed with Tree-sitter.",
                "Supported topology: one local Git repository and one exact revision/working-tree identity.",
                "Impact is calibrated static evidence, not a universal program-analysis or safe-change guarantee.",
                "The handoff transfers bounded context, never source, reasoning, delivery, execution, or effect authority.",
            ),
        )

    def _safe_path(self, path: str) -> Path:
        if not path or Path(path).is_absolute():
            raise ValueError("target path must be a non-empty repository-relative path")
        try:
            candidate = (self.root / path).resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError("target path cannot be resolved safely") from exc
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("target path escapes repository") from exc
        if path != relative.as_posix():
            raise ValueError("target path must use one canonical repository-relative spelling without symlinks")
        if not candidate.is_file():
            raise ValueError(f"target file does not exist: {path}")
        return candidate

    def _exists(self, path: str) -> bool:
        try:
            self._safe_path(path)
        except ValueError:
            return False
        return True

    def _contains_symlink(self, path: Path) -> bool:
        """Detect a symlink at or below any component of a candidate path.

        Mirrors ``GitHubCodeownersAdapter._contains_symlink``: every path
        component is inspected with ``lstat`` before any size or content is
        read, so a symlink pointing outside the repository (or to another
        contained path in a way ``_safe_path`` would otherwise catch later)
        is rejected up front, before the expensive read.
        """
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

    def _read(self, path: str) -> str:
        return self._safe_path(path).read_text(encoding="utf-8", errors="replace")

    def _line_count(self, path: str) -> int:
        return max(1, len(self._read(path).splitlines()))

    def _anchor(
        self,
        path: str,
        line_start: int,
        line_end: int,
        derivation: DerivationKind,
        confidence: ConfidenceBand,
        explanation: str,
    ) -> SourceAnchorV1Alpha1:
        lines = self._read(path).splitlines()
        start = min(max(1, line_start), max(1, len(lines)))
        end = min(max(start, line_end), max(1, len(lines)))
        body = "\n".join(lines[start - 1 : end])
        return SourceAnchorV1Alpha1(
            path=path,
            line_start=start,
            line_end=end,
            content_digest=stable_digest(body),
            derivation=derivation,
            confidence=confidence,
            explanation=explanation,
        )

    def index_identity(self, builder: GraphBuilder) -> RepositoryIndexIdentityV1Alpha1:
        """Bind one phase-one graph to its exact Git revision and working tree."""
        dirty = self.repo.is_dirty(untracked_files=True)
        if dirty:
            status = self.repo.git.status("--porcelain=v1", "--untracked-files=all")
            diff = self.repo.git.diff("--binary", "HEAD")
            untracked, _ = self._untracked_digests()
            working_tree_digest = stable_digest({"status": status, "diff": diff, "untracked": untracked})
        else:
            working_tree_digest = "clean"
        observed = sorted(
            {
                LANG_MAP.get(Path(item["path"]).suffix, Path(item["path"]).suffix.lstrip("."))
                for item in builder.get_files()
                if Path(item["path"]).suffix
            }
        )
        remote = next(iter(self.repo.remotes), None)
        repository = self.root.name
        if remote is not None:
            url = next(iter(remote.urls), "")
            match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
            if match:
                repository = match.group(1)
        return RepositoryIndexIdentityV1Alpha1(
            repository=repository,
            revision=self.repo.head.commit.hexsha,
            dirty=dirty,
            working_tree_digest=working_tree_digest,
            scanner_contract="core.engine.intelligence.graph-builder/phase1-tree-sitter",
            observed_languages=tuple(observed),
            generated_at=datetime.now(timezone.utc),
        )

    def _untracked_digests(self) -> tuple[list[str], list[str]]:
        """Digest untracked entries without ever reading through a symlink.

        A symlink contributes its own target text, not the bytes it points at,
        so an untracked link into another tree can never pull outside material
        into this repository's working-tree identity.
        """
        entries: list[str] = []
        symlinks: list[str] = []
        for path in sorted(self.repo.untracked_files):
            file_path = self.root / path
            try:
                info = file_path.lstat()
            except OSError:
                entries.append(f"{path}:missing")
                continue
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(file_path)
                entries.append(f"{path}:symlink:{hashlib.sha256(target.encode()).hexdigest()}")
                symlinks.append(path)
            elif stat.S_ISREG(info.st_mode):
                try:
                    payload = self._read_regular_bytes(file_path)
                except OSError:
                    entries.append(f"{path}:missing")
                    continue
                entries.append(f"{path}:{hashlib.sha256(payload).hexdigest()}")
            else:
                entries.append(f"{path}:unsupported")
        return entries, symlinks

    @staticmethod
    def _read_regular_bytes(path: Path) -> bytes:
        """Read a regular file, refusing to follow a link swapped in mid-read."""
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 65_536)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(descriptor)

    def _impact(
        self,
        target_path: str,
        builder: GraphBuilder,
        selected_symbols: list[dict],
    ) -> tuple[ChangeImpactV1Alpha1, int]:
        report = blast_radius(target_path, builder.graph)
        direct = (
            sorted(
                node for node in builder.graph.predecessors(target_path) if isinstance(node, str) and "::" not in node
            )
            if target_path in builder.graph
            else []
        )
        transitive = sorted(
            node for node in report.get("affected_files", []) if isinstance(node, str) and "::" not in node
        )
        lexical_tests, skipped_symlink_tests = self._lexical_tests(target_path, selected_symbols)
        affected_tests = sorted(
            {path for path in [*direct, *transitive, *lexical_tests] if self._kind(path) is CodeArtifactKind.TEST}
        )
        gaps = [
            "Call-site and data-flow impact are unavailable without the optional LSP/runtime layers.",
            "Tests are linked by static imports or bounded symbol-name matches; collection and execution are not implied.",
        ]
        if not affected_tests:
            gaps.append("No affected test was found in the bounded static and lexical evidence.")
        impact = ChangeImpactV1Alpha1(
            target_path=target_path,
            direct_dependents=tuple(direct),
            transitive_dependents=tuple(transitive),
            affected_tests=tuple(affected_tests),
            known_coverage_gaps=tuple(gaps),
            confidence=ConfidenceBand.SUPPORTED if direct or affected_tests else ConfidenceBand.INFERRED,
            basis="Tree-sitter file/symbol inventory plus resolved static imports and bounded lexical test references.",
        )
        return impact, skipped_symlink_tests

    def _lexical_tests(self, target_path: str, selected_symbols: list[dict]) -> tuple[tuple[str, ...], int]:
        """Lexically scan test candidates without ever reading through a symlink.

        Every candidate is rejected before its size is read or its bytes are
        opened if any path component is a symlink, and the surviving path
        must still resolve to a contained regular file (``_exists``/``_read``
        apply the same lexical+resolved containment as every other read in
        this class). Skipped symlink candidates are counted, never read, so
        the caller can surface an honest bounded omission instead of silently
        acting as if fewer candidates existed.
        """
        names = {item["name"].split(".")[-1] for item in selected_symbols if not item["name"].startswith("_")}
        module = target_path.removesuffix(".py").replace("/", ".")
        matches: list[str] = []
        skipped_symlinks = 0
        for path in sorted(self.root.rglob("test*.py")):
            if self._contains_symlink(path):
                skipped_symlinks += 1
                continue
            rel = path.relative_to(self.root).as_posix()
            if not self._exists(rel):
                continue
            text = self._read(rel)
            matched = any(re.search(rf"\b{re.escape(name)}\b", text) for name in names) if names else module in text
            if matched:
                matches.append(rel)
        return tuple(matches[:50]), skipped_symlinks

    @staticmethod
    def _selected_symbols(query: str, target_symbols: list[dict]) -> list[dict]:
        query_terms = {word.lower() for word in _WORD.findall(query)}
        selected = [
            item
            for item in target_symbols
            if item["name"].lower() in query_terms or item["name"].split(".")[-1].lower() in query_terms
        ]
        return selected[:12]

    @staticmethod
    def _service_path(target_path: str) -> str:
        parts = Path(target_path).parts
        if len(parts) >= 3 and parts[:2] == ("core", "engine"):
            return "/".join(parts[:3])
        if len(parts) >= 2:
            return "/".join(parts[:2])
        return parts[0]

    def _decision_connections(
        self,
        *,
        query: str,
        target_path: str,
        feature_node: CodeNodeV1Alpha1,
    ) -> tuple[list[CodeNodeV1Alpha1], list[CodeEdgeV1Alpha1], list[SourceAnchorV1Alpha1], int]:
        """Scan decision documents without ever reading through a symlink.

        Every candidate is rejected before it is opened if any path component
        is a symlink, matching ``_lexical_tests``. Skipped symlink candidates
        are counted, never read, so the caller can surface an honest bounded
        omission.
        """
        terms = {Path(target_path).stem.lower()}
        terms.update(word.lower() for word in _WORD.findall(query) if len(word) >= 5)
        nodes: list[CodeNodeV1Alpha1] = []
        edges: list[CodeEdgeV1Alpha1] = []
        evidence: list[SourceAnchorV1Alpha1] = []
        skipped_symlinks = 0
        roots = [self.root / "docs" / "design", self.root / "docs" / "evidence"]
        for base in roots:
            if not base.exists():
                continue
            for path in sorted(base.glob("*.md")):
                if self._contains_symlink(path):
                    skipped_symlinks += 1
                    continue
                rel = path.relative_to(self.root).as_posix()
                if not self._exists(rel):
                    continue
                lines = self._read(rel).splitlines()
                match_line = next(
                    (idx for idx, line in enumerate(lines, 1) if any(term in line.lower() for term in terms)),
                    None,
                )
                if match_line is None:
                    continue
                anchor = self._anchor(
                    rel,
                    max(1, match_line - 2),
                    min(len(lines), match_line + 3),
                    DerivationKind.HEURISTIC,
                    ConfidenceBand.INFERRED,
                    "Bounded lexical connection to a design or evidence record; relevance requires human review.",
                )
                kind = CodeArtifactKind.ADR if "/design/" in rel else CodeArtifactKind.DECISION
                node = CodeNodeV1Alpha1(
                    node_id=_node_id(kind, rel),
                    kind=kind,
                    label=path.stem.replace("-", " "),
                    path=rel,
                    derivation=DerivationKind.HEURISTIC,
                    confidence=ConfidenceBand.INFERRED,
                    evidence_refs=(anchor.anchor_id,),
                    detail="Possible rationale/evidence connection; not a declared ADR edge.",
                )
                nodes.append(node)
                evidence.append(anchor)
                edges.append(
                    CodeEdgeV1Alpha1(
                        source=feature_node.node_id,
                        target=node.node_id,
                        relation="possibly_informed_by",
                        derivation=DerivationKind.HEURISTIC,
                        confidence=ConfidenceBand.INFERRED,
                        evidence_refs=(anchor.anchor_id,),
                    )
                )
                if len(nodes) >= 8:
                    return nodes, edges, evidence, skipped_symlinks
        return nodes, edges, evidence, skipped_symlinks

    def _historical_ownership(
        self,
        target_path: str,
        target_node: CodeNodeV1Alpha1,
    ) -> tuple[list[CodeNodeV1Alpha1], list[CodeEdgeV1Alpha1]]:
        commits = list(self.repo.iter_commits(paths=target_path, max_count=30))
        counts = Counter(commit.author.name or commit.author.email or "unknown" for commit in commits)
        nodes = []
        edges = []
        for author, count in counts.most_common(3):
            node = CodeNodeV1Alpha1(
                node_id=_node_id(CodeArtifactKind.CONTRIBUTOR, author),
                kind=CodeArtifactKind.CONTRIBUTOR,
                label=author,
                derivation=DerivationKind.GIT,
                confidence=ConfidenceBand.SUPPORTED,
                detail=f"Historical contributor on {count} of the last {len(commits)} path commits; not current authority.",
            )
            nodes.append(node)
            edges.append(
                CodeEdgeV1Alpha1(
                    source=node.node_id,
                    target=target_node.node_id,
                    relation="historical_contributor",
                    derivation=DerivationKind.GIT,
                    confidence=ConfidenceBand.SUPPORTED,
                    evidence_refs=tuple(
                        f"git:{commit.hexsha}"
                        for commit in commits
                        if (commit.author.name or commit.author.email) == author
                    )[:5],
                )
            )
        return nodes, edges

    @staticmethod
    def _declared_ownership(
        projection: CodeOwnershipProjectionV1Alpha1,
        target_node: CodeNodeV1Alpha1,
    ) -> tuple[list[CodeNodeV1Alpha1], list[CodeEdgeV1Alpha1], list[SourceAnchorV1Alpha1]]:
        if projection.status is not OwnershipProjectionStatus.DECLARED:
            return [], [], []

        nodes: list[CodeNodeV1Alpha1] = []
        edges: list[CodeEdgeV1Alpha1] = []
        evidence: list[SourceAnchorV1Alpha1] = []
        for owner in projection.owners:
            anchor = owner.evidence
            node = CodeNodeV1Alpha1(
                node_id=_node_id(
                    CodeArtifactKind.OWNERSHIP,
                    f"declared-review:{owner.owner_ref}:{owner.matched_pattern}",
                ),
                kind=CodeArtifactKind.OWNERSHIP,
                label=owner.owner_ref,
                path=anchor.path,
                derivation=DerivationKind.DECLARED,
                confidence=owner.confidence,
                evidence_refs=(anchor.anchor_id,),
                detail=(
                    f"Declared review responsibility from pattern {owner.matched_pattern!r}. "
                    "Identity and platform enforcement are unverified; this grants no source, change, approval, "
                    "delivery, or effect authority through ACE."
                ),
            )
            nodes.append(node)
            evidence.append(anchor)
            edges.append(
                CodeEdgeV1Alpha1(
                    source=node.node_id,
                    target=target_node.node_id,
                    relation="declared_review_responsibility",
                    derivation=DerivationKind.DECLARED,
                    confidence=owner.confidence,
                    evidence_refs=(anchor.anchor_id,),
                )
            )
        return nodes, edges, evidence

    def _disconnected(
        self,
        builder: GraphBuilder,
    ) -> tuple[tuple[DisconnectedSymbolCandidateV1Alpha1, ...], list[SourceAnchorV1Alpha1]]:
        candidates = []
        evidence = []
        seen_symbol_ids: set[str] = set()
        for item in sorted(
            find_dead_code(builder), key=lambda value: (value["file"], value["line_start"], value["name"])
        ):
            name = item["name"]
            if item.get("kind") not in {"function", "method"} or name.startswith("test_") or name.startswith("__"):
                continue
            symbol_id = f"{item['file']}::{name}"
            if symbol_id in seen_symbol_ids:
                continue
            seen_symbol_ids.add(symbol_id)
            anchor = self._anchor(
                item["file"],
                int(item["line_start"]),
                int(item["line_end"]),
                DerivationKind.GRAPH,
                ConfidenceBand.INFERRED,
                "The defining file has no incoming resolved static import edge in the bounded index.",
            )
            evidence.append(anchor)
            candidates.append(
                DisconnectedSymbolCandidateV1Alpha1(
                    symbol_id=symbol_id,
                    path=item["file"],
                    symbol=name,
                    line_start=int(item["line_start"]),
                    reason=(
                        "Defining file has no incoming resolved static import edge. The symbol may still be a CLI, "
                        "plugin, framework, generated, reflection, or external entrypoint; do not delete without verification."
                    ),
                    evidence_ref=anchor.anchor_id,
                )
            )
            if len(candidates) >= 25:
                break
        return tuple(candidates), evidence

    def _plan_context_blocks(
        self,
        *,
        target_path: str,
        target_symbols: list[dict],
        candidate_paths: list[str],
        evidence: list[SourceAnchorV1Alpha1],
    ) -> tuple[list[CodeContextBlockV1Alpha1], list[str]]:
        """Select bounded bodies, appending any anchor they need to ``evidence``.

        Every block span is inclusive and its body is the exact ``"\\n".join``
        of those lines, so an empty file is one empty line and a byte-truncated
        body ends on the line its final newline opens.
        """
        symbol_spans: dict[str, tuple[str, int, int]] = {}
        for item in target_symbols:
            symbol_spans.setdefault(
                item["file"],
                (item["name"], int(item["line_start"]), int(item["line_end"])),
            )
        blocks: list[CodeContextBlockV1Alpha1] = []
        omitted = []
        # Per-candidate omission reasons are aggregated by reason (count, not
        # path) so a repository with a large candidate set and a tiny byte
        # budget cannot grow the manifest's omission metadata proportionally
        # to the number of candidates.
        omission_counts: Counter[str] = Counter()
        total_bytes = 0
        for path in _unique(candidate_paths):
            if len(blocks) >= self.max_context_files:
                omitted.append("context_file_limit_reached")
                break
            if not self._exists(path):
                continue
            lines = self._read(path).splitlines()
            selected_symbol = symbol_spans.get(path)
            if selected_symbol is not None:
                _, symbol_start, symbol_end = selected_symbol
                start = max(1, symbol_start - 8)
                end = max(start, min(len(lines), symbol_end + 8))
            else:
                start = 1
                end = max(start, min(len(lines), 80))
            body = "\n".join(lines[start - 1 : end])
            encoded = body.encode()
            remaining = self.max_context_bytes - total_bytes
            if remaining <= 0:
                omitted.append("context_byte_limit_reached")
                break
            if selected_symbol is not None and len(encoded) > remaining:
                _, symbol_start, symbol_end = selected_symbol
                exact_body = "\n".join(lines[symbol_start - 1 : symbol_end])
                exact_encoded = exact_body.encode()
                if len(exact_encoded) > remaining:
                    # A named symbol body is emitted whole or not at all: it is
                    # never split mid-line, so a symbol too large for the
                    # remaining budget is omitted rather than partially sent.
                    omission_counts["symbol_context_omitted"] += 1
                    continue
                start = symbol_start
                end = symbol_end
                body = exact_body
                encoded = exact_encoded
                omission_counts["symbol_context_reduced"] += 1
            if len(encoded) > remaining:
                # Never split a line: keep the longest whole-line prefix of the
                # selected span whose exact body fits the remaining budget, so
                # line_start/line_end/digest always describe complete lines.
                selected_lines = lines[start - 1 : end]
                fitted_count = 0
                consumed = 0
                for offset, line in enumerate(selected_lines):
                    line_bytes = len(line.encode()) + (1 if offset > 0 else 0)
                    if consumed + line_bytes > remaining:
                        break
                    consumed += line_bytes
                    fitted_count = offset + 1
                if fitted_count == 0:
                    omission_counts["context_byte_limit_omitted"] += 1
                    continue
                end = start + fitted_count - 1
                body = "\n".join(selected_lines[:fitted_count])
                encoded = body.encode()
                omission_counts["context_byte_limit_reduced"] += 1
            body_digest = stable_digest(body)
            symbol_body_digest = (
                stable_digest("\n".join(lines[selected_symbol[1] - 1 : selected_symbol[2]]))
                if selected_symbol is not None
                else None
            )
            # A named-symbol block's evidence must resolve to an anchor over the
            # exact symbol span; a non-symbol block's evidence must resolve to an
            # anchor over its own exact bounded body span. Either reuse an
            # existing published anchor that matches exactly, or mint one.
            if selected_symbol is not None:
                required_start, required_end, required_digest = (
                    selected_symbol[1],
                    selected_symbol[2],
                    symbol_body_digest,
                )
            else:
                required_start, required_end, required_digest = start, end, body_digest
            anchor = next(
                (
                    item
                    for item in evidence
                    if item.path == path
                    and item.line_start == required_start
                    and item.line_end == required_end
                    and item.content_digest == required_digest
                ),
                None,
            )
            if anchor is None:
                anchor = self._anchor(
                    path,
                    required_start,
                    required_end,
                    DerivationKind.PARSER,
                    ConfidenceBand.OBSERVED,
                    "Exact bounded source excerpt selected for the coding-agent handoff.",
                )
                evidence.append(anchor)
            block = CodeContextBlockV1Alpha1(
                path=path,
                line_start=start,
                line_end=end,
                body=body,
                body_digest=body_digest,
                byte_count=len(encoded),
                token_estimate=(len(body) + 3) // 4,
                reason=(
                    f"named target symbol:{selected_symbol[0]}"
                    if selected_symbol is not None
                    else ("target" if path == target_path else "affected test or connected code")
                ),
                evidence_ref=anchor.anchor_id,
                symbol=selected_symbol[0] if selected_symbol is not None else None,
                symbol_line_start=selected_symbol[1] if selected_symbol is not None else None,
                symbol_line_end=selected_symbol[2] if selected_symbol is not None else None,
                symbol_body_digest=symbol_body_digest,
            )
            blocks.append(block)
            total_bytes += len(encoded)
        omitted.extend(f"{reason}:{count}" for reason, count in sorted(omission_counts.items()))
        return blocks, omitted

    def _bounded_handoff(
        self,
        *,
        lens: AtriumCodeLensV1Alpha1,
        blocks: list[CodeContextBlockV1Alpha1],
        omitted: list[str],
        receiver_ref: str,
    ) -> BoundedCodeHandoffV1Alpha1:
        """Close the manifest and receipt over one exact ordered block set."""
        receipts = tuple(
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
            for item in blocks
        )
        manifest = CodeContextManifestV1Alpha1(
            index_id=lens.index.index_id,
            lens_id=lens.lens_id,
            blocks=receipts,
            total_bytes=sum(item.byte_count for item in receipts),
            total_token_estimate=sum(item.token_estimate for item in receipts),
            max_files=self.max_context_files,
            max_bytes=self.max_context_bytes,
            omissions=tuple(omitted),
            degraded_reasons=lens.degraded_reasons,
        )
        receipt = CodingAgentHandoffReceiptV1Alpha1(
            receiver_ref=receiver_ref,
            requested_change=lens.query,
            requested_outputs=("reasoned_plan", "proposed_change_or_no_change", "verification_result"),
            index_id=lens.index.index_id,
            lens_id=lens.lens_id,
            manifest_id=manifest.manifest_id,
            included_paths=tuple(item.path for item in receipts),
        )
        return BoundedCodeHandoffV1Alpha1(manifest=manifest, receipt=receipt, blocks=tuple(blocks))

    @staticmethod
    def _kind(path: str) -> CodeArtifactKind:
        normalized = path.replace(os.sep, "/")
        if _TEST_PATH.search(normalized) or Path(normalized).name.startswith("test_"):
            return CodeArtifactKind.TEST
        if _API_PATH.search("/" + normalized):
            return CodeArtifactKind.API
        if normalized.startswith("docs/design/"):
            return CodeArtifactKind.ADR
        if normalized.startswith("docs/evidence/"):
            return CodeArtifactKind.DECISION
        return CodeArtifactKind.FILE

    @staticmethod
    def _dedupe_nodes(nodes: list[CodeNodeV1Alpha1]) -> list[CodeNodeV1Alpha1]:
        return list({item.node_id: item for item in nodes}.values())

    @staticmethod
    def _dedupe_edges(edges: list[CodeEdgeV1Alpha1]) -> list[CodeEdgeV1Alpha1]:
        return list({(item.source, item.target, item.relation): item for item in edges}.values())

    @staticmethod
    def _dedupe_evidence(evidence: list[SourceAnchorV1Alpha1]) -> list[SourceAnchorV1Alpha1]:
        return list({item.anchor_id: item for item in evidence}.values())
