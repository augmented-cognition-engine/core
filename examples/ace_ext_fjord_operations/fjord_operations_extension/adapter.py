"""Fjord Operations source mapper on ACE's bounded grounded-state adapter seam."""

from __future__ import annotations

from extensions.reference.grounded_state_adapter import OLCStyleReferenceAdapter


class FjordOperationsAdapter(OLCStyleReferenceAdapter):
    """Map the frozen public-safe fixture without owning Core identity or persistence."""

    adapter_id = "fjord-operations-public-fixture"
    adapter_version = "v1"
    primary_model_calls = 0
