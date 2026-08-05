"""Authenticated Productized State adapter discovery and ingestion."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.extensions.registry import (
    registered_grounded_state_adapter,
    registered_grounded_state_adapter_manifests,
    registered_task_actions,
)
from core.engine.grounded_state.ingestion import GroundedStateIngestionService
from core.engine.product_state.contracts import (
    PRODUCT_STATE_CAPABILITIES_VERSION,
    PRODUCT_STATE_INGESTION_VERSION,
    ProductStateIngestionEnvelopeV1,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/product-state", tags=["product-state"])
_PRODUCT_ID = re.compile(r"product:[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _failure(code: str, message: str, recovery: str) -> dict[str, str]:
    return {"code": code, "message": message, "recovery": recovery}


@router.get("/capabilities")
async def product_state_capabilities(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """List domain-neutral state adapters and their compatible task actions."""
    del user
    actions = registered_task_actions()
    return {
        "contract_version": PRODUCT_STATE_CAPABILITIES_VERSION,
        "authority": {
            "product_scope": "authenticated_token_only",
            "source_mapping": "extension_owned",
            "identity_persistence_and_receipts": "core_owned",
            "source_text_instruction_authority": False,
        },
        "adapters": registered_grounded_state_adapter_manifests(),
        "actions": [actions[key].public_manifest() for key in sorted(actions)],
    }


@router.post("/ingestions", status_code=status.HTTP_201_CREATED)
async def ingest_product_state(
    envelope: ProductStateIngestionEnvelopeV1,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Map extension-owned source input and persist it under authenticated Core scope."""
    product_id = str(user.get("product") or "")
    if not _PRODUCT_ID.fullmatch(product_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_failure(
                "malformed_product_identity",
                "The authenticated product identity is not a canonical product:<slug> identifier.",
                "Authenticate again with a token scoped to an existing product.",
            ),
        )

    adapter = registered_grounded_state_adapter(envelope.extension_id, envelope.adapter_name)
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_failure(
                "product_state_adapter_not_registered",
                "The requested Product State adapter is not installed or available.",
                "Install a compatible extension, restart ACE, and inspect `ace state capabilities`.",
            ),
        )
    manifests = {
        (item["extension_id"], item["adapter_name"]): item for item in registered_grounded_state_adapter_manifests()
    }
    manifest_identity = manifests.get((envelope.extension_id, envelope.adapter_name), {})
    if envelope.extension_version is not None and envelope.extension_version != manifest_identity.get(
        "extension_version"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_failure(
                "product_state_extension_version_mismatch",
                "The installed extension version does not match the requested journey.",
                "Install the pinned extension version or update and refreeze the journey input.",
            ),
        )

    try:
        manifest = adapter.build_manifest(
            product_id=product_id,
            manifest_external_id=envelope.manifest_external_id,
            extraction_run_id=envelope.extraction_run_id,
            submitted_at=envelope.submitted_at,
            records=envelope.records,
        )
        manifest_product_id = manifest.get("product_id") if isinstance(manifest, Mapping) else manifest.product_id
        if str(manifest_product_id) != product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_failure(
                    "product_state_product_scope_mismatch",
                    "The extension adapter returned a manifest outside the authenticated product scope.",
                    "Correct or remove the installed adapter; Core will not ingest cross-product output.",
                ),
            )
        receipt = await GroundedStateIngestionService(pool).ingest(manifest)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Product State ingestion failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_failure(
                "product_state_ingestion_rejected",
                f"The adapter input or resulting manifest was rejected ({type(exc).__name__}).",
                "Inspect the input against the extension contract; no caller product identity is accepted.",
            ),
        ) from exc

    return {
        "contract_version": PRODUCT_STATE_INGESTION_VERSION,
        "extension": manifest_identity,
        "adapter": {
            "extension_id": envelope.extension_id,
            "adapter_name": envelope.adapter_name,
            "adapter_id": str(getattr(adapter, "adapter_id", envelope.adapter_name)),
            "adapter_version": str(getattr(adapter, "adapter_version", "unknown")),
        },
        "authority": {
            "product_scope": "authenticated_token_only",
            "source_mapping": "extension_owned",
            "identity_persistence_and_receipts": "core_owned",
            "model_review_or_promotion_authority": False,
        },
        "receipt": receipt.model_dump(mode="json"),
    }
