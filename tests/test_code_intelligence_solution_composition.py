from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from types import SimpleNamespace

import pytest

from ace.application import (
    IntelligenceResourceKind,
    IntelligenceResourceQueryV1Alpha1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourcePageState,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.code_intelligence.solution import CodeIntelligenceSolution
from core.engine.core import intelligence_resource_plane as host
from core.engine.extensions import loader, registry
from core.engine.version import VERSION

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _expected_solution_version() -> str:
    """Mirror the solution's own installed-metadata-then-source resolution.

    A worktree may run against an installed distribution built from a different
    revision, so pinning a literal here would assert the build environment
    rather than the binding under test.
    """

    try:
        return version("ace-core")
    except PackageNotFoundError:
        return VERSION


def test_code_solution_version_is_bound_to_the_installed_core_version() -> None:
    assert CodeIntelligenceSolution.version == _expected_solution_version()


def _definition(*, name: str, kind: str, factory):
    return SimpleNamespace(
        extension_id="test-solution",
        extension_version="1.0.0",
        provider_name=name,
        supported_kinds=(kind,),
        factory=factory,
    )


def _query(kind: IntelligenceResourceKind) -> IntelligenceResourceQueryV1Alpha1:
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id="product:test",
        actor_ref="principal:test",
        authentication_receipt_ref="authentication_receipt:test",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
    )
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=context,
        product_id=context.product_id,
        authority_grant_ref="authority_grant:test",
        resource_kinds=(kind,),
        as_of=NOW,
        available_at=NOW,
        page_size=10,
    )


@pytest.mark.asyncio
async def test_installed_code_solution_contributes_existing_semantic_revision_kind(monkeypatch) -> None:
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    monkeypatch.setattr(loader, "_ensured", True)
    CodeIntelligenceSolution().register(
        registry.Registry(
            extension_id=CodeIntelligenceSolution.name, extension_version=CodeIntelligenceSolution.version
        )
    )

    definitions = registry.registered_intelligence_resource_projection_providers()
    assert [(item.extension_id, item.extension_version, item.provider_name) for item in definitions] == [
        ("code-intelligence", _expected_solution_version(), "atrium-code-lens")
    ]
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())
    assert IntelligenceResourceKind.SEMANTIC_REVISION in reader.supported_kinds
    assert type(reader.contributors[-1]).__name__ == "_InstalledIntelligenceResourceProjectionReader"
    batch = await reader.read(query=_query(IntelligenceResourceKind.SEMANTIC_REVISION), after=None, limit=10)
    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert batch.degraded_reason_refs == ()


@pytest.mark.asyncio
async def test_naked_kernel_omits_code_provider_and_reports_semantic_revision_unsupported(monkeypatch) -> None:
    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    monkeypatch.setattr(loader, "_loaded", set())
    monkeypatch.setattr(loader, "_ensured", False)

    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    assert registry.registered_intelligence_resource_projection_providers() == ()
    assert IntelligenceResourceKind.SEMANTIC_REVISION not in reader.supported_kinds
    batch = await reader.read(
        query=SimpleNamespace(resource_kinds=(IntelligenceResourceKind.SEMANTIC_REVISION,)),
        after=None,
        limit=1,
    )
    assert batch.records == ()
    assert batch.degraded_reason_refs == ("degraded_reason:unsupported-semantic_revision",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory",
    [
        lambda records: object(),
        lambda records: SimpleNamespace(
            supported_kinds={IntelligenceResourceKind.SEMANTIC_REVISION}, read=lambda: None
        ),
        lambda records: SimpleNamespace(
            supported_kinds=frozenset({IntelligenceResourceKind.ACTION}), read=lambda: None
        ),
    ],
)
async def test_malformed_installed_provider_degrades_only_its_claimed_kind(monkeypatch, factory) -> None:
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="malformed", kind="semantic_revision", factory=factory),),
    )

    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())
    batch = await reader.read(query=_query(IntelligenceResourceKind.SEMANTIC_REVISION), after=None, limit=10)

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert len(batch.degraded_reason_refs) == 1
    assert batch.degraded_reason_refs[0].startswith(
        "degraded_reason:projection-provider-unavailable:semantic_revision:"
    )


