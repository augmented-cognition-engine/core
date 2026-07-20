"""Source registry — discipline-aware sources with quality tiers.

Every research request routes through the source registry to bias extraction
toward authoritative sources before falling back to open web search.
"""

from __future__ import annotations

from enum import Enum
from urllib.parse import urlparse


class SourceClass(str, Enum):
    REFERENCE = "reference"  # Framework authors, official specs → HIGH confidence
    EXEMPLAR = "exemplar"  # Well-governed OSS repos → MEDIUM-HIGH
    SIGNAL = "signal"  # Popular but unvetted → LOW, needs corroboration
    NOISE = "noise"  # Skip entirely


# Per-discipline curated sources. Add more as research encounters them.
DISCIPLINE_SOURCES: dict[str, list[dict]] = {
    "security": [
        {"url": "https://owasp.org", "name": "OWASP", "class": SourceClass.REFERENCE},
        {"url": "https://cve.mitre.org", "name": "CVE Database", "class": SourceClass.REFERENCE},
        {"url": "https://cwe.mitre.org", "name": "CWE", "class": SourceClass.REFERENCE},
        {"url": "https://snyk.io/blog", "name": "Snyk Blog", "class": SourceClass.SIGNAL},
    ],
    "architecture": [
        {"url": "https://www.thoughtworks.com/radar", "name": "ThoughtWorks Radar", "class": SourceClass.REFERENCE},
        {"url": "https://martinfowler.com", "name": "Martin Fowler", "class": SourceClass.REFERENCE},
        {"url": "https://www.infoq.com", "name": "InfoQ", "class": SourceClass.SIGNAL},
    ],
    "ux": [
        {"url": "https://www.nngroup.com", "name": "Nielsen Norman Group", "class": SourceClass.REFERENCE},
        {"url": "https://www.w3.org/WAI/WCAG21/quickref/", "name": "WCAG", "class": SourceClass.REFERENCE},
        {"url": "https://a11yproject.com", "name": "A11y Project", "class": SourceClass.EXEMPLAR},
    ],
    "accessibility": [
        {"url": "https://www.w3.org/WAI/WCAG21/quickref/", "name": "WCAG", "class": SourceClass.REFERENCE},
        {"url": "https://a11yproject.com", "name": "A11y Project", "class": SourceClass.EXEMPLAR},
        {"url": "https://www.deque.com/axe/", "name": "axe-core", "class": SourceClass.EXEMPLAR},
    ],
    "testing": [
        {"url": "https://github.com/django/django", "name": "Django", "class": SourceClass.EXEMPLAR},
        {"url": "https://github.com/pydantic/pydantic", "name": "Pydantic", "class": SourceClass.EXEMPLAR},
        {"url": "https://github.com/tiangolo/fastapi", "name": "FastAPI", "class": SourceClass.EXEMPLAR},
        {"url": "https://github.com/pallets/flask", "name": "Flask", "class": SourceClass.EXEMPLAR},
    ],
    "api_design": [
        {"url": "https://stripe.com/docs/api", "name": "Stripe API Docs", "class": SourceClass.REFERENCE},
        {"url": "https://docs.github.com/en/rest", "name": "GitHub REST API", "class": SourceClass.REFERENCE},
        {"url": "https://www.twilio.com/docs/usage/api", "name": "Twilio API", "class": SourceClass.REFERENCE},
    ],
    "performance": [
        {"url": "https://web.dev", "name": "web.dev", "class": SourceClass.REFERENCE},
        {
            "url": "https://developer.chrome.com/docs/devtools/",
            "name": "Chrome DevTools",
            "class": SourceClass.REFERENCE,
        },
    ],
    "data_modeling": [
        {"url": "https://www.postgresql.org/docs/current/", "name": "PostgreSQL Docs", "class": SourceClass.REFERENCE},
        {"url": "https://docs.surrealdb.com", "name": "SurrealDB Docs", "class": SourceClass.REFERENCE},
    ],
    "observability": [
        {"url": "https://opentelemetry.io/docs/", "name": "OpenTelemetry", "class": SourceClass.REFERENCE},
        {"url": "https://prometheus.io/docs/", "name": "Prometheus Docs", "class": SourceClass.REFERENCE},
    ],
    "deployment": [
        {"url": "https://docs.docker.com", "name": "Docker Docs", "class": SourceClass.REFERENCE},
        {"url": "https://kubernetes.io/docs/", "name": "Kubernetes Docs", "class": SourceClass.REFERENCE},
    ],
    "code_conventions": [
        {"url": "https://peps.python.org/pep-0008/", "name": "PEP 8", "class": SourceClass.REFERENCE},
        {"url": "https://google.github.io/styleguide/", "name": "Google Style Guide", "class": SourceClass.REFERENCE},
    ],
    "devops": [
        {"url": "https://docs.github.com/en/actions", "name": "GitHub Actions Docs", "class": SourceClass.REFERENCE},
    ],
    "error_handling": [
        {"url": "https://martinfowler.com", "name": "Martin Fowler", "class": SourceClass.REFERENCE},
    ],
    "integration": [
        {"url": "https://www.enterpriseintegrationpatterns.com", "name": "EIP", "class": SourceClass.REFERENCE},
    ],
    "configuration": [
        {"url": "https://12factor.net", "name": "12-Factor App", "class": SourceClass.REFERENCE},
    ],
    "versioning": [
        {"url": "https://semver.org", "name": "SemVer", "class": SourceClass.REFERENCE},
    ],
    "dependency_management": [
        {"url": "https://docs.astral.sh/uv/", "name": "uv Docs", "class": SourceClass.REFERENCE},
    ],
    "data": [
        {"url": "https://www.postgresql.org/docs/current/", "name": "PostgreSQL Docs", "class": SourceClass.REFERENCE},
    ],
    "documentation": [
        {
            "url": "https://www.divio.com/blog/documentation/",
            "name": "Divio Documentation System",
            "class": SourceClass.REFERENCE,
        },
    ],
    "business_logic": [
        {"url": "https://martinfowler.com", "name": "Martin Fowler", "class": SourceClass.REFERENCE},
    ],
}

