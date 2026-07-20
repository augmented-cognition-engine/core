from core.engine.product.pillars import LEGACY_DIM_TO_PILLAR, PILLARS, Pillar, aggregate_to_pillars


def test_seven_pillars():
    assert len(PILLARS) == 7
    assert PILLARS[0] == Pillar.EXPERIENCE
    assert PILLARS[-1] == Pillar.TRUST


def test_legacy_mapping_covers_all_dimensions():
    expected_dims = {
        "ux",
        "accessibility",
        "api_design",
        "integration",
        "data_modeling",
        "business_logic",
        "error_handling",
        "data",
        "versioning",
        "observability",
        "deployment",
        "devops",
        "performance",
        "configuration",
        "testing",
        "documentation",
        "code_conventions",
        "dependency_management",
        "architecture",
        "security",
    }
    assert set(LEGACY_DIM_TO_PILLAR.keys()) >= expected_dims


def test_aggregate_to_pillars_simple_average():
    dim_scores = {
        "ux": 0.8,
        "accessibility": 0.6,
        "security": 0.5,
        "testing": 0.4,
    }
    pillar_scores = aggregate_to_pillars(dim_scores)
    # Experience contains ux + accessibility -> 0.7
    assert abs(pillar_scores[Pillar.EXPERIENCE] - 0.7) < 0.01
    # Trust contains security -> 0.5
    assert abs(pillar_scores[Pillar.TRUST] - 0.5) < 0.01
    # Evolution contains testing -> 0.4
    assert abs(pillar_scores[Pillar.EVOLUTION] - 0.4) < 0.01


def test_aggregate_handles_empty_pillar():
    pillar_scores = aggregate_to_pillars({"ux": 0.5})
    assert Pillar.OPERATIONS in pillar_scores
    assert pillar_scores[Pillar.OPERATIONS] == 0.0  # no contributing dims
