# engine/capture/synthesizer.py
"""Synthesizer — distills observations into durable insights.

Runs on batch threshold (default 5), periodic timer, or session end (flush).
Uses primary LLM. Deduplicates, merges, detects conflicts against existing insights.
Writes to insight and conflict tables using doc 18 field names.
"""

from __future__ import annotations

import asyncio
import logging
import math

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.capture.cognify import cognify
from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.embedding.base import get_embedder
from core.engine.product.decisions import create_decision

logger = logging.getLogger(__name__)

_EMBEDDING_DEDUPE_THRESHOLD = 0.85
_EMBEDDING_DEDUPE_BOOST = 0.05


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Standard cosine similarity; returns 0.0 for any zero-norm input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _safe_confidence(value) -> float:
    """Safely coerce a value to a confidence float in [0.0, 1.0]."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (ValueError, TypeError):
        return 0.5


_SPECIALTY_TYPES = {"fact", "pattern", "discovery"}
_ORG_TYPES = {"convention", "preference", "decision"}

# Observation `source` -> provenance kind for SELF-GENERATED content (the active loop). When a batch is
# entirely one of these, the resulting insight's source_domain is prefixed `kind.<slug>` so the
# provenance reconciler scores it at the self-generated (low) trust prior instead of laundering it into
# capture-tier 0.80. External/human captures carry none of these sources, so they're unaffected.
_SELF_GENERATED_KINDS = {"reasoning_conclusion": "reasoning", "composition_phase": "composition"}


def _batch_provenance_kind(observations: list[dict]) -> str | None:
    """The self-generated provenance kind for a batch, or None.

    Conservative: returns a kind ONLY when EVERY observation in the batch is the same self-generated
    source. A mixed batch (any human/external observation) returns None, so a real capture corroborating
    a conclusion is never silently downgraded.
    """
    if not observations:
        return None
    kinds = {_SELF_GENERATED_KINDS.get(str(o.get("source") or "")) for o in observations}
    if len(kinds) == 1:
        return next(iter(kinds))  # a single value: a shared kind, or None (no obs was self-generated)
    return None


def _compose_source_domain(domain_path: str, provenance_kind: str | None) -> str:
    """Encode the provenance kind into source_domain (`kind.<slug>`) while leaving domain_path — the
    retrieval/routing field — as the bare slug. parse_source then recovers the kind for trust scoring."""
    if provenance_kind and domain_path:
        return f"{provenance_kind}.{domain_path}"
    return domain_path


def _route_to_graph(insight_type: str) -> str:
    """Determine which graph an insight belongs to based on its type.

    Returns: 'specialty' | 'org' | 'inherit' (correction follows the corrected insight).
    """
    if insight_type in _SPECIALTY_TYPES:
        return "specialty"
    if insight_type in _ORG_TYPES:
        return "org"
    if insight_type == "correction":
        return "inherit"
    return "org"


class Synthesizer:
    """Batches observations and synthesizes into insights."""

    def __init__(
        self,
        product_id: str,
        workspace_id: str | None,
        batch_size: int = 5,
    ) -> None:
        self.product_id = product_id
        self.workspace_id = workspace_id
        self.batch_size = batch_size
        self._pending: list[dict] = []
        self._db_pool = None  # Set via pipeline after construction
        self._cognify_tasks: set[asyncio.Task] = set()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def add_observation(self, observation: dict) -> None:
        """Add an observation. Triggers synthesis if batch threshold reached."""
        self._pending.append(observation)
        if len(self._pending) >= self.batch_size:
            await self.synthesize()

    async def flush(self) -> None:
        """Synthesize any remaining observations (called on session end).

        Then DRAIN any pending fire-and-forget cognify tasks: flush runs at
        session end, often right before process exit, so a scheduled-but-unrun
        synapse-former task would otherwise drop its edges. Non-fatal — cognify
        is already guarded; return_exceptions keeps a failed task from raising here.
        """
        if self._pending:
            await self.synthesize()
        if self._cognify_tasks:
            await asyncio.gather(*self._cognify_tasks, return_exceptions=True)

    async def synthesize(self) -> dict:
        """Process pending observations into insights."""
        if not self._pending:
            return {"new_insights": 0, "updates": 0, "conflicts": 0, "skipped": 0}

        observations = list(self._pending)
        self._pending = []  # optimistically clear

        try:
            existing = await self._load_existing_insights(observations)
            non_matched, auto_merged = await self._embedding_dedupe(observations, existing)
            if non_matched:
                result = await self._call_primary_llm(non_matched, existing)
            else:
                result = {"new_insights": [], "updates": [], "conflicts": [], "skipped": []}
        except Exception:
            # Restore observations to avoid data loss on LLM failure
            self._pending = observations + self._pending
            raise

        counts = {"new_insights": 0, "updates": 0, "conflicts": 0, "skipped": len(auto_merged), "write_failures": 0}

        # Collect discipline hints from source observations as fallback
        obs_disciplines = [
            o.get("discipline_hint") or o.get("domain_hint")
            for o in observations
            if o.get("discipline_hint") or o.get("domain_hint")
        ]
        fallback_domain = obs_disciplines[0] if obs_disciplines else ""

        # Collect observation IDs to wire derived_from edges after insight creation
        batch_obs_ids = [str(obs.get("id", "")) for obs in observations if obs.get("id")]

        # Provenance: a fully self-generated batch (reasoning conclusion / composition phase) gets its
        # insights tagged at the self-generated trust prior, not laundered into capture-tier.
        provenance_kind = _batch_provenance_kind(observations)

        written, failures, written_records = await self._write_new_insights(
            result.get("new_insights", []), fallback_domain, batch_obs_ids, provenance_kind=provenance_kind
        )
        counts["new_insights"] = written
        counts["write_failures"] = failures

        # Phase 5 — synapse-former: relate new insights to existing ones (non-blocking).
        self._maybe_cognify(written_records, existing)

        for update in result.get("updates", []):
            await self._apply_update(update)
            counts["updates"] += 1

        for conflict in result.get("conflicts", []):
            await self._write_conflict(conflict)
            counts["conflicts"] += 1

        counts["skipped"] += len(result.get("skipped", []))

        # Emit insight.created events
        if counts["new_insights"] > 0:
            try:
                from core.engine.events.bus import bus

                await bus.emit("insight.created", {"product_id": self.product_id, "count": counts["new_insights"]})
            except Exception:
                pass

        if counts["conflicts"] > 0:
            try:
                from core.engine.events.bus import bus

                await bus.emit("insight.conflict", {"product_id": self.product_id, "count": counts["conflicts"]})
            except Exception:
                pass

        # Post-synthesis: check for specialty emergence
        if self._db_pool:
            try:
                from core.engine.intelligence.emergence import check_emergence

                emerged = await check_emergence(self.product_id)
                if emerged:
                    counts["specialties_emerged"] = len(emerged)
                    for spec in emerged:
                        try:
                            from core.engine.events.bus import bus

                            await bus.emit(
                                "specialty.emerged",
                                {
                                    "product_id": self.product_id,
                                    "specialty_id": str(spec.get("id", "")),
                                    "slug": spec.get("slug", ""),
                                    "insight_count": spec.get("insight_count", 0),
                                },
                            )
                        except Exception:
                            pass
            except Exception as exc:
                logger.warning("Emergence check failed after synthesis: %s", exc)

        return counts

    async def _load_existing_insights(self, observations: list[dict]) -> list[dict]:
        """Load existing insights matching the discipline hints of pending observations."""
        if not self._db_pool:
            return []
        # Collect discipline hints, falling back to domain_hint for backward compat
        disciplines = list(
            {
                o.get("discipline_hint") or o.get("domain_hint")
                for o in observations
                if o.get("discipline_hint") or o.get("domain_hint")
            }
        )
        if not disciplines:
            return []
        async with self._db_pool.connection() as db:
            result = await db.query(
                """
                SELECT id, content, confidence, tier, insight_type, source_domain, tags, embedding
                FROM insight
                WHERE product = <record>$product AND status = 'active'
                  AND (tags CONTAINSANY $disciplines OR source_domain IN $disciplines)
                ORDER BY confidence DESC LIMIT 20
                """,
                {"product": self.product_id, "disciplines": disciplines},
            )
        from core.engine.core.db import parse_rows

        return parse_rows(result)

    async def _embedding_dedupe(
        self, observations: list[dict], existing: list[dict]
    ) -> tuple[list[dict], list[tuple[str, str]]]:
        """Pre-LLM dedupe using cosine similarity.

        For each observation, find the best-matching existing insight (by cosine
        similarity over content embedding). If similarity >= _EMBEDDING_DEDUPE_THRESHOLD,
        skip the LLM call and boost the matched insight's confidence instead.

        Returns:
            (non_matched_observations, auto_merged)
            where auto_merged is [(obs_id, insight_id), ...]

        Gracefully no-ops if:
          - embedder returns 0-dim vectors (noop embedder)
          - no existing insight has an embedding
          - the embedder raises
        """
        if not observations:
            return observations, []

        existing_with_emb = [e for e in existing if e.get("embedding")]
        if not existing_with_emb:
            return observations, []

        try:
            embedder = get_embedder()
            if embedder.dimensions == 0:
                return observations, []
            obs_texts = [o.get("content", "") for o in observations]
            obs_vectors = await embedder.embed(obs_texts)
        except Exception as exc:
            logger.warning("embedding dedupe: embedder failed (non-fatal): %s", exc)
            return observations, []

        non_matched: list[dict] = []
        auto_merged: list[tuple[str, str]] = []

        for obs, vec in zip(observations, obs_vectors):
            best_sim = 0.0
            best_insight_id = ""
            for ins in existing_with_emb:
                sim = _cosine_similarity(vec, ins.get("embedding") or [])
                if sim > best_sim:
                    best_sim = sim
                    best_insight_id = str(ins.get("id") or "")

            if best_sim >= _EMBEDDING_DEDUPE_THRESHOLD and best_insight_id:
                obs_id = str(obs.get("id") or "")
                auto_merged.append((obs_id, best_insight_id))
                await self._boost_insight_confidence(best_insight_id)
            else:
                non_matched.append(obs)

        return non_matched, auto_merged

    def _cognify_candidate_finder(self, existing: list[dict]):
        """Build a CandidateFinder over already-loaded existing insights.

        Ranks by cosine similarity to the new insight's embedding (highest first).
        Mirrors _embedding_dedupe's signal; no new DB query. Cognify slices to k.
        """
        existing_with_emb = [e for e in existing if e.get("embedding")]

        async def find_candidates(new_insight: dict) -> list[dict]:
            emb = new_insight.get("embedding")
            if not emb or not existing_with_emb:
                return []
            return sorted(
                existing_with_emb,
                key=lambda e: _cosine_similarity(emb, e.get("embedding") or []),
                reverse=True,
            )

        return find_candidates

    def _maybe_cognify(self, new_records: list[dict], existing: list[dict]):
        """Schedule the synapse-former (non-blocking) for newly written insights.

        Returns the asyncio.Task (so callers/tests can await it) or None when the
        feature is gated off or there is nothing to relate. Fire-and-forget in
        production: synthesize() ignores the return so capture latency is unchanged.
        cognify() is fully non-fatal, so a failure can never affect capture.
        """
        if not settings.cognify_enabled or not new_records:
            return None
        finder = self._cognify_candidate_finder(existing)
        task = asyncio.create_task(
            cognify(
                new_records,
                finder,
                min_confidence=settings.cognify_min_confidence,
                candidate_k=settings.cognify_candidate_k,
            )
        )
        self._cognify_tasks.add(task)
        task.add_done_callback(self._cognify_tasks.discard)
        return task

    async def _boost_insight_confidence(self, insight_id: str) -> None:
        """Boost confidence on an auto-merged insight by _EMBEDDING_DEDUPE_BOOST (capped at 1.0)."""
        if not self._db_pool or not insight_id:
            return
        try:
            async with self._db_pool.connection() as db:
                await db.query(
                    """UPDATE <record>$id SET
                       confidence = math::min([1.0, confidence + $boost]),
                       updated_at = time::now()""",
                    {"id": insight_id, "boost": _EMBEDDING_DEDUPE_BOOST},
                )
        except Exception as exc:
            logger.warning("boost confidence failed for %s: %s", insight_id, exc)

    async def _call_primary_llm(self, observations: list[dict], existing: list[dict]) -> dict:
        """Call primary LLM to synthesize observations into insights."""
        obs_text = "\n".join(
            f"{i}. [{o.get('observation_type', '?')}] {o['content']} (conf: {o.get('confidence', '?')}, discipline: {o.get('discipline_hint') or o.get('domain_hint', '?')})"
            for i, o in enumerate(observations)
        )

        existing_text = (
            "\n".join(
                f"- [{e.get('insight_type', '?')}] {e.get('content', '')} (conf: {e.get('confidence', '?')}, id: {e.get('id', '?')})"
                for e in existing
            )
            or "(none yet)"
        )

        prompt = f"""Synthesize these observations into durable insights.

