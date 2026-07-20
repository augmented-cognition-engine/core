# engine/product/cost_intelligence.py
"""E4 — Cost Intelligence Engine: code-graph-parameterized cost estimation.

Three-pass analysis that reads the ACE knowledge graph and produces
monthly cost estimates at a given MAU (monthly active users):

Pass 1 — Query Cost Analysis
  Identifies DB anti-patterns (N+1, unbounded selects, ORM lazy loading)
  from function names, complexity scores, and capability_finding records.
  Maps patterns to queries-per-user and data egress estimates.

Pass 2 — Compute Cost Analysis
  Detects deployment topology from capabilities and stack.
  Maps to provider pricing catalogs (Vercel, Railway, Fly.io, AWS Lambda).

Pass 3 — Third-Party API Cost Analysis
  Detects external API integrations from capability slugs.
  Maps to maintained pricing catalog (OpenAI, Anthropic, Stripe, SendGrid, etc.).

Output: monthly cost breakdown per provider + optimization recommendations.

Closes: #9 (Free Tier Trap) D→A
New tool: ace_cost_estimate(users, providers)
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

# ── Pricing catalogs ──────────────────────────────────────────────────────────

# Community-updateable: these are the ground truth for cost calculations.
# Update when providers change pricing. Values are USD.
PROVIDER_PRICING: dict[str, dict] = {
    "vercel": {
        "display": "Vercel",
        "type": "serverless",
        "free_invocations": 100_000,
        "price_per_million_invocations": 1.00,
        "free_bandwidth_gb": 100,
        "price_per_gb_bandwidth": 0.15,
        "assumed_avg_invocations_per_user_session": 20,
        "assumed_avg_response_kb": 50,
    },
    "railway": {
        "display": "Railway",
        "type": "always_on",
        "price_per_vcpu_hour": 0.000463,
        "price_per_gb_ram_hour": 0.000231,
        "free_monthly_credit_usd": 5.00,
        "assumed_vcpu": 0.5,
        "assumed_ram_gb": 0.5,
    },
    "fly_io": {
        "display": "Fly.io",
        "type": "always_on",
        "price_per_shared_cpu_hour": 0.0000022,
        "price_per_gb_ram_hour": 0.0000032,
        "free_machines": 3,
        "assumed_vcpu": 1,
        "assumed_ram_gb": 0.256,
    },
    "aws_lambda": {
        "display": "AWS Lambda",
        "type": "serverless",
        "free_requests_per_month": 1_000_000,
        "price_per_million_requests": 0.20,
        "price_per_gb_second": 0.0000166667,
        "assumed_duration_ms": 200,
        "assumed_memory_mb": 512,
        "assumed_invocations_per_user_session": 15,
    },
    "supabase": {
        "display": "Supabase",
        "type": "db_saas",
        "free_db_size_mb": 500,
        "pro_price_usd": 25.00,
        "pro_db_size_gb": 8.0,
        "price_per_extra_gb_usd": 0.125,
        "free_tier_mau_cap": 50_000,
        "estimated_db_growth_mb_per_1k_users": 50,
    },
    "neon": {
        "display": "Neon",
        "type": "db_saas",
        "free_compute_hours": 191,
        "free_storage_gb": 0.5,
        "launch_price_usd": 19.00,
        "price_per_extra_compute_hour": 0.16,
    },
    "upstash_redis": {
        "display": "Upstash Redis",
        "type": "cache_saas",
        "free_commands_per_day": 10_000,
        "price_per_100k_commands": 0.20,
        "assumed_commands_per_user_session": 8,
    },
}

THIRD_PARTY_PRICING: dict[str, dict] = {
    "openai": {
        "display": "OpenAI",
        "slug_keywords": ["openai", "gpt", "chatgpt", "embeddings_openai"],
        "gpt4o_input_per_million_tokens": 2.50,
        "gpt4o_output_per_million_tokens": 10.00,
        "gpt4o_mini_input_per_million_tokens": 0.15,
        "gpt4o_mini_output_per_million_tokens": 0.60,
        "assumed_calls_per_user_session": 3,
        "assumed_avg_tokens_in": 800,
        "assumed_avg_tokens_out": 400,
        "assumed_model": "gpt4o_mini",
    },
    "anthropic": {
        "display": "Anthropic",
        "slug_keywords": ["anthropic", "claude"],
        "claude_sonnet_input_per_million_tokens": 3.00,
        "claude_sonnet_output_per_million_tokens": 15.00,
        "claude_haiku_input_per_million_tokens": 0.25,
        "claude_haiku_output_per_million_tokens": 1.25,
        "assumed_calls_per_user_session": 3,
        "assumed_avg_tokens_in": 800,
        "assumed_avg_tokens_out": 400,
        "assumed_model": "claude_haiku",
    },
    "stripe": {
        "display": "Stripe",
        "slug_keywords": ["stripe", "payment", "billing", "subscription"],
        "payment_fee_pct": 2.9,
        "payment_flat_fee_usd": 0.30,
        "assumed_monthly_transaction_rate_pct": 5.0,
        "assumed_avg_transaction_usd": 29.00,
    },
    "sendgrid": {
        "display": "SendGrid",
        "slug_keywords": ["sendgrid", "email", "transactional_email", "mailer"],
        "free_emails_per_day": 100,
        "essentials_plan_usd": 19.95,
        "essentials_emails_per_month": 50_000,
        "assumed_emails_per_user_per_month": 2,
    },
    "twilio": {
        "display": "Twilio",
        "slug_keywords": ["twilio", "sms", "phone", "whatsapp"],
        "price_per_sms_usd": 0.0079,
        "assumed_sms_per_user_per_month": 1,
    },
    "resend": {
        "display": "Resend",
        "slug_keywords": ["resend", "email_resend"],
        "free_emails_per_month": 3_000,
        "pro_price_usd": 20.00,
        "pro_emails_per_month": 50_000,
        "assumed_emails_per_user_per_month": 2,
    },
    "cloudinary": {
        "display": "Cloudinary",
        "slug_keywords": ["cloudinary", "media", "image_upload", "cdn"],
        "free_credits": 25,
        "plus_price_usd": 89.00,
        "assumed_transformations_per_user_per_month": 5,
    },
}

# ── Pass 1: Query pattern analysis ────────────────────────────────────────────

# Function names that strongly suggest N+1 query patterns
_N1_NAME_SIGNALS = [
    "get_",
    "fetch_",
    "load_",
    "list_",
    "find_",
    "for_user",
    "per_user",
    "for_each",
    "for_all",
]

# Function names that suggest unbounded selects
_UNBOUNDED_SIGNALS = ["get_all_", "list_all_", "fetch_all_", "select_all_"]


async def _analyze_query_patterns(product_id: str, db) -> list[dict]:
    """Pass 1: Detect DB anti-patterns from graph_function names and findings.

    Returns list of detected patterns:
        {pattern, location, description, queries_per_user_estimate, severity}
    """
    patterns = []

    # Check capability_finding for data-related issues (from E2 scans)
    try:
        finding_rows = parse_rows(
            await db.query(
                """SELECT file, line, message, severity, discipline
                   FROM capability_finding
                   WHERE product = <record>$product
                     AND discipline IN ['data', 'data_modeling', 'performance']
                   ORDER BY severity ASC LIMIT 20""",
                {"product": product_id},
            )
        )
        for finding in finding_rows:
            patterns.append(
                {
                    "pattern": "static_analysis_finding",
                    "location": f"{finding.get('file', '?')}:{finding.get('line', 0)}",
                    "description": finding.get("message", ""),
                    "queries_per_user_estimate": 0,
                    "severity": finding.get("severity", "medium"),
                    "source": "capability_finding",
                }
            )
    except Exception:
        pass

    # Check capability_quality for data_modeling dimension
    try:
        quality_rows = parse_rows(
            await db.query(
                """SELECT dimension, score, gaps
                   FROM capability_quality
                   WHERE product = <record>$product AND dimension = 'data_modeling'""",
                {"product": product_id},
            )
        )
        for row in quality_rows:
            score = float(row.get("score") or 1.0)
            if score < 0.6:
                patterns.append(
                    {
                        "pattern": "data_modeling_gap",
                        "location": "data layer",
                        "description": f"Data modeling score {score:.1%} — likely contains inefficient query patterns",
                        "queries_per_user_estimate": max(0, int((0.6 - score) * 20)),
                        "severity": "high" if score < 0.4 else "medium",
                        "source": "capability_quality",
                    }
                )
    except Exception:
        pass

    # Check graph_function for N+1 name patterns and high complexity
    try:
        func_rows = parse_rows(
            await db.query(
                """SELECT name, complexity, line_start
                   FROM graph_function
                   WHERE graph_id = 'default' AND complexity > 10
                   ORDER BY complexity DESC LIMIT 30""",
                {"product": product_id},
            )
        )
        for fn in func_rows:
            name = (fn.get("name") or "").lower()
            is_n1_candidate = any(sig in name for sig in _N1_NAME_SIGNALS)
            is_unbounded = any(sig in name for sig in _UNBOUNDED_SIGNALS)

            if is_n1_candidate and fn.get("complexity", 0) > 15:
                patterns.append(
                    {
                        "pattern": "n1_candidate",
                        "location": f"function:{fn.get('name', '?')} (line {fn.get('line_start', 0)})",
                        "description": f"High-complexity fetch function '{fn.get('name')}' (complexity={fn.get('complexity')}) — likely N+1 pattern",
                        "queries_per_user_estimate": fn.get("complexity", 1),
                        "severity": "high",
                        "source": "graph_function",
                    }
                )
            elif is_unbounded:
                patterns.append(
                    {
                        "pattern": "unbounded_select",
                        "location": f"function:{fn.get('name', '?')}",
                        "description": f"'{fn.get('name')}' may return unbounded results — missing LIMIT clause",
                        "queries_per_user_estimate": 1,
                        "severity": "medium",
                        "source": "graph_function",
                    }
                )
    except Exception:
        pass

    return patterns


# ── Pass 2: Compute pattern analysis ─────────────────────────────────────────


async def _analyze_compute_patterns(product_id: str, db, stack: list[str]) -> list[dict]:
    """Pass 2: Detect deployment topology from capabilities and stack.

    Returns list of detected compute patterns:
        {provider, pattern_type, confidence, notes}
    """
    patterns = []

    # Detect provider signals from capabilities
    try:
        cap_rows = parse_rows(
            await db.query(
                """SELECT slug, title, category FROM capability
                   WHERE product = <record>$product AND status != 'deprecated'""",
                {"product": product_id},
            )
        )
        cap_text = " ".join(
            (c.get("slug", "") + " " + c.get("title", "") + " " + c.get("category", "")).lower() for c in cap_rows
        )
    except Exception:
        cap_text = ""

    stack_text = " ".join(stack).lower()
    combined = cap_text + " " + stack_text

    # Provider detection rules
    provider_signals = [
        ("vercel", ["vercel", "next.js", "nextjs", "edge function"]),
        ("railway", ["railway"]),
        ("fly_io", ["fly.io", "flyio", "fly io"]),
        ("aws_lambda", ["lambda", "aws", "serverless", "sam", "chalice"]),
        ("supabase", ["supabase"]),
        ("neon", ["neon", "neondb"]),
        ("upstash_redis", ["upstash", "redis"]),
    ]

    for provider_key, keywords in provider_signals:
        if any(kw in combined for kw in keywords):
            pricing = PROVIDER_PRICING.get(provider_key, {})
            patterns.append(
                {
                    "provider": provider_key,
                    "display": pricing.get("display", provider_key),
                    "pattern_type": pricing.get("type", "unknown"),
                    "confidence": "high",
                    "notes": "Detected from capability/stack signals",
                }
            )

    # If nothing detected, infer from stack defaults
    if not patterns:
        if "nextjs" in stack_text or "node" in stack_text:
            patterns.append(
                {
                    "provider": "vercel",
                    "display": "Vercel",
                    "pattern_type": "serverless",
                    "confidence": "low",
                    "notes": "Inferred from Next.js/Node stack — common default",
                }
            )
        elif "fastapi" in stack_text or "python" in stack_text:
            patterns.append(
                {
                    "provider": "railway",
                    "display": "Railway",
                    "pattern_type": "always_on",
                    "confidence": "low",
                    "notes": "Inferred from FastAPI/Python stack — common default",
                }
            )

    return patterns


# ── Pass 3: Third-party API analysis ──────────────────────────────────────────


async def _analyze_api_patterns(product_id: str, db) -> list[dict]:
    """Pass 3: Detect third-party API integrations from capability slugs.

    Returns list of detected API patterns:
        {api, display, calls_per_user_session, monthly_estimate_at_1k_users}
    """
    patterns = []

    try:
        cap_rows = parse_rows(
            await db.query(
                """SELECT slug, title, category FROM capability
                   WHERE product = <record>$product AND status != 'deprecated'""",
                {"product": product_id},
            )
        )
        cap_text = " ".join((c.get("slug", "") + " " + c.get("title", "")).lower() for c in cap_rows)
    except Exception:
        cap_text = ""

    for api_key, pricing in THIRD_PARTY_PRICING.items():
        keywords = pricing.get("slug_keywords", [])
        if any(kw in cap_text for kw in keywords):
            patterns.append(
                {
                    "api": api_key,
                    "display": pricing.get("display", api_key),
                    "pricing": pricing,
                    "confidence": "high",
                }
            )

    return patterns


# ── Cost calculation ──────────────────────────────────────────────────────────


def _estimate_provider_cost(provider_key: str, users: int) -> dict:
    """Calculate monthly cost estimate for a provider at given MAU."""
    pricing = PROVIDER_PRICING.get(provider_key, {})
    if not pricing:
        return {"provider": provider_key, "monthly_usd": 0.0, "breakdown": {}}

    provider_type = pricing.get("type", "unknown")
    breakdown = {}
    total = 0.0

    if provider_type == "serverless":
        # invocations-based pricing
        sessions_per_month = users * 20  # 20 sessions/user/month
        invocations = sessions_per_month * pricing.get("assumed_avg_invocations_per_user_session", 15)
        free = pricing.get("free_invocations", 0) or pricing.get("free_requests_per_month", 0)
        price_per_m = pricing.get("price_per_million_invocations", 0) or pricing.get("price_per_million_requests", 0)
        billable = max(0, invocations - free)
        invocation_cost = (billable / 1_000_000) * price_per_m
        breakdown["invocations"] = {
            "count": invocations,
            "billable": billable,
            "cost_usd": round(invocation_cost, 2),
        }
        total += invocation_cost

        # bandwidth
        bandwidth_gb = (
            sessions_per_month
            * pricing.get("assumed_avg_invocations_per_user_session", 15)
            * pricing.get("assumed_avg_response_kb", 50)
            / (1024 * 1024)
        )
        free_bw = pricing.get("free_bandwidth_gb", 0)
        bw_cost = max(0, bandwidth_gb - free_bw) * pricing.get("price_per_gb_bandwidth", 0)
        breakdown["bandwidth_gb"] = round(bandwidth_gb, 1)
        breakdown["bandwidth_cost_usd"] = round(bw_cost, 2)
        total += bw_cost

    elif provider_type == "always_on":
        # vcpu + ram hours
        hours_per_month = 730
        vcpu_cost = pricing.get("assumed_vcpu", 0.5) * hours_per_month * pricing.get("price_per_vcpu_hour", 0)
        ram_cost = pricing.get("assumed_ram_gb", 0.5) * hours_per_month * pricing.get("price_per_gb_ram_hour", 0)
        credit = pricing.get("free_monthly_credit_usd", 0)
        total = max(0, vcpu_cost + ram_cost - credit)
        breakdown["vcpu_cost_usd"] = round(vcpu_cost, 2)
        breakdown["ram_cost_usd"] = round(ram_cost, 2)
        breakdown["free_credit_usd"] = credit

    elif provider_type == "db_saas":
        # SaaS DB pricing (Supabase-style)
        estimated_db_mb = users * pricing.get("estimated_db_growth_mb_per_1k_users", 50) / 1000
        free_mb = pricing.get("free_db_size_mb", 500)
        pro_price = pricing.get("pro_price_usd", 0)
        pro_gb = pricing.get("pro_db_size_gb", 8)

        if estimated_db_mb <= free_mb:
            total = 0.0
            breakdown["tier"] = "free"
        elif estimated_db_mb <= pro_gb * 1024:
            total = pro_price
            breakdown["tier"] = "pro"
            # Warn about tier upgrade threshold
            upgrade_users = int(free_mb / pricing.get("estimated_db_growth_mb_per_1k_users", 50) * 1000)
            breakdown["free_tier_cap_users"] = upgrade_users
        else:
            extra_gb = (estimated_db_mb / 1024) - pro_gb
            total = pro_price + extra_gb * pricing.get("price_per_extra_gb_usd", 0.125)
            breakdown["tier"] = "pro_extra"

        breakdown["estimated_db_gb"] = round(estimated_db_mb / 1024, 2)

    elif provider_type == "cache_saas":
        # Command-based pricing (Upstash-style)
        sessions_per_month = users * 20
        commands = sessions_per_month * pricing.get("assumed_commands_per_user_session", 8)
        free_daily = pricing.get("free_commands_per_day", 10_000)
        free_monthly = free_daily * 30
        billable = max(0, commands - free_monthly)
        total = (billable / 100_000) * pricing.get("price_per_100k_commands", 0.20)
        breakdown["commands_per_month"] = int(commands)
        breakdown["billable_commands"] = int(billable)

    return {
        "provider": provider_key,
        "display": pricing.get("display", provider_key),
        "monthly_usd": round(total, 2),
        "breakdown": breakdown,
    }


def _estimate_api_cost(api_key: str, users: int) -> dict:
    """Calculate monthly cost for a third-party API at given MAU."""
    pricing = THIRD_PARTY_PRICING.get(api_key, {})
    if not pricing:
        return {"api": api_key, "monthly_usd": 0.0, "breakdown": {}}

    sessions_per_month = users * 20
    total = 0.0
    breakdown = {}
    warning = None

    if api_key in ("openai", "anthropic"):
        calls = sessions_per_month * pricing.get("assumed_calls_per_user_session", 3)
        model = pricing.get("assumed_model", "")
        tokens_in = pricing.get("assumed_avg_tokens_in", 800)
        tokens_out = pricing.get("assumed_avg_tokens_out", 400)

        if api_key == "openai":
            input_price = pricing.get("gpt4o_mini_input_per_million_tokens", 0.15)
            output_price = pricing.get("gpt4o_mini_output_per_million_tokens", 0.60)
        else:
            input_price = pricing.get("claude_haiku_input_per_million_tokens", 0.25)
            output_price = pricing.get("claude_haiku_output_per_million_tokens", 1.25)

        input_cost = (calls * tokens_in / 1_000_000) * input_price
        output_cost = (calls * tokens_out / 1_000_000) * output_price
        total = input_cost + output_cost
        breakdown["calls_per_month"] = int(calls)
        breakdown["model"] = model
        breakdown["input_cost_usd"] = round(input_cost, 2)
        breakdown["output_cost_usd"] = round(output_cost, 2)

    elif api_key == "stripe":
        transactions = sessions_per_month * pricing.get("assumed_monthly_transaction_rate_pct", 5) / 100
        avg_amount = pricing.get("assumed_avg_transaction_usd", 29.00)
        fee = (avg_amount * pricing.get("payment_fee_pct", 2.9) / 100) + pricing.get("payment_flat_fee_usd", 0.30)
        total = transactions * fee
        breakdown["transactions_per_month"] = int(transactions)
        breakdown["avg_fee_per_transaction_usd"] = round(fee, 2)
        breakdown["note"] = "Stripe fees are revenue-proportional — scales with GMV"

    elif api_key in ("sendgrid", "resend"):
        emails_per_month = users * pricing.get("assumed_emails_per_user_per_month", 2)
        free_per_month = pricing.get("free_emails_per_month", 0) or (pricing.get("free_emails_per_day", 0) * 30)
        pro_price = pricing.get("essentials_plan_usd") or pricing.get("pro_price_usd", 0)
        pro_volume = pricing.get("essentials_emails_per_month") or pricing.get("pro_emails_per_month", 50_000)

        if emails_per_month <= free_per_month:
            total = 0.0
            breakdown["tier"] = "free"
        elif emails_per_month <= pro_volume:
            total = pro_price
            breakdown["tier"] = "pro"
        else:
            total = pro_price
            warning = f"Volume ({int(emails_per_month):,} emails/mo) exceeds pro plan — upgrade required"
        breakdown["emails_per_month"] = int(emails_per_month)

    elif api_key == "twilio":
        sms_per_month = users * pricing.get("assumed_sms_per_user_per_month", 1)
        total = sms_per_month * pricing.get("price_per_sms_usd", 0.0079)
        breakdown["sms_per_month"] = int(sms_per_month)

    result = {
        "api": api_key,
        "display": pricing.get("display", api_key),
        "monthly_usd": round(total, 2),
        "breakdown": breakdown,
    }
    if warning:
        result["warning"] = warning
    return result


# ── LLM synthesis prompt ──────────────────────────────────────────────────────

_SYNTHESIS_PROMPT = """You are ACE's Cost Intelligence Engine synthesizing a cost estimate report.

