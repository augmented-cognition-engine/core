# engine/product/seed_packs.py
"""Best practice discipline and specialty definitions.

23 disciplines across 4 categories, 146 specialties total.
Each discipline has an applies_to field indicating product types it's relevant for.
Not all disciplines apply to every product — onboarding activates relevant ones.

Quality template (all disciplines must meet this bar):
  - Minimum 5 specialties covering the full decision surface
  - Inline scope comment on every non-obvious specialty
  - applies_to accurately scoped to relevant product types

Changelog:
  v3 (2026-05-08): Expanded all 12 thin disciplines to 5-7 specialties with scope comments.
    109 → 146 specialties. All 23 disciplines now meet the quality template.
  v2 (2026-04-11): Added ai_ml + scale disciplines. Expanded specialties in architecture,
    data_modeling, security, deployment, observability, performance, integration,
    business_logic to reflect full systems-design decision surface (14 zones, ~100 domains).
"""

QUALITY_DISCIPLINES = [
    "security",
    "testing",
    "ux",
    "performance",
    "devops",
    "data",
    "accessibility",
    "documentation",
    "ai_ml",  # LLM integration, agent architecture, RAG, AI safety, MLOps
]

PRODUCT_DISCIPLINES = [
    "architecture",
    "api_design",
    "data_modeling",
    "business_logic",
    "integration",
    "product_strategy",  # Product-market fit, pricing, positioning, roadmap, growth loops
    "marketing",  # B2B marketing audit, content strategy, buying-committee deliberation, conversion optimization
]

OPERATIONAL_DISCIPLINES = [
    "error_handling",
    "observability",
    "configuration",
    "deployment",
    "versioning",
    "scale",  # Capacity planning, distributed systems, multi-region, rate limiting
]

TEAM_DISCIPLINES = [
    "code_conventions",
    "dependency_management",
]

ALL_DISCIPLINES = QUALITY_DISCIPLINES + PRODUCT_DISCIPLINES + OPERATIONAL_DISCIPLINES + TEAM_DISCIPLINES