@pytest.mark.asyncio
async def test_broken_provider_is_lazy_and_does_not_poison_unrelated_core_kind(monkeypatch) -> None:
    calls = 0

    def broken(_records):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="broken", kind="semantic_revision", factory=broken),),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())
    assert calls == 0

    unrelated = await reader.read(query=_query(IntelligenceResourceKind.AGENT), after=None, limit=10)
    assert unrelated.state is IntelligenceResourcePageState.COMPLETE
    assert unrelated.degraded_reason_refs == ()
    assert calls == 0

    claimed = await reader.read(query=_query(IntelligenceResourceKind.SEMANTIC_REVISION), after=None, limit=10)
    assert claimed.state is IntelligenceResourcePageState.DEGRADED
    assert calls == 1


def test_valid_overlapping_kind_claims_still_fail_closed(monkeypatch) -> None:

    overlapping = SimpleNamespace(
        supported_kinds=frozenset({IntelligenceResourceKind.AGENT}),
        read=lambda **kwargs: None,
    )
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="overlap", kind="agent", factory=lambda records: overlapping),),
    )
    with pytest.raises(host.IntelligenceResourceProjectionCompositionError, match="overlapping"):
        host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())


@pytest.mark.asyncio
async def test_unknown_kind_declaration_is_ignored_without_constructing_provider(monkeypatch) -> None:
    def must_not_construct(_records):
        raise AssertionError("unknown provider kind must not be constructed")

    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="future-kind", kind="not_a_public_kind", factory=must_not_construct),),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    batch = await reader.read(query=_query(IntelligenceResourceKind.AGENT), after=None, limit=10)
    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert batch.degraded_reason_refs == ()


def test_unknown_kind_does_not_hide_an_overlapping_valid_kind(monkeypatch) -> None:
    definition = _definition(name="mixed", kind="agent", factory=lambda records: records)
    definition.supported_kinds = ("not_a_public_kind", "agent")
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (definition,),
    )

    with pytest.raises(host.IntelligenceResourceProjectionCompositionError, match="overlapping"):
        host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())


def test_two_extensions_can_share_local_name_but_overlapping_kinds_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    monkeypatch.setattr(loader, "_ensured", True)

    class Provider:
        supported_kinds = frozenset({IntelligenceResourceKind.SEMANTIC_REVISION})

        async def read(self, **kwargs):
            raise AssertionError("overlap must fail before query")

    for extension_id in ("zeta", "alpha"):
        registry.Registry(
            extension_id=extension_id, extension_version="1.0.0"
        ).register_intelligence_resource_projection_provider(
            "shared-reader",
            lambda records: Provider(),
            supported_kinds=frozenset({"semantic_revision"}),
        )

    assert [item.extension_id for item in registry.registered_intelligence_resource_projection_providers()] == [
        "alpha",
        "zeta",
    ]
    with pytest.raises(host.IntelligenceResourceProjectionCompositionError, match="overlapping"):
        host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())


@pytest.mark.asyncio
async def test_provider_read_exception_returns_bounded_degradation(monkeypatch) -> None:
    class BrokenReadProvider:
        supported_kinds = frozenset({IntelligenceResourceKind.SEMANTIC_REVISION})

        async def read(self, **kwargs):
            raise RuntimeError("read failed")

    provider = BrokenReadProvider()
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="broken-read", kind="semantic_revision", factory=lambda records: provider),),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    batch = await reader.read(
        query=_query(IntelligenceResourceKind.SEMANTIC_REVISION),
        after=None,
        limit=1,
    )
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert len(batch.degraded_reason_refs) == 1
    assert "read failed" not in batch.degraded_reason_refs[0]


