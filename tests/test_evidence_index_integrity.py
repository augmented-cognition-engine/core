from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence"
EVIDENCE_README = EVIDENCE_DIR / "README.md"

# Historical candidate labels remain intentional after publication: the point-in-time P1/P2
# records are immutable. The later public GI2 receipt is separately indexed as the authoritative
# passed closeout. Keep these checks aligned with tests/test_public_roadmap_positioning.py.

LOCAL_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]*)?\)")


def _local_links(text: str) -> list[str]:
    links = []
    for target in LOCAL_MARKDOWN_LINK.findall(text):
        if target.startswith(("http://", "https://")):
            continue
        links.append(target)
    return links


def test_every_local_markdown_link_in_evidence_readme_resolves() -> None:
    text = EVIDENCE_README.read_text(encoding="utf-8")
    links = _local_links(text)
    assert links, "expected at least one local markdown link in docs/evidence/README.md"

    missing = [link for link in links if not (EVIDENCE_DIR / link).resolve().is_file()]
    assert not missing, f"dead local links in docs/evidence/README.md: {missing}"


def test_evidence_readme_manifesto_label_is_internally_consistent() -> None:
    """The legend defines "public" as a re-derivable published artifact; the manifesto isn't one.

    This is a durable label-consistency rule, not pre-release prose: whatever label the manifesto
    carries must match what the legend defines for it, now and after publication.
    """
    text = EVIDENCE_README.read_text(encoding="utf-8")
    manifesto_line = next(line for line in text.splitlines() if "ACE Core manifesto" in line)
    assert "current, authoritative" in manifesto_line
    assert "public, current" not in manifesto_line


def test_evidence_readme_indexes_manifesto_and_new_platform_records() -> None:
    text = EVIDENCE_README.read_text(encoding="utf-8")

    required_targets = [
        "../../MANIFESTO.md",
        "gi2-public-cross-domain-falsification-v1.md",
        "platform-p1c1-declarative-source-mapping-v1.md",
        "platform-p1c2-governed-live-source-ingress-v1.md",
        "platform-p1d1-governed-routed-brief-v1.md",
        "platform-p1e-governed-feedback-v1.md",
        "platform-p1f-governed-live-intelligence-bridge-v1.md",
        "platform-p2b-categorical-detection-v1.md",
        "platform-p2b-immutable-case-closure-v1.md",
        "platform-p2b-independent-resource-admission-v1.md",
        "platform-p2c-case-bound-governed-brief-v1.md",
        "platform-p2d-per-statement-epistemic-status-v1.md",
        "platform-p2e-derivation-family-independence-v1.md",
        "platform-p2f-supersession-impact-projection-v1.md",
        "context-manifest-code-context-v1.md",
        "productized-state-golden-journey-v1.md",
    ]
    links = set(_local_links(text))
    missing = [target for target in required_targets if target not in links]
    assert not missing, f"docs/evidence/README.md is missing links to: {missing}"


def test_evidence_readme_labels_candidate_and_historical_records_honestly() -> None:
    text = EVIDENCE_README.read_text(encoding="utf-8")

    gi2_line = next(
        line
        for line in text.splitlines()
        if line.startswith("- [GI2 public cross-domain falsification](")
    )
    assert "public, passed" in gi2_line

    for line in text.splitlines():
        if "platform-p1" in line or "platform-p2" in line:
            assert "candidate, local" in line, f"unlabeled candidate record: {line!r}"
        if "context-manifest-code-context-v1.md" in line or "productized-state-golden-journey-v1.md" in line:
            assert "historical" in line, f"unlabeled historical record: {line!r}"


def test_every_evidence_markdown_file_referenced_from_this_pr_is_indexed() -> None:
    """New evidence files added alongside this change must not become orphans."""
    readme_text = EVIDENCE_README.read_text(encoding="utf-8")
    linked = set(_local_links(readme_text))

    newly_added = {
        "platform-p1c1-declarative-source-mapping-v1.md",
        "platform-p1c2-governed-live-source-ingress-v1.md",
        "platform-p1d1-governed-routed-brief-v1.md",
        "platform-p1e-governed-feedback-v1.md",
        "platform-p1f-governed-live-intelligence-bridge-v1.md",
        "platform-p2b-categorical-detection-v1.md",
        "platform-p2b-immutable-case-closure-v1.md",
        "platform-p2b-independent-resource-admission-v1.md",
        "platform-p2c-case-bound-governed-brief-v1.md",
        "platform-p2d-per-statement-epistemic-status-v1.md",
        "platform-p2e-derivation-family-independence-v1.md",
        "platform-p2f-supersession-impact-projection-v1.md",
        "context-manifest-code-context-v1.md",
        "productized-state-golden-journey-v1.md",
        "gi2-public-cross-domain-falsification-v1.md",
    }
    for name in newly_added:
        assert (EVIDENCE_DIR / name).is_file(), f"expected fixture file missing: {name}"

    orphaned = sorted(newly_added - linked)
    assert not orphaned, f"evidence files not indexed in README.md: {orphaned}"
