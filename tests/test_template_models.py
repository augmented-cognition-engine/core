# tests/test_template_models.py


def test_template_variable_valid():
    from core.engine.templates.models import TemplateVariable

    v = TemplateVariable(name="customer_name", type="string", prompt="Customer name?")
    assert v.name == "customer_name"
    assert v.default is None


def test_template_variable_with_default():
    from core.engine.templates.models import TemplateVariable

    v = TemplateVariable(name="quarter", type="string", prompt="Which quarter?", default="Q2 2026")
    assert v.default == "Q2 2026"


def test_template_work_item_valid():
    from core.engine.templates.models import TemplateWorkItem

    wi = TemplateWorkItem(
        title="Pull revenue data for {{customer_name}}",
        archetype="executor",
        mode="procedural",
        domain_path="business.finance.revenue",
    )
    assert "{{customer_name}}" in wi.title


def test_template_milestone_valid():
    from core.engine.templates.models import TemplateMilestone, TemplateWorkItem

    ms = TemplateMilestone(
        title="M1: {{customer_name}} data pull",
        done_criteria=["All revenue data pulled"],
        work_items=[
            TemplateWorkItem(
                title="Pull data", archetype="executor", mode="procedural", domain_path="business.finance"
            ),
        ],
    )
    assert len(ms.work_items) == 1
    assert len(ms.done_criteria) == 1


def test_template_valid():
    from core.engine.templates.models import Template, TemplateMilestone, TemplateVariable, TemplateWorkItem

    pb = Template(
        name="QBR Prep",
        description="Quarterly business review preparation",
        domain_path="business.operations",
        variables=[TemplateVariable(name="customer_name", type="string", prompt="Customer?")],
        milestones=[
            TemplateMilestone(
                title="M1: Data pull for {{customer_name}}",
                done_criteria=["Data pulled"],
                work_items=[
                    TemplateWorkItem(
                        title="Pull data", archetype="executor", mode="procedural", domain_path="business"
                    ),
                ],
            ),
        ],
    )
    assert pb.name == "QBR Prep"
    assert len(pb.variables) == 1
    assert len(pb.milestones) == 1


def test_template_produces_json_schema():
    from core.engine.templates.models import Template

    schema = Template.model_json_schema()
    assert schema["type"] == "object"
    assert "milestones" in schema.get("properties", {})
