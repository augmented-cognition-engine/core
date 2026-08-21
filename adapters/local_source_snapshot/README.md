# ace-local-source-snapshot

Installable **`source_snapshot` capability provider** for ACE. It implements the public
`SourceSnapshotProvider` port from ace-core and registers itself under the
`ace.source_snapshot_providers` entry-point group as `local_source_snapshot`, so a host
registry discovers it fail-closed once the package is installed. The naked kernel without
this package loads no snapshot provider.

```python
from ace_local_source_snapshot import LocalSourceSnapshotProvider
from ace.application import SourceSnapshotRequestV1Alpha1

provider = LocalSourceSnapshotProvider()
request = SourceSnapshotRequestV1Alpha1(
    authorized_root="/authorized/notes",
    include=("**/*.md",),
    exclude=("drafts/**",),
)
acquired = await provider.snapshot(request)  # -> tuple[AcquiredLocalFile, ...]
```

## Identity

The provider declares an exact `CapabilityArtifactIdentityV1Alpha1`:

| Field | Value |
|-------|-------|
| `capability` | `source_snapshot` |
| `contract` | `ace.source.snapshot/v1alpha1` |
| `implementation_id` | `local_source_snapshot` |
| `implementation_version` | `0.1.0` |
| `artifact_digest` | `sha256:` digest of `provider.py`'s exact bytes |

Registration revalidates this identity before a host registry accepts the implementation.

## Boundary

`snapshot(request)` first revalidates the request from its exact model dump, then only calls
ace-core's governed `acquire_local_folder` with the `source_units_for` normalizer dispatch
from ace-local-source-normalizers. This package owns no filesystem traversal, scope
enforcement, digesting, or format logic — all of that stays behind the governed acquisition
port. It reads only the already-authorized local root named by the request, carries no
authority material, and performs no admission or recording of its own.

## Development

The package depends on ace-core and ace-local-source-normalizers only, and is exercised by
the provider contract and registry tests in the ace-core repository.
