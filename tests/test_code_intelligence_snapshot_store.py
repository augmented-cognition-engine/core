from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

from core.engine.code_intelligence.contracts import RepositoryIndexIdentityV1Alpha1, stable_digest
from core.engine.code_intelligence.snapshot_store import (
    DurablePhase1IndexSnapshotV1Alpha1,
    DurablePhase1IndexStore,
    Phase1IndexGenerationConflict,
    Phase1IndexIdentityMismatch,
    Phase1IndexIntegrityError,
)
from core.engine.intelligence.graph_builder import GraphBuilder


def _repository(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "service.py").write_text(
        "from pkg.value import VALUE\n\ndef answer() -> int:\n    return VALUE\n",
        encoding="utf-8",
    )
    (root / "pkg" / "value.py").write_text("VALUE = 42\n", encoding="utf-8")
    return root


def _builder(root: Path) -> GraphBuilder:
    builder = GraphBuilder(str(root))
    builder.phase1_treesitter()
    return builder


def _identity(root: Path, *, revision: str = "a" * 40) -> RepositoryIndexIdentityV1Alpha1:
    return RepositoryIndexIdentityV1Alpha1(
        repository=root.name,
        revision=revision,
        dirty=False,
        working_tree_digest="clean",
        scanner_contract="core.engine.intelligence.graph-builder/phase1-tree-sitter",
        observed_languages=("python",),
        generated_at=datetime.now(timezone.utc),
    )


def _open(store: DurablePhase1IndexStore, index: RepositoryIndexIdentityV1Alpha1, snapshot):
    """Reopen with the caller-held external snapshot id and digest pair."""
    return store.open_latest(
        expected_index=index,
        expected_snapshot_id=snapshot.snapshot_id,
        expected_snapshot_digest=snapshot.snapshot_digest,
    )


def _snapshot_files(store_path: Path) -> list[Path]:
    return sorted(store_path.glob("snapshot-*.json"))


