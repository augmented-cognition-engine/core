"""Create-only workspace export through ACE's public governed-action contract."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ace.core import (
    ActionDisposition,
    ActionEffectState,
    ActionEvidenceV1Alpha1,
    ActionIntentV1Alpha1,
    ActionResultV1Alpha1,
    ActionReversibility,
    CapabilityArtifactIdentityV1Alpha1,
    GovernedActionAuthorizationProjection,
    PreparedActionV1Alpha1,
    canonical_hash,
    canonical_json,
)

ACTION_TYPE = "create_workspace_export"
MAX_CONTENT_BYTES = 128_000
MAX_RELATIVE_PATH_CHARS = 240
ADAPTER_ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="bounded_action_execution",
    contract="ace.core.action-adapter/v1alpha1",
    implementation_id="reference_workspace_export",
    implementation_version="0.1.0",
    artifact_digest="sha256:" + canonical_hash("ace-reference-workspace-action:0.1.0"),
)


class ReferenceWorkspaceActionError(ValueError):
    """The requested export crossed the adapter's bounded workspace contract."""


@dataclass(frozen=True, slots=True)
class _PreparedMaterial:
    plan: PreparedActionV1Alpha1
    target: Path
    content: bytes


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReferenceWorkspaceActionError(f"duplicate parameter: {key}")
        result[key] = value
    return result


def _parameters(value: str) -> tuple[str, bytes]:
    try:
        parsed = json.loads(value, object_pairs_hook=_unique_object)
    except ReferenceWorkspaceActionError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReferenceWorkspaceActionError("parameters must be one unambiguous JSON object") from exc
    if type(parsed) is not dict or set(parsed) != {"content", "relative_path"}:
        raise ReferenceWorkspaceActionError("parameters require exactly content and relative_path")
    relative_path = parsed["relative_path"]
    content = parsed["content"]
    if type(relative_path) is not str or not 1 <= len(relative_path) <= MAX_RELATIVE_PATH_CHARS:
        raise ReferenceWorkspaceActionError("relative_path must be bounded text")
    if type(content) is not str or "\x00" in content:
        raise ReferenceWorkspaceActionError("content must be NUL-free text")
    encoded = content.encode("utf-8")
    if not encoded or len(encoded) > MAX_CONTENT_BYTES:
        raise ReferenceWorkspaceActionError("UTF-8 content exceeds the bounded byte range")
    return relative_path, encoded


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ReferenceWorkspaceActionError("relative_path must be canonical and cannot traverse")
    return path


