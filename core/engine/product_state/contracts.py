"""Bounded public contracts for extension-first Productized State ingestion."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PRODUCT_STATE_INGESTION_VERSION = "ace.product-state.ingestion/v1"
PRODUCT_STATE_CAPABILITIES_VERSION = "ace.product-state.capabilities/v1"
MAX_INGESTION_ITEMS = 200
MAX_INGESTION_BYTES = 2_000_000
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_ADAPTER_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")


class ProductStateIngestionEnvelopeV1(BaseModel):
    """One authenticated adapter request; Core supplies product scope and identity."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["ace.product-state.ingestion/v1"] = PRODUCT_STATE_INGESTION_VERSION
    extension_id: str = Field(min_length=1, max_length=160)
    extension_version: str | None = Field(default=None, min_length=1, max_length=120)
    adapter_name: str = Field(min_length=1, max_length=120)
    manifest_external_id: str = Field(min_length=1, max_length=500)
    extraction_run_id: str = Field(min_length=1, max_length=500)
    submitted_at: datetime
    records: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_INGESTION_ITEMS)

    @model_validator(mode="after")
    def validate_boundary(self):
        if not _IDENTIFIER.fullmatch(self.extension_id):
            raise ValueError("extension_id contains unsupported characters")
        if not _ADAPTER_NAME.fullmatch(self.adapter_name):
            raise ValueError("adapter_name contains unsupported characters")
        encoded = json.dumps(self.records, sort_keys=True, separators=(",", ":"), default=str)
        if len(encoded.encode("utf-8")) > MAX_INGESTION_BYTES:
            raise ValueError("records exceed the bounded serialized size")
        for record in self.records:
            forbidden = {"product", "product_id"} & set(record)
            if forbidden:
                raise ValueError("records cannot set authenticated product scope")
        return self
