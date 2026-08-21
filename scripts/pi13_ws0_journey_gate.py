#!/usr/bin/env python3
"""PI13 WS0 journey gate runner.

Evaluates the J1-J10 journey steps through injectable probe callables and
emits deterministic JSON and Markdown reports. Stdlib-only at import time.

Exit code is 0 only when all ten steps report PASS, otherwise 1.
"""

from __future__ import annotations

import argparse
import asyncio
import enum
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import secrets
import sys
import tempfile
import traceback
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:  # installed/package import (tests, installed wheel)
    from scripts.pi13_ws0_stub_provider import StubProviderServer
except ImportError:  # pragma: no cover - running as a loose script from the checkout
    from pi13_ws0_stub_provider import StubProviderServer  # type: ignore[no-redef]

STEP_IDS: tuple[str, ...] = tuple(f"J{index}" for index in range(1, 11))

STEP_NAMES: dict[str, str] = {
    "J1": "Install",
    "J2": "Choose",
    "J3": "Connect",
    "J4": "Inventory",
    "J5": "First Brief",
    "J6": "Change",
    "J7": "Ask",
    "J8": "Correct",
    "J9": "Restart",
    "J10": "Own",
}


class StepStatus(enum.Enum):
    """Closed status vocabulary for a journey step."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class StepResult:
    """Immutable outcome of a single journey step probe."""

    step_id: str
    name: str
    status: StepStatus
    summary: str
    evidence: tuple[str, ...] = ()
    blocker: str | None = None

    def __post_init__(self) -> None:
        if self.step_id not in STEP_IDS:
            raise ValueError(f"unknown step id: {self.step_id!r}")
        if not isinstance(self.status, StepStatus):
            raise TypeError(f"status must be StepStatus, got {type(self.status).__name__}")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not all(isinstance(item, str) for item in self.evidence):
            raise TypeError("evidence entries must be strings")
        if self.blocker is not None and not isinstance(self.blocker, str):
            raise TypeError("blocker must be a string or None")
        if self.status is not StepStatus.PASS and not self.evidence and not self.blocker:
            raise ValueError(f"{self.step_id}: non-PASS result requires evidence or a blocker")

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status.value,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "blocker": self.blocker,
        }


@dataclass(frozen=True)
class JourneyReport:
    """Validated, ordered collection of the ten journey step results."""

    results: tuple[StepResult, ...]
    surreal_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))
        seen_ids = [result.step_id for result in self.results]
        duplicates = sorted({step_id for step_id in seen_ids if seen_ids.count(step_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate step results: {', '.join(duplicates)}")
        missing = [step_id for step_id in STEP_IDS if step_id not in seen_ids]
        if missing:
            raise ValueError(f"missing step results: {', '.join(missing)}")
        if tuple(seen_ids) != STEP_IDS:
            raise ValueError(f"step results out of order: got {seen_ids}, expected {list(STEP_IDS)}")

    @property
    def all_pass(self) -> bool:
        return all(result.status is StepStatus.PASS for result in self.results)

    @property
    def exit_code(self) -> int:
        return 0 if self.all_pass else 1

    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in StepStatus}
        for result in self.results:
            counts[result.status.value] += 1
        return counts

    def to_json(self) -> str:
        payload = {
            "report": "pi13_ws0_journey_gate",
            "surreal_url": self.surreal_url,
            "all_pass": self.all_pass,
            "status_counts": self.status_counts(),
            "steps": [result.to_dict() for result in self.results],
        }
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# PI13 WS0 Journey Gate Report",
            "",
            f"- Surreal URL: `{self.surreal_url or '(unset)'}`",
            f"- All pass: {'yes' if self.all_pass else 'no'}",
            "",
            "| Step | Name | Status | Summary | Evidence | Blocker |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for result in self.results:
            evidence = "; ".join(result.evidence) if result.evidence else "-"
            blocker = result.blocker if result.blocker else "-"
            lines.append(
                "| {step} | {name} | {status} | {summary} | {evidence} | {blocker} |".format(
                    step=result.step_id,
                    name=_markdown_cell(result.name),
                    status=result.status.value,
                    summary=_markdown_cell(result.summary),
                    evidence=_markdown_cell(evidence),
                    blocker=_markdown_cell(blocker),
                )
            )
        lines.append("")
        return "\n".join(lines)


def _markdown_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_atomic(path: Path, content: str) -> None:
    """Write content to path atomically via a same-directory temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


@dataclass(frozen=True)
class ProbeContext:
    """Everything a probe needs to evaluate its journey step."""

    repository_root: Path
    fixture_corpus: Path
    json_report: Path
    markdown_report: Path
    surreal_url: str


ProbeCallable = Callable[[ProbeContext], StepResult]


class JourneyGate:
    """Runs an injectable step-id -> probe mapping across all ten steps."""

    def __init__(self, probes: Mapping[str, ProbeCallable]) -> None:
        unknown = sorted(set(probes) - set(STEP_IDS))
        if unknown:
            raise ValueError(f"probes for unknown step ids: {', '.join(unknown)}")
        self._probes: dict[str, ProbeCallable] = dict(probes)

    def run(self, context: ProbeContext) -> JourneyReport:
        results: list[StepResult] = []
        for step_id in STEP_IDS:
            name = STEP_NAMES[step_id]
            probe = self._probes.get(step_id)
            if probe is None:
                results.append(
                    StepResult(
                        step_id=step_id,
                        name=name,
                        status=StepStatus.BLOCKED,
                        summary="No probe registered for this step.",
                        blocker=f"probe_not_implemented:{step_id}",
                    )
                )
                continue
            try:
                result = probe(context)
                if not isinstance(result, StepResult):
                    raise TypeError(f"probe returned {type(result).__name__}, expected StepResult")
                if result.step_id != step_id:
                    raise ValueError(f"probe returned result for {result.step_id}, expected {step_id}")
            except Exception as exc:  # noqa: BLE001 - one probe must not stop the rest
                result = StepResult(
                    step_id=step_id,
                    name=name,
                    status=StepStatus.FAIL,
                    summary=f"Probe raised {type(exc).__name__}.",
                    evidence=(f"{type(exc).__name__}: {exc}",),
                )
            results.append(result)
        return JourneyReport(results=tuple(results), surreal_url=context.surreal_url)


