# tests/test_clearance.py


def test_open_clearance_visible_to_all():
    from core.engine.flow.clearance import is_visible

    assert is_visible("open", task_domain="architecture", task_specialty=None, insight_domain="security") is True


def test_domain_clearance_visible_within_domain():
    from core.engine.flow.clearance import is_visible

    assert is_visible("domain", task_domain="security", task_specialty=None, insight_domain="security") is True


def test_domain_clearance_hidden_across_domains():
    from core.engine.flow.clearance import is_visible

    assert is_visible("domain", task_domain="architecture", task_specialty=None, insight_domain="security") is False


def test_sealed_visible_within_specialty():
    from core.engine.flow.clearance import is_visible

    assert (
        is_visible(
            "sealed",
            task_domain="security",
            task_specialty="specialty:contracts",
            insight_domain="security",
            insight_specialty="specialty:contracts",
        )
        is True
    )


def test_sealed_hidden_across_specialties():
    from core.engine.flow.clearance import is_visible

    assert (
        is_visible(
            "sealed",
            task_domain="security",
            task_specialty="specialty:ip",
            insight_domain="security",
            insight_specialty="specialty:contracts",
        )
        is False
    )


def test_restricted_treated_as_domain_in_phase2b():
    from core.engine.flow.clearance import is_visible

    assert is_visible("restricted", task_domain="security", task_specialty=None, insight_domain="security") is True
    assert is_visible("restricted", task_domain="architecture", task_specialty=None, insight_domain="security") is False


def test_clearance_filter_sql():
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause(task_domain="architecture", task_specialty=None)
    assert "clearance = 'open'" in clause
    assert "domain" in clause
    assert "restricted" in clause
    assert params["task_domain"] == "architecture"


def test_synaptic_only_open():
    from core.engine.flow.clearance import is_visible_via_synapse

    assert is_visible_via_synapse("open") is True
    assert is_visible_via_synapse("domain") is False
    assert is_visible_via_synapse("restricted") is False
    assert is_visible_via_synapse("sealed") is False
