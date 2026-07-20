# engine/product/capability_mapper.py
import fnmatch
import logging

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.core.exceptions import CapabilityMapperError
from core.engine.core.llm import get_llm
from core.engine.product.map import ProductMap

logger = logging.getLogger(__name__)


def _canonical_path(path: str) -> str:
    """Strip a leading core/ so the canonical core/engine/... generation matches the engine/...
    fallback globs, and so a stale engine/x twin and a current core/engine/x collapse to one logical
    key (item E — the codebase was restructured engine/ -> core/engine/ and the graph held both)."""
    return path[5:] if path.startswith("core/") else path


class CapabilityMapper:
    """Map existing graph data to product-level capabilities.
    Reads from graph_file, graph_function, graph_decision tables.
    Writes to capability table + realizes edges."""

    def __init__(self, db_pool):
        self._pool = db_pool
        self._product_map = ProductMap(db_pool)
        self._llm = get_llm()

    def _validate_mapper_inputs(self, product_id: str, description: str = "") -> None:
        """Validate capability mapper inputs before graph queries or LLM calls.

        Raises CapabilityMapperError for malformed product_id so bootstrap
        and intent-mapping paths fail fast instead of writing orphaned
        capability records with invalid org references.
        """
        if not product_id or ":" not in product_id:
            raise CapabilityMapperError(f"Invalid product_id: {product_id!r}")
        if description is not None and len(description) > 10_000:
            raise CapabilityMapperError(f"description too long: {len(description)} > 10000 characters")

    def _matches_glob(self, file_path: str, pattern: str) -> bool:
        """Check if a file path matches a glob pattern.
        Supports ** for recursive matching. Normalizes a leading core/ so the engine/... fallback
        globs match the canonical core/engine/... generation (item E)."""
        file_path = _canonical_path(file_path)
        if "**" in pattern:
            base = pattern.replace("/**", "")
            return file_path.startswith(base + "/")
        return fnmatch.fnmatch(file_path, pattern)

    async def bootstrap_from_graph(self, product_id: str, graph_id: str | None = None) -> list[dict]:
        """Read existing graph, propose capability groupings.
        1. Create capability_scan record (status: running)  [skipped when graph_id passed directly]
        2. Query all graph_file and graph_decision records for the graph
        3. LLM clusters files into logical capabilities
        4. Update capability_scan record (status: completed)  [skipped when graph_id passed directly]
        5. Return proposed capabilities (NOT auto-committed)

        Args:
            product_id: Product to associate the scan record with.
            graph_id:   Explicit graph_id to query. When provided, skips the
                        product→graph lookup and capability_scan record creation.
                        Used by the external scanner for competitor graphs.
        """
        self._validate_mapper_inputs(product_id)
        scan_id = None
        logger.info("Bootstrap capability mapping from graph: product=%s graph_id=%s", product_id, graph_id)

        async with self._pool.connection() as db:
            if graph_id is None:
                # Step 1: Create scan record with status=running (internal path only)
                scan_result = await db.query(
                    """
                    CREATE capability_scan SET
                        status = 'running',
                        started_at = time::now()
                    """,
                    {"product": product_id},
                )
                scan = parse_one(scan_result)
                scan_id = scan.get("id") if scan else None

                # Resolve graph_id from product
                graph_result = await db.query(
                    """
                    SELECT graph_id, scan_completed_at FROM graph
                    WHERE product = <record>$product
                    ORDER BY scan_completed_at DESC LIMIT 1
                    """,
                    {"product": product_id},
                )
                graph_rows = parse_rows(graph_result)
                graph_id = graph_rows[0].get("graph_id") if graph_rows else None

            # Step 2: Query graph_file and graph_decision records
            if graph_id:
                files_result = await db.query(
                    """
                    SELECT id, path, language, line_count, change_frequency, graph_id
                    FROM graph_file WHERE graph_id = $gid ORDER BY path
                    """,
                    {"gid": graph_id},
                )
            else:
                files_result = await db.query(
                    "SELECT id, path, language, line_count, change_frequency, graph_id FROM graph_file ORDER BY path"
                )
            files = parse_rows(files_result)

            decisions_result = await db.query(
                """
                SELECT id, title, description, timestamp, files_changed, graph_id
                FROM graph_decision WHERE graph_id = $gid ORDER BY timestamp DESC
                """,
                {"gid": graph_id or "default"},
            )
            decisions = parse_rows(decisions_result)

        # Step 3: LLM proposes capabilities (outside db connection scope)
        proposals = await self.propose_capabilities(files, decisions)

        if scan_id:
            async with self._pool.connection() as db:
                # Step 4: Update scan record with status=completed (internal path only)
                await db.query(
                    """
                    UPDATE <record>$scan_id SET
                        status = 'completed',
                        file_count = $file_count,
                        proposal_count = $proposal_count,
                        completed_at = time::now()
                    """,
                    {
                        "scan_id": scan_id,
                        "file_count": len(files),
                        "proposal_count": len(proposals),
                    },
                )

            try:
                from core.engine.events.bus import bus

                await bus.emit(
                    "capabilities.scanned",
                    {
                        "product_id": product_id,
                        "file_count": len(files),
                        "proposal_count": len(proposals),
                    },
                )
            except Exception:
                pass

        logger.info(
            "Bootstrap complete: product=%s files=%d proposals=%d",
            product_id,
            len(files),
            len(proposals),
        )
        # Step 5: Return proposals (auto-committed by caller for external repos;
        # human confirms for internal repos)
        return proposals

    async def bootstrap_from_intent(self, description: str, product_id: str) -> dict:
        """Generate capability map from a project description (greenfield path).

        Inverse of bootstrap_from_graph — works from intent, not code.
        Writes capabilities (status: planned) and vision to DB.
        """
        prompt = f"""You are a product architect. Given this project description, propose a capability map.

PROJECT: {description}

Return JSON with:
- "capabilities": list of 8-15 capabilities, each with:
  - "name": human-readable name
  - "slug": snake_case identifier
  - "description": 1-2 sentence description of what it does
  - "priority": "critical" | "important" | "nice_to_have"
- "vision": 1-2 sentence product vision
- "recommended_first": {{"capability": "<slug>", "reason": "why this should be built first"}}

Focus on user-facing capabilities, not technical layers. Order by dependency (build-first at top)."""

        self._validate_mapper_inputs(product_id, description)
        result = await self._llm.complete_json(prompt)

        capabilities = result.get("capabilities", [])
        if not capabilities:
            raise CapabilityMapperError(f"LLM returned no capabilities for intent: {description[:100]!r}")

        vision = result.get("vision", "")
        recommended_first = result.get("recommended_first", {})

        # Write capabilities to DB
        async with self._pool.connection() as db:
            for cap in capabilities:
                await db.query(
                    """UPSERT capability SET
                        product = <record>$product,
                        name = $name,
                        slug = <string>$slug,
                        description = $description,
                        status = 'planned',
                        priority = $priority,
                        tags = ['greenfield'],
                        updated_at = time::now()
                    WHERE product = <record>$product AND slug = <string>$slug""",
                    {
                        "product": product_id,
                        "name": cap.get("name", ""),
                        "slug": cap.get("slug", ""),
                        "description": cap.get("description", ""),
                        "priority": cap.get("priority", "important"),
                    },
                )

            # Write vision
            if vision:
                await db.query(
                    """UPSERT product_vision SET
                        product = <record>$product,
                        name = 'Product Vision',
                        description = $desc,
                        active = true,
                        updated_at = time::now()
                    WHERE product = <record>$product AND active = true""",
                    {"product": product_id, "desc": vision},
                )

        return {
            "capabilities": capabilities,
            "vision": vision,
            "recommended_first": recommended_first,
        }

    async def propose_capabilities(self, files: list[dict], decisions: list[dict]) -> list[dict]:
        """LLM proposes capabilities with confidence scores.

        Two-pass approach for large codebases:
        1. Group files by top-level directory (no LLM, just structure)
        2. Send directory summary + decision context to LLM for capability naming
        """
        if not files:
            return []
        return await self._llm_propose(files, decisions)

    def _group_by_directory(self, files: list[dict]) -> dict[str, list[dict]]:
        """Group files by their top-level module directory."""
        groups = {}
        for f in files:
            path = f.get("path", "")
            parts = path.split("/")
            # Use first 2 levels for grouping (e.g., engine/capture, portal/src)
            if len(parts) >= 2:
                key = f"{parts[0]}/{parts[1]}"
            else:
                key = parts[0] if parts else "root"
            groups.setdefault(key, []).append(f)
        return groups

    async def _llm_propose(self, files: list[dict], decisions: list[dict]) -> list[dict]:
        """Call LLM to cluster directory groups into capabilities."""
        # Step 1: group by directory structure
        groups = self._group_by_directory(files)

        # Step 2: build compact summary (directory → file count + languages)
        dir_summary = []
        for dir_path, dir_files in sorted(groups.items()):
            langs = {}
            for f in dir_files:
                lang = f.get("language", "unknown")
                langs[lang] = langs.get(lang, 0) + 1
            lang_str = ", ".join(f"{lang}: {cnt}" for lang, cnt in sorted(langs.items()))
            sample_files = [f.get("path", "") for f in dir_files[:5]]
            samples = "\n    ".join(sample_files)
            dir_summary.append(f"  {dir_path}/ ({len(dir_files)} files, {lang_str})\n    {samples}")

        dir_text = "\n".join(dir_summary)

        decision_list = (
            "\n".join(f"- {d.get('title', '')}" for d in decisions[:30]) if decisions else "(no decisions recorded)"
        )

        prompt = f"""You are an expert software architect analyzing a codebase.

Here are the directory groups with file counts and sample files:

{dir_text}

Recent architectural decisions:
{decision_list}

Group these directories into logical PRODUCT CAPABILITIES. A capability is a user-facing or system feature, not a technical layer.

Good examples: "Intelligence Pipeline", "Task Runner", "Portal Dashboard", "Code Scanner", "Ideas Pipeline"
Bad examples: "Python Files", "Utils", "Config"

Return a JSON array where each element has:
- name: human-readable capability name
- slug: snake_case identifier
- description: one sentence about what it does
- file_glob: glob pattern matching the files (e.g., "engine/capture/**")
- file_ids: [] (empty — will be populated later)
- confidence: 0.0-1.0

Merge related directories into single capabilities. Aim for 8-20 capabilities.
"""
        result = await self._llm.complete_json(prompt)

        # Handle both direct list and dict-wrapped responses
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("capabilities", "items", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
        return []

    async def map_files_to_capabilities(self, product_id: str) -> dict:  # noqa: PLR0912
        """Backfill realizes edges for all graph_file records using glob patterns.

        Loads all capabilities and their file_glob patterns, then matches
        every graph_file against them deterministically (no LLM).  Falls back
        to slug-derived directory patterns when file_glob is not set.

        Returns:
            {"mapped": int, "unmatched": int}
        """
        import fnmatch

        async with self._pool.connection() as db:
            caps_result = await db.query(
                "SELECT id, slug, file_glob FROM capability WHERE product = $product",
                {"product": parse_record_id(product_id)},
            )
            caps = parse_rows(caps_result)

            files_result = await db.query("SELECT id, path FROM graph_file WHERE graph_id = 'default'")
            files = parse_rows(files_result)

        # Dedup by canonical (core/-stripped) path: the graph carried two generations (a stale
        # engine/x beside the current core/engine/x). Keep one logical record per file, preferring
        # the canonical core/ record, so reality.files maps each file once (item E).
        _by_canon: dict[str, dict] = {}
        for f in files:
            canon = _canonical_path(f.get("path", ""))
            if canon not in _by_canon or str(f.get("path", "")).startswith("core/"):
                _by_canon[canon] = f
        # Drop stale orphans: a bare `engine/...` record with no `core/engine/...` twin is a file
        # removed in the current generation. Keeping it would leak a stale path into reality.files
        # (it survives dedup because it has no canonical twin). Every default-graph `engine/` path is
        # stale, so exclude them outright — reality.files then holds only current code.
        files = [f for f in _by_canon.values() if not str(f.get("path", "")).startswith("engine/")]

        # Build (cap_id, glob_pattern) pairs; derive pattern from slug when missing
        _SLUG_GLOB_FALLBACKS: dict[str, list[str]] = {
            # Orchestration & intelligence
            "intelligence_pipeline": ["engine/orchestrator/**"],
            "agent_orchestration": ["engine/orchestration/**"],
            "orchestration_engine": ["engine/orchestrator/**", "engine/orchestration/**"],
            "runtime_intelligence": ["engine/runtime/**", "engine/intelligence/**"],
            "intelligence_loading": ["engine/runtime/**", "engine/intelligence/**"],
            "intelligence_maturation": ["engine/runtime/**", "engine/intelligence/**"],
            "reasoning_frameworks": ["engine/reasoning/**", "engine/cognition/**"],
            "cognitive_composition": ["engine/cognition/**"],
            "task_classification": ["engine/orchestrator/**"],
            "dispatch_planning": ["engine/orchestration/**", "engine/pm/**"],
            "flow_control": ["engine/flow/**", "engine/conductor/**"],
            # Capture & knowledge
            "capture_pipeline": ["engine/capture/**"],
            "content_capture": ["engine/capture/**"],
            "decision_capture": ["engine/capture/**"],
            "decision_tracking": ["engine/capture/**", "engine/graph/**"],
            "knowledge_graph": ["engine/graph/**"],
            "graph_operations": ["engine/graph/**"],
            # Scanner
            "code_scanner": ["engine/scanner/**"],
            "git_integration": ["engine/scanner/**", "engine/github/**"],
            "live_file_watching": ["engine/live/**"],
            # Product & PM
            "agentic_pm": ["engine/product/**", "engine/pm/**"],
            "product_map": ["engine/product/**"],
            "spec_generator": ["engine/product/**"],
            "acceptance_verifier": ["engine/verification/**"],
            "initiative_decomposition": ["engine/product/**"],
            "smart_decomposer": ["engine/product/**"],
            "question_engine": ["engine/product/**"],
            "product_prioritizer": ["engine/product/**", "engine/pm/**"],
            "project_management": ["engine/pm/**"],
            "work_tracking": ["engine/pm/**"],
            "synthetic_experiments": ["engine/research/**", "engine/flow/**"],
            "gap_analysis": ["engine/sentinel/**"],
            "quality_gates": ["engine/pm/**", "engine/sentinel/**"],
            "briefing_generator": ["engine/conductor/**", "engine/product/**"],
            "capability_mapping": ["engine/product/**", "engine/scanner/**"],
            # Sentinel & discovery
            "sentinel_engines": ["engine/sentinel/**"],
            "ideas_pipeline": ["engine/ideas/**"],
            "idea_lifecycle": ["engine/ideas/**"],
            "discovery_pipeline": ["engine/discovery/**"],
            "conflict_detection": ["engine/atc/**", "engine/orchestration/**"],
            "specialty_emergence": ["engine/cognition/**", "engine/orchestrator/**"],
            # Execution
            "task_execution": ["engine/runner/**", "engine/skills/**", "engine/playbooks/**"],
            "task_runner": ["engine/runner/**"],
            "skill_execution": ["engine/skills/**", "engine/playbooks/**"],
            "skill_executor": ["engine/skills/**"],
            "playbook_executor": ["engine/playbooks/**"],
            "template_engine": ["engine/templates/**"],
            "template_system": ["engine/templates/**"],
            "seed_packs": ["engine/cognition/**", "engine/reasoning/**"],
            # LLM & database
            "llm_integration": ["engine/core/**"],
            "database_layer": ["engine/core/**"],
            # Review & competitive
            "pr_review_engine": ["engine/review/**"],
            "competitive_intelligence": ["engine/competitive/**"],
            "ecosystem_management": ["engine/seam/**", "engine/graph/**"],
            "ecosystem_manager": ["engine/ecosystem/**"],
            # Search
            "hybrid_search": ["engine/search/**", "engine/embedding/**"],
            # Communication
            "notification_system": ["engine/notifications/**"],
            "conversational_interface": ["engine/chat/**"],
            "chat_interface": ["engine/chat/**", "portal/src/pages/Conversation.tsx"],
            "event_bus": ["engine/events/**"],
            "signal_processing": ["engine/signals/**"],
            # Live state & ATC
            "portal_live_state": ["engine/live/**", "portal/src/stores/**", "portal/src/contexts/**"],
            # Infrastructure
            "mcp_server": ["engine/mcp/**", "ace_mcp_client/**"],
            "rest_api": ["engine/api/**"],
            "api_gateway": ["engine/api/**"],
            "cli": ["engine/cli/**"],
            "cli_interface": ["engine/cli/**"],
            "core_infrastructure": ["engine/core/**", "engine/embedding/**", "engine/search/**"],
            "memory_context": ["engine/memory/**"],
            # Portal pages
            "portal_dashboard": ["portal/src/pages/Hub.tsx", "portal/src/**"],
            "portal_agents": ["portal/src/pages/Agents.tsx", "portal/src/pages/Tower.tsx"],
            "portal_product": ["portal/src/pages/Product.tsx", "portal/src/pages/Proposals.tsx"],
            "portal_project": ["portal/src/pages/Project.tsx", "portal/src/pages/Work.tsx"],
            "portal_radar": ["portal/src/pages/Radar.tsx", "portal/src/pages/Conflicts.tsx"],
            "portal_settings": [
                "portal/src/pages/Settings.tsx",
                "portal/src/pages/Account.tsx",
                "portal/src/pages/Integrations.tsx",
            ],
            "portal_conversation": [
                "portal/src/pages/Conversation.tsx",
                "portal/src/components/conversation/**",
                "portal/src/components/Chat*.tsx",
            ],
            "portal_graph": ["portal/src/pages/GraphExplorer.tsx", "portal/src/components/graph/**"],
            "portal_hub": ["portal/src/pages/Hub.tsx", "portal/src/components/hub/**"],
            "portal_design_system": [
                "portal/src/styles/**",
                "portal/src/components/glass/**",
                "portal/src/components/aurora/**",
                "portal/src/components/canvas/**",
            ],
            # Misc
            "onboarding": ["engine/onboarding/**"],
            # Strategic (partnership-thesis) capabilities — kebab-case slugs, authored here so they
            # stop surfacing as phantom 0.00 gaps now that the graph reflects current code (item E).
            "closed-loop-learning": ["engine/arms/strategy/**", "engine/arms/outcome.py"],
            "intelligence-routing": ["engine/orchestrator/**"],
            "onboarding-flow": ["engine/onboarding/**", "engine/api/onboarding*.py"],
            "partner-voice": ["engine/voice/**", "engine/proactive/voice.py", "engine/api/voice_*.py"],
            "substrate-quality": ["engine/sentinel/**", "engine/eval/**"],
        }

        cap_globs: list[tuple[str, str]] = []
        for cap in caps:
            slug = cap.get("slug", "")
            cap_id = str(cap["id"])
            globs = [cap["file_glob"]] if cap.get("file_glob") else _SLUG_GLOB_FALLBACKS.get(slug, [])
            for pattern in globs:
                cap_globs.append((cap_id, pattern))

        def _matches(path: str, pattern: str) -> bool:
            path = _canonical_path(path)  # core/engine/x -> engine/x so engine/** globs match (item E)
            if "/**" in pattern:
                base = pattern.replace("/**", "")
                return path.startswith(base + "/") or path == base
            return fnmatch.fnmatch(path, pattern)

        # Build test-file index: map test files to capabilities by slug word matching.
        # e.g. "capability_mapping" matches test_capability_mapper.py because "capability"
        # and "mapping/mapper" appear in the filename.
        _slug_to_cap_id: dict[str, str] = {cap.get("slug", ""): str(cap["id"]) for cap in caps}
        _cap_test_paths: dict[str, list[str]] = {}
        async with self._pool.connection() as _tdb:
            _test_file_rows = parse_rows(
                await _tdb.query(
                    "SELECT path FROM graph_file WHERE graph_id = 'default' AND path CONTAINS 'tests/test_'"
                )
            )
        for tf in _test_file_rows:
            tf_name = tf.get("path", "").split("/")[-1].removeprefix("test_").removesuffix(".py")
            for slug, cap_id in _slug_to_cap_id.items():
                words = [w for w in slug.split("_") if len(w) > 3]
                if any(w in tf_name for w in words):
                    _cap_test_paths.setdefault(cap_id, []).append(tf.get("path", ""))

        # Group files by matched capability so we can batch-update reality.files
        cap_file_paths: dict[str, list[str]] = {}

        mapped = 0
        unmatched = 0

        async with self._pool.connection() as db:
            # Idempotency: this is a FULL bootstrap, so clear prior backfill edges before
            # re-RELATE — otherwise a re-bootstrap (scanner stale-edge path) piles up dupes.
            # Scoped to source='backfill' so LLM/manual edges (other sources) survive, AND to
            # out.product = $product so bootstrapping one product never wipes another product's
            # backfill edges (this run only recreates THIS product's edges). out.product
            # traverses the realizes edge to capability.product (v3 supports the edge field path).
            await db.query(
                "DELETE realizes WHERE source = 'backfill' AND out.product = $product",
                {"product": parse_record_id(product_id)},
            )
            for f in files:
                file_id = str(f["id"])
                file_path = f.get("path", "")
                matched_caps: list[str] = []

                for cap_id, pattern in cap_globs:
                    if _matches(file_path, pattern):
                        matched_caps.append(cap_id)

                # Deduplicate (same cap may have multiple matching patterns)
                seen: set[str] = set()
                for cap_id in matched_caps:
                    if cap_id in seen:
                        continue
                    seen.add(cap_id)
                    q = f'RELATE {file_id} -> realizes -> {cap_id} SET source = "backfill"'
                    await db.query(q)
                    cap_file_paths.setdefault(cap_id, []).append(file_path)

                if matched_caps:
                    mapped += 1
                else:
                    unmatched += 1

            # Merge test file paths into implementation paths before writing reality.files
            all_cap_ids = set(cap_file_paths.keys()) | set(_cap_test_paths.keys())
            for cap_id in all_cap_ids:
                impl = cap_file_paths.get(cap_id, [])
                tests = _cap_test_paths.get(cap_id, [])
                combined = sorted(set(impl + tests))
                cap_file_paths[cap_id] = combined

            # Write reality.files for each capability so gap_analyzer can read it directly.
            # decision:fepcr57v26jh9qyk9jfy — prior shape `SET reality = { files: $files }`
            # OVERWROTE the entire reality object, blowing away file_glob and test_glob
            # that capabilities are created with. Smoke-verified: SET reality.files = ...
            # works correctly when reality is non-null, preserving sibling keys. Use a
            # nested SET when the parent is populated (the common case post-bootstrap);
            # fall back to whole-object SET when reality is missing.
            for cap_id, paths in cap_file_paths.items():
                try:
                    # First check if reality is already populated (sibling keys exist)
                    has_reality_row = parse_one(await db.query(f"SELECT reality FROM {cap_id}"))
                    has_reality = bool((has_reality_row or {}).get("reality"))
                    if has_reality:
                        # Merge: preserve file_glob/test_glob, replace files.
                        await db.query(
                            f"UPDATE {cap_id} SET reality.files = $files",
                            {"files": paths},
                        )
                    else:
                        # Cold start: parent NULL; write the whole thing.
                        await db.query(
                            f"UPDATE {cap_id} SET reality = {{ files: $files }}",
                            {"files": paths},
                        )
                except Exception as exc:
                    logger.debug("Failed to update reality.files for %s: %s", cap_id, exc)

        logger.info(
            "File→capability mapping complete: product=%s mapped=%d unmatched=%d", product_id, mapped, unmatched
        )
        return {"mapped": mapped, "unmatched": unmatched}

    async def incremental_map(self, new_files: list[dict], product_id: str) -> dict:
        """Map new files to existing capabilities.
        1. Load existing capabilities and their glob patterns from realizes edges
        2. For each new file: try glob match first (deterministic, no LLM)
        3. If no glob match: add to unmapped list (queued for LLM later)
        4. Returns {mapped: int, unmapped: int}"""
        async with self._pool.connection() as db:
            # Step 1: Load realizes edges with their glob patterns
            realizes_result = await db.query(
                """
                SELECT capability, file_glob FROM realizes
                """,
                {"product": product_id},
            )
            realizes_rows = parse_rows(realizes_result)

        # Build a list of (cap_id, file_glob) pairs for matching
        cap_globs = [
            (row["capability"], row["file_glob"])
            for row in realizes_rows
            if row.get("capability") and row.get("file_glob")
        ]

        mapped = 0
        unmapped = 0

        for file in new_files:
            file_id = file.get("id")
            file_path = file.get("path", "")
            matched_cap = None

            # Step 2: Try glob match (deterministic, no LLM)
            for cap_id, glob_pattern in cap_globs:
                if self._matches_glob(file_path, glob_pattern):
                    matched_cap = cap_id
                    break

            if matched_cap:
                async with self._pool.connection() as db:
                    await db.query(
                        "RELATE $file_id -> realizes -> $cap_id",
                        {"file_id": parse_record_id(file_id), "cap_id": parse_record_id(matched_cap)},
                    )
                    # Keep reality.files in sync with realizes edges.
                    # Use SET reality = { files: ... } not SET reality.files = ...
                    # because SurrealDB silently no-ops nested-field writes when
                    # the parent object is NULL (new capabilities start with reality=NULL).
                    try:
                        await db.query(
                            """
                            UPDATE <record>$cap_id SET
                                reality = { files: array::union(reality.files ?? [], [$path]) }
                            """,
                            {"cap_id": matched_cap, "path": file_path},
                        )
                    except Exception:
                        pass
                mapped += 1
            else:
                unmapped += 1

        return {"mapped": mapped, "unmapped": unmapped}