SEED_STRUCTURE = {
    # ── QUALITY ─────────────────────────────────────────
    "security": {
        "discipline": "engineering",
        "perspective": "sentinel",
        "applies_to": ["web", "api", "mobile", "cli", "library", "ai"],
        "specialties": [
            "api_security",
            "data_security",
            "dependency_security",
            "auth_patterns",
            "threat_modeling",  # STRIDE, attack surface analysis, trust boundaries
            "compliance_patterns",  # GDPR, CCPA, HIPAA, SOC 2, PCI-DSS, data residency
            "network_security",  # TLS, mTLS, VPN, zero-trust, ingress hardening
        ],
    },
    "testing": {
        "discipline": "engineering",
        "perspective": "practitioner",
        "applies_to": ["web", "api", "mobile", "cli", "library"],
        "specialties": [
            "unit_testing",  # Isolation, mocking boundaries, AAA pattern, test doubles
            "integration_testing",  # Service wiring, DB fixtures, contract boundaries, real I/O
            "e2e_testing",  # User journey coverage, Playwright/Cypress, flake prevention, CI parallelism
            "test_infrastructure",  # Fixture factories, test DB seeding, parallelisation, coverage gates
            "property_based_testing",  # Generative testing, Hypothesis, fuzzing, invariant verification
            "contract_testing",  # Consumer-driven contracts, Pact, schema compatibility, mock servers
            "test_data_management",  # Factories, seeding strategies, PII masking, data isolation per test
        ],
    },
    "devops": {
        "discipline": "engineering",
        "perspective": "operator",
        "applies_to": ["web", "api", "mobile"],
        "specialties": [
            "ci_cd",  # Pipeline stages, artifact caching, branch policies, gating on tests + lint
            "infrastructure",  # IaC (Terraform/Pulumi), drift detection, idempotency, state management
            "monitoring",  # Dashboard design, RED/USE metrics, alerting thresholds, on-call hygiene
            "reliability",  # SLO/SLA tracking, error budgets, toil reduction, blameless postmortems
            "artifact_management",  # Container registries, versioned artifacts, build provenance, SBOM
            "secrets_rotation",  # Credential lifecycle, zero-downtime rotation, Vault leases, HSM
            "environment_promotion",  # Dev→staging→prod pipelines, promotion gates, config per env
        ],
    },
    "ux": {
        "discipline": "design",
        "perspective": "practitioner",
        "applies_to": ["web", "mobile"],
        "specialties": [
            "error_handling_ux",  # Error message clarity, recovery paths, validation feedback placement
            "loading_states",  # Skeleton screens, progressive loading, optimistic UI, perceived performance
            "responsive_design",  # Breakpoint strategy, fluid grids, touch targets, viewport units
            "navigation",  # Information architecture, breadcrumbs, back-stack behavior, deep links
            "forms_and_input",  # Inline validation, autofill, multi-step flows, error recovery
            "empty_states",  # Zero-data UX, first-run onboarding, progressive disclosure, call-to-action
            "feedback_and_motion",  # Micro-interactions, animation principles, system status, transitions
        ],
    },
    "performance": {
        "discipline": "engineering",
        "perspective": "analyst",
        "applies_to": ["web", "api", "mobile"],
        "specialties": [
            "frontend_perf",
            "backend_perf",
            "api_perf",
            "capacity_estimation",  # DAU/MAU projections, QPS, storage growth, bandwidth
            "rate_limiting",  # Token bucket, sliding window, leaky bucket, per-tenant
            "connection_pooling",  # DB connections, HTTP keep-alive, gRPC channels
        ],
    },
    "data": {
        "discipline": "engineering",
        "perspective": "practitioner",
        "applies_to": ["web", "api", "mobile", "cli"],
        "specialties": [
            "schema_design",  # Table/collection design, normalization level, denormalization tradeoffs
            "data_integrity",  # Constraints, foreign keys, transactions, idempotency, consistency models
            "data_access",  # ORM vs raw queries, repository pattern, read/write separation
            "query_optimization",  # Index design, query planning, N+1 detection, read replicas, EXPLAIN
            "change_data_capture",  # CDC patterns, outbox pattern, event streaming from DB, audit logging
            "backup_and_recovery",  # RTO/RPO targets, point-in-time recovery, backup testing, validation
        ],
    },
    "accessibility": {
        "discipline": "design",
        "perspective": "practitioner",
        "applies_to": ["web", "mobile"],
        "specialties": [
            "a11y_standards",  # WCAG 2.2 levels A/AA/AAA, audit tooling, compliance reporting
            "keyboard_nav",  # Tab order, keyboard traps, shortcut design, focus indicators
            "screen_reader",  # Semantic HTML, ARIA roles, live regions, announcement patterns
            "focus_management",  # Focus trapping in modals, skip links, dialog patterns, route changes
            "aria_patterns",  # Landmarks, states and properties, name computation, combobox/listbox
            "cognitive_accessibility",  # Reading level, error prevention, consistent labeling, chunking
        ],
    },
    "documentation": {
        "discipline": "engineering",
        "perspective": "strategist",
        "applies_to": ["web", "api", "mobile", "cli", "library"],
        "specialties": [
            "api_docs",  # OpenAPI/AsyncAPI spec, interactive docs, versioned references, code samples
            "code_docs",  # Docstring standards, type hints as docs, inline comments for non-obvious WHY
            "user_docs",  # Diátaxis framework (tutorial/how-to/reference/explanation), content strategy
            "architecture_decisions",  # ADRs, decision lifecycle, consequence tracking, stakeholder review
            "runbooks_and_playbooks",  # Incident runbooks, operational procedures, escalation paths
            "developer_experience",  # README standards, quickstart quality, changelog hygiene, examples
        ],
    },
    # ── PRODUCT ─────────────────────────────────────────
    "architecture": {
        "discipline": "engineering",
        "perspective": "strategist",
        "applies_to": ["web", "api", "mobile", "cli", "ai"],
        "specialties": [
            "module_boundaries",
            "system_patterns",
            "scalability",
            "technical_debt",
            "multi_tenancy",  # Tenant isolation, data segregation, shared vs dedicated
            "event_driven",  # Event sourcing, CQRS, pub/sub, outbox pattern
            "service_mesh",  # Service boundaries, BFF, strangler fig, sidecar
        ],
    },
    "api_design": {
        "discipline": "engineering",
        "perspective": "practitioner",
        "applies_to": ["api", "web"],
        "specialties": [
            "rest_conventions",  # HTTP method semantics, status codes, URL structure, HATEOAS
            "api_versioning",  # URI vs header versioning, sunset headers, migration guides
            "api_contracts",  # OpenAPI-first design, schema registry, breaking change detection
            "graphql_patterns",  # Schema design, N+1 via DataLoader, persisted queries, federation
            "pagination_and_filtering",  # Cursor vs offset, filter syntax, sort options, total counts
            "error_response_standards",  # Problem+JSON (RFC 9457), correlation IDs, structured errors
            "idempotency_and_safety",  # Idempotency keys, safe methods, retry semantics, PUT vs PATCH
        ],
    },
    "data_modeling": {
        "discipline": "engineering",
        "perspective": "analyst",
        "applies_to": ["web", "api", "mobile", "cli"],
        "specialties": [
            "relational_modeling",
            "document_modeling",
            "migration_strategy",
            "graph_modeling",
            "caching_patterns",  # Cache-aside, write-through, TTL, invalidation, stampede
            "search_indexing",  # Full-text, vector, hybrid BM25+ANN, faceted, reranking
            "data_lifecycle",  # Hot/warm/cold, retention, soft deletes, PII purging
        ],
    },
    "business_logic": {
        "discipline": "engineering",
        "perspective": "practitioner",
        "applies_to": ["web", "api", "mobile", "cli"],
        "specialties": [
            "domain_modeling",
            "state_machines",
            "validation_rules",
            "workflow_patterns",
            "pricing_billing",  # Pricing models, metered usage, dunning, refunds
            "analytics_experimentation",  # A/B testing, feature flags, funnel analysis, cohorts
        ],
    },
    "integration": {
        "discipline": "engineering",
        "perspective": "operator",
        "applies_to": ["web", "api", "mobile"],
        "specialties": [
            "third_party_apis",
            "webhook_patterns",
            "event_systems",
            "oauth_integration",
            "idempotency_patterns",  # Idempotency keys, at-least-once, exactly-once delivery
            "schema_contracts",  # Schema registry, data contracts, producer-consumer SLAs
        ],
    },
    "product_strategy": {
        "discipline": "product",
        "perspective": "advisor",
        "applies_to": ["web", "api", "mobile", "cli", "ai"],
        "specialties": [
            "problem_solution_fit",  # JTBD, pain severity, hair-on-fire vs nice-to-have
            "market_positioning",  # Competitive moats, value prop, Porter's Five Forces
            "monetization_design",  # Revenue models, unit economics, pricing architecture
            "roadmap_sequencing",  # ICE/RICE scoring, dependency DAGs, critical path
            "growth_loops",  # Activation moments, habit formation, viral coefficient
            "retention_mechanics",  # Churn drivers, expansion triggers, NRR levers
        ],
    },
    "marketing": {
        "discipline": "product",
        "perspective": "advisor",
        "applies_to": ["web", "api", "ai"],
        "specialties": [
            "b2b_marketing",  # B2B-specific go-to-market, enterprise sales cycles, account-based strategy
            "buying_committee",  # Multi-stakeholder deliberation, persona composition, value consensus, two-pass evaluation
            "conversion_optimization",  # Landing page audits, message architecture, value prop clarity, CTA friction
            "content_strategy",  # Blog cadence, SEO targeting, buyer-journey content mapping, thought leadership
            "message_architecture",  # Positioning, differentiation, competitive contrast, vertical-specific messaging
        ],
    },
    # ── OPERATIONAL ─────────────────────────────────────
    "error_handling": {
        "discipline": "engineering",
        "perspective": "sentinel",
        "applies_to": ["web", "api", "mobile", "cli"],
        "specialties": [
            "backend_errors",  # Typed exception hierarchies, error propagation, logging at boundaries
            "frontend_errors",  # Error boundaries, user-facing messages, silent failure prevention
            "graceful_degradation",  # Fallback UI, partial failure, feature disable under load
            "error_reporting",  # Sentry/Datadog integration, fingerprinting, alert fatigue reduction
            "retry_and_timeout",  # Exponential backoff, jitter, circuit breakers, timeout budgets
            "bulkhead_isolation",  # Resource pool separation, thread isolation, load shedding
            "dead_letter_handling",  # DLQ patterns, poison message detection, reprocessing strategies
        ],
    },
    "observability": {
        "discipline": "engineering",
        "perspective": "operator",
        "applies_to": ["web", "api", "mobile"],
        "specialties": [
            "structured_logging",
            "metrics_collection",
            "distributed_tracing",
            "health_checks",
            "slo_sli",  # Error budgets, burn rate alerts, toil reduction
            "alerting_strategy",  # On-call routing, runbooks, incident severity, escalation
        ],
    },
    "configuration": {
        "discipline": "engineering",
        "perspective": "operator",
        "applies_to": ["web", "api", "mobile", "cli"],
        "specialties": [
            "env_management",  # Per-environment config, .env conventions, 12-factor compliance
            "secrets_management",  # Vault, AWS Secrets Manager, rotation, least-privilege access
            "feature_flags",  # Flag lifecycle, targeting rules, kill switches, gradual rollout
            "config_validation",  # Startup validation, schema enforcement, required-field checks, type coercion
            "config_promotion",  # Config promotion pipelines, per-env diff tooling, change audit, rollback
            "config_as_code",  # Declarative config, schema evolution, backward compatibility, canary config
        ],
    },
    "deployment": {
        "discipline": "engineering",
        "perspective": "operator",
        "applies_to": ["web", "api", "mobile"],
        "specialties": [
            "container_patterns",
            "deploy_strategies",
            "rollback_procedures",
            "blue_green_canary",  # Traffic splitting, feature flags for rollout, dark launches
            "migration_ops",  # Schema migrations under load, zero-downtime deploys
            "chaos_engineering",  # Fault injection, resilience testing, gamedays
        ],
    },
    "versioning": {
        "discipline": "engineering",
        "perspective": "strategist",
        "applies_to": ["api", "library"],
        "specialties": [
            "semver_practices",  # Major/minor/patch semantics, pre-release tagging, lockfiles
            "changelog_generation",  # Conventional Commits, auto-changelog, keep-a-changelog format
            "deprecation_policy",  # Sunset periods, migration notices, removal timelines, telemetry
            "api_compatibility",  # Breaking vs non-breaking changes, expansion-only rules, sunset headers
            "release_automation",  # Release pipelines, auto-tag strategies, branch protection, publish gates
            "migration_guides",  # Upgrade paths, codemods, compatibility shims, version-specific docs
        ],
    },
    # ── AI/ML ───────────────────────────────────────────
    "ai_ml": {
        "discipline": "engineering",
        "perspective": "analyst",
        "applies_to": ["web", "api", "ai"],
        "specialties": [
            "llm_integration",  # Model routing, prompt versioning, token cost, streaming
            "agent_architecture",  # Tool use, multi-agent orchestration, memory tiers, state machines
            "rag_pipeline",  # Chunking, hybrid search, reranking, provenance, eval metrics
            "ai_safety",  # Prompt injection defense, output filtering, confidence scoring, red teaming
            "mlops",  # Model versioning, A/B model testing, drift detection, experiment tracking
        ],
    },
    # ── OPERATIONAL (SCALE) ──────────────────────────────
    "scale": {
        "discipline": "engineering",
        "perspective": "operator",
        "applies_to": ["web", "api"],
        "specialties": [
            "load_balancing",  # L4 vs L7, consistent hashing, auto-scaling, graceful shutdown
            "distributed_patterns",  # CAP theorem, PACELC tradeoffs, replication, partitioning
            "multi_region",  # Active-active vs active-passive, data residency, latency routing
            "backpressure",  # Slow consumers, queue depth limits, circuit breakers, load shedding
            "stateless_design",  # Session externalization, shared-nothing, horizontal scaling, sticky session avoidance
            "capacity_planning",  # Demand forecasting, headroom targets, auto-scaling policies, cost modeling
        ],
    },
    # ── TEAM ────────────────────────────────────────────
    "code_conventions": {
        "discipline": "engineering",
        "perspective": "practitioner",
        "applies_to": ["web", "api", "mobile", "cli", "library"],
        "specialties": [
            "naming_conventions",  # Variable/function/class naming, abbreviation rules, domain vocabulary
            "project_structure",  # Module layout, layer separation, circular import prevention, barrel files
            "code_style",  # Formatter config (Black/Prettier/Ruff), linter rules, enforcement in CI
            "git_practices",  # Branch naming, commit granularity, squash vs merge, rebase discipline
            "commit_conventions",  # Conventional Commits, semantic messages, PR description standards
            "code_review_standards",  # PR size limits, review checklists, approval requirements, CODEOWNERS
            "module_organization",  # Public API surface, internal vs exported, cohesion rules, coupling limits
        ],
    },
    "dependency_management": {
        "discipline": "engineering",
        "perspective": "sentinel",
        "applies_to": ["web", "api", "mobile", "cli", "library"],
        "specialties": [
            "package_selection",  # Evaluation criteria, maintenance signals, alternatives comparison
            "version_pinning",  # Lockfiles, upper bounds, floating vs exact, monorepo strategies
            "audit_practices",  # CVE scanning, npm audit / pip-audit, alert routing, remediation SLAs
            "license_compliance",  # License compatibility matrix, copyleft detection, attribution requirements
            "automated_updates",  # Dependabot/Renovate, auto-PR config, semantic version policies
            "supply_chain_security",  # SBOM (SPDX/CycloneDX), SLSA levels, artifact signing, provenance
        ],
    },
}