@pytest.mark.asyncio
async def test_provider_malformed_batch_cannot_escape_as_a_host_error(monkeypatch) -> None:
    class MalformedBatchProvider:
        supported_kinds = frozenset({IntelligenceResourceKind.SEMANTIC_REVISION})

        async def read(self, **kwargs):
            return host.IntelligenceResourceProjectionBatch(records=(object(),))

    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (
            _definition(
                name="malformed-batch",
                kind="semantic_revision",
                factory=lambda records: MalformedBatchProvider(),
            ),
        ),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    batch = await reader.read(query=_query(IntelligenceResourceKind.SEMANTIC_REVISION), after=None, limit=1)
    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert len(batch.degraded_reason_refs) == 1


# ---------------------------------------------------------------------------
# Installed projection-provider isolation
#
# The generic resource-plane service already rejects a batch that crosses
# product, kind, temporal, subject, ordering, or page bounds — but it rejects
# the *whole page*, which would let one optional installed provider take
# unrelated Core kinds down with it. The host wrapper therefore enforces the
# same invariants per provider and degrades only that provider's claimed kinds.
# ---------------------------------------------------------------------------

FINGERPRINT_PREFIX = "degraded_reason:projection-provider-unavailable:semantic_revision:"


def _reference(
    *,
    kind: IntelligenceResourceKind = IntelligenceResourceKind.SEMANTIC_REVISION,
    product_id: str = "product:test",
    resource_id: str = "atrium_code_lens_family:one",
    revision: int = 1,
    as_of: datetime = NOW,
    available_at: datetime = NOW,
) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=product_id,
        resource_kind=kind,
        resource_id=resource_id,
        resource_digest="sha256:" + "e" * 64,
        resource_contract="ace.code-intelligence.atrium-code-lens-revision/v1alpha1",
        revision=revision,
        as_of=as_of,
        available_at=available_at,
    )


def _record(*, subject_refs: tuple[str, ...] = ("repository:test",), **kwargs) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_reference(**kwargs),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Atrium Code lens revision 1",
        subject_refs=subject_refs,
    )


def _subject_query(kind: IntelligenceResourceKind, subject_refs: tuple[str, ...]):
    query = _query(kind)
    return query.model_copy(update={"subject_refs": subject_refs})


def _provider_returning(batch):
    class _Provider:
        supported_kinds = frozenset({IntelligenceResourceKind.SEMANTIC_REVISION})

        async def read(self, **kwargs):
            return batch

    return lambda _records: _Provider()


async def _read_installed(monkeypatch, batch, *, query=None, limit: int = 10):
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="rogue", kind="semantic_revision", factory=_provider_returning(batch)),),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())
    return await reader.read(
        query=query or _query(IntelligenceResourceKind.SEMANTIC_REVISION),
        after=None,
        limit=limit,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "records"),
    [
        (
            "oversized_count",
            tuple(_record(resource_id=f"atrium_code_lens_family:{index:03d}") for index in range(11)),
        ),
        ("cross_product", (_record(product_id="product:other"),)),
        ("cross_kind", (_record(kind=IntelligenceResourceKind.AGENT),)),
        (
            "cross_time_as_of",
            (_record(as_of=NOW + timedelta(minutes=1), available_at=NOW + timedelta(minutes=1)),),
        ),
        (
            "unstable_ordering",
            (
                _record(resource_id="atrium_code_lens_family:zeta"),
                _record(resource_id="atrium_code_lens_family:alpha"),
            ),
        ),
        (
            "duplicate_ordering",
            (_record(), _record()),
        ),
        ("malformed_record_type", (object(),)),
        ("unbounded_records", (item for item in ())),
    ],
)
async def test_provider_records_outside_the_exact_request_degrade_only_its_kind(
    monkeypatch,
    label: str,
    records,
) -> None:
    batch = host.IntelligenceResourceProjectionBatch(records=records)

    result = await _read_installed(monkeypatch, batch, limit=10)

    assert result.records == (), label
    assert result.state is IntelligenceResourcePageState.DEGRADED, label
    assert result.degraded_reason_refs == tuple(
        item for item in result.degraded_reason_refs if item.startswith(FINGERPRINT_PREFIX)
    )
    assert len(result.degraded_reason_refs) == 1, label


