"""Read-only catalog of installed Intelligence material and consumer contracts."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from core.engine.core.auth import get_current_user
from core.engine.core.installed_intelligence_catalog import (
    DomainPackActivationHistoryDenied,
    DomainPackActivationHistoryNotFound,
    DomainPackActivationHistoryProjectionV1,
    DomainPackActivationHistoryUnauthenticated,
    DomainPackActivationHistoryUnavailable,
    DomainPackManifestV1,
    IntelligenceOnboardingProfileV1Alpha1,
    ace_version,
    discover_installed_domain_pack_previews,
    discover_installed_onboarding_profiles,
    domain_pack_activation_store,
    mcp_client_version,
    read_domain_pack_activation_history,
)

RESOURCE_PLANE_QUERY_VERSION = "ace.intelligence.resource-plane-query/v1alpha1"
RESOURCE_PLANE_RECORD_VERSION = "ace.intelligence.resource-plane-record/v1alpha1"
RESOURCE_PLANE_PAGE_VERSION = "ace.intelligence.resource-plane-page/v1alpha1"
ORGANIZATION_OVERLAY_VERSION = "ace.intelligence.organization-overlay/v1alpha1"
DOMAIN_ACTIVATION_REVISION_VERSION = "ace.intelligence.domain-activation-revision/v1alpha1"
DOMAIN_ACTIVATION_PLAN_REVISION_VERSION = "ace.intelligence.domain-activation-revision/v1alpha2"
SUBSCRIPTION_VERSION = "ace.intelligence.subscription/v1alpha1"
MONITORING_LIFECYCLE_REQUEST_VERSION = "ace.intelligence.monitoring-lifecycle-request/v1alpha1"
MONITORING_LIFECYCLE_RECEIPT_VERSION = "ace.intelligence.monitoring-lifecycle-receipt/v1alpha1"
SUBSCRIPTION_LIFECYCLE_HTTP_RESULT_VERSION = "ace.http.intelligence-subscription-lifecycle-result/v1alpha1"

router = APIRouter(prefix="/v1/intelligence/catalog", tags=["intelligence-catalog"])


class InstalledIntelligenceProfileV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution: str
    distribution_version: str
    resource_path: str
    profile: IntelligenceOnboardingProfileV1Alpha1


class InstalledIntelligenceCatalogV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.installed-intelligence-catalog/v1alpha1"] = (
        "ace.http.installed-intelligence-catalog/v1alpha1"
    )
    profiles: tuple[InstalledIntelligenceProfileV1, ...]


PackLifecycleAvailability = Literal["available", "contract_only", "not_exposed"]


class DomainPackLifecycleCapabilityV1(BaseModel):
    """One truthful Pack lifecycle capability, never an inferred product state."""

    model_config = ConfigDict(extra="forbid")

    capability_id: Literal[
        "installed_material",
        "reviewed_customization",
        "upgrade_discovery",
        "activation_history",
        "rollback",
    ]
    label: str
    availability: PackLifecycleAvailability
    contract_refs: tuple[str, ...] = ()
    endpoint: str | None = None
    boundary: str


class InstalledDomainPackPreviewV1(BaseModel):
    """Installed declarative Pack material; presence does not imply activation."""

    model_config = ConfigDict(extra="forbid")

    distribution: str
    distribution_version: str
    manifest_resource_path: str
    manifest_digest: str
    manifest: DomainPackManifestV1
    lifecycle: tuple[DomainPackLifecycleCapabilityV1, ...]


class InstalledDomainPackCatalogV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.installed-domain-pack-catalog/v1alpha1"] = (
        "ace.http.installed-domain-pack-catalog/v1alpha1"
    )
    packs: tuple[InstalledDomainPackPreviewV1, ...]


ConsumerAvailability = Literal["available", "contract_only", "navigation_only", "not_exposed"]


class IntelligenceConsumerInterfaceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface_id: str
    label: str
    kind: Literal["api", "mcp", "sdk", "subscription", "stream", "webhook", "schema", "handoff"]
    availability: ConsumerAvailability
    version: str | None = None
    endpoint: str | None = None
    contract_refs: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()
    permission_boundary: str
    provenance_boundary: str
    delivery_boundary: str


class IntelligenceConsumerCatalogV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: Literal["ace.http.intelligence-consumer-catalog/v1alpha1"] = (
        "ace.http.intelligence-consumer-catalog/v1alpha1"
    )
    interfaces: tuple[IntelligenceConsumerInterfaceV1, ...]
    unresolved_dependencies: tuple[str, ...]


@router.get("/profiles", response_model=InstalledIntelligenceCatalogV1)
async def installed_profiles(user: dict = Depends(get_current_user)) -> InstalledIntelligenceCatalogV1:
    """List validated installed profiles; authentication never grants their proposed effects."""

    del user
    return InstalledIntelligenceCatalogV1(
        profiles=tuple(
            InstalledIntelligenceProfileV1(
                distribution=item.distribution,
                distribution_version=item.distribution_version,
                resource_path=item.resource_path,
                profile=item.profile,
            )
            for item in discover_installed_onboarding_profiles()
        )
    )


@router.get("/packs", response_model=InstalledDomainPackCatalogV1)
async def installed_packs(user: dict = Depends(get_current_user)) -> InstalledDomainPackCatalogV1:
    """List exact installed manifests without compiling or activating unrelated Packs."""

    del user
    return InstalledDomainPackCatalogV1(
        packs=tuple(
            InstalledDomainPackPreviewV1(
                distribution=item.distribution,
                distribution_version=item.distribution_version,
                manifest_resource_path=item.manifest_resource_path,
                manifest_digest=item.manifest_digest,
                manifest=item.manifest,
                lifecycle=(
                    DomainPackLifecycleCapabilityV1(
                        capability_id="installed_material",
                        label="Installed material",
                        availability="available",
                        endpoint="GET /v1/intelligence/catalog/packs",
                        boundary=(
                            "The host exposes this exact validated manifest. Presence does not compile, activate, "
                            "connect, or grant authority."
                        ),
                    ),
                    DomainPackLifecycleCapabilityV1(
                        capability_id="reviewed_customization",
                        label="Local customization",
                        availability="contract_only",
                        contract_refs=(ORGANIZATION_OVERLAY_VERSION,),
                        endpoint="GET /v1/intelligence/catalog/packs/activations/{activation_key}",
                        boundary=(
                            f"The Pack declares {len(item.manifest.overlay_slots)} overlay slot(s). Exact active "
                            "overlay values are readable by activation key; editing still requires a future "
                            "reviewed mutation surface."
                        ),
                    ),
                    DomainPackLifecycleCapabilityV1(
                        capability_id="upgrade_discovery",
                        label="Upgrade",
                        availability="not_exposed",
                        boundary=(
                            "ACE exposes the installed Pack and distribution versions only; it does not claim "
                            "that a newer compatible release exists."
                        ),
                    ),
                    DomainPackLifecycleCapabilityV1(
                        capability_id="activation_history",
                        label="Version history",
                        availability="available",
                        contract_refs=(DOMAIN_ACTIVATION_PLAN_REVISION_VERSION,),
                        endpoint="GET /v1/intelligence/catalog/packs/activations/{activation_key}",
                        boundary=(
                            "Returns the exact append-only governed revision chain, newest first. Historical "
                            "references never grant current runtime authority."
                        ),
                    ),
                    DomainPackLifecycleCapabilityV1(
                        capability_id="rollback",
                        label="Rollback",
                        availability="contract_only",
                        contract_refs=(DOMAIN_ACTIVATION_PLAN_REVISION_VERSION,),
                        boundary=(
                            "Rollback is represented as a new approved active revision; no customer rollback action "
                            "is exposed."
                        ),
                    ),
                ),
            )
            for item in discover_installed_domain_pack_previews()
        )
    )


@router.get(
    "/packs/activations/{activation_key}",
    response_model=DomainPackActivationHistoryProjectionV1,
)
async def pack_activation_history(
    activation_key: str,
    user: dict = Depends(get_current_user),
    store=Depends(domain_pack_activation_store),
) -> DomainPackActivationHistoryProjectionV1:
    """Read one exact product-scoped active Pack, overlay, and immutable history."""

    try:
        return await read_domain_pack_activation_history(
            activation_key=activation_key,
            user=user,
            store=store,
        )
    except DomainPackActivationHistoryUnauthenticated as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except DomainPackActivationHistoryDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DomainPackActivationHistoryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainPackActivationHistoryUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/consumers", response_model=IntelligenceConsumerCatalogV1)
async def intelligence_consumers(user: dict = Depends(get_current_user)) -> IntelligenceConsumerCatalogV1:
    """Describe installed or contracted interfaces without claiming configured delivery."""

    del user
    return IntelligenceConsumerCatalogV1(
        interfaces=(
            IntelligenceConsumerInterfaceV1(
                interface_id="intelligence_resource_http",
                label="Intelligence Resource API",
                kind="api",
                availability="available",
                version="v1",
                endpoint="POST /v1/intelligence/resources/query",
                contract_refs=(
                    RESOURCE_PLANE_QUERY_VERSION,
                    RESOURCE_PLANE_RECORD_VERSION,
                    RESOURCE_PLANE_PAGE_VERSION,
                ),
                operations=("point-in-time query", "cursor pagination"),
                permission_boundary=(
                    "Every query reauthenticates product scope and reauthorizes authority_grant_ref; cursors grant no authority."
                ),
                provenance_boundary=(
                    "Every record carries an exact resource reference and upstream provenance; the page carries query and page digests."
                ),
                delivery_boundary="Authenticated point-in-time JSON pages only.",
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="ace_thin_mcp_client",
                label="ACE MCP thin client",
                kind="mcp",
                availability="available",
                version=mcp_client_version,
                endpoint="ace-mcp-client",
                operations=(
                    "ace_start",
                    "ace_load",
                    "ace_capture",
                    "ace_task",
                    "ace_status",
                    "ace_capture_idea",
                    "ace_search",
                    "ace_briefing",
                    "ace_impact",
                    "ace_history",
                    "ace_related",
                ),
                permission_boundary="The client uses ACE_TOKEN, a local token, or ACE_API_KEY exchange for each HTTP call.",
                provenance_boundary=(
                    "Tool-specific HTTP responses are returned as-is or formatted; resource-plane provenance parity is not contracted."
                ),
                delivery_boundary="Installed 11-tool client; it is not an Intelligence subscription or event stream.",
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="ace_python_contracts",
                label="ACE Python contracts",
                kind="sdk",
                availability="available",
                version=ace_version,
                endpoint="Python package: ace",
                contract_refs=(
                    RESOURCE_PLANE_QUERY_VERSION,
                    RESOURCE_PLANE_RECORD_VERSION,
                    RESOURCE_PLANE_PAGE_VERSION,
                    ORGANIZATION_OVERLAY_VERSION,
                    DOMAIN_ACTIVATION_REVISION_VERSION,
                    SUBSCRIPTION_VERSION,
                ),
                operations=("validate immutable contracts", "compose against public application ports"),
                permission_boundary="Importing a contract grants no runtime capability or authority.",
                provenance_boundary="Content-addressed references and digests are preserved by the public contracts.",
                delivery_boundary="Python contracts and ports only; no universal generated SDK is exposed.",
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="intelligence_subscription",
                label="Intelligence subscription",
                kind="subscription",
                availability="contract_only",
                endpoint="POST /v1/intelligence/subscriptions/lifecycle",
                contract_refs=(
                    SUBSCRIPTION_VERSION,
                    MONITORING_LIFECYCLE_REQUEST_VERSION,
                    MONITORING_LIFECYCLE_RECEIPT_VERSION,
                    SUBSCRIPTION_LIFECYCLE_HTTP_RESULT_VERSION,
                ),
                operations=(
                    "record-only create",
                    "record-only pause",
                    "record-only resume",
                    "record-only revoke",
                ),
                permission_boundary=(
                    "The host derives product and owner from the verified identity and requires administer_lifecycle; "
                    "a subscription is not an API credential or destination authority."
                ),
                provenance_boundary=(
                    "The exact subscription and append-only owner lifecycle are content-addressed and restart-replayable; "
                    "no delivery provenance or downstream provenance-return receipt is exposed."
                ),
                delivery_boundary=(
                    "The endpoint records only an owner preference lifecycle. No list/current projection, scheduler, "
                    "destination, send, or delivery receipt exists; immediate and digest fail closed."
                ),
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="intelligence_stream",
                label="Intelligence stream",
                kind="stream",
                availability="not_exposed",
                permission_boundary=(
                    "No product-scoped Intelligence stream connect, read, replay, retention, or revocation authority "
                    "contract is exposed."
                ),
                provenance_boundary=(
                    "No ordered Intelligence event envelope binds an event ID, subscription lifecycle, exact resource "
                    "references and digests, causation, redaction, or replay position."
                ),
                delivery_boundary=(
                    "Chat token SSE, LIVE operator-state SSE, and memory polling streams are internal UI transports; "
                    "none is an Intelligence consumer stream or durable replay ledger."
                ),
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="intelligence_webhook",
                label="Intelligence webhook",
                kind="webhook",
                availability="not_exposed",
                permission_boundary=(
                    "No Intelligence resource-to-destination preparation binds the existing destination-delivery "
                    "authority and policy checks to a configured webhook recipient."
                ),
                provenance_boundary=(
                    "No versioned signed outbound Intelligence envelope, key identity/rotation contract, or exact "
                    "resource delivery receipt is exposed."
                ),
                delivery_boundary=(
                    "Inbound/provider webhooks and the global notification webhook are unrelated: they do not provide "
                    "an Intelligence subscription destination, durable acknowledgment, or lookup-before-retry path."
                ),
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="intelligence_schemas",
                label="Schemas and OpenAPI",
                kind="schema",
                availability="available",
                version=ace_version,
                endpoint="GET /openapi.json",
                contract_refs=(
                    RESOURCE_PLANE_QUERY_VERSION,
                    RESOURCE_PLANE_RECORD_VERSION,
                    RESOURCE_PLANE_PAGE_VERSION,
                ),
                operations=("OpenAPI response schemas", "bundled Domain Pack JSON schemas"),
                permission_boundary="Schema inspection grants no data access or runtime authority.",
                provenance_boundary="Contract versions and content-addressed fields are explicit in each schema.",
                delivery_boundary="Machine-readable schemas only.",
            ),
            IntelligenceConsumerInterfaceV1(
                interface_id="investigation_board",
                label="Investigation Board",
                kind="handoff",
                availability="navigation_only",
                endpoint="/board",
                permission_boundary="The existing application route applies its own product and session boundary.",
                provenance_boundary="No consumer payload or provenance-return contract is exposed for this navigation.",
                delivery_boundary="Existing in-product destination only; no second handoff framework is implied.",
            ),
        ),
        unresolved_dependencies=(
            "Domain Pack upgrade discovery, compatibility planning, reviewed overlay mutation, and rollback actions",
            "Authoritative subscription target read/list projection and outbound delivery receipts",
            "Intelligence outbound event envelope, durable ordered ledger, resume cursor, retention/replay, and per-subscription revocation gates",
            "Intelligence-to-existing destination-delivery preparation, configured destination adapter, signing/key rotation, acknowledgment, lookup-before-retry, cancellation, and audit exposure",
            "A required provenance envelope that downstream consumers preserve and return with outcomes",
        ),
    )


__all__ = [
    "InstalledDomainPackCatalogV1",
    "InstalledDomainPackPreviewV1",
    "pack_activation_history",
    "DomainPackLifecycleCapabilityV1",
    "InstalledIntelligenceCatalogV1",
    "InstalledIntelligenceProfileV1",
    "IntelligenceConsumerCatalogV1",
    "IntelligenceConsumerInterfaceV1",
    "installed_packs",
    "installed_profiles",
    "intelligence_consumers",
    "router",
]