New observations:
{obs_text}

Existing insights in the intelligence graph:
{existing_text}

For each observation or group:
1. Duplicates an existing insight? → Skip (or boost confidence)
2. Extends an existing insight? → Return as update
3. Contradicts an existing insight? → Flag as conflict
4. Genuinely new? → Return as new insight

For new insights, classify:
- tier: specialty | subdomain | domain | org
- discipline: one of security, testing, ux, performance, devops, data, accessibility, documentation, ai_ml, architecture, api_design, data_modeling, business_logic, integration, error_handling, observability, configuration, deployment, versioning, scale, code_conventions, dependency_management
- insight_type: fact | pattern | decision | correction | preference | convention | discovery
- confidence: 0.0-1.0
- clearance: open"""

        try:
            from core.engine.capture.schemas import SynthesizerOutput

            result = await llm.complete_structured(prompt, SynthesizerOutput, model=settings.llm_model)
            return result.model_dump()
        except Exception:
            logger.warning("Structured synthesis failed, falling back to freeform JSON")
            raw = await llm.complete_json(
                prompt
                + '\n\nReturn JSON: {"new_insights": [{"content": "...", "tier": "subdomain", "discipline": "testing", "insight_type": "fact", "confidence": 0.8}], "updates": [{"existing_insight_id": "...", "updated_content": "...", "updated_confidence": 0.8}], "conflicts": [{"existing_insight_id": "...", "conflicting_observation": "...", "explanation": "..."}], "skipped": [indices]}',
                model=settings.llm_model,
            )
            # Ensure new_insights have required content field
            if "new_insights" in raw:
                raw["new_insights"] = [ins for ins in raw["new_insights"] if ins.get("content")]
            return raw

    async def _write_new_insights(
        self,
        new_insights: list[dict],
        fallback_domain: str,
        batch_obs_ids: list[str],
        provenance_kind: str | None = None,
    ) -> tuple[int, int, list[dict]]:
        """Write a batch of new insights, isolating per-insight failures.

        atomic_capture_write raises on a failed transaction (the row is rolled
        back). Each write is guarded so one failure can't abort the rest of the
        batch (and _pending is already cleared, so a thrown batch would be lost).

        A swallowed write failure IS silent data loss — so every failure is made
        OBSERVABLE: counted, metered (ace_capture_write_failures_total), and
        emitted as a capture.write_failed event. This is the signal that would
        have surfaced the Phase-1 RELATE-endpoint regression. Returns
        (written, failures, records).
        """
        written = 0
        failures = 0
        records: list[dict] = []
        for insight_data in new_insights:
            if not insight_data.get("domain_path"):
                insight_data["domain_path"] = fallback_domain
            try:
                record = await self._write_insight(
                    insight_data, observation_ids=batch_obs_ids, provenance_kind=provenance_kind
                )
                written += 1
                if record:
                    records.append(record)
            except Exception as exc:
                failures += 1
                logger.warning(
                    "insight write FAILED (rolled back); skipping. product=%s err=%s",
                    self.product_id,
                    exc,
                )
                try:
                    from core.engine.core.metrics import capture_write_failures_total

                    capture_write_failures_total.labels(product=str(self.product_id)).inc()
                except Exception:
                    pass

        if failures > 0:
            try:
                from core.engine.events.bus import bus

                await bus.emit(
                    "capture.write_failed",
                    {"product_id": self.product_id, "count": failures},
                )
            except Exception:
                pass

        return written, failures, records

    async def _write_insight(
        self,
        insight_data: dict,
        observation_ids: list[str] | None = None,
        provenance_kind: str | None = None,
    ) -> dict | None:
        """Write a new insight to SurrealDB. `provenance_kind` (e.g. 'reasoning') encodes self-generated
        provenance into source_domain for trust scoring; None preserves direct-capture behavior."""
        if not self._db_pool:
            return None
        # Guard: LLM occasionally returns consolidation stubs ("Consolidated with
        # insight:xxx — ...") as new_insights instead of using the updates action.
        # These contain no useful information — skip them entirely.
        content = insight_data.get("content", "")
        if content.startswith("Consolidated with insight:"):
            logger.debug("Skipping consolidation stub (LLM artefact): %.80s", content)
            return None
        # Resolve discipline slug — prefer discipline field, fall back to domain_path for legacy
        domain_path = insight_data.get("domain_path", "")
        domain_slug = (
            insight_data.get("discipline")
            or insight_data.get("discipline_hint")
            or (domain_path.split(".")[0] if domain_path else None)
        )
        # Normalize: domain_path should be the discipline slug (not a dotted path)
        if domain_slug:
            domain_path = domain_slug

        # Lookup flow config to set clearance
        clearance = "open"  # default
        tier = insight_data.get("tier", "subdomain")
        domain_id = None  # record ID for the domain

        specialty_id = None  # record ID for the specialty (enables dual_loader to find this insight)

        if domain_slug and self._db_pool:
            try:
                from core.engine.flow.config import get_flow_config

                # Resolve domain slug to domain ID + specialty ID in one connection
                async with self._db_pool.connection() as db_cfg:
                    dom_result = await db_cfg.query(
                        "SELECT id FROM domain WHERE slug = <string>$slug LIMIT 1",
                        {"slug": domain_slug},
                    )
                    dom_rows = dom_result[0] if dom_result and isinstance(dom_result[0], list) else (dom_result or [])
                    if dom_rows and isinstance(dom_rows[0], dict):
                        domain_id = dom_rows[0].get("id")
                        flow_config = await get_flow_config(str(domain_id), self.product_id)
                        clearance = flow_config.default_clearance

                        # Propagation controls — strictest wins
                        if not flow_config.insight_propagation:
                            tier = "subdomain"
                        elif not flow_config.contribute_org_intelligence:
                            if tier == "product":
                                tier = "domain"

                    # Resolve specialty slug so dual_loader can find this insight
                    spec_result = await db_cfg.query(
                        "SELECT id FROM specialty WHERE slug = <string>$slug LIMIT 1",
                        {"slug": domain_slug},
                    )
                    spec_rows = (
                        spec_result[0] if spec_result and isinstance(spec_result[0], list) else (spec_result or [])
                    )
                    if spec_rows and isinstance(spec_rows[0], dict):
                        specialty_id = spec_rows[0].get("id")
            except Exception:
                pass  # Fall through to defaults

        # Compute embedding BEFORE the transaction (keeps model latency out of
        # the DB lock). Degraded mode (embedder unavailable) -> embedding=None.
        # `content` is already bound at the top of the method.
        tags = []
        if domain_slug:
            tags.append(domain_slug)
        if domain_path and domain_path != domain_slug:
            tags.append(domain_path)

        embedding = None
        try:
            embedder = get_embedder()
            if embedder.dimensions:
                # Contextual chunk enrichment: embed a [discipline · type · tags]-prefixed text so the
                # vector captures context; the STORED content (below) stays raw. Off → raw content.
                embed_text = content
                if settings.contextual_chunk_enrichment:
                    from core.engine.capture.contextualize import contextualize_for_embedding

                    embed_text = contextualize_for_embedding(
                        content,
                        domain_path=domain_path,
                        insight_type=insight_data.get("insight_type", "fact"),
                        tags=tags,
                    )
                vecs = await embedder.embed([embed_text])
                if vecs and vecs[0] and len(vecs[0]) == embedder.dimensions:
                    embedding = vecs[0]
        except Exception:
            logger.warning("embedding failed; writing insight in degraded mode", exc_info=True)

        insight_id_str = await atomic_capture_write(
            self._db_pool,
            insight_fields={
                "product": self.product_id,
                "content": content,
                "insight_type": insight_data.get("insight_type", "fact"),
                "tier": tier,
                "clearance": clearance,
                "confidence": _safe_confidence(insight_data.get("confidence", 0.5)),
                "source_domain": _compose_source_domain(domain_path, provenance_kind),
                "domain_path": domain_path,
                "domain": domain_id,
                "subdomain": None,
                "specialty": specialty_id,
                "tags": tags,
            },
            embedding=embedding,
            specialty_slug=domain_slug or None,
            observation_ids=[str(o) for o in (observation_ids or []) if o],
        )

        # Bridge decision insights to the decision table
        insight_type = insight_data.get("insight_type", "fact")
        if insight_type == "decision":
            try:
                content = insight_data.get("content", "")
                decision_record = await create_decision(
                    title=content[:100],
                    decision_type="architecture",
                    rationale=content,
                    product_id=self.product_id,
                    source="synthesizer",
                    pool=self._db_pool,
                )
                # Attach a forward prediction — fire-and-forget, never raises
                if decision_record and decision_record.get("id"):
                    from core.engine.foresight.forecaster import attach_prediction

                    await attach_prediction(
                        decision_id=str(decision_record["id"]),
                        decision_content=content,
                        product_id=self.product_id,
                        pool=self._db_pool,
                    )
            except Exception:
                logger.warning("Failed to bridge decision insight to decision table", exc_info=True)

        return {"id": insight_id_str, "content": content, "embedding": embedding}

    async def _apply_update(self, update: dict) -> None:
        """Update an existing insight's content and confidence."""
        if not self._db_pool:
            return
        insight_id = update.get("existing_insight_id")
        if not insight_id:
            return
        new_content = update.get("updated_content", "")

        # Recompute the embedding for the rewritten content (outside the DB call)
        # so the vector stays in sync with content. Degraded mode (embedder
        # unavailable) -> embedding=None + needs_embedding=true for the reconciler.
        # Contextual chunk enrichment: fetch the existing insight's structural context so the rewritten
        # vector stays consistently enriched with freshly-captured ones. Fail-safe — any miss → raw embed.
        ctx: dict = {}
        if settings.contextual_chunk_enrichment:
            try:
                from core.engine.core.db import parse_rows

                async with self._db_pool.connection() as db:
                    crows = parse_rows(
                        await db.query(
                            "SELECT domain_path, insight_type, tags FROM insight WHERE id = <record>$id LIMIT 1",
                            {"id": insight_id},
                        )
                    )
                if crows:
                    ctx = crows[0]
            except Exception:
                ctx = {}

        embedding = None
        try:
            embedder = get_embedder()
            if embedder.dimensions:
                embed_text = new_content
                if settings.contextual_chunk_enrichment:
                    from core.engine.capture.contextualize import contextualize_for_embedding

                    embed_text = contextualize_for_embedding(
                        new_content,
                        domain_path=ctx.get("domain_path"),
                        insight_type=ctx.get("insight_type"),
                        tags=ctx.get("tags"),
                    )
                vecs = await embedder.embed([embed_text])
                if vecs and vecs[0] and len(vecs[0]) == embedder.dimensions:
                    embedding = vecs[0]
        except Exception:
            logger.warning("embedding failed on update; marking needs_embedding", exc_info=True)

        async with self._db_pool.connection() as db:
            await db.query(
                """
                UPDATE <record>$insight_id SET
                    content = $content,
                    confidence = $confidence,
                    embedding = $embedding,
                    needs_embedding = $needs_embedding,
                    updated_at = time::now(),
                    last_confirmed = time::now()
                """,
                {
                    "insight_id": insight_id,
                    "content": new_content,
                    "confidence": _safe_confidence(update.get("updated_confidence", 0.5)),
                    "embedding": embedding,
                    "needs_embedding": embedding is None,
                },
            )

    async def _write_conflict(self, conflict: dict) -> None:
        """Write a conflict record. Note: maps LLM's 'conflicting_observation' to schema's 'conflicting_content'."""
        if not self._db_pool:
            return
        insight_a_id = conflict.get("existing_insight_id")
        if not insight_a_id:
            return
        async with self._db_pool.connection() as db:
            await db.query(
                """
                CREATE conflict SET
                    insight_a = <record>$insight_a,
                    conflicting_content = $conflicting_content,
                    explanation = $explanation,
                    status = 'pending',
                    created_at = time::now()
                """,
                {
                    "product": self.product_id,
                    "insight_a": insight_a_id,
                    "conflicting_content": conflict.get("conflicting_observation", ""),
                    "explanation": conflict.get("explanation", ""),
                },
            )