@pytest.mark.asyncio
async def test_provider_record_outside_the_subject_filter_degrades_only_its_kind(monkeypatch) -> None:
    batch = host.IntelligenceResourceProjectionBatch(records=(_record(subject_refs=("repository:unrelated",)),))

    result = await _read_installed(
        monkeypatch,
        batch,
        query=_subject_query(IntelligenceResourceKind.SEMANTIC_REVISION, ("repository:requested",)),
    )

    assert result.records == ()
    assert result.state is IntelligenceResourcePageState.DEGRADED
    assert len(result.degraded_reason_refs) == 1
    assert result.degraded_reason_refs[0].startswith(FINGERPRINT_PREFIX)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "reasons"),
    [
        ("non_string", (1,)),
        ("empty_string", ("",)),
        ("duplicate", ("degraded_reason:a", "degraded_reason:a")),
        ("oversized_count", tuple(f"degraded_reason:{index}" for index in range(9))),
        ("oversized_item", ("d" * 201,)),
        ("oversized_total", tuple("d" * 200 + f"{index:02d}" for index in range(6))),
        ("unbounded_type", (item for item in ("degraded_reason:a",))),
        ("raw_provider_text", ("connection failed for postgres://user:hunter2@db/prod",) * 2),
        (
            "unique_raw_provider_text",
            ("connection failed for postgres://user:hunter2@db/prod",),
        ),
    ],
)
async def test_provider_degraded_references_are_bounded_and_never_raw_text(
    monkeypatch,
    label: str,
    reasons,
) -> None:
    batch = host.IntelligenceResourceProjectionBatch(
        records=(),
        state=IntelligenceResourcePageState.DEGRADED,
        degraded_reason_refs=reasons,
    )

    result = await _read_installed(monkeypatch, batch)

    assert result.records == (), label
    assert result.state is IntelligenceResourcePageState.DEGRADED, label
    assert len(result.degraded_reason_refs) == 1, label
    assert result.degraded_reason_refs[0].startswith(FINGERPRINT_PREFIX), label
    assert "hunter2" not in result.degraded_reason_refs[0]
    assert len(result.degraded_reason_refs[0]) <= host.MAX_INSTALLED_PROVIDER_DEGRADED_REASON_CHARS


@pytest.mark.asyncio
async def test_provider_inside_the_exact_request_still_succeeds(monkeypatch) -> None:
    batch = host.IntelligenceResourceProjectionBatch(records=(_record(),))

    result = await _read_installed(monkeypatch, batch)

    assert result.state is IntelligenceResourcePageState.COMPLETE
    assert result.degraded_reason_refs == ()
    assert [item.reference.resource_id for item in result.records] == ["atrium_code_lens_family:one"]


@pytest.mark.asyncio
async def test_violating_provider_never_poisons_an_unrelated_core_kind(monkeypatch) -> None:
    batch = host.IntelligenceResourceProjectionBatch(records=(_record(product_id="product:other"),))
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="rogue", kind="semantic_revision", factory=_provider_returning(batch)),),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    unrelated = await reader.read(query=_query(IntelligenceResourceKind.AGENT), after=None, limit=10)
    assert unrelated.state is IntelligenceResourcePageState.COMPLETE
    assert unrelated.degraded_reason_refs == ()

    combined_query = _query(IntelligenceResourceKind.AGENT).model_copy(
        update={
            "resource_kinds": (
                IntelligenceResourceKind.AGENT,
                IntelligenceResourceKind.SEMANTIC_REVISION,
            )
        }
    )
    combined = await reader.read(query=combined_query, after=None, limit=10)
    assert combined.state is IntelligenceResourcePageState.DEGRADED
    assert len(combined.degraded_reason_refs) == 1
    assert combined.degraded_reason_refs[0].startswith(FINGERPRINT_PREFIX)
    assert not any("agent" in item for item in combined.degraded_reason_refs)


