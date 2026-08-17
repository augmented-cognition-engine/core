import pytest

import core.engine.extensions.registry as registry


def test_register_verify_check_appends_and_accessor_returns(monkeypatch):
    monkeypatch.setattr(registry, "_verify_checks", [])  # isolate the module-global store
    reg = registry.Registry()

    def _check(files):
        return [{"rule": "x", "severity": "enforced", "file": "a.py", "line": 1, "snippet": "x"}]

    reg.register_verify_check(_check)
    got = registry.registered_verify_checks()
    assert got == [_check]
    # accessor returns a COPY (mutating it must not corrupt the store)
    got.append(lambda f: [])
    assert len(registry.registered_verify_checks()) == 1


def test_projection_provider_registration_is_scoped_bounded_and_manifested(monkeypatch):
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    monkeypatch.setattr(registry, "_ensure_extensions_loaded", lambda: None)

    def factory(records):
        return records

    reg = registry.Registry(extension_id="code-intelligence", extension_version="1.0.3")

    reg.register_intelligence_resource_projection_provider(
        "atrium-code-lens",
        factory,
        supported_kinds=frozenset({"semantic_revision"}),
    )

    definitions = registry.registered_intelligence_resource_projection_providers()
    assert len(definitions) == 1
    assert definitions[0].factory is factory
    assert definitions[0].supported_kinds == ("semantic_revision",)
    assert registry.registered_intelligence_resource_projection_provider_manifests() == (
        {
            "extension_id": "code-intelligence",
            "extension_version": "1.0.3",
            "provider_name": "atrium-code-lens",
            "supported_kinds": ["semantic_revision"],
        },
    )


def test_projection_provider_registration_rejects_malformed_and_duplicate_entries(monkeypatch):
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    reg = registry.Registry(extension_id="solution", extension_version="1.0.0")

    with pytest.raises(RuntimeError, match="extension-scoped"):
        registry.Registry().register_intelligence_resource_projection_provider(
            "reader", lambda records: records, supported_kinds=frozenset({"semantic_revision"})
        )
    with pytest.raises(TypeError, match="factory must be callable"):
        reg.register_intelligence_resource_projection_provider(
            "reader", object(), supported_kinds=frozenset({"semantic_revision"})
        )
    for malformed in (set(), frozenset(), frozenset({"Not Generic"})):
        with pytest.raises(ValueError, match="nonempty immutable bounded set"):
            reg.register_intelligence_resource_projection_provider(
                "reader", lambda records: records, supported_kinds=malformed
            )

    reg.register_intelligence_resource_projection_provider(
        "reader", lambda records: records, supported_kinds=frozenset({"semantic_revision"})
    )
    with pytest.raises(RuntimeError, match="solution:reader.*already registered"):
        reg.register_intelligence_resource_projection_provider(
            "reader", lambda records: records, supported_kinds=frozenset({"semantic_revision"})
        )


def test_projection_provider_same_local_name_is_scoped_and_deterministic(monkeypatch):
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    monkeypatch.setattr(registry, "_ensure_extensions_loaded", lambda: None)
    for extension_id in ("zeta", "alpha"):
        registry.Registry(
            extension_id=extension_id, extension_version="1.0.0"
        ).register_intelligence_resource_projection_provider(
            "reader", lambda records: records, supported_kinds=frozenset({"semantic_revision"})
        )

    definitions = registry.registered_intelligence_resource_projection_providers()
    assert [(item.extension_id, item.provider_name) for item in definitions] == [
        ("alpha", "reader"),
        ("zeta", "reader"),
    ]


def test_projection_provider_registration_enforces_bounded_count(monkeypatch):
    monkeypatch.setattr(
        registry,
        "_intelligence_resource_projection_providers",
        {
            ("solution", f"provider-{index}"): object()
            for index in range(registry.MAX_INTELLIGENCE_RESOURCE_PROJECTION_PROVIDERS)
        },
    )
    reg = registry.Registry(extension_id="solution", extension_version="1.0.0")

    with pytest.raises(RuntimeError, match="limited to 32 entries"):
        reg.register_intelligence_resource_projection_provider(
            "overflow", lambda records: records, supported_kinds=frozenset({"semantic_revision"})
        )
