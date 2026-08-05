"""Supported product-facing contracts for extension-owned grounded state."""

from core.engine.product_state.contracts import (
    PRODUCT_STATE_CAPABILITIES_VERSION,
    PRODUCT_STATE_INGESTION_VERSION,
    ProductStateIngestionEnvelopeV1,
)

__all__ = [
    "PRODUCT_STATE_CAPABILITIES_VERSION",
    "PRODUCT_STATE_INGESTION_VERSION",
    "ProductStateIngestionEnvelopeV1",
]