Project: {product_id}
MAU (Monthly Active Users): {users:,}

=== COMPUTE COSTS ===
{compute_lines}

=== THIRD-PARTY API COSTS ===
{api_lines}

=== DB QUERY PATTERNS DETECTED ===
{query_pattern_lines}

Format this as a concise Cost Intelligence Report:

1. Start with a cost summary table:
   Provider     | Monthly Cost | Notes
   -------------|--------------|------
   [list each]

2. Total estimated monthly cost

3. If total > $100: flag it as "⚠ Cost Alert"
   If any provider will hit a paid tier below {users_cap_pct:.0%} of current MAU: flag "⚠ Tier Risk"

4. Top 2-3 optimization recommendations based on the query patterns + cost breakdown.
   Each should have: what to fix, estimated savings, and why.

5. If AI API costs > 40% of total: suggest caching completions, using smaller models, or batching

Return clean markdown. No JSON, no code fences. Be specific with numbers."""


# ── Main entry point ──────────────────────────────────────────────────────────


async def run_cost_estimate(
    product_id: str,
    users: int = 1000,
    providers: list[str] | None = None,
) -> dict:
    """Run three-pass cost analysis and return estimated monthly costs.

    Args:
        product_id: Product to analyze.
        users:      Monthly active users for the estimate (default 1000).
        providers:  Limit to specific providers. None = auto-detect all.

    Returns:
        {
            users, compute_costs, api_costs, query_patterns,
            total_monthly_usd, report (markdown), warnings
        }
    """
    if users <= 0:
        return {"error": "users must be > 0", "users": users}

    async with pool.connection() as db:
        # Detect stack
        try:
            cap_rows = parse_rows(
                await db.query(
                    "SELECT slug, title, category FROM capability WHERE product = <record>$product AND status != 'deprecated'",
                    {"product": product_id},
                )
            )
        except Exception:
            cap_rows = []

        from core.engine.product.generation_engine import _infer_stack_from_capabilities

        stack = _infer_stack_from_capabilities(cap_rows)

        # Run three passes
        query_patterns = await _analyze_query_patterns(product_id, db)
        compute_patterns = await _analyze_compute_patterns(product_id, db, stack)
        api_patterns = await _analyze_api_patterns(product_id, db)

    # Calculate costs
    provider_keys = providers or [p["provider"] for p in compute_patterns]
    compute_costs = [_estimate_provider_cost(key, users) for key in provider_keys]
    api_costs = [_estimate_api_cost(p["api"], users) for p in api_patterns]

    total_monthly_usd = round(
        sum(c["monthly_usd"] for c in compute_costs) + sum(a["monthly_usd"] for a in api_costs),
        2,
    )

    # Collect warnings
    warnings = []
    for cost in compute_costs + api_costs:
        if cost.get("warning"):
            warnings.append(cost["warning"])
        # Tier risk: check if free tier cap is below users
        cap = cost.get("breakdown", {}).get("free_tier_cap_users")
        if cap and cap < users:
            warnings.append(
                f"{cost.get('display', cost.get('provider', cost.get('api', '?')))}: "
                f"hits paid tier at ~{cap:,} users (currently {users:,})"
            )

    # LLM synthesis
    compute_lines = (
        "\n".join(f"  {c['display']}: ${c['monthly_usd']:.2f}/mo  {c['breakdown']}" for c in compute_costs)
        or "  No compute providers detected"
    )

    api_lines = (
        "\n".join(f"  {a['display']}: ${a['monthly_usd']:.2f}/mo  {a['breakdown']}" for a in api_costs)
        or "  No third-party API integrations detected"
    )

    query_lines = (
        "\n".join(f"  [{p['severity']}] {p['pattern']} — {p['description'][:100]}" for p in query_patterns[:5])
        or "  No query anti-patterns detected"
    )

    # users_cap_pct: at what fraction of users do tier upgrades happen?
    users_cap_pct = 0.5  # warn if tier risk below 50% of current MAU

    prompt = _SYNTHESIS_PROMPT.format(
        product_id=product_id,
        users=users,
        compute_lines=compute_lines,
        api_lines=api_lines,
        query_pattern_lines=query_lines,
        users_cap_pct=users_cap_pct,
    )

    report = ""
    try:
        llm = get_llm()
        report = await llm.complete(prompt, max_tokens=1500)
    except Exception as exc:
        logger.warning("Cost estimate LLM synthesis failed: %s", exc)
        report = f"[LLM synthesis unavailable: {exc}]"

    logger.info(
        "Cost estimate complete: product=%s users=%d total=$%.2f providers=%d apis=%d",
        product_id,
        users,
        total_monthly_usd,
        len(compute_costs),
        len(api_costs),
    )

    return {
        "users": users,
        "stack": stack,
        "compute_costs": compute_costs,
        "api_costs": api_costs,
        "query_patterns": query_patterns,
        "total_monthly_usd": total_monthly_usd,
        "warnings": warnings,
        "report": report,
    }
