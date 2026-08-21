from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

from ace.application.installed_pack_artifacts import (
    InstalledCompiledPackArtifactResolver,
    InstalledPackArtifactError,
    discover_installed_domain_pack_previews,
)
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.packs.compiler import compile_pack_document_with_report

pytestmark = pytest.mark.unit


def _encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _pack(*, pack_id: str = "neutral_measurement", expected_material: bool = True) -> dict[str, bytes]:
    modules = {
        "modules/ontology.json": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "measurement",
                    "attributes": [{"attribute_id": "value", "value_type": "number", "required": True}],
                }
            ],
            "relation_types": [],
        },
        "modules/detection.json": {
            "contract": "ace.intelligence.detection/v1alpha1",
            "module_id": "detection",
            "numeric_delta_rules": [
                {
                    "detector_id": "value_change",
                    "entity_type_id": "measurement",
                    "attribute_id": "value",
                    "metric": "absolute_change",
                    "threshold": 5,
                    "direction": "any",
                    "shift_type": "value_changed",
                    "signal_type": "value_attention",
                }
            ],
        },
        "modules/synthesis.json": {
            "contract": "ace.intelligence.synthesis/v1alpha1",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "measurement_brief",
                    "brief_type": "measurement_update",
                    "display_name": "Measurement update",
                    "objective": "Explain the material change.",
                    "required_sections": ["summary"],
                }
            ],
        },
        "modules/personas.json": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [{"persona_id": "analyst", "display_name": "Analyst", "description": "Reviews."}],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "measurement_route",
                    "signal_type": "value_attention",
                    "persona_ids": ["analyst"],
                    "minimum_confidence": 0.5,
                    "brief_template_id": "measurement_brief",
                }
            ],
        },
    }
    refs = (
        ("ontology", "ace.intelligence.ontology/v1alpha1", "ontology_resource", ()),
        ("detection", "ace.intelligence.detection/v1alpha1", "detection_resource", ("ontology",)),
        ("synthesis", "ace.intelligence.synthesis/v1alpha1", "synthesis_resource", ()),
        ("personas", "ace.intelligence.personas/v1alpha1", "personas_resource", ("detection", "synthesis")),
    )
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1",
        "metadata": {"pack_id": pack_id, "version": "1.0.0", "display_name": "Neutral Measurement"},
        "compatibility": {
            "compiler_minimum": "ace.intelligence.pack-compiler/v1alpha1",
            "compiler_maximum_exclusive": "ace.intelligence.pack-compiler/v2",
            "intelligence_minimum": "ace.intelligence.runtime/v1alpha1",
            "intelligence_maximum_exclusive": "ace.intelligence.runtime/v2",
        },
        "resources": [
            {
                "resource_id": resource_id,
                "path": path,
                "digest": _digest(_encoded(modules[path])),
            }
            for path, (_, _, resource_id, _) in zip(modules, refs, strict=True)
        ],
        "modules": [
            {
                "module_id": module_id,
                "contract": contract,
                "resource_id": resource_id,
                "depends_on": depends_on,
            }
            for module_id, contract, resource_id, depends_on in refs
        ],
    }
    expected = [
        {
            "detector_id": "value_change",
            "entity_ref": "entity:measurement-one",
            "material": expected_material,
            **(
                {
                    "shift_type": "value_changed",
                    "signal_type": "value_attention",
                    "routing_rule_ids": ["measurement_route"],
                    "persona_ids": ["analyst"],
                    "template_ids": ["measurement_brief"],
                }
                if expected_material
                else {}
            ),
        }
    ]
    fixture = {
        "contract": "ace.intelligence.domain-pack-golden-fixture/v1",
        "fixture_id": f"{pack_id}_activation",
        "fixture_version": "1.0.0",
        "observations": [
            {
                "case_id": "material_change",
                "entity_type_id": "measurement",
                "entity_ref": "entity:measurement-one",
                "baseline_attributes_json": '{"value":10}',
                "current_attributes_json": '{"value":20}',
                "baseline_as_of": "2026-08-11T00:00:00Z",
                "current_as_of": "2026-08-11T01:00:00Z",
                "confidence": 0.9,
                "expected": expected,
            }
        ],
    }
    root = f"domain_packs/{pack_id}"
    return {
        f"{root}/manifest.json": _encoded(manifest),
        **{f"{root}/{path}": _encoded(value) for path, value in modules.items()},
        f"{root}/conformance/activation_golden_fixture.json": _encoded(fixture),
        f"{root}/conformance/manifest.json": b"not an installed Pack root",
        f"{root}/releases/v2/manifest.json": b"not an installed Pack root",
        f"{root}/__init__.py": b"raise RuntimeError('must never import inert pack')",
    }


@dataclass
class _Metadata:
    name: str

    def get(self, key: str):
        return self.name if key == "Name" else None


