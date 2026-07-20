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