# Domain → SourceClass mapping for fast URL classification.
# Checked as prefix — "github.com/pydantic" matches before "github.com".
_DOMAIN_CLASSES: list[tuple[str, SourceClass]] = [
    # EXEMPLAR — specific orgs (must come before generic "github.com")
    ("github.com/django/", SourceClass.EXEMPLAR),
    ("github.com/pydantic/", SourceClass.EXEMPLAR),
    ("github.com/tiangolo/", SourceClass.EXEMPLAR),
    ("github.com/pallets/", SourceClass.EXEMPLAR),
    ("github.com/encode/", SourceClass.EXEMPLAR),
    ("github.com/anthropics/", SourceClass.EXEMPLAR),
    # REFERENCE domains
    ("owasp.org", SourceClass.REFERENCE),
    ("cve.mitre.org", SourceClass.REFERENCE),
    ("cwe.mitre.org", SourceClass.REFERENCE),
    ("martinfowler.com", SourceClass.REFERENCE),
    ("thoughtworks.com", SourceClass.REFERENCE),
    ("nngroup.com", SourceClass.REFERENCE),
    ("w3.org", SourceClass.REFERENCE),
    ("stripe.com/docs", SourceClass.REFERENCE),
    ("web.dev", SourceClass.REFERENCE),
    ("postgresql.org/docs", SourceClass.REFERENCE),
    ("surrealdb.com/docs", SourceClass.REFERENCE),
    ("opentelemetry.io", SourceClass.REFERENCE),
    ("prometheus.io/docs", SourceClass.REFERENCE),
    ("docs.docker.com", SourceClass.REFERENCE),
    ("kubernetes.io/docs", SourceClass.REFERENCE),
    ("peps.python.org", SourceClass.REFERENCE),
    ("docs.python.org", SourceClass.REFERENCE),
    ("google.github.io/styleguide", SourceClass.REFERENCE),
    ("12factor.net", SourceClass.REFERENCE),
    ("semver.org", SourceClass.REFERENCE),
    ("docs.github.com", SourceClass.REFERENCE),
    ("developer.mozilla.org", SourceClass.REFERENCE),
    ("docs.anthropic.com", SourceClass.REFERENCE),
    ("docs.surrealdb.com", SourceClass.REFERENCE),
    ("developer.chrome.com", SourceClass.REFERENCE),
    ("docs.astral.sh/uv", SourceClass.REFERENCE),
    ("www.divio.com", SourceClass.REFERENCE),
    ("enterpriseintegrationpatterns.com", SourceClass.REFERENCE),
    ("a11yproject.com", SourceClass.EXEMPLAR),
    ("deque.com", SourceClass.EXEMPLAR),
    # SIGNAL
    ("medium.com", SourceClass.SIGNAL),
    ("dev.to", SourceClass.SIGNAL),
    ("hackernoon.com", SourceClass.SIGNAL),
    ("stackoverflow.com", SourceClass.SIGNAL),
    ("reddit.com", SourceClass.SIGNAL),
    ("news.ycombinator.com", SourceClass.SIGNAL),
    ("lobste.rs", SourceClass.SIGNAL),
]


def get_sources_for_discipline(discipline: str) -> list[dict]:
    """Return curated sources for a discipline. Empty list if not in registry."""
    return list(DISCIPLINE_SOURCES.get(discipline, []))


def classify_url(url: str) -> SourceClass:
    """Classify a URL by domain pattern. Unknown → SIGNAL (never NOISE)."""
    try:
        parsed = urlparse(url)
        authority_path = (parsed.netloc + parsed.path).removeprefix("www.")
    except Exception:
        return SourceClass.SIGNAL

    for pattern, cls in _DOMAIN_CLASSES:
        if authority_path.startswith(pattern):
            return cls

    return SourceClass.SIGNAL
