# tests/test_template_suggest.py
from core.engine.templates.suggest import (
    are_structurally_similar,
    extract_template_draft,
    find_clusters,
    initiative_fingerprint,
    jaccard_similarity,
)


def _make_initiative(title, milestones):
    return {
        "id": f"initiative:{title.replace(' ', '_')}",
        "title": title,
        "domain_path": "architecture",
        "milestones_detail": milestones,
    }


def _make_milestone(work_items):
    return {"title": "M1", "description": "test", "done_criteria": [], "work_items_detail": work_items}


def _make_wi(archetype="creator", mode="deliberative", domain="architecture"):
    return {"archetype": archetype, "mode": mode, "domain_path": domain}


def test_fingerprint_basic():
    init = _make_initiative(
        "Test",
        [
            _make_milestone([_make_wi("creator"), _make_wi("analyst")]),
            _make_milestone([_make_wi("executor")]),
        ],
    )
    fp = initiative_fingerprint(init)
    assert fp["milestone_count"] == 2
    assert fp["archetype_sequence"] == ["creator", "analyst", "executor"]
    assert fp["total_work_items"] == 3


def test_similar_initiatives():
    fp_a = {
        "milestone_count": 2,
        "archetype_sequence": ["creator", "analyst", "executor"],
        "domain_paths": ["architecture", "testing"],
        "total_work_items": 3,
    }
    fp_b = {
        "milestone_count": 2,
        "archetype_sequence": ["creator", "analyst", "executor"],
        "domain_paths": ["architecture", "testing"],
        "total_work_items": 3,
    }
    assert are_structurally_similar(fp_a, fp_b) is True


def test_different_milestone_count():
    fp_a = {"milestone_count": 2, "archetype_sequence": ["creator"], "domain_paths": ["tech"], "total_work_items": 1}
    fp_b = {"milestone_count": 3, "archetype_sequence": ["creator"], "domain_paths": ["tech"], "total_work_items": 1}
    assert are_structurally_similar(fp_a, fp_b) is False


def test_low_archetype_similarity():
    fp_a = {
        "milestone_count": 2,
        "archetype_sequence": ["creator", "analyst"],
        "domain_paths": ["tech"],
        "total_work_items": 2,
    }
    fp_b = {
        "milestone_count": 2,
        "archetype_sequence": ["executor", "sentinel"],
        "domain_paths": ["tech"],
        "total_work_items": 2,
    }
    assert are_structurally_similar(fp_a, fp_b) is False


def test_find_clusters_with_3_similar():
    """3+ structurally similar initiatives form a cluster."""
    ms = [_make_milestone([_make_wi("creator"), _make_wi("analyst")])]
    inits = [
        _make_initiative("A", ms),
        _make_initiative("B", ms),
        _make_initiative("C", ms),
    ]
    clusters = find_clusters(inits)
    assert len(clusters) == 1
    assert len(clusters[0]) == 3


def test_find_clusters_no_false_positive():
    """2 similar initiatives do not form a cluster."""
    ms = [_make_milestone([_make_wi("creator")])]
    inits = [
        _make_initiative("A", ms),
        _make_initiative("B", ms),
    ]
    clusters = find_clusters(inits)
    assert len(clusters) == 0


def test_extract_template_draft():
    ms = [_make_milestone([_make_wi("creator"), _make_wi("analyst")])]
    cluster = [_make_initiative("A", ms), _make_initiative("B", ms), _make_initiative("C", ms)]
    draft = extract_template_draft(cluster)
    assert "Auto-suggested" in draft["name"]
    assert len(draft["source_initiatives"]) == 3
    assert len(draft["milestones"]) == 1


def test_jaccard_identical():
    assert jaccard_similarity(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_jaccard_no_overlap():
    assert jaccard_similarity(["a", "b"], ["c", "d"]) == 0.0


def test_jaccard_partial():
    sim = jaccard_similarity(["a", "b", "c"], ["a", "b", "d"])
    assert 0.4 < sim < 0.6  # 2/4 = 0.5
