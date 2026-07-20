# engine/product/seed_generator.py
"""Best Practice Seed Generator — use LLM to generate actionable insights per specialty.

For each specialty, prompts the LLM with authoritative source context
and generates 3-5 concrete, actionable best practice insights.
These become durable intelligence in the specialty graph.
"""

import logging

from core.engine.core.db import parse_one, pool
from core.engine.core.llm import get_llm
from core.engine.product.seed_packs import SEED_STRUCTURE

logger = logging.getLogger(__name__)

# Authoritative sources per discipline for LLM context
AUTHORITATIVE_SOURCES = {
    "security": "OWASP Top 10, NIST guidelines, CWE database",
    "testing": "Testing Pyramid, Martin Fowler's testing guides, pytest best practices",
    "ux": "Nielsen Norman Group, Material Design guidelines, Apple HIG",
    "performance": "Web Vitals (Google), Lighthouse audits, database optimization guides",
    "devops": "12-Factor App, DORA metrics, SRE handbook (Google)",
    "data": "Database normalization theory, indexing best practices, CAP theorem",
    "accessibility": "WCAG 2.2, WAI-ARIA practices, a11y project",
    "documentation": "Diátaxis framework, OpenAPI specification, readme-driven development",
    "architecture": "Clean Architecture (Robert Martin), Domain-Driven Design, SOLID principles",
    "api_design": "REST API Design Rulebook, JSON:API spec, GraphQL best practices",
    "data_modeling": "Database normalization (1NF-5NF), Martin Fowler's data modeling patterns",
    "business_logic": "Domain-Driven Design (Eric Evans), Event Sourcing, CQRS patterns",
    "integration": "Enterprise Integration Patterns, Circuit Breaker pattern, idempotency",
    "error_handling": "Effective error handling patterns, structured logging, Sentry best practices",
    "observability": "OpenTelemetry, Prometheus/Grafana patterns, distributed tracing guides",
    "configuration": "12-Factor App (config), HashiCorp Vault patterns, feature flag best practices",
    "deployment": "Blue-green deployments, canary releases, container best practices (Docker)",
    "versioning": "Semantic Versioning (semver.org), Conventional Commits, changelog best practices",
    "code_conventions": "PEP 8, Google style guides, Airbnb JavaScript style guide",
    "dependency_management": "Supply chain security (SLSA), lockfile best practices, SBOM standards",
    "ai_ml": "Anthropic model usage guidelines, LangChain best practices, MLflow, Weights & Biases, OWASP LLM Top 10, NIST AI RMF",
    "scale": "Google SRE handbook, AWS Well-Architected Framework, CAP theorem, PACELC, Designing Data-Intensive Applications (Kleppmann)",
    "product_strategy": "Continuous Discovery Habits (Teresa Torres), Inspired (Marty Cagan), Competing Against Luck (Christensen), Obviously Awesome (April Dunford), Lean Startup (Ries), Blue Ocean Strategy",
    "marketing": "Miller Heiman buying-committee roles, The Challenger Sale (Dixon & Adamson), Crossing the Chasm (Moore) & Diffusion of Innovations (Rogers), Eisenberg persuasion architecture (cognitive styles), Jobs-to-be-Done (Christensen), Obviously Awesome positioning (April Dunford), conversion-rate optimization & experimentation (Nielsen Norman Group, GoodUI)",
}


class BestPracticeSeedGenerator:
    """Generate best practice insights per specialty using LLM."""

    def __init__(self, db_pool=None):
        self._pool = db_pool or pool
        self._llm = get_llm()

    async def generate_for_specialty(self, specialty_slug: str, dimension: str, product_id: str) -> list[dict]:
        """Generate 3-5 best practice insights for a specialty.

        Returns list of created insight dicts.
        """
        sources = AUTHORITATIVE_SOURCES.get(dimension, "general best practices")

        prompt = f"""Generate 3-5 concrete, actionable best practice rules for "{specialty_slug}" in software engineering.

Reference these authoritative sources: {sources}

Each practice should be:
- Specific enough that an agent can CHECK if code follows it
- Actionable — not vague advice, but concrete rules
- Relevant to modern software development (Python, TypeScript, React, FastAPI)

Examples of GOOD practices:
- "API endpoints must validate input at the boundary using Pydantic models before passing to business logic"
- "Database queries must use parameterized values, never string interpolation"
- "Error responses must include an error code, message, and correlation ID"

Examples of BAD practices (too vague):
- "Write clean code"
- "Follow best practices"
- "Test your code"

Return JSON array: [{{"content": "the practice rule", "confidence": 0.8}}]"""

        try:
            result = await self._llm.complete_json(prompt)
            practices = result if isinstance(result, list) else result.get("practices", result.get("items", []))
        except Exception as e:
            logger.warning(f"LLM generation failed for {specialty_slug}: {e}")
            return []

        created = []
        async with self._pool.connection() as db:
            for practice in practices:
                if not isinstance(practice, dict) or "content" not in practice:
                    continue

                content = practice["content"]
                confidence = min(1.0, max(0.0, float(practice.get("confidence", 0.7))))

                # Check for duplicate
                existing = await db.query(
                    "SELECT id FROM insight WHERE content = $content AND product = <record>$product LIMIT 1",
                    {"content": content, "product": product_id},
                )
                if parse_one(existing):
                    continue

                result = await db.query(
                    """CREATE insight SET
                        content = $content,
                        insight_type = 'fact',
                        confidence = $confidence,
                        tier = 'specialty',
                        tags = [$dimension, $specialty, 'best_practice'],
                        status = 'active',
                        source_domain = $dimension,
                        domain_path = $dimension,
                        product = <record>$product,
                        created_at = time::now()""",
                    {
                        "product": product_id,
                        "content": content,
                        "confidence": confidence,
                        "dimension": dimension,
                        "specialty": specialty_slug,
                    },
                )
                insight = parse_one(result)
                if insight:
                    created.append(insight)
                    logger.info(f"  Created: {content[:60]}...")

        return created

    async def generate_all(self, product_id: str, limit_per_specialty: int = 5) -> dict:
        """Generate best practices for ALL specialties.

        Returns: {total_created: int, by_dimension: {dim: count}}
        """
        total = 0
        by_dimension = {}

        for dimension, config in SEED_STRUCTURE.items():
            dim_count = 0
            for specialty_slug in config["specialties"]:
                # Check if already has enough insights
                async with self._pool.connection() as db:
                    count_result = await db.query(
                        "SELECT count() AS c FROM insight WHERE tags CONTAINS $specialty AND tags CONTAINS 'best_practice' AND product = <record>$product GROUP ALL",
                        {"specialty": specialty_slug, "product": product_id},
                    )
                    existing_count = 0
                    row = parse_one(count_result)
                    if row:
                        existing_count = row.get("c", 0)

                if existing_count >= limit_per_specialty:
                    logger.info(f"  Skip {specialty_slug} — already has {existing_count} practices")
                    continue

                created = await self.generate_for_specialty(specialty_slug, dimension, product_id)
                dim_count += len(created)
                total += len(created)

            by_dimension[dimension] = dim_count

        return {"total_created": total, "by_dimension": by_dimension}