_DISCIPLINE_SET = frozenset(ALL_DISCIPLINES)


def validate_discipline(discipline: str) -> bool:
    """Return True if discipline is a recognised ACE quality dimension.

    Use this at API and configuration boundaries to catch typos early.
    Returns False (not raises) so callers can decide whether to warn or error.
    """
    return discipline in _DISCIPLINE_SET


def get_disciplines_for_product_type(product_type: str) -> list[str]:
    """Return list of discipline names relevant to a product type."""
    return [name for name, config in SEED_STRUCTURE.items() if product_type in config["applies_to"]]


def get_all_specialties() -> list[str]:
    """Return flat list of all specialty slugs."""
    specialties = []
    for config in SEED_STRUCTURE.values():
        specialties.extend(config["specialties"])
    return specialties


def audit_quality() -> dict:
    """Return quality audit results for all disciplines against the quality template.

    Returns a dict with 'passing', 'failing', and per-discipline detail.
    Used in tests and CI to prevent regressions in discipline coverage.
    """
    MIN_SPECIALTIES = 5
    passing = []
    failing = []
    detail = {}

    for name, config in SEED_STRUCTURE.items():
        specs = config.get("specialties", [])
        count = len(specs)
        meets_min = count >= MIN_SPECIALTIES
        detail[name] = {"specialty_count": count, "meets_minimum": meets_min}
        if meets_min:
            passing.append(name)
        else:
            failing.append(name)

    return {
        "passing": passing,
        "failing": failing,
        "detail": detail,
        "total_specialties": sum(d["specialty_count"] for d in detail.values()),
    }