class ReferenceWorkspaceActionAdapter:
    """Explicitly constructed trusted adapter for one create-only file effect."""

    artifact_identity = ADAPTER_ARTIFACT

    def __init__(self, *, workspace_root: Path) -> None:
        root = workspace_root.resolve(strict=True)
        if not root.is_dir() or workspace_root.is_symlink():
            raise ReferenceWorkspaceActionError("workspace_root must be an existing non-symlink directory")
        self._root = root
        self._prepared: dict[str, _PreparedMaterial] = {}

    def _target(self, relative_path: str) -> Path:
        relative = _relative(relative_path)
        target = self._root.joinpath(*relative.parts)
        cursor = self._root
        for part in relative.parts[:-1]:
            cursor /= part
            if cursor.is_symlink() or not cursor.is_dir():
                raise ReferenceWorkspaceActionError("target parent must be an existing non-symlink directory")
        try:
            parent = target.parent.resolve(strict=True)
        except OSError as exc:
            raise ReferenceWorkspaceActionError("target parent must already exist") from exc
        if parent != self._root and self._root not in parent.parents:
            raise ReferenceWorkspaceActionError("target parent escaped the approved workspace")
        if target.exists() or target.is_symlink():
            raise ReferenceWorkspaceActionError("target must not already exist")
        return target

    def _open_target(self, relative_path: str) -> int:
        """Exclusively create a target without following mutable parent symlinks."""
        relative = _relative(relative_path)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open(self._root, directory_flags)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, directory_flags, dir_fd=directory)
                os.close(directory)
                directory = child
            return os.open(
                relative.parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
        finally:
            os.close(directory)

    @staticmethod
    def _target_changed_result() -> ActionResultV1Alpha1:
        return ActionResultV1Alpha1(
            disposition=ActionDisposition.FAILED,
            effect_state=ActionEffectState.NONE,
            failure_code="target_changed",
            failure_message="The create-only target changed after preparation; no file was written.",
            completed_at=datetime.now(UTC),
        )

    async def prepare(self, intent: ActionIntentV1Alpha1) -> PreparedActionV1Alpha1:
        try:
            exact = ActionIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ReferenceWorkspaceActionError("action intent failed exact public-contract validation") from exc
        if exact.action_type != ACTION_TYPE:
            raise ReferenceWorkspaceActionError("adapter received an unsupported action type")
        relative_path, content = _parameters(exact.parameters_json)
        target = self._target(relative_path)
        target_ref = f"workspace:{relative_path}"
        plan = PreparedActionV1Alpha1(
            product_id=exact.product_id,
            intent_id=str(exact.intent_id),
            intent_digest=str(exact.intent_digest),
            artifact=self.artifact_identity,
            action_type=exact.action_type,
            target_ref=target_ref,
            target_digest="sha256:" + canonical_hash({"relative_path": relative_path}),
            required_permissions=("workspace.create",),
            declared_side_effects=("create_file",),
            reversibility=ActionReversibility.REVERSIBLE,
            before_evidence=(
                ActionEvidenceV1Alpha1(
                    evidence_type="file_absent",
                    target_ref=target_ref,
                    material_digest="sha256:" + hashlib.sha256(b"ACE_FILE_ABSENT").hexdigest(),
                ),
            ),
            timeout_seconds=10.0,
            prepared_at=datetime.now(UTC),
        )
        self._prepared[str(plan.plan_id)] = _PreparedMaterial(plan=plan, target=target, content=content)
        return plan

    async def execute(
        self,
        plan: PreparedActionV1Alpha1,
        authorization: GovernedActionAuthorizationProjection,
    ) -> ActionResultV1Alpha1:
        try:
            exact_plan = PreparedActionV1Alpha1.model_validate(plan.model_dump(mode="python"))
            GovernedActionAuthorizationProjection.model_validate(authorization.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ReferenceWorkspaceActionError("execution material failed exact public-contract validation") from exc
        prepared = self._prepared.pop(str(exact_plan.plan_id), None)
        if prepared is None or prepared.plan != exact_plan:
            raise ReferenceWorkspaceActionError("execution did not match one exact prepared plan")
        try:
            relative_path = prepared.target.relative_to(self._root).as_posix()
            self._target(relative_path)
        except ReferenceWorkspaceActionError:
            return self._target_changed_result()
        descriptor: int | None = None
        try:
            try:
                descriptor = self._open_target(relative_path)
            except OSError:
                return self._target_changed_result()
            remaining = memoryview(prepared.content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("workspace export write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
        digest = "sha256:" + hashlib.sha256(prepared.content).hexdigest()
        return ActionResultV1Alpha1(
            disposition=ActionDisposition.SUCCEEDED,
            effect_state=ActionEffectState.CONFIRMED,
            result_json=canonical_json(
                {
                    "bytes_written": len(prepared.content),
                    "material_digest": digest,
                    "target_ref": exact_plan.target_ref,
                }
            ),
            after_evidence=(
                ActionEvidenceV1Alpha1(
                    evidence_type="file_created",
                    target_ref=exact_plan.target_ref,
                    material_digest=digest,
                ),
            ),
            completed_at=datetime.now(UTC),
        )


__all__ = [
    "ACTION_TYPE",
    "ADAPTER_ARTIFACT",
    "ReferenceWorkspaceActionAdapter",
    "ReferenceWorkspaceActionError",
]