class _Distribution:
    def __init__(self, root: Path, name: str, resources: dict[str, bytes], *, version: str = "99.4.1") -> None:
        self.root = root
        self.metadata = _Metadata(name)
        self.version = version
        self.files = tuple(PurePosixPath(path) for path in resources)
        for relative, payload in resources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

    def locate_file(self, path) -> Path:
        return self.root / str(path)

    @property
    def entry_points(self):
        raise AssertionError("installed Pack discovery must never inspect or execute entry points")


def _reference(resources: dict[str, bytes], *, pack_id: str = "neutral_measurement") -> CompiledPackRefV1:
    root = f"domain_packs/{pack_id}"
    manifest_document = resources[f"{root}/manifest.json"]
    manifest = json.loads(manifest_document)
    pack = compile_pack_document_with_report(
        manifest_document,
        {item["path"]: resources[f"{root}/{item['path']}"] for item in manifest["resources"]},
    ).pack
    return CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )


def test_previews_exact_installed_manifest_without_loading_activation_material(tmp_path: Path) -> None:
    resources = _pack()
    resources.pop("domain_packs/neutral_measurement/conformance/activation_golden_fixture.json")
    distribution = _Distribution(tmp_path / "preview", "preview-pack", resources, version="4.2.0")

    previews = discover_installed_domain_pack_previews([distribution])

    assert len(previews) == 1
    preview = previews[0]
    assert preview.distribution == "preview-pack"
    assert preview.distribution_version == "4.2.0"
    assert preview.manifest.metadata.pack_id == "neutral_measurement"
    assert preview.manifest.metadata.version == "1.0.0"
    assert preview.manifest_digest == _digest(resources["domain_packs/neutral_measurement/manifest.json"])


@pytest.mark.asyncio
async def test_discovers_inert_pack_by_shape_and_resolves_all_exact_coordinates(tmp_path: Path) -> None:
    resources = _pack()
    distribution = _Distribution(tmp_path / "renamed", "anything-at-all", resources)

    first = InstalledCompiledPackArtifactResolver.discover([distribution])
    second = InstalledCompiledPackArtifactResolver.discover([distribution])
    exact = _reference(resources)
    artifact = await first.resolve_exact(reference=exact)
    rediscovered = await second.resolve_exact(reference=exact)

    assert artifact == rediscovered
    assert artifact is not None
    assert artifact.distribution == "anything-at-all"
    assert artifact.distribution_version == "99.4.1"
    assert artifact.pack.metadata.version == "1.0.0"
    assert artifact.conformance_receipts[0].passed is True
    assert artifact.conformance_receipts[0].compilation_result_id == artifact.compilation.result_id
    assert await first.load_exact(reference=exact) == artifact.pack
    assert (await first.resolve_exact(reference=exact)).conformance_receipts == artifact.conformance_receipts
    for field, value in (
        ("pack_id", "other_pack"),
        ("pack_version", "2.0.0"),
        ("compiled_pack_id", "pack_ir:" + "0" * 32),
        ("pack_digest", "sha256:" + "0" * 64),
    ):
        changed = exact.model_copy(update={field: value})
        assert await first.load_exact(reference=changed) is None


@pytest.mark.asyncio
async def test_exact_requested_pack_rejects_missing_malformed_or_failed_fixed_fixture(tmp_path: Path) -> None:
    missing = _pack()
    missing.pop("domain_packs/neutral_measurement/conformance/activation_golden_fixture.json")
    missing_resolver = InstalledCompiledPackArtifactResolver.discover(
        [_Distribution(tmp_path / "missing", "missing", missing)]
    )
    with pytest.raises(InstalledPackArtifactError, match="activation golden fixture"):
        await missing_resolver.resolve_exact(reference=_reference(missing))

    malformed = _pack()
    malformed["domain_packs/neutral_measurement/conformance/activation_golden_fixture.json"] = b"not-json"
    malformed_resolver = InstalledCompiledPackArtifactResolver.discover(
        [_Distribution(tmp_path / "malformed", "malformed", malformed)]
    )
    with pytest.raises(InstalledPackArtifactError, match="validation|conformance"):
        await malformed_resolver.resolve_exact(reference=_reference(malformed))

    failed = _pack(expected_material=False)
    failed_resolver = InstalledCompiledPackArtifactResolver.discover(
        [_Distribution(tmp_path / "failed", "failed", failed)]
    )
    with pytest.raises(InstalledPackArtifactError, match="conformance"):
        await failed_resolver.resolve_exact(reference=_reference(failed))


