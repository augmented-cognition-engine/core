from __future__ import annotations

import pytest
from pydantic import ValidationError

from ace.application import (
    SOURCE_SNAPSHOT_CAPABILITY,
    SOURCE_SNAPSHOT_CONTRACT,
    SOURCE_SNAPSHOT_REQUEST_VERSION,
    SourceSnapshotRequestV1Alpha1,
    validate_source_snapshot_provider_registration,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1

pytestmark = pytest.mark.unit


def _request(**overrides) -> SourceSnapshotRequestV1Alpha1:
    material = {
        "authorized_root": "/authorized/notes",
        "include": ("**/*.md", "**/*.csv"),
        "exclude": ("drafts/**",),
    }
    material.update(overrides)
    return SourceSnapshotRequestV1Alpha1(**material)


class _Provider:
    artifact_identity = CapabilityArtifactIdentityV1Alpha1(
        capability=SOURCE_SNAPSHOT_CAPABILITY,
        contract=SOURCE_SNAPSHOT_CONTRACT,
        implementation_id="fixture_snapshot_provider",
        implementation_version="1.0.0",
        artifact_digest="sha256:" + "b" * 64,
    )

    async def snapshot(self, request):
        del request
        raise AssertionError("contract tests never take a snapshot")


def test_capability_names_match_the_pack_requirement() -> None:
    assert SOURCE_SNAPSHOT_CAPABILITY == "source_snapshot"
    assert SOURCE_SNAPSHOT_CONTRACT == "ace.source.snapshot/v1alpha1"


def test_request_derives_deterministic_identity_over_sorted_patterns() -> None:
    request = _request(include=("**/*.md", "**/*.csv"))
    reordered = _request(include=("**/*.csv", "**/*.md"))

    assert request.contract == SOURCE_SNAPSHOT_REQUEST_VERSION
    assert request.include == ("**/*.csv", "**/*.md")
    assert request.request_id is not None and request.request_id.startswith("source_snapshot_request:")
    assert request.request_digest is not None and request.request_digest.startswith("sha256:")
    assert (reordered.request_id, reordered.request_digest) == (request.request_id, request.request_digest)

    revalidated = SourceSnapshotRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
    assert revalidated == request


def test_request_rejects_a_supplied_identity_that_does_not_match_its_material() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="identity"):
        _request(request_id=request.request_id, request_digest="sha256:" + "0" * 64)
    with pytest.raises(ValidationError, match="identity"):
        _request(authorized_root="/authorized/other", request_id=request.request_id)


def test_request_requires_nonempty_include_and_unique_bounded_patterns() -> None:
    with pytest.raises(ValidationError):
        _request(include=())
    with pytest.raises(ValidationError, match="unique"):
        _request(include=("**/*.md", "**/*.md"))
    with pytest.raises(ValidationError, match="unique"):
        _request(exclude=("drafts/**", "drafts/**"))
    with pytest.raises(ValidationError, match="nonempty"):
        _request(include=("",))
    with pytest.raises(ValidationError):
        _request(authorized_root="")


def test_request_is_frozen_strict_and_carries_no_authority_material() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        request.authorized_root = "/authorized/elsewhere"
    with pytest.raises(ValidationError):
        _request(grant_ref="authority_grant:anything")
    assert set(SourceSnapshotRequestV1Alpha1.model_fields) == {
        "contract",
        "authorized_root",
        "include",
        "exclude",
        "request_id",
        "request_digest",
    }


def test_provider_registration_revalidates_the_exact_artifact_identity() -> None:
    artifact = validate_source_snapshot_provider_registration(_Provider())
    assert artifact == _Provider.artifact_identity
    assert artifact is not _Provider.artifact_identity


def test_provider_registration_rejects_the_wrong_capability_or_contract() -> None:
    class _WrongCapability(_Provider):
        artifact_identity = _Provider.artifact_identity.model_copy(update={"capability": "other_capability"})

    class _WrongContract(_Provider):
        artifact_identity = _Provider.artifact_identity.model_copy(update={"contract": "ace.source.other/v1alpha1"})

    with pytest.raises(ValueError, match="wrong capability contract"):
        validate_source_snapshot_provider_registration(_WrongCapability())
    with pytest.raises(ValueError, match="wrong capability contract"):
        validate_source_snapshot_provider_registration(_WrongContract())


def test_provider_registration_rejects_missing_identity_and_sync_snapshot() -> None:
    class _NoIdentity:
        async def snapshot(self, request):
            del request

    class _SyncSnapshot(_Provider):
        def snapshot(self, request):
            del request

    with pytest.raises(ValueError, match="artifact identity"):
        validate_source_snapshot_provider_registration(_NoIdentity())
    with pytest.raises(ValueError, match="async snapshot"):
        validate_source_snapshot_provider_registration(_SyncSnapshot())