@pytest.mark.asyncio
async def test_unique_valid_raw_batch_reason_never_reaches_an_unrelated_kind(monkeypatch) -> None:
    """A single, count/length-valid provider reason is still never forwarded.

    Bounded validation alone (count, length, uniqueness) is not sufficient to
    let a provider's own text through: even one unique, well-formed reason
    must be replaced by the deterministic host reason, and that replacement
    must stay scoped to the provider's claimed kind when the query also asks
    for an unrelated Core kind.
    """

    raw = "connection failed for postgres://user:hunter2@db/prod"
    batch = host.IntelligenceResourceProjectionBatch(
        records=(),
        state=IntelligenceResourcePageState.DEGRADED,
        degraded_reason_refs=(raw,),
    )
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (_definition(name="rogue", kind="semantic_revision", factory=_provider_returning(batch)),),
    )
    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    combined_query = _query(IntelligenceResourceKind.AGENT).model_copy(
        update={
            "resource_kinds": (
                IntelligenceResourceKind.AGENT,
                IntelligenceResourceKind.SEMANTIC_REVISION,
            )
        }
    )
    combined = await reader.read(query=combined_query, after=None, limit=10)

    assert combined.state is IntelligenceResourcePageState.DEGRADED
    assert len(combined.degraded_reason_refs) == 1
    assert combined.degraded_reason_refs[0].startswith(FINGERPRINT_PREFIX)
    assert "hunter2" not in combined.degraded_reason_refs[0]
    assert not any("agent" in item for item in combined.degraded_reason_refs)

    unrelated = await reader.read(query=_query(IntelligenceResourceKind.AGENT), after=None, limit=10)
    assert unrelated.state is IntelligenceResourcePageState.COMPLETE
    assert unrelated.degraded_reason_refs == ()


@pytest.mark.asyncio
async def test_record_level_degraded_reason_refs_are_never_forwarded(monkeypatch) -> None:
    """A record's own degraded_reason_refs is provider material too.

    Even a single reference-pattern-valid token on one record must be replaced
    with the deterministic host reason for that record's exact kind — never
    forwarded, whether or not the batch itself is otherwise COMPLETE.
    """

    raw_but_pattern_valid = "internal-diagnostic-token-for-user-hunter2-db-prod"
    record = IntelligenceResourceRecordV1Alpha1(
        reference=_reference(),
        availability=IntelligenceResourceAvailability.DEGRADED,
        title="Atrium Code lens revision 1",
        subject_refs=("repository:test",),
        degraded_reason_refs=(raw_but_pattern_valid,),
    )
    batch = host.IntelligenceResourceProjectionBatch(records=(record,))

    result = await _read_installed(monkeypatch, batch)

    assert result.state is IntelligenceResourcePageState.COMPLETE
    assert len(result.records) == 1
    forwarded = result.records[0].degraded_reason_refs
    assert len(forwarded) == 1
    assert forwarded[0].startswith(FINGERPRINT_PREFIX)
    assert "hunter2" not in forwarded[0]
    assert forwarded[0] != raw_but_pattern_valid


def test_duplicate_kind_declaration_within_one_provider_is_deduplicated(monkeypatch) -> None:
    definition = _definition(name="duplicated", kind="semantic_revision", factory=lambda records: records)
    definition.supported_kinds = ("semantic_revision", "semantic_revision")
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (definition,),
    )

    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    assert IntelligenceResourceKind.SEMANTIC_REVISION in reader.supported_kinds


@pytest.mark.parametrize(
    "declared",
    ["semantic_revision", ("semantic_revision",) * 33, (), None],
)
def test_malformed_kind_declarations_are_ignored_before_live_use(monkeypatch, declared) -> None:
    def must_not_construct(_records):
        raise AssertionError("malformed provider declaration must not be constructed")

    definition = _definition(name="malformed-kinds", kind="semantic_revision", factory=must_not_construct)
    definition.supported_kinds = declared
    monkeypatch.setattr(
        host,
        "registered_intelligence_resource_projection_providers",
        lambda: (definition,),
    )

    reader = host.intelligence_resource_projection_reader(InMemoryImmutableRecordStore())

    assert IntelligenceResourceKind.SEMANTIC_REVISION not in reader.supported_kinds