@pytest.mark.asyncio
async def test_unrelated_unactivatable_pack_does_not_block_exact_valid_resolution(tmp_path: Path) -> None:
    requested = _pack()
    unrelated = _pack(pack_id="unrelated_unready")
    unrelated.pop("domain_packs/unrelated_unready/conformance/activation_golden_fixture.json")
    distribution = _Distribution(tmp_path / "combined", "combined", {**requested, **unrelated})

    resolver = InstalledCompiledPackArtifactResolver.discover([distribution])
    artifact = await resolver.resolve_exact(reference=_reference(requested))

    assert artifact is not None
    assert artifact.pack.metadata.pack_id == "neutral_measurement"
    with pytest.raises(InstalledPackArtifactError, match="activation golden fixture"):
        await resolver.resolve_exact(reference=_reference(unrelated, pack_id="unrelated_unready"))


@pytest.mark.asyncio
async def test_rejects_requested_resource_substitution_and_indexes_duplicates_fail_closed(tmp_path: Path) -> None:
    substituted = _pack()
    substituted["domain_packs/neutral_measurement/modules/ontology.json"] += b" "
    substituted_resolver = InstalledCompiledPackArtifactResolver.discover(
        [_Distribution(tmp_path / "changed", "changed", substituted)]
    )
    with pytest.raises(InstalledPackArtifactError, match="compilation"):
        await substituted_resolver.resolve_exact(reference=_reference(_pack()))

    one = _Distribution(tmp_path / "one", "one", _pack())
    two = _Distribution(tmp_path / "two", "two", _pack())
    with pytest.raises(InstalledPackArtifactError, match="ambiguous"):
        InstalledCompiledPackArtifactResolver.discover([one, two])


@pytest.mark.asyncio
async def test_rejects_symlinked_requested_installed_material(tmp_path: Path) -> None:
    resources = _pack()
    distribution = _Distribution(tmp_path / "linked", "linked", resources)
    module = distribution.root / "domain_packs/neutral_measurement/modules/ontology.json"
    target = tmp_path / "outside.json"
    target.write_bytes(module.read_bytes())
    module.unlink()
    module.symlink_to(target)
    resolver = InstalledCompiledPackArtifactResolver.discover([distribution])
    with pytest.raises(InstalledPackArtifactError, match="symbolic link|escaped"):
        await resolver.resolve_exact(reference=_reference(resources))


@pytest.mark.asyncio
async def test_resolver_constructor_rejects_changed_compilation_or_conformance(tmp_path: Path) -> None:
    resources = _pack()
    discovered = InstalledCompiledPackArtifactResolver.discover([_Distribution(tmp_path / "exact", "exact", resources)])
    artifact = await discovered.resolve_exact(reference=_reference(resources))
    assert artifact is not None
    changed_compilation = artifact.compilation.model_copy(update={"pack_digest": "sha256:" + "0" * 64})
    with pytest.raises(InstalledPackArtifactError, match="validation|compilation"):
        InstalledCompiledPackArtifactResolver(
            (
                artifact.__class__(
                    distribution=artifact.distribution,
                    distribution_version=artifact.distribution_version,
                    manifest_resource_path=artifact.manifest_resource_path,
                    pack=artifact.pack,
                    compilation=changed_compilation,
                    conformance_receipts=artifact.conformance_receipts,
                ),
            )
        )

    changed_conformance = artifact.conformance_receipts[0].model_copy(update={"passed": False})
    with pytest.raises(InstalledPackArtifactError, match="validation|conformance"):
        InstalledCompiledPackArtifactResolver(
            (
                artifact.__class__(
                    distribution=artifact.distribution,
                    distribution_version=artifact.distribution_version,
                    manifest_resource_path=artifact.manifest_resource_path,
                    pack=artifact.pack,
                    compilation=artifact.compilation,
                    conformance_receipts=(changed_conformance,),
                ),
            )
        )


class _EnumeratedTwice(_Distribution):
    """importlib.metadata enumerates one dist-info once per duplicate sys.path entry."""

    def __init__(self, root: Path, name: str, resources: dict[str, bytes]) -> None:
        super().__init__(root, name, resources)
        self._path = root / f"{name}.dist-info"


@pytest.mark.asyncio
async def test_one_dist_info_enumerated_twice_is_not_a_duplicate_root(tmp_path: Path) -> None:
    """A duplicated sys.path entry makes importlib.metadata yield the same
    dist-info twice. That is one installed Pack, not two, and must index once;
    two genuinely different roots carrying the same Pack stay ambiguous."""

    resources = _pack()
    first = _EnumeratedTwice(tmp_path / "site", "ace-personal-intelligence-pack", resources)
    again = _EnumeratedTwice(tmp_path / "site", "ace-personal-intelligence-pack", resources)

    resolver = InstalledCompiledPackArtifactResolver.discover([first, again])
    artifact = await resolver.resolve_exact(reference=_reference(resources))
    assert artifact is not None
    assert artifact.distribution == "ace-personal-intelligence-pack"

    other_root = _EnumeratedTwice(tmp_path / "elsewhere", "ace-personal-intelligence-pack", resources)
    with pytest.raises(InstalledPackArtifactError, match="declared more than once|ambiguous"):
        InstalledCompiledPackArtifactResolver.discover([first, other_root])
