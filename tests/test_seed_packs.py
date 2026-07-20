def test_seed_structure_has_all_disciplines():
    from core.engine.product.seed_packs import ALL_DISCIPLINES, SEED_STRUCTURE

    for dim in ALL_DISCIPLINES:
        assert dim in SEED_STRUCTURE, f"Missing discipline: {dim}"


def test_each_discipline_has_specialties():
    from core.engine.product.seed_packs import SEED_STRUCTURE

    for dim, config in SEED_STRUCTURE.items():
        assert "discipline" in config
        assert "perspective" in config
        assert "specialties" in config
        assert "applies_to" in config
        assert len(config["specialties"]) >= 5, f"{dim} has fewer than 5 specialties — must meet quality template"


def test_no_duplicate_specialty_slugs():
    from core.engine.product.seed_packs import get_all_specialties

    all_slugs = get_all_specialties()
    assert len(all_slugs) == len(set(all_slugs)), "Duplicate specialty slugs found"


def test_get_disciplines_for_product_type():
    from core.engine.product.seed_packs import get_disciplines_for_product_type

    web = get_disciplines_for_product_type("web")
    cli = get_disciplines_for_product_type("cli")
    assert len(web) >= 16  # web apps get almost all disciplines
    assert len(cli) < len(web)  # CLI tools get fewer
    assert "ux" in web
    assert "ux" not in cli


def test_audit_quality_all_passing():
    from core.engine.product.seed_packs import audit_quality

    result = audit_quality()
    assert result["failing"] == [], f"Disciplines below quality bar: {result['failing']}"
    assert len(result["passing"]) == 24  # includes marketing (added on the B2B marketing branch)
    assert result["total_specialties"] >= 146


def test_audit_quality_structure():
    from core.engine.product.seed_packs import SEED_STRUCTURE, audit_quality

    result = audit_quality()
    assert set(result["detail"].keys()) == set(SEED_STRUCTURE.keys())
    for name, info in result["detail"].items():
        assert "specialty_count" in info
        assert "meets_minimum" in info
        assert info["specialty_count"] == len(SEED_STRUCTURE[name]["specialties"])