class DeterministicStubProvider:
    """Offline stand-in for a model provider; records invocations, no network."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return "PI13 WS0 deterministic stub response"


_FIXTURE_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("notes/vault.md", "PI13 WS0"),
    ("notes/second.md", "PI13 WS0"),
    ("sample.pdf", "%PDF-1.4"),
    ("sample.csv", "id,name,value"),
    ("sample.json", "pi13_ws0"),
)

_REQUIRED_DISTRIBUTIONS: tuple[str, ...] = (
    "ace-core",
    "ace-personal-intelligence-pack",
    "ace-personal-intelligence-bundle",
    "ace-local-markdown-source",
    "ace-local-pdf-source",
    "ace-local-csv-source",
    "ace-local-json-source",
    "ace-local-source-snapshot",
)

_INSTALL_IMPORTS: tuple[str, ...] = (
    "ace",
    "core.engine.api.main",
    "scripts.schema_apply",
    "ace_mcp_client.server",
)


def _check_fixtures(context: ProbeContext) -> list[str]:
    evidence = []
    for relative, signature in _FIXTURE_SIGNATURES:
        path = context.fixture_corpus / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing fixture: {path}")
        data = path.read_bytes()
        if signature.encode("utf-8") not in data:
            raise ValueError(f"fixture {path} lacks expected signature {signature!r}")
        evidence.append(f"fixture:{relative}:{signature}")
    return evidence


def _import_outside_repo(module_name: str, repository_root: Path) -> object:
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if module_file:
        resolved = Path(module_file).resolve()
        root = repository_root.resolve()
        if root == resolved or root in resolved.parents:
            raise RuntimeError(f"module {module_name} resolved inside repository root: {resolved}")
    return module


def _max_schema_version(schema_apply_module: object) -> str:
    module_file = getattr(schema_apply_module, "__file__", None)
    if not module_file:
        raise RuntimeError("scripts.schema_apply has no __file__; cannot locate migrations")
    schema_dir = Path(module_file).resolve().parent.parent / "core" / "schema"
    versions = sorted(
        match.group(1) for path in schema_dir.glob("v*.surql") if (match := re.match(r"v(\d{3})", path.name))
    )
    if not versions:
        raise RuntimeError(f"no vNNN migration files found under {schema_dir}")
    return versions[-1]


async def _check_surreal_schema(surreal_url: str, expected_version: str) -> str:
    from surrealdb import AsyncSurreal

    db = AsyncSurreal(surreal_url)
    try:
        await db.connect()
        await db.signin(
            {
                "username": os.environ.get("SURREAL_USER", "root"),
                "password": os.environ.get("SURREAL_PASS", "root"),
            }
        )
        await db.use(os.environ.get("SURREAL_NS", "ace"), os.environ.get("SURREAL_DB", "ace"))
        rows = await db.query("SELECT `value` FROM config_entry WHERE key = 'schema_version'")
    finally:
        await db.close()

    values: set[str] = set()
    for result in rows if isinstance(rows, list) else [rows]:
        for row in result if isinstance(result, list) else [result]:
            if isinstance(row, dict) and "value" in row:
                values.add(str(row["value"]))
    if values != {expected_version}:
        raise RuntimeError(f"schema_version mismatch: db={sorted(values)}, expected {expected_version}")
    return expected_version


async def _count_mcp_tools(server_module: object) -> int:
    tools = await server_module.mcp.list_tools()
    return len(tools)


def probe_j1(context: ProbeContext) -> StepResult:
    """J1 Install: packages, schema, fixtures, MCP surface, offline provider."""
    if not context.surreal_url:
        raise RuntimeError("SURREAL_URL is not set; cannot verify applied schema")

    evidence: list[str] = []

    for distribution in _REQUIRED_DISTRIBUTIONS:
        version = importlib.metadata.version(distribution)
        evidence.append(f"dist:{distribution}=={version}")

    modules = {name: _import_outside_repo(name, context.repository_root) for name in _INSTALL_IMPORTS}

    expected_version = _max_schema_version(modules["scripts.schema_apply"])
    applied = asyncio.run(_check_surreal_schema(context.surreal_url, expected_version))
    evidence.append(f"schema_version:{applied}")

    evidence.extend(_check_fixtures(context))

    tool_count = asyncio.run(_count_mcp_tools(modules["ace_mcp_client.server"]))
    if tool_count != 11:
        raise RuntimeError(f"expected 11 MCP tools, found {tool_count}")
    evidence.append(f"mcp_tools:{tool_count}")

    provider = DeterministicStubProvider()
    provider.complete("pi13 ws0 j1 provider smoke")
    if len(provider.calls) != 1:
        raise RuntimeError("deterministic provider was not invoked exactly once")
    evidence.append("provider:deterministic_stub_invoked")

    return StepResult(
        step_id="J1",
        name=STEP_NAMES["J1"],
        status=StepStatus.PASS,
        summary="Install verified: distributions, schema, fixtures, MCP tools, provider.",
        evidence=tuple(evidence),
    )


_PERSONAL_PROFILE_ID = "intelligence_onboarding_profile:personal"
_PERSONAL_PACK_ID = "personal_intelligence"
_BUILDER_ENTRY_POINT_GROUP = "ace.intelligence_builders"
_CONNECT_PREVIEW_ROUTE = "/v1/intelligence/builds/connect/preview"
_CONNECT_AUTHORIZE_ROUTE = "/v1/intelligence/builds/connect/authorize"
_REQUIRED_CONNECT_ROUTES = (_CONNECT_PREVIEW_ROUTE, _CONNECT_AUTHORIZE_ROUTE)


def probe_j2(context: ProbeContext) -> StepResult:
    """J2 Choose: Personal onboarding profile discovered and planner registered."""
    catalog = _import_outside_repo("core.engine.core.installed_intelligence_catalog", context.repository_root)
    planner_registry = _import_outside_repo(
        "core.engine.core.intelligence_build_planner_registry", context.repository_root
    )

    evidence: list[str] = []

    installed = catalog.discover_installed_onboarding_profiles()
    by_id = {item.profile.profile_id: item for item in installed}
    personal = by_id.get(_PERSONAL_PROFILE_ID)
    if personal is None:
        raise RuntimeError(f"profile {_PERSONAL_PROFILE_ID} not discovered; found: {sorted(by_id)}")
    evidence.append(
        "profile:{pid}@{dist}=={version}".format(
            pid=_PERSONAL_PROFILE_ID,
            dist=personal.distribution,
            version=personal.distribution_version,
        )
    )
    evidence.append(f"profile_digest:{personal.profile.profile_digest}")

    loaded = planner_registry.load_installed_intelligence_build_planners()
    if _PERSONAL_PROFILE_ID not in loaded:
        raise RuntimeError(f"planner for {_PERSONAL_PROFILE_ID} not loaded; loaded: {sorted(loaded)}")
    evidence.append(f"planners_loaded:{','.join(sorted(loaded))}")

    planner = planner_registry.resolve_intelligence_build_planner(_PERSONAL_PROFILE_ID)
    if planner is None:
        raise RuntimeError(f"planner for {_PERSONAL_PROFILE_ID} did not resolve")
    pack_id = planner.pack_reference.pack_id
    if pack_id != _PERSONAL_PACK_ID:
        raise RuntimeError(f"planner pack_id {pack_id!r} != expected {_PERSONAL_PACK_ID!r}")
    evidence.append(f"planner_pack:{pack_id}")

    return StepResult(
        step_id="J2",
        name=STEP_NAMES["J2"],
        status=StepStatus.PASS,
        summary="Choose verified: Personal profile discovered and planner resolves to its pack.",
        evidence=tuple(evidence),
    )


def _openapi_paths(api_module: object) -> set[str]:
    paths = api_module.app.openapi().get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("OpenAPI schema has no paths dict")
    return {path for path in paths if isinstance(path, str)}


def _qualified_connect_routes(api_module: object) -> list[str]:
    paths = _openapi_paths(api_module)
    return sorted(path for path in _REQUIRED_CONNECT_ROUTES if path in paths)


def _installed_distributions_exact(
    distributions: Iterable[importlib.metadata.Distribution] | None = None,
) -> tuple[importlib.metadata.Distribution, ...]:
    """Deterministic exact snapshot of installed distributions for discovery.

    Duplicate sys.path entries (extension loading re-prepending an already
    present site-packages path) make importlib.metadata enumerate the same
    dist-info twice. Collapse only entries whose canonical distribution name
    and resolved dist-info path are both identical; entries sharing a name
    across genuinely different paths, or lacking a name or path, are retained
    so downstream ambiguity still fails closed.
    """
    installed = importlib.metadata.distributions() if distributions is None else distributions
    keyed: dict[tuple[str, str], importlib.metadata.Distribution] = {}
    unkeyed: list[importlib.metadata.Distribution] = []
    for distribution in installed:
        raw_metadata = distribution.metadata
        name = raw_metadata.get("Name") if raw_metadata is not None else None
        dist_info = getattr(distribution, "_path", None)
        if not isinstance(name, str) or not name.strip() or dist_info is None:
            unkeyed.append(distribution)
            continue
        canonical = re.sub(r"[-_.]+", "-", name.strip()).lower()
        try:
            resolved = str(Path(str(dist_info)).resolve())
        except OSError:
            unkeyed.append(distribution)
            continue
        keyed.setdefault((canonical, resolved), distribution)
    ordered = tuple(item for _, item in sorted(keyed.items(), key=lambda entry: entry[0]))
    return ordered + tuple(unkeyed)


def _prepare_snapshot_activation(context: ProbeContext, provider_artifact: object) -> list[str]:
    """Prepare (never persist) a Personal pack activation bound to the snapshot provider.

    Builds an exact DomainActivationSpecV1 from the installed compiled pack with
    deterministic fixture authority grants. Nothing is committed and no sources
    are read; the returned evidence records the prepared spec only.
    """
    planner_registry = _import_outside_repo(
        "core.engine.core.intelligence_build_planner_registry", context.repository_root
    )
    installed_packs = _import_outside_repo("ace.application.installed_pack_artifacts", context.repository_root)
    activation_contracts = _import_outside_repo("ace.intelligence.contracts.activation", context.repository_root)
    pack_activation = _import_outside_repo("ace.intelligence.packs.activation", context.repository_root)

    planner_registry.load_installed_intelligence_build_planners()
    planner = planner_registry.resolve_intelligence_build_planner(_PERSONAL_PROFILE_ID)
    if planner is None:
        raise RuntimeError(f"planner for {_PERSONAL_PROFILE_ID} did not resolve")

    resolver = installed_packs.InstalledCompiledPackArtifactResolver.discover(_installed_distributions_exact())
    installed = asyncio.run(resolver.resolve_exact(reference=planner.pack_reference))
    if installed is None:
        raise RuntimeError(f"no exact installed compiled pack for {planner.pack_reference.pack_id}")
    pack = installed.pack

    matching = [
        item
        for item in pack.capability_requirements
        if item.capability == provider_artifact.capability and item.contract == provider_artifact.contract
    ]
    if len(matching) != 1:
        raise RuntimeError(
            f"expected exactly one pack capability requirement for "
            f"{provider_artifact.capability}:{provider_artifact.contract}, found {len(matching)}"
        )
    requirement = matching[0]

    capability_binding = activation_contracts.CapabilityBindingV1(
        requirement_id=requirement.requirement_id,
        capability=requirement.capability,
        contract=requirement.contract,
        implementation_id=provider_artifact.implementation_id,
        implementation_version=provider_artifact.implementation_version,
        artifact_digest=provider_artifact.artifact_digest,
    )

    overlay = activation_contracts.CompiledOverlayV1(
        overlay_id="pi13_ws0_empty_overlay",
        version="0.0.0",
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        pack_digest=pack.pack_digest,
        values=(),
    )

    authority_bindings = tuple(
        activation_contracts.AuthorityBindingV1(
            request_id=request.request_id,
            authority=request.authority,
            grant_ref=f"authority_grant:pi13_ws0_{request.request_id}",
        )
        for request in sorted(pack.authority_requests, key=lambda item: item.request_id)
    )

    spec = pack_activation.prepare_domain_activation(
        product_id="product:pi13-ws0",
        activation_key="pi13_ws0",
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref=installed.compilation.result_id,
        conformance_receipts=installed.conformance_receipts,
        capability_bindings=(capability_binding,),
        authority_bindings=authority_bindings,
    )

    return [
        f"activation_capability_binding:{requirement.requirement_id}:{requirement.capability}:"
        f"{requirement.contract}:{provider_artifact.implementation_id}=={provider_artifact.implementation_version}",
        f"activation_spec_prepared:{spec.spec_id}",
        "activation_authority:authority_fixture_only:not_resolved",
    ]


_CONSENT_PROBE_AUTHORIZED_ROOT = "/pi13_ws0_consent_probe_root_does_not_exist"


def _consent_before_read_probe(context: ProbeContext) -> list[str]:
    """Prove Connect requires explicit consent before any read, with zero I/O.

    Builds a valid, lexical-only Connect preview request against the
    installed Personal planner's exact pack reference and a deliberately
    unconfigured ``authorized_root``, proving preview succeeds and reports
    local/read-only/no-network/no-write without touching the filesystem.
    Then feeds two authorization-shaped requests, one missing consent and one
    with false consent, to ``authorize_local_source_connect`` bound to a
    provider that raises if its identity is read or its snapshot method is
    called at all, proving both are rejected before any provider contact and
    the provider's call count stays zero.
    """
    planner_registry = _import_outside_repo(
        "core.engine.core.intelligence_build_planner_registry", context.repository_root
    )
    local_source_connect = _import_outside_repo("ace.application.local_source_connect", context.repository_root)

    planner_registry.load_installed_intelligence_build_planners()
    planner = planner_registry.resolve_intelligence_build_planner(_PERSONAL_PROFILE_ID)
    if planner is None:
        raise RuntimeError(f"planner for {_PERSONAL_PROFILE_ID} did not resolve")

    scope = local_source_connect.LocalSourceMappingScope(
        mapping_id="pi13_ws0_consent_probe",
        source_definition_ref="pi13_ws0_consent_probe_source_definition",
        source_type_ref="pi13_ws0_consent_probe_source_type",
        subject_binding_id="pi13_ws0_consent_probe",
        entity_type_id="pi13_ws0_consent_probe",
        include=("**/*",),
    )
    preview_request = local_source_connect.LocalSourceConnectPreviewRequest(
        product_id="product:pi13-ws0-consent-probe",
        actor_ref="pi13_ws0_consent_probe_actor",
        pack=planner.pack_reference,
        profile_id=_PERSONAL_PROFILE_ID,
        profile_digest="sha256:" + hashlib.sha256(b"pi13_ws0_consent_probe").hexdigest(),
        source_group_id="pi13_ws0_consent_probe",
        expected_contribution="pi13 ws0 consent probe",
        authorized_root=_CONSENT_PROBE_AUTHORIZED_ROOT,
        mapping_scopes=(scope,),
    )
    preview = local_source_connect.preview_local_source_connect(preview_request)
    if not (
        preview.read_only is True
        and preview.acquisition_mode.value == "local"
        and preview.network_capture_performed is False
        and preview.write_access_requested is False
        and preview.reusable_authority is False
    ):
        raise RuntimeError("lexical Connect preview did not report local/read-only/no-network/no-write")

    evidence = [f"consent_probe_preview:{preview.preview_id}:local:read_only:no_network:no_write"]

    authorization_request = local_source_connect.LocalSourceConnectAuthorizationRequest(
        preview=preview,
        authorized=True,
        authorized_at=datetime.now(UTC),
    )
    valid_payload = authorization_request.model_dump(mode="python")

    class _ExplodingCountingSnapshotProvider:
        """Fails if touched at all; counts calls to prove zero provider contact."""

        def __init__(self) -> None:
            self.calls = 0

        @property
        def artifact_identity(self):
            raise AssertionError("snapshot provider identity must not be read for a rejected authorization")

        async def snapshot(self, request: object) -> tuple[object, ...]:
            self.calls += 1
            raise AssertionError("snapshot provider must not be called for a rejected authorization")

    class _AuthorizationShapedRequest:
        """Duck-types the model_dump seam authorize_local_source_connect reads."""

        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def model_dump(self, mode: str = "python") -> dict[str, object]:
            return self._payload

    missing_consent_payload = dict(valid_payload)
    del missing_consent_payload["authorized"]
    false_consent_payload = dict(valid_payload)
    false_consent_payload["authorized"] = False

    for label, payload in (
        ("missing_authorized", missing_consent_payload),
        ("false_authorized", false_consent_payload),
    ):
        provider = _ExplodingCountingSnapshotProvider()
        shaped_request = _AuthorizationShapedRequest(payload)
        try:
            asyncio.run(local_source_connect.authorize_local_source_connect(shaped_request, provider))
        except local_source_connect.LocalSourceConnectError:
            pass
        else:
            raise RuntimeError(f"authorize_local_source_connect did not reject a {label} request")
        if provider.calls != 0:
            raise RuntimeError(f"snapshot provider was contacted for a {label} request")
        evidence.append(f"consent_probe_rejected:{label}:provider_calls=0")

    return evidence


def probe_j3(context: ProbeContext) -> StepResult:
    """J3 Connect: exact connect routes, snapshot binding, and consent-before-read."""
    executor_registry = _import_outside_repo(
        "core.engine.core.intelligence_build_executor_registry", context.repository_root
    )
    api_main = _import_outside_repo("core.engine.api.main", context.repository_root)
    snapshot_registry = _import_outside_repo(
        "core.engine.core.source_snapshot_provider_registry", context.repository_root
    )
    snapshot_port = _import_outside_repo("ace.application.source_snapshot_provider", context.repository_root)

    evidence: list[str] = []

    entry_point_names = sorted(
        entry_point.name for entry_point in importlib.metadata.entry_points(group=_BUILDER_ENTRY_POINT_GROUP)
    )
    evidence.append(
        f"executor_entry_points[{_BUILDER_ENTRY_POINT_GROUP}]:"
        + (",".join(entry_point_names) if entry_point_names else "(none)")
    )

    loaded = executor_registry.load_installed_intelligence_build_executors()
    evidence.append("executors_loaded:" + (",".join(sorted(loaded)) if loaded else "(none)"))
    executor_present = _PERSONAL_PROFILE_ID in loaded

    connect_routes = _qualified_connect_routes(api_main)
    evidence.append("connect_routes:" + (",".join(connect_routes) if connect_routes else "(none)"))
    connect_routes_complete = set(connect_routes) == set(_REQUIRED_CONNECT_ROUTES)

    snapshot_group = snapshot_registry.SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP
    snapshot_entry_points = sorted(
        entry_point.name for entry_point in importlib.metadata.entry_points(group=snapshot_group)
    )
    evidence.append(
        f"snapshot_entry_points[{snapshot_group}]:"
        + (",".join(snapshot_entry_points) if snapshot_entry_points else "(none)")
    )

    snapshot_available = False
    try:
        loaded_providers = snapshot_registry.load_installed_source_snapshot_providers()
        evidence.append(
            "snapshot_providers_loaded:" + (",".join(sorted(loaded_providers)) if loaded_providers else "(none)")
        )
        provider = snapshot_registry.resolve_source_snapshot_provider()
        if provider is None:
            evidence.append("snapshot_binding:unavailable:no_installed_source_snapshot_provider")
        else:
            artifact = snapshot_port.validate_source_snapshot_provider_registration(provider)
            evidence.append(
                f"snapshot_provider_artifact:{artifact.capability}:{artifact.contract}:"
                f"{artifact.implementation_id}=={artifact.implementation_version}:{artifact.artifact_digest}"
            )
            evidence.extend(_prepare_snapshot_activation(context, artifact))
            snapshot_available = True
    except Exception as exc:  # noqa: BLE001 - a broken snapshot seam must not hide the other J3 evidence
        evidence.append(f"snapshot_binding:unavailable:{type(exc).__name__}: {exc}")

    consent_probe_passed = False
    try:
        evidence.extend(_consent_before_read_probe(context))
        consent_probe_passed = True
    except Exception as exc:  # noqa: BLE001 - a broken consent seam must not hide the other J3 evidence
        evidence.append(f"consent_probe:unavailable:{type(exc).__name__}: {exc}")

    evidence.append(f"executor_present:{executor_present} (visible only, does not gate J3)")

    if snapshot_available and connect_routes_complete and consent_probe_passed:
        return StepResult(
            step_id="J3",
            name=STEP_NAMES["J3"],
            status=StepStatus.PASS,
            summary=(
                "Connect verified: snapshot binding, both exact connect routes, and consent-before-read all pass."
            ),
            evidence=tuple(evidence),
        )

    missing = [
        label
        for label, present in (
            ("snapshot", snapshot_available),
            ("connect_routes", connect_routes_complete),
            ("consent_probe", consent_probe_passed),
        )
        if not present
    ]
    return StepResult(
        step_id="J3",
        name=STEP_NAMES["J3"],
        status=StepStatus.FAIL,
        summary=f"Connect wall: missing {', '.join(missing)} on main.",
        evidence=tuple(evidence),
        blocker="F5-F10:missing_" + "_".join(missing),
    )


STUB_PROVIDER_SWITCH = "PI13_WS0_STUB_PROVIDER"
_PROVIDER_BASE_URL_ENV = "OPENAI_COMPAT_BASE_URL"
_PERSONAL_SOURCE_GROUP_ID = "personal_local_sources"
# One scope per kind the Personal onboarding profile advertises; the pack maps
# exactly these four (proven by tests/intelligence/test_personal_intelligence_pack_source_mapping.py).
_PERSONAL_MAPPING_SCOPES: tuple[dict[str, Any], ...] = (
    {"mapping_id": "local_markdown_note", "include": ["notes/*.md"]},
    {"mapping_id": "local_pdf_page", "include": ["*.pdf"]},
    {"mapping_id": "local_csv_row", "include": ["*.csv"]},
    {"mapping_id": "local_json_pointer", "include": ["*.json"]},
)
_ADVERTISED_SOURCE_KINDS: tuple[str, ...] = ("csv", "json", "md", "pdf")
_PERSONAL_OUTCOME_ID = "personal_orientation"
_PERSONAL_CADENCE_ID = "daily"
_OBSERVE_READ_GRANT_REF = "authority_grant:atrium-observe-read"
_FEEDBACK_GRANT_REF = "authority_grant:atrium-resource-feedback"
_EXPORT_GRANT_REF = "authority_grant:personal-export"
_DELETE_GRANT_REF = "authority_grant:personal-delete"
_BUILDS = "/v1/intelligence/builds"


def configure_stub_provider_environment() -> StubProviderServer | None:
    """Bind WS0's deterministic provider through the production selection path.

    The gate never injects a provider object. It starts the loopback
    OpenAI-compatible stub and publishes it through ``OPENAI_COMPAT_BASE_URL``
    so ``get_llm()`` selects ``OpenAICompatProvider`` exactly as an operator's
    own endpoint would be selected. It also plays ``ace setup``'s one
    bootstrapping role -- writing the local owner's API key -- so the walk can
    log in through ``/auth/token`` like the CLI does. An operator-set base URL
    is never overridden, and ``PI13_WS0_STUB_PROVIDER=0`` disables the stub.
    """

    if os.environ.get(STUB_PROVIDER_SWITCH, "1") == "0":
        return None
    os.environ.setdefault("API_KEY", secrets.token_hex(24))
    if os.environ.get(_PROVIDER_BASE_URL_ENV):
        return None
    server = StubProviderServer().start()
    os.environ[_PROVIDER_BASE_URL_ENV] = server.base_url
    return server


class _Clock:
    """Strictly increasing UTC instants that never run ahead of real time.

    Every durable transition must order exactly, and every artifact the walk
    stamps must already be available at the server's real ``now`` -- later
    reads (``/start`` evaluates at server-now) cannot see material dated in
    the future. Microsecond precision keeps both properties without drift.
    """

    def __init__(self) -> None:
        self._last = datetime.now(UTC) - timedelta(seconds=1)

    def now(self) -> datetime:
        current = datetime.now(UTC)
        while current <= self._last:  # wait for real time to pass; never stamp the future
            current = datetime.now(UTC)
        self._last = current
        return current

    def iso(self) -> str:
        return self.now().isoformat()


class _WalkStopped(RuntimeError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


def _json(model: object) -> Any:
    return json.loads(model.model_dump_json())  # type: ignore[attr-defined]


def _payload_of(item: dict[str, Any]) -> dict[str, Any] | None:
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None
    value_json = payload.get("value_json")
    if not isinstance(value_json, str):
        return None
    try:
        parsed = json.loads(value_json)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _relative_source_path(source_uri: str, *, corpus_root: Path) -> str | None:
    """Return the corpus-relative path for one admitted local source URI, else None."""

    path = source_uri.split("://", 1)[-1]
    if path.rsplit(".", 1)[-1].lower() not in _ADVERTISED_SOURCE_KINDS:
        return None
    root = str(corpus_root)
    return path[len(root) :].lstrip("/") if path.startswith(root) else path.lstrip("/")


def _source_kind(relative_path: str) -> str:
    return relative_path.rsplit(".", 1)[-1].lower()


def _snapshot_source_paths(items: list[dict[str, Any]], *, corpus_root: Path) -> dict[str, str]:
    """Map each admitted snapshot reference to its corpus-relative source path.

    ``source_health`` is the projected surface carrying an admitted source's own
    identity: its payload binds ``source_snapshot_ref`` -- the exact value an
    Observation and a Brief citation both use as ``source_ref`` -- to the
    ``source_uri`` that was authorized and read.
    """

    paths: dict[str, str] = {}
    for item in items:
        if str(item.get("reference", {}).get("resource_kind")) != "source_health":
            continue
        payload = _payload_of(item) or {}
        snapshot_ref = payload.get("source_snapshot_ref")
        source_uri = payload.get("source_uri")
        if not isinstance(snapshot_ref, str) or not isinstance(source_uri, str):
            continue
        relative = _relative_source_path(source_uri, corpus_root=corpus_root)
        if relative is not None:
            paths[snapshot_ref] = relative
    return paths


async def _probe_grounded_ask(post, *, clock: _Clock) -> dict[str, Any]:
    """Ask a corpus-answerable question, and prove an unanswerable one refuses.

    A connected cited answer is the half J7 could never reach before; the honest
    no-answer half must keep working beside it.
    """

    at = clock.iso()

    async def ask(question: str) -> dict[str, Any]:
        return await post(
            "ask",
            "/v1/intelligence/ask",
            {
                "authority_grant_ref": _OBSERVE_READ_GRANT_REF,
                "question": question,
                "subject_refs": [],
                "as_of": at,
                "available_at": at,
                "max_claims": 5,
            },
        )

    answered = await ask("What do my admitted local sources currently say?")
    refused = await ask("Which harbour did the schooner Amelia depart from in 1887?")
    answered_claims = answered.get("claims") or answered.get("answer_claims") or []
    citations = answered.get("citations") or []
    return {
        "answered": bool(answered_claims),
        "answer_claims": len(answered_claims),
        "answer_citations": len(citations),
        "refused_unanswerable": not (refused.get("claims") or refused.get("answer_claims")),
        "evidence": (
            f"answered_claims={len(answered_claims)};citations={len(citations)};"
            f"refused_unanswerable={not (refused.get('claims') or refused.get('answer_claims'))}"
        ),
    }


async def _probe_claim_correction(post, *, brief: dict[str, Any]) -> dict[str, Any]:
    """Bind a correction to one exact cited claim of the real Brief."""

    payload = _payload_of(brief) or {}
    reference = brief.get("reference") or {}
    cited = next(
        (item for item in payload.get("claims") or [] if item.get("grounding_kind") == "cited"),
        None,
    )
    if cited is None or not (cited.get("citation_ids") or []):
        return {"bound": False, "evidence": "no cited claim available to correct"}
    target = {
        "contract": "ace.intelligence.resource-plane-reference/v1alpha1",
        "product_id": reference["product_id"],
        "resource_kind": reference["resource_kind"],
        "resource_id": reference["resource_id"],
        "resource_digest": reference["resource_digest"],
        "resource_contract": reference["resource_contract"],
        "revision": reference["revision"],
        "as_of": reference["as_of"],
        "available_at": reference["available_at"],
    }
    admission = await post(
        "correction",
        "/v1/intelligence/ask/corrections",
        expect=(201,),
        body={
            "authority_grant_ref": _FEEDBACK_GRANT_REF,
            "request_key": "claim_correction:pi13-ws0-journey",
            "target": target,
            "claim_id": str(cited["claim_id"]),
            "citation_id": str((cited["citation_ids"])[0]),
            "correction_intent": "outdated",
            "note": "The owner reports this cited claim is out of date for the admitted corpus.",
            "evidence": [],
        },
    )
    return {
        "bound": True,
        "claim_id": str(cited["claim_id"]),
        "evidence": f"claim={cited['claim_id']};admission={admission.get('contract', 'recorded')}",
    }


def _resource_identities(items: list[dict[str, Any]]) -> tuple[tuple[str, str, str], ...]:
    """Exact (kind, id, digest) identity of every projected resource, order-independent."""

    return tuple(
        sorted(
            (
                str(item.get("reference", {}).get("resource_kind")),
                str(item.get("reference", {}).get("resource_id")),
                str(item.get("reference", {}).get("resource_digest")),
            )
            for item in items
        )
    )


async def _probe_ownership(post, *, clock: _Clock) -> dict[str, Any]:
    """Export, preview deletion, confirm it, and prove the material does not reappear.

    Deletion is destructive, so this runs last in the walk.
    """

    export = await post(
        "ownership_export",
        "/v1/intelligence/ownership/export",
        {"authority_grant_ref": _EXPORT_GRANT_REF},
    )
    preview = await post(
        "ownership_delete_preview",
        "/v1/intelligence/ownership/deletion/preview",
        {"authority_grant_ref": _DELETE_GRANT_REF, "confirmation_window_seconds": 900},
    )
    confirmation = await post(
        "ownership_delete_confirm",
        "/v1/intelligence/ownership/deletion/confirm",
        {
            "authority_grant_ref": _DELETE_GRANT_REF,
            "preview": preview,
            "confirmation_digest": preview["confirmation_digest"],
        },
    )
    at = clock.iso()
    remaining = await post(
        "ownership_verify",
        "/v1/intelligence/resources/query",
        {
            "authority_grant_ref": _OBSERVE_READ_GRANT_REF,
            "resource_kinds": ["brief", "observation", "entity"],
            "subject_refs": [],
            "as_of": at,
            "available_at": at,
            "page_size": 200,
        },
    )
    survivors = len(remaining.get("items") or [])
    exported_records = int(export.get("record_count") or 0)
    previewed_records = int(preview.get("record_count") or 0)
    return {
        "exported": bool(export.get("contract")) and exported_records > 0,
        "export_records": exported_records,
        "previewed": previewed_records,
        "deletion_proved": bool(confirmation.get("proof")),
        "survivors_after_deletion": survivors,
        "evidence": (
            f"export_records={exported_records};preview_records={previewed_records};"
            f"proof={bool(confirmation.get('proof'))};survivors={survivors}"
        ),
    }


async def _run_installed_journey(context: ProbeContext, clock: _Clock) -> dict[str, Any]:
    """Drive the public route sequence from installed artifacts against the live SurrealDB."""

    root = context.repository_root
    evidence: list[str] = []
    state: dict[str, Any] = {
        "reached": "start",
        "error": None,
        "evidence": evidence,
        "inventory": None,
        "brief": None,
        "ask": None,
        "correction": None,
        "restart": None,
        "ownership": None,
    }

    def reached(step: str, note: str | None = None) -> None:
        state["reached"] = step
        evidence.append(f"{step}:{note}" if note else f"{step}:ok")

    api_main = _import_outside_repo("core.engine.api.main", root)
    db = _import_outside_repo("core.engine.core.db", root)
    catalog = _import_outside_repo("core.engine.core.installed_intelligence_catalog", root)
    planner_registry = _import_outside_repo("core.engine.core.intelligence_build_planner_registry", root)
    installed_packs = _import_outside_repo("ace.application.installed_pack_artifacts", root)
    snapshot_registry = _import_outside_repo("core.engine.core.source_snapshot_provider_registry", root)
    snapshot_port = _import_outside_repo("ace.application.source_snapshot_provider", root)
    connect_host = _import_outside_repo("core.engine.core.local_source_connect", root)
    first_run = _import_outside_repo("core.engine.core.local_first_run_bootstrap", root)
    builder_app = _import_outside_repo("ace.application.intelligence_builder", root)
    builder_contracts = _import_outside_repo("ace.application.intelligence_builder_contracts", root)
    agent_contracts = _import_outside_repo("ace.application.intelligence_agent_contracts", root)
    immutable = _import_outside_repo("core.engine.core.immutable_records", root)
    httpx = importlib.import_module("httpx")

    api_key = os.environ.get("API_KEY", "")
    if not api_key:
        raise _WalkStopped("token", "API_KEY is not set; the gate must play ace setup before login")

    await db.pool.init()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_main.app), base_url="http://ws0") as client:
            headers: dict[str, str] = {}

            async def post(
                step: str,
                path: str,
                body: dict[str, Any] | None = None,
                *,
                expect: tuple[int, ...] = (200,),
            ) -> dict[str, Any]:
                response = await client.post(path, json=body or {}, headers=headers)
                if response.status_code not in expect:
                    raise _WalkStopped(step, f"{path}: {response.status_code} {response.text[:600]}")
                return response.json()

            token = (await post("token", "/auth/token", {"api_key": api_key}))["token"]
            headers["Authorization"] = f"Bearer {token}"
            reached("token", "issued_via_/auth/token")

            bootstrap = await post("owner_bootstrap", "/auth/local-owner/bootstrap", {})
            grants = bootstrap.get("grants") or []
            cognition = bootstrap.get("cognition") or []
            reached(
                "owner_bootstrap",
                "grants="
                + ",".join(f"{g.get('grant_ref')}:{g.get('state')}" for g in grants)
                + ";cognition="
                + ",".join(f"{c.get('state_id', c.get('capability', '?'))}:{c.get('state')}" for c in cognition),
            )

            installed = {item.profile.profile_id: item for item in catalog.discover_installed_onboarding_profiles()}
            personal = installed.get(_PERSONAL_PROFILE_ID)
            if personal is None:
                raise _WalkStopped("profile", f"{_PERSONAL_PROFILE_ID} is not installed")
            profile_digest = personal.profile.profile_digest
            planner_registry.load_installed_intelligence_build_planners()
            planner = planner_registry.resolve_intelligence_build_planner(_PERSONAL_PROFILE_ID)
            if planner is None:
                raise _WalkStopped("profile", "Personal planner did not resolve")
            resolver = installed_packs.InstalledCompiledPackArtifactResolver.discover(_installed_distributions_exact())
            artifact = await resolver.resolve_exact(reference=planner.pack_reference)
            if artifact is None:
                raise _WalkStopped("profile", "exact installed Personal pack did not resolve")
            pack = artifact.pack
            reached("profile", f"{_PERSONAL_PROFILE_ID}:{profile_digest}")

            preview = await post(
                "connect_preview",
                f"{_BUILDS}/connect/preview",
                {
                    "profile_id": _PERSONAL_PROFILE_ID,
                    "profile_digest": profile_digest,
                    "source_group_id": _PERSONAL_SOURCE_GROUP_ID,
                    "authorized_root": str(context.fixture_corpus),
                    "mapping_scopes": [dict(scope) for scope in _PERSONAL_MAPPING_SCOPES],
                    "exclude": [],
                },
            )
            reached(
                "connect_preview",
                f"read_only={preview.get('read_only')};mode={preview.get('acquisition_mode')};"
                f"network={preview.get('network_capture_performed')};write={preview.get('write_access_requested')}",
            )

            authorized_at = clock.now()
            connect_result = await post(
                "connect_authorize",
                f"{_BUILDS}/connect/authorize",
                {"preview": preview, "authorized": True, "authorized_at": authorized_at.isoformat()},
            )
            captures = connect_result.get("captures") or []
            if len(captures) < 2:
                raise _WalkStopped("connect_authorize", f"expected >=2 Markdown captures, got {len(captures)}")
            reached("connect_authorize", "captures=" + ",".join(str(c.get("relative_path")) for c in captures))
            connect_request = _json(
                connect_host.LocalSourceConnectAuthorizationHostRequest(
                    preview=preview, authorized=True, authorized_at=authorized_at
                ).exact_request()
            )
            selection_refs = [
                {
                    "source_group_id": c["selection"]["source_group_id"],
                    "selection_id": c["selection"]["selection_id"],
                    "selection_digest": c["selection"]["selection_digest"],
                }
                for c in captures
            ]

            plan = await post(
                "prepare",
                f"{_BUILDS}/prepare",
                {
                    "client_request_id": "atrium_request:pi13-ws0-journey",
                    "profile_id": _PERSONAL_PROFILE_ID,
                    "profile_digest": profile_digest,
                    "subject": "Keep me oriented in my own authorized local notes.",
                    "outcome_id": _PERSONAL_OUTCOME_ID,
                    "source_group_ids": [_PERSONAL_SOURCE_GROUP_ID],
                    "recorded_source_selection_refs": selection_refs,
                    "cadence_id": _PERSONAL_CADENCE_ID,
                    "requested_at": clock.iso(),
                },
            )
            reached(
                "prepare",
                f"plan_id={plan.get('plan_id')};selections={len(plan.get('recorded_source_selections') or [])}",
            )

            provider = snapshot_registry.resolve_source_snapshot_provider()
            if provider is None:
                raise _WalkStopped("bind", "no installed source snapshot provider")
            provider_artifact = snapshot_port.validate_source_snapshot_provider_registration(provider)
            requirements = [
                item
                for item in pack.capability_requirements
                if item.capability == provider_artifact.capability and item.contract == provider_artifact.contract
            ]
            if len(requirements) != 1:
                raise _WalkStopped("bind", f"expected one snapshot capability requirement, found {len(requirements)}")
            requirement = requirements[0]
            bound = await post(
                "bind",
                f"{_BUILDS}/bind",
                {
                    "plan": plan,
                    "capability_bindings": [
                        {
                            "requirement_id": requirement.requirement_id,
                            "capability": requirement.capability,
                            "contract": requirement.contract,
                            "implementation_id": provider_artifact.implementation_id,
                            "implementation_version": provider_artifact.implementation_version,
                            "artifact_digest": provider_artifact.artifact_digest,
                        }
                    ],
                    "authority_bindings": [
                        json.loads(item.model_dump_json())
                        for item in first_run.local_owner_authority_bindings(pack.authority_requests)
                    ],
                    "bound_at": clock.iso(),
                },
            )
            reached("bind", f"bound_plan_id={bound.get('bound_plan_id')}")

            authority = await post(
                "first_run_bootstrap",
                f"{_BUILDS}/bootstrap/local-first-run",
                {"decision": "approve", "bound_plan": bound, "approved_at": clock.iso()},
            )
            receipt_ref = authority["approval"]["receipt_ref"]
            start_request = authority["start_request"]
            reached("first_run_bootstrap", f"approval={receipt_ref};resumed={authority.get('resumed')}")

            associated = await post(
                "session_associate",
                f"{_BUILDS}/session/associate",
                {"bound_plan": bound, "approval_receipt_ref": receipt_ref},
            )
            session = associated["session"]
            reached("session_associate", f"session={session.get('session_id')};stage={session.get('stage')}")

            connect = {"connect_request": connect_request, "connect_result": connect_result}
            proposed = await post(
                "builder_source_propose",
                f"{_BUILDS}/builder/source/propose",
                {**connect, "current": session, "occurred_at": clock.iso()},
            )
            reached("builder_source_propose", f"stage={proposed['session_revision'].get('stage')}")
            connected = await post(
                "builder_source_approve_connect",
                f"{_BUILDS}/builder/source/approve-connect",
                {
                    **connect,
                    "approval": {
                        "decision": "approve",
                        "current": proposed["session_revision"],
                        "proposal": proposed["proposal"],
                        "approved_at": clock.iso(),
                    },
                },
            )
            if connected.get("blocked_reason") is not None:
                raise _WalkStopped("builder_source_approve_connect", f"blocked: {connected['blocked_reason']}")
            reached("builder_source_approve_connect", f"stage={connected['session_revision'].get('stage')}")
            concept_proposed = await post(
                "builder_concept_propose",
                f"{_BUILDS}/builder/concept/propose",
                {
                    "current": connected["session_revision"],
                    "source_profile": connected["profile"],
                    "user_intent": "Understand what my authorized local notes are about and what currently matters.",
                    "organization_terminology": [],
                    "proposed_at": clock.iso(),
                },
            )
            reached("builder_concept_propose", f"stage={concept_proposed['session_revision'].get('stage')}")
            concept_approved = await post(
                "builder_concept_approve",
                f"{_BUILDS}/builder/concept/approve",
                {
                    "decision": "approve",
                    "current": concept_proposed["session_revision"],
                    "proposal": concept_proposed["proposal"],
                    "approved_at": clock.iso(),
                },
            )
            reached("builder_concept_approve", f"stage={concept_approved['session_revision'].get('stage')}")
            intelligence_proposed = await post(
                "builder_intelligence_propose",
                f"{_BUILDS}/builder/intelligence/propose",
                {
                    **connect,
                    "current": concept_approved["session_revision"],
                    "source_profile": connected["profile"],
                    "concept_model": concept_approved["proposal"],
                    "concept_disposition": concept_approved["disposition"],
                    "user_intent": "Watch material changes in my authorized local notes.",
                    "audience_constraints": ["Review material changes without executing decisions."],
                    "cadence_constraints": ["daily"],
                    "proposed_at": clock.iso(),
                },
            )
            reached("builder_intelligence_propose", f"stage={intelligence_proposed['session_revision'].get('stage')}")
            intelligence_approved = await post(
                "builder_intelligence_approve",
                f"{_BUILDS}/builder/intelligence/approve",
                {
                    "decision": "approve",
                    "current": intelligence_proposed["session_revision"],
                    "proposal": intelligence_proposed["proposal"],
                    "approved_at": clock.iso(),
                },
            )
            reached("builder_intelligence_approve", f"stage={intelligence_approved['session_revision'].get('stage')}")

            # The exact admitted observation set is durable Builder material. No
            # public route returns it yet (a WS6-relevant surface gap recorded in
            # the tracker); the gate reopens it read-only from the installed
            # session service rather than authoring it.
            current = builder_contracts.IntelligenceBuilderSessionRevisionV1.model_validate(
                intelligence_approved["session_revision"], strict=False
            )
            observation_ref = next(
                (
                    item
                    for item in current.artifacts
                    if item.artifact_kind is builder_contracts.OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET
                ),
                None,
            )
            if observation_ref is None:
                raise _WalkStopped("observation_reopen", "session carries no authorized observation set artifact")
            sessions = builder_app.IntelligenceBuilderSessionService(
                store=immutable.SurrealImmutableRecordStore(db.pool)
            )
            observations = await sessions.load_artifact(
                product_id=current.product_id,
                reference=observation_ref,
                artifact_type=agent_contracts.AuthorizedObservationSetV1,
                available_at=clock.now(),
            )
            reached("observation_reopen", f"observations={len(observations.observations)}")

            briefing = await post(
                "builder_first_brief_prepare",
                f"{_BUILDS}/builder/first-brief/prepare",
                {
                    "current": intelligence_approved["session_revision"],
                    "concept_model": concept_approved["proposal"],
                    "concept_disposition": concept_approved["disposition"],
                    "intelligence_model": intelligence_approved["proposal"],
                    "intelligence_disposition": intelligence_approved["disposition"],
                    "observations": _json(observations),
                    "generated_at": clock.iso(),
                },
            )
            briefing_ready = briefing["session_revision"]
            reached("builder_first_brief_prepare", f"stage={briefing_ready.get('stage')}")

            await post(
                "activation_plan_prepare",
                f"{_BUILDS}/activation-plan/prepare",
                {"current": briefing_ready, "bound_plan": bound, "requested_at": clock.iso()},
            )
            reached("activation_plan_prepare")
            commit = await post(
                "activation_plan_approve",
                f"{_BUILDS}/activation-plan/approve",
                {"decision": "approve", "current": briefing_ready, "bound_plan": bound, "approved_at": clock.iso()},
            )
            reached("activation_plan_approve", f"activation_key={commit.get('activation_key')}")
            activated = await post(
                "activation_plan_activate",
                f"{_BUILDS}/activation-plan/activate",
                {"bound_plan": bound, "activation_approval_receipt_ref": receipt_ref, "requested_at": clock.iso()},
            )
            reached("activation_plan_activate", f"replayed={activated.get('replayed')};session=ACTIVE")

            started = await post("start", f"{_BUILDS}/start", start_request)
            build_page = started.get("resource_page") or {}
            build_counts: dict[str, int] = {}
            for item in build_page.get("items") or []:
                kind = str(item.get("reference", {}).get("resource_kind"))
                build_counts[kind] = build_counts.get(kind, 0) + 1
            reached(
                "start",
                f"page_state={build_page.get('state')};items="
                + ",".join(f"{k}={v}" for k, v in sorted(build_counts.items())),
            )

            # J4 is what the owner can actually inspect after the build, so the
            # gate reads the resource plane itself rather than trusting the
            # build's own page (which is projected at the corpus cut).
            inventory_at = clock.iso()
            inventory_page = await post(
                "inventory_query",
                "/v1/intelligence/resources/query",
                {
                    "authority_grant_ref": _OBSERVE_READ_GRANT_REF,
                    "resource_kinds": ["source_health", "entity", "observation"],
                    "subject_refs": [],
                    "as_of": inventory_at,
                    "available_at": inventory_at,
                    "page_size": 200,
                },
            )
            inventory_items = inventory_page.get("items") or []
            counts: dict[str, int] = {}
            for item in inventory_items:
                kind = str(item.get("reference", {}).get("resource_kind"))
                counts[kind] = counts.get(kind, 0) + 1
            source_paths = _snapshot_source_paths(inventory_items, corpus_root=context.fixture_corpus)
            locators = [
                relative
                for item in inventory_items
                if str(item.get("reference", {}).get("resource_kind")) == "observation"
                and (relative := source_paths.get(str((_payload_of(item) or {}).get("source_ref")))) is not None
            ]
            state["inventory"] = {
                "source_health": counts.get("source_health", 0),
                "entity": counts.get("entity", 0),
                "observation": counts.get("observation", 0),
                "observation_locators": sorted(locators),
                "observation_kinds": sorted({_source_kind(item) for item in locators}),
            }
            reached(
                "inventory_query",
                f"page_state={inventory_page.get('state')};"
                f"degraded={inventory_page.get('degraded_reason_refs')};"
                + "items="
                + ",".join(f"{k}={v}" for k, v in sorted(counts.items())),
            )

            query_at = clock.iso()
            brief_page = await post(
                "brief_query",
                "/v1/intelligence/resources/query",
                {
                    "authority_grant_ref": _OBSERVE_READ_GRANT_REF,
                    "resource_kinds": ["brief"],
                    "subject_refs": [],
                    "as_of": query_at,
                    "available_at": query_at,
                    "page_size": 50,
                },
            )
            briefs = [
                item
                for item in brief_page.get("items") or []
                if item.get("reference", {}).get("resource_kind") == "brief"
            ]
            cited_claims = uncited_claims = unresolved = 0
            citation_sources: set[str] = set()
            for item in briefs:
                payload = _payload_of(item) or {}
                citations = {str(c.get("citation_id")): c for c in payload.get("citations") or []}
                for claim in payload.get("claims") or []:
                    if claim.get("grounding_kind") != "cited":
                        continue
                    ids = claim.get("citation_ids") or []
                    if not ids:
                        uncited_claims += 1
                        continue
                    cited_claims += 1
                    for citation_id in ids:
                        source_ref = str(citations.get(citation_id, {}).get("source_ref"))
                        relative = source_paths.get(source_ref)
                        if relative is None:
                            unresolved += 1
                        else:
                            citation_sources.add(relative)
            state["brief"] = {
                "count": len(briefs),
                "cited_claims": cited_claims,
                "uncited_claims": uncited_claims,
                "citation_sources": sorted(citation_sources),
                "citation_kinds": sorted({_source_kind(item) for item in citation_sources}),
                "unresolved_citations": unresolved,
            }
            reached("brief_queried", f"briefs={len(briefs)};cited_claims={cited_claims};uncited={uncited_claims}")

            # J7/J8 only become answerable once a cited Brief exists, which it now
            # does. Both are exercised against that exact Brief.
            state["ask"] = await _probe_grounded_ask(post, clock=clock)
            reached("ask", state["ask"]["evidence"])
            if briefs:
                state["correction"] = await _probe_claim_correction(post, brief=briefs[0])
                reached("correction", state["correction"]["evidence"])

            # J9 before J10: the ownership probe deletes the very material a
            # restart must be able to reopen.
            before = _resource_identities(inventory_items + briefs)
            await db.pool.close()
            await db.pool.init()
            reopen_at = clock.iso()
            reopened = await post(
                "restart_reopen",
                "/v1/intelligence/resources/query",
                {
                    "authority_grant_ref": _OBSERVE_READ_GRANT_REF,
                    "resource_kinds": ["source_health", "entity", "observation", "brief"],
                    "subject_refs": [],
                    "as_of": reopen_at,
                    "available_at": reopen_at,
                    "page_size": 200,
                },
            )
            after = _resource_identities(reopened.get("items") or [])
            state["restart"] = {
                "reopened_identically": before == after,
                "before": len(before),
                "after": len(after),
                "evidence": f"before={len(before)};after={len(after)};identical={before == after}",
            }
            reached("restart_reopen", state["restart"]["evidence"])

            state["ownership"] = await _probe_ownership(post, clock=clock)
            reached("ownership", state["ownership"]["evidence"])
    except _WalkStopped as exc:
        # Keep everything the walk already proved. A step that fails late must not
        # erase the evidence earlier steps produced, or the report would call a
        # passing step failed.
        state["reached"] = exc.step
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            await db.pool.close()
        except Exception:  # noqa: BLE001 - teardown must not mask the walk's own outcome
            pass
    return state


_WALK_RESULTS: dict[str, dict[str, Any]] = {}


def _installed_journey_walk(context: ProbeContext) -> dict[str, Any]:
    """Run the installed walk once per gate run; later probes reuse the same result."""

    key = str(context.json_report)
    cached = _WALK_RESULTS.get(key)
    if cached is not None:
        return cached
    clock = _Clock()
    try:
        result = asyncio.run(_run_installed_journey(context, clock))
    except _WalkStopped as exc:
        result = {
            "reached": exc.step,
            "error": f"{type(exc).__name__}: {exc}",
            "evidence": [],
            "inventory": None,
            "brief": None,
        }
    except Exception as exc:  # noqa: BLE001 - the walk must report, never crash the gate
        result = {
            "reached": "walk_error",
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}",
            "evidence": [],
            "inventory": None,
            "brief": None,
            "ask": None,
            "correction": None,
            "restart": None,
            "ownership": None,
        }
    _WALK_RESULTS[key] = result
    return result


def _walk_evidence(walk: dict[str, Any]) -> tuple[str, ...]:
    evidence = list(walk.get("evidence") or [])
    if walk.get("error"):
        evidence.append(f"walk_error_at_{walk.get('reached')}: {walk['error']}")
    return tuple(evidence)


def probe_j4(context: ProbeContext) -> StepResult:
    """J4 Inventory: the installed walk must produce real Markdown-grounded inventory."""
    walk = _installed_journey_walk(context)
    inventory = walk.get("inventory")
    if walk.get("error") and inventory is None:
        return StepResult(
            step_id="J4",
            name=STEP_NAMES["J4"],
            status=StepStatus.FAIL,
            summary=f"Inventory failed: the installed journey walk stopped at {walk.get('reached')}.",
            evidence=_walk_evidence(walk),
            blocker=f"WS0:journey_walk:{walk.get('reached')}",
        )
    inventory = inventory or {}
    summary_counts = (
        f"source_health={inventory.get('source_health', 0)} entity={inventory.get('entity', 0)} "
        f"observation={inventory.get('observation', 0)}"
    )
    locators = list(inventory.get("observation_locators") or [])
    kinds = list(inventory.get("observation_kinds") or [])
    evidence = (
        *_walk_evidence(walk),
        f"inventory:{summary_counts}",
        "observation_locators:" + ",".join(locators),
        "observation_kinds:" + ",".join(kinds),
    )
    if (
        inventory.get("source_health", 0) < 1
        or inventory.get("entity", 0) < 1
        or inventory.get("observation", 0) < 2
        or len(locators) < 2
    ):
        return StepResult(
            step_id="J4",
            name=STEP_NAMES["J4"],
            status=StepStatus.FAIL,
            summary=f"Inventory empty or unresolved to admitted sources: {summary_counts}.",
            evidence=evidence,
            blocker="WS0:inventory_empty",
        )
    missing = [kind for kind in _ADVERTISED_SOURCE_KINDS if kind not in kinds]
    if missing:
        return StepResult(
            step_id="J4",
            name=STEP_NAMES["J4"],
            status=StepStatus.FAIL,
            summary=f"Inventory covers only {','.join(kinds)}; the profile advertises {','.join(_ADVERTISED_SOURCE_KINDS)}.",
            evidence=(*evidence, "missing_source_kinds:" + ",".join(missing)),
            blocker="WS0:inventory_source_kinds_incomplete",
        )
    return StepResult(
        step_id="J4",
        name=STEP_NAMES["J4"],
        status=StepStatus.PASS,
        summary=(
            f"Inventory verified from installed artifacts: {summary_counts}; every observation resolves to an "
            f"admitted source across {','.join(kinds)}."
        ),
        evidence=evidence,
    )


def probe_j5(context: ProbeContext) -> StepResult:
    """J5 First Brief: a Brief exists and every cited claim resolves to a Markdown observation."""
    walk = _installed_journey_walk(context)
    brief = walk.get("brief")
    if brief is None:
        return StepResult(
            step_id="J5",
            name=STEP_NAMES["J5"],
            status=StepStatus.BLOCKED,
            summary=f"First Brief blocked: the installed journey walk stopped at {walk.get('reached')} before a Brief.",
            evidence=_walk_evidence(walk),
            blocker=f"J4/WS0:journey_walk:{walk.get('reached')}",
        )
    counts = (
        f"briefs={brief.get('count', 0)} cited_claims={brief.get('cited_claims', 0)} "
        f"uncited_claims={brief.get('uncited_claims', 0)} unresolved_citations={brief.get('unresolved_citations', 0)}"
    )
    sources = list(brief.get("citation_sources") or [])
    citation_kinds = list(brief.get("citation_kinds") or [])
    evidence = (
        *_walk_evidence(walk),
        f"brief:{counts}",
        "citation_sources:" + ",".join(sources),
        "citation_kinds:" + ",".join(citation_kinds),
    )
    if brief.get("count", 0) < 1:
        return StepResult(
            step_id="J5",
            name=STEP_NAMES["J5"],
            status=StepStatus.FAIL,
            summary="First Brief missing: the build completed without a Brief resource.",
            evidence=evidence,
            blocker="WS0:brief_missing",
        )
    if brief.get("uncited_claims", 0) > 0 or brief.get("cited_claims", 0) < 1:
        return StepResult(
            step_id="J5",
            name=STEP_NAMES["J5"],
            status=StepStatus.FAIL,
            summary=f"First Brief has material claims without citations: {counts}.",
            evidence=evidence,
            blocker="WS0:brief_claims_uncited",
        )
    if brief.get("unresolved_citations", 0) > 0 or not sources:
        return StepResult(
            step_id="J5",
            name=STEP_NAMES["J5"],
            status=StepStatus.FAIL,
            summary=f"First Brief citations do not resolve to admitted Markdown observations: {counts}.",
            evidence=evidence,
            blocker="WS0:brief_citations_unresolved",
        )
    missing_kinds = [kind for kind in _ADVERTISED_SOURCE_KINDS if kind not in citation_kinds]
    if missing_kinds:
        return StepResult(
            step_id="J5",
            name=STEP_NAMES["J5"],
            status=StepStatus.FAIL,
            summary=(
                f"First Brief cites only {','.join(citation_kinds)}; the profile advertises "
                f"{','.join(_ADVERTISED_SOURCE_KINDS)}."
            ),
            evidence=(*evidence, "missing_citation_kinds:" + ",".join(missing_kinds)),
            blocker="WS0:brief_citation_kinds_incomplete",
        )
    return StepResult(
        step_id="J5",
        name=STEP_NAMES["J5"],
        status=StepStatus.PASS,
        summary=(
            f"First Brief verified from installed artifacts: {counts}; citations resolve to admitted spans across "
            f"{','.join(citation_kinds)}."
        ),
        evidence=evidence,
    )


def probe_j6(context: ProbeContext) -> StepResult:
    """J6 Change: the substrate can now detect a revision; no public surface admits one."""
    return StepResult(
        step_id="J6",
        name=STEP_NAMES["J6"],
        status=StepStatus.BLOCKED,
        summary=(
            "Change blocked: content-revision detection, the Pack's declared detectors, and the executor's "
            "Brief-revision routing all exist, but no public surface admits a second capture of an edited "
            "source, so nothing can reach them."
        ),
        evidence=(
            "Core declares the content-revision detector family and resolves the prior_snapshot baseline "
            "its rules declare",
            "the Personal Pack declares personal_note_revised and personal_document_revised over the mapped "
            "body attribute",
            "the Personal executor compares every admitted entity against its prior state and routes an "
            "append-only Brief revision for a material Shift",
            "a second PREPARED build cannot carry new captures: DurableIntelligenceBuildHostComposer binds "
            "the ACTIVE Builder session to one exact activation approval, and a start request's selections "
            "come from that approval's own bound plan, so newly captured material has no admitted path",
            "the substrate's continuous-update path is live source ingress "
            "(ace.application.live_source_ingress through the live intelligence bridge), which the API "
            "exposes through no public route and which the Personal journey does not compose",
            "no refresh, re-ingest, or watch route exists on the public surface",
        ),
        blocker="WS5:public_reingest_surface_unavailable",
    )


def _api_route_paths(context: ProbeContext) -> set[str]:
    api_main = _import_outside_repo("core.engine.api.main", context.repository_root)
    return _openapi_paths(api_main)


def probe_j7(context: ProbeContext) -> StepResult:
    """J7 Ask: a cited answer from the admitted corpus, and an honest refusal beside it."""
    walk = _installed_journey_walk(context)
    ask = walk.get("ask")
    if ask is None:
        return StepResult(
            step_id="J7",
            name=STEP_NAMES["J7"],
            status=StepStatus.BLOCKED,
            summary=f"Ask blocked: the installed journey walk stopped at {walk.get('reached')} before asking.",
            evidence=_walk_evidence(walk),
            blocker=f"J5/WS0:journey_walk:{walk.get('reached')}",
        )
    evidence = (*_walk_evidence(walk), f"ask:{ask.get('evidence')}")
    if ask.get("answered", False) and ask.get("answer_citations", 0) < 1:
        return StepResult(
            step_id="J7",
            name=STEP_NAMES["J7"],
            status=StepStatus.FAIL,
            summary="Ask returned claims without citations, which is an answer beyond its evidence.",
            evidence=evidence,
            blocker="WS0:ask_answered_without_citations",
        )
    if not ask.get("answered", False):
        return StepResult(
            step_id="J7",
            name=STEP_NAMES["J7"],
            status=StepStatus.PARTIAL,
            summary="Ask produced no connected cited answer from the admitted corpus.",
            evidence=evidence,
            blocker="WS0:connected_cited_answer_unavailable",
        )
    if not ask.get("refused_unanswerable", False):
        return StepResult(
            step_id="J7",
            name=STEP_NAMES["J7"],
            status=StepStatus.PARTIAL,
            summary=(
                "Ask produces connected cited answers, but its honest refusal cannot be demonstrated: a "
                "lexically disjoint question was still answered."
            ),
            evidence=(
                *evidence,
                "GroundedAskService scores a claim by the raw token overlap between the question and the "
                "claim statement, with no stopword filtering and a score>0 threshold, so a single shared "
                "common word such as 'the' or 'in' is enough to answer",
                "the returned claims are real and cited -- this is a relevance weakness, not fabrication -- "
                "but it means missing_coverage:no_claims_matched_question_terms is rarely reachable once a "
                "corpus exists",
                "narrowing that scoring would change the substrate's released retrieval behaviour, which "
                "this continuation is explicitly forbidden to do, so it is reported rather than repaired",
            ),
            blocker="WS0:ask_refusal_not_demonstrable",
        )
    return StepResult(
        step_id="J7",
        name=STEP_NAMES["J7"],
        status=StepStatus.PASS,
        summary=(
            f"Ask verified from installed artifacts: {ask.get('answer_claims')} cited claim(s) with "
            f"{ask.get('answer_citations')} citation(s), and an unanswerable question refused."
        ),
        evidence=evidence,
    )


def probe_j8(context: ProbeContext) -> StepResult:
    """J8 Correct: a correction bound to one exact cited claim of a real Brief."""
    walk = _installed_journey_walk(context)
    correction = walk.get("correction")
    if correction is None:
        return StepResult(
            step_id="J8",
            name=STEP_NAMES["J8"],
            status=StepStatus.BLOCKED,
            summary=f"Correct blocked: the installed journey walk stopped at {walk.get('reached')} before a Brief.",
            evidence=_walk_evidence(walk),
            blocker=f"J5/WS0:journey_walk:{walk.get('reached')}",
        )
    evidence = (*_walk_evidence(walk), f"correction:{correction.get('evidence')}")
    if not correction.get("bound", False):
        return StepResult(
            step_id="J8",
            name=STEP_NAMES["J8"],
            status=StepStatus.PARTIAL,
            summary="Correction surface present, but no real cited claim was available to bind.",
            evidence=evidence,
            blocker="WS0:claim_bound_correction_unavailable",
        )
    return StepResult(
        step_id="J8",
        name=STEP_NAMES["J8"],
        status=StepStatus.PASS,
        summary=(
            "Correct verified from installed artifacts: a correction is bound to one exact cited claim of "
            "the admitted Brief and recorded as a proposal only."
        ),
        evidence=evidence,
    )


def probe_j9(context: ProbeContext) -> StepResult:
    """J9 Restart: every admitted resource reopens with its exact identity."""
    walk = _installed_journey_walk(context)
    restart = walk.get("restart")
    if restart is None:
        return StepResult(
            step_id="J9",
            name=STEP_NAMES["J9"],
            status=StepStatus.BLOCKED,
            summary=f"Restart blocked: the installed journey walk stopped at {walk.get('reached')}.",
            evidence=_walk_evidence(walk),
            blocker=f"J5/WS0:journey_walk:{walk.get('reached')}",
        )
    evidence = (
        *_walk_evidence(walk),
        f"restart:{restart.get('evidence')}",
        # Claim exactly what was proven and no more.
        "scope: the durable connection pool was closed and reopened and every resource re-resolved from "
        "storage; this is not a full service restart with a persisted volume, which the memory-only "
        "lane database cannot demonstrate",
    )
    if not restart.get("reopened_identically", False):
        return StepResult(
            step_id="J9",
            name=STEP_NAMES["J9"],
            status=StepStatus.FAIL,
            summary=(
                f"Restart changed durable material: {restart.get('before')} resources before, "
                f"{restart.get('after')} after."
            ),
            evidence=evidence,
            blocker="WS0:restart_material_changed",
        )
    return StepResult(
        step_id="J9",
        name=STEP_NAMES["J9"],
        status=StepStatus.PASS,
        summary=(
            f"Restart verified from installed artifacts: all {restart.get('after')} resources reopened with "
            "their exact identities after the connection pool was closed and reopened."
        ),
        evidence=evidence,
    )


def probe_j10(context: ProbeContext) -> StepResult:
    """J10 Own: truthful export, deletion proof, and verified non-reappearance."""
    walk = _installed_journey_walk(context)
    ownership = walk.get("ownership")
    if ownership is None:
        return StepResult(
            step_id="J10",
            name=STEP_NAMES["J10"],
            status=StepStatus.BLOCKED,
            summary=f"Own blocked: the installed journey walk stopped at {walk.get('reached')}.",
            evidence=_walk_evidence(walk),
            blocker=f"J5/WS0:journey_walk:{walk.get('reached')}",
        )
    evidence = (*_walk_evidence(walk), f"ownership:{ownership.get('evidence')}")
    if not ownership.get("exported", False):
        return StepResult(
            step_id="J10",
            name=STEP_NAMES["J10"],
            status=StepStatus.FAIL,
            summary="Own failed: the corpus could not be exported.",
            evidence=evidence,
            blocker="WS0:ownership_export_unavailable",
        )
    if not ownership.get("deletion_proved", False):
        return StepResult(
            step_id="J10",
            name=STEP_NAMES["J10"],
            status=StepStatus.FAIL,
            summary="Own failed: deletion returned no proof.",
            evidence=evidence,
            blocker="WS0:ownership_deletion_unproven",
        )
    if ownership.get("previewed", 0) < 1:
        return StepResult(
            step_id="J10",
            name=STEP_NAMES["J10"],
            status=StepStatus.FAIL,
            summary="Own failed: deletion was confirmed against a preview that covered no records.",
            evidence=evidence,
            blocker="WS0:ownership_deletion_preview_empty",
        )
    if ownership.get("survivors_after_deletion", 0) > 0:
        return StepResult(
            step_id="J10",
            name=STEP_NAMES["J10"],
            status=StepStatus.FAIL,
            summary=(
                f"Own failed: {ownership.get('survivors_after_deletion')} resources remained readable after "
                "a proved deletion."
            ),
            evidence=evidence,
            blocker="WS0:deleted_material_reappeared",
        )
    return StepResult(
        step_id="J10",
        name=STEP_NAMES["J10"],
        status=StepStatus.PASS,
        summary=(
            "Own verified from installed artifacts: the corpus exported, deletion returned an exact proof, "
            "and no deleted material reappeared."
        ),
        evidence=evidence,
    )


def build_default_probes() -> dict[str, ProbeCallable]:
    """Fresh probe registry per call; covers every J1-J10 step."""
    return {
        "J1": probe_j1,
        "J2": probe_j2,
        "J3": probe_j3,
        "J4": probe_j4,
        "J5": probe_j5,
        "J6": probe_j6,
        "J7": probe_j7,
        "J8": probe_j8,
        "J9": probe_j9,
        "J10": probe_j10,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pi13_ws0_journey_gate",
        description="Run the PI13 WS0 J1-J10 journey gate and write JSON/Markdown reports.",
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--fixture-corpus", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    return parser.parse_args(argv)


def _fallback_report(surreal_url: str, error: BaseException) -> JourneyReport:
    """Full BLOCKED report used when the gate itself fails before producing rows."""
    reason = f"{type(error).__name__}: {error}"
    results = tuple(
        StepResult(
            step_id=step_id,
            name=STEP_NAMES[step_id],
            status=StepStatus.BLOCKED,
            summary="Journey gate failed before this step could be evaluated.",
            blocker=f"gate_error:{reason}",
        )
        for step_id in STEP_IDS
    )
    return JourneyReport(results=results, surreal_url=surreal_url)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stub = configure_stub_provider_environment()
    surreal_url = os.environ.get("SURREAL_URL", "")
    context = ProbeContext(
        repository_root=args.repository_root,
        fixture_corpus=args.fixture_corpus,
        json_report=args.json_report,
        markdown_report=args.markdown_report,
        surreal_url=surreal_url,
    )

    try:
        report = JourneyGate(build_default_probes()).run(context)
    except Exception as exc:  # noqa: BLE001 - still write reports where possible
        print(f"journey gate error: {type(exc).__name__}: {exc}", file=sys.stderr)
        report = _fallback_report(surreal_url, exc)

    write_failed = False
    for path, content in (
        (context.json_report, report.to_json()),
        (context.markdown_report, report.to_markdown()),
    ):
        try:
            write_atomic(path, content)
        except OSError as exc:
            write_failed = True
            print(f"failed to write report {path}: {exc}", file=sys.stderr)

    if stub is not None:
        stub.stop()
    return 1 if write_failed else report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