def test_capture_and_reopen_exact_phase1_state_without_authority(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    builder = _builder(root)
    index = _identity(root)
    store = DurablePhase1IndexStore(tmp_path / "store", root)

    snapshot = store.capture(builder, index, expected_generation=0)
    reopened = _open(store, index, snapshot)

    assert snapshot.generation == 1
    assert snapshot.parent_snapshot_id is None
    assert snapshot.phase1_state_digest == stable_digest(snapshot.phase1_state)
    assert reopened.snapshot == snapshot
    assert reopened.builder.export_phase1_state() == builder.export_phase1_state()
    assert set(reopened.builder.graph.nodes) == set(builder.graph.nodes)
    assert snapshot.provider_neutral is True
    assert snapshot.grants_source_authority is False
    assert snapshot.grants_reasoning_authority is False
    assert snapshot.grants_delivery_authority is False
    assert snapshot.grants_effect_authority is False
    assert snapshot.execution_authority is False
    assert snapshot.repository_revalidation_required is True


def test_append_preserves_first_snapshot_and_links_generation(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store_path = tmp_path / "store"
    store = DurablePhase1IndexStore(store_path, root)
    first_index = _identity(root)
    first = store.capture(_builder(root), first_index, expected_generation=0)
    first_file = _snapshot_files(store_path)[0]
    first_bytes = first_file.read_bytes()

    (root / "pkg" / "consumer.py").write_text(
        "from pkg.service import answer\n\nresult = answer()\n",
        encoding="utf-8",
    )
    second_index = _identity(root, revision="b" * 40)
    second = store.capture(
        _builder(root),
        second_index,
        expected_generation=1,
        expected_parent_snapshot_id=first.snapshot_id,
        expected_parent_snapshot_digest=first.snapshot_digest,
    )

    assert second.generation == 2
    assert second.parent_snapshot_id == first.snapshot_id
    assert second.parent_snapshot_digest == first.snapshot_digest
    assert first_file.read_bytes() == first_bytes
    assert store.list_snapshots() == (first, second)
    assert (
        store.read(first.snapshot_id, expected_index=first_index, expected_snapshot_digest=first.snapshot_digest)
        == first
    )
    assert _open(store, second_index, second).snapshot == second


def test_capture_rejects_stale_generation_and_wrong_builder_repository(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    other = _repository(tmp_path, "other")
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)
    first = store.capture(_builder(root), index, expected_generation=0)

    with pytest.raises(Phase1IndexGenerationConflict, match="expected 0, actual 1"):
        store.capture(_builder(root), index, expected_generation=0)
    with pytest.raises(Phase1IndexIdentityMismatch, match="builder repository mismatch"):
        store.capture(
            _builder(other),
            index,
            expected_generation=1,
            expected_parent_snapshot_id=first.snapshot_id,
            expected_parent_snapshot_digest=first.snapshot_digest,
        )


def test_concurrent_capture_publishes_one_generation_atomically(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    builder = _builder(root)
    index = _identity(root)
    ready = Barrier(2)

    def capture() -> str:
        ready.wait()
        try:
            return store.capture(builder, index, expected_generation=0).snapshot_id
        except Phase1IndexGenerationConflict:
            return "generation-conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _position: capture(), range(2)))

    assert results.count("generation-conflict") == 1
    assert len(store.list_snapshots()) == 1
    published = store.list_snapshots()[-1]
    assert _open(store, index, published).snapshot.generation == 1


def test_reopen_requires_exact_repository_and_index_identity(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    other = _repository(tmp_path, "other")
    store_path = tmp_path / "store"
    index = _identity(root)
    snapshot = DurablePhase1IndexStore(store_path, root).capture(_builder(root), index, expected_generation=0)

    wrong_index = _identity(root, revision="b" * 40)
    with pytest.raises(Phase1IndexIdentityMismatch, match="snapshot index mismatch"):
        _open(DurablePhase1IndexStore(store_path, root), wrong_index, snapshot)
    with pytest.raises(Phase1IndexIdentityMismatch, match="repository mismatch"):
        _open(DurablePhase1IndexStore(store_path, other), index, snapshot)

    same_stable_identity_observed_later = index.model_copy(update={"generated_at": datetime.now(timezone.utc)})
    reopened = _open(DurablePhase1IndexStore(store_path, root), same_stable_identity_observed_later, snapshot)
    assert reopened.snapshot.index_id == same_stable_identity_observed_later.index_id


def test_reopen_fails_closed_when_snapshot_bytes_are_tampered(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store_path = tmp_path / "store"
    index = _identity(root)
    store = DurablePhase1IndexStore(store_path, root)
    snapshot = store.capture(_builder(root), index, expected_generation=0)
    snapshot_path = _snapshot_files(store_path)[0]
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["phase1_state"]["symbols"][0]["name"] = "tampered"
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(Phase1IndexIntegrityError, match="snapshot byte digest mismatch"):
        _open(store, index, snapshot)


def test_reopen_fails_closed_when_latest_pointer_is_tampered(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store_path = tmp_path / "store"
    index = _identity(root)
    store = DurablePhase1IndexStore(store_path, root)
    snapshot = store.capture(_builder(root), index, expected_generation=0)
    pointer_path = store_path / "latest.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["generation"] = 2
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(Phase1IndexIntegrityError, match="latest pointer differs"):
        _open(store, index, snapshot)
    with pytest.raises(Phase1IndexIntegrityError, match="latest pointer differs"):
        store.list_snapshots()


def test_coherently_rewritten_cache_is_rejected_by_external_expected_coordinates(tmp_path: Path) -> None:
    """The writable cache never self-authenticates; the caller's pair decides."""
    root = _repository(tmp_path)
    store_path = tmp_path / "store"
    index = _identity(root)
    store = DurablePhase1IndexStore(store_path, root)
    trusted = store.capture(_builder(root), index, expected_generation=0)

    # Rewrite the stored phase-one state and republish a fully self-consistent
    # chain: new snapshot bytes, file name, snapshot id, digest, and pointer.
    payload = json.loads(_snapshot_files(store_path)[0].read_text(encoding="utf-8"))
    payload["phase1_state"]["imports"] = []
    payload["phase1_state"]["symbols"][0]["name"] = "rewritten"
    payload["phase1_state_digest"] = stable_digest(payload["phase1_state"])
    forged = DurablePhase1IndexSnapshotV1Alpha1.model_validate(payload)
    for path in _snapshot_files(store_path):
        path.unlink()
    forged_bytes = json.dumps(forged.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    forged_file = store_path / f"snapshot-{forged.snapshot_digest.split(':', 1)[1]}.json"
    forged_file.write_bytes(forged_bytes)
    pointer = json.loads((store_path / "latest.json").read_text(encoding="utf-8"))
    pointer.update(
        {
            "snapshot_id": forged.snapshot_id,
            "snapshot_digest": forged.snapshot_digest,
            "snapshot_file": forged_file.name,
        }
    )
    (store_path / "latest.json").write_text(json.dumps(pointer), encoding="utf-8")

    # The rewritten chain is internally consistent for a discovery-only open...
    assert store.list_snapshots()[-1].snapshot_id == forged.snapshot_id
    # ...and still rejected against the coordinates the caller holds externally.
    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected snapshot id and digest"):
        _open(store, index, trusted)


def test_historical_read_and_revalidation_calibration_survive_external_pairing(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    first_index = _identity(root)
    first = store.capture(_builder(root), first_index, expected_generation=0)
    (root / "pkg" / "consumer.py").write_text("from pkg.service import answer\n", encoding="utf-8")
    second_index = _identity(root, revision="b" * 40)
    second = store.capture(
        _builder(root),
        second_index,
        expected_generation=1,
        expected_parent_snapshot_id=first.snapshot_id,
        expected_parent_snapshot_digest=first.snapshot_digest,
    )

    assert (
        store.read(first.snapshot_id, expected_index=first_index, expected_snapshot_digest=first.snapshot_digest)
        == first
    )
    reopened = _open(store, second_index, second)
    assert reopened.snapshot.repository_revalidation_required is True
    assert reopened.builder.get_files()


def test_read_rejects_wrong_historical_digest(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)
    first = store.capture(_builder(root), index, expected_generation=0)

    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected snapshot id and digest"):
        store.read(first.snapshot_id, expected_index=index, expected_snapshot_digest="sha256:" + "0" * 64)


def test_read_rejects_crossed_generation_id_and_digest_pair(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    first_index = _identity(root)
    first = store.capture(_builder(root), first_index, expected_generation=0)
    (root / "pkg" / "consumer.py").write_text("from pkg.service import answer\n", encoding="utf-8")
    second_index = _identity(root, revision="b" * 40)
    second = store.capture(
        _builder(root),
        second_index,
        expected_generation=1,
        expected_parent_snapshot_id=first.snapshot_id,
        expected_parent_snapshot_digest=first.snapshot_digest,
    )

    # Generation one's id paired with generation two's digest must not resolve.
    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected snapshot id and digest"):
        store.read(first.snapshot_id, expected_index=first_index, expected_snapshot_digest=second.snapshot_digest)


def test_open_latest_rejects_stale_pair_while_historical_read_with_that_pair_still_succeeds(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    first_index = _identity(root)
    first = store.capture(_builder(root), first_index, expected_generation=0)
    (root / "pkg" / "consumer.py").write_text("from pkg.service import answer\n", encoding="utf-8")
    second_index = _identity(root, revision="b" * 40)
    store.capture(
        _builder(root),
        second_index,
        expected_generation=1,
        expected_parent_snapshot_id=first.snapshot_id,
        expected_parent_snapshot_digest=first.snapshot_digest,
    )

    # The generation advanced: generation-one's id/digest pair no longer names
    # the latest snapshot, even though the caller's index identity is current.
    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected snapshot id and digest"):
        store.open_latest(
            expected_index=second_index,
            expected_snapshot_id=first.snapshot_id,
            expected_snapshot_digest=first.snapshot_digest,
        )
    # The identical exact pair still opens as immutable history.
    assert (
        store.read(first.snapshot_id, expected_index=first_index, expected_snapshot_digest=first.snapshot_digest)
        == first
    )


def test_capture_generation_zero_rejects_expected_parent_coordinates(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)

    with pytest.raises(ValueError, match="generation zero capture must not name an expected parent"):
        store.capture(
            _builder(root),
            index,
            expected_generation=0,
            expected_parent_snapshot_id="code_index_snapshot:" + "0" * 32,
            expected_parent_snapshot_digest="sha256:" + "0" * 64,
        )


def test_capture_requires_expected_parent_pair_when_generation_is_positive(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)
    store.capture(_builder(root), index, expected_generation=0)

    with pytest.raises(ValueError, match="expected_generation > 0 requires"):
        store.capture(_builder(root), index, expected_generation=1)


def test_capture_rejects_expected_parent_id_without_digest(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)
    first = store.capture(_builder(root), index, expected_generation=0)

    with pytest.raises(ValueError, match="expected parent snapshot id and digest must be provided together"):
        store.capture(
            _builder(root),
            index,
            expected_generation=1,
            expected_parent_snapshot_id=first.snapshot_id,
        )


def test_capture_rejects_expected_parent_digest_without_id(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)
    first = store.capture(_builder(root), index, expected_generation=0)

    with pytest.raises(ValueError, match="expected parent snapshot id and digest must be provided together"):
        store.capture(
            _builder(root),
            index,
            expected_generation=1,
            expected_parent_snapshot_digest=first.snapshot_digest,
        )


def test_capture_rejects_wrong_expected_parent_snapshot(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    index = _identity(root)
    store.capture(_builder(root), index, expected_generation=0)

    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected parent id and digest pair"):
        store.capture(
            _builder(root),
            index,
            expected_generation=1,
            expected_parent_snapshot_id="code_index_snapshot:" + "f" * 32,
            expected_parent_snapshot_digest="sha256:" + "f" * 64,
        )


def test_capture_rejects_crossed_expected_parent_id_and_digest_pair(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = DurablePhase1IndexStore(tmp_path / "store", root)
    first_index = _identity(root)
    first = store.capture(_builder(root), first_index, expected_generation=0)
    (root / "pkg" / "consumer.py").write_text("from pkg.service import answer\n", encoding="utf-8")
    second_index = _identity(root, revision="b" * 40)
    second = store.capture(
        _builder(root),
        second_index,
        expected_generation=1,
        expected_parent_snapshot_id=first.snapshot_id,
        expected_parent_snapshot_digest=first.snapshot_digest,
    )
    (root / "pkg" / "consumer.py").write_text("from pkg.service import answer\nresult = answer()\n", encoding="utf-8")
    third_index = _identity(root, revision="c" * 40)

    # First generation's id crossed with second generation's digest must not
    # resolve as the actual latest parent (second), even though each half is
    # individually a real snapshot coordinate from this exact chain.
    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected parent id and digest pair"):
        store.capture(
            _builder(root),
            third_index,
            expected_generation=2,
            expected_parent_snapshot_id=first.snapshot_id,
            expected_parent_snapshot_digest=second.snapshot_digest,
        )


def test_capture_rejects_coherently_rewritten_parent(tmp_path: Path) -> None:
    """A rewritten cache cannot forge itself into the caller's trusted parent lineage."""
    root = _repository(tmp_path)
    store_path = tmp_path / "store"
    store = DurablePhase1IndexStore(store_path, root)
    index = _identity(root)
    trusted = store.capture(_builder(root), index, expected_generation=0)

    # Rewrite the stored phase-one state and republish a fully self-consistent
    # generation-one chain: new snapshot bytes, file name, id, digest, pointer.
    payload = json.loads(_snapshot_files(store_path)[0].read_text(encoding="utf-8"))
    payload["phase1_state"]["imports"] = []
    payload["phase1_state"]["symbols"][0]["name"] = "rewritten"
    payload["phase1_state_digest"] = stable_digest(payload["phase1_state"])
    forged = DurablePhase1IndexSnapshotV1Alpha1.model_validate(payload)
    for path in _snapshot_files(store_path):
        path.unlink()
    forged_bytes = json.dumps(forged.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    forged_file = store_path / f"snapshot-{forged.snapshot_digest.split(':', 1)[1]}.json"
    forged_file.write_bytes(forged_bytes)
    pointer = json.loads((store_path / "latest.json").read_text(encoding="utf-8"))
    pointer.update(
        {
            "snapshot_id": forged.snapshot_id,
            "snapshot_digest": forged.snapshot_digest,
            "snapshot_file": forged_file.name,
        }
    )
    (store_path / "latest.json").write_text(json.dumps(pointer), encoding="utf-8")

    # The rewritten chain is internally consistent for a discovery-only read...
    assert store.list_snapshots()[-1].snapshot_id == forged.snapshot_id
    # ...but a generation-two capture naming the caller's originally trusted
    # parent coordinates must still be rejected: the actual latest snapshot no
    # longer matches what the caller holds externally.
    with pytest.raises(Phase1IndexIdentityMismatch, match="externally expected parent id and digest pair"):
        store.capture(
            _builder(root),
            index,
            expected_generation=1,
            expected_parent_snapshot_id=trusted.snapshot_id,
            expected_parent_snapshot_digest=trusted.snapshot_digest,
        )
