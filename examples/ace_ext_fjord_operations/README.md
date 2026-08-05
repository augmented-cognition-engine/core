# Fjord Operations ACE extension

This separately installable, fictional extension is the public-safe product package used by ACE's
K1–K3 and Productized State acceptance journeys. It attaches through the documented `ace.extensions`
entry-point boundary and never modifies or imports private Core implementation modules.

The extension owns the product name, corpus mapping, evidence-query action registration, promotion
review action registration, and fixture data. Core continues to own authenticated product scope,
stable identities, temporal semantics, validation, persistence, replay, review authority, task
lifecycle, rollout reconciliation, and I3 receipts.

Install it beside ACE from a source checkout:

```bash
python -m pip install ./examples/ace_ext_fjord_operations
```

The complete executable journey is documented in
[`docs/state-engine-product-builder.md`](../../docs/state-engine-product-builder.md).
The integrated 0.3.x candidate surface is documented in
[`docs/productized-state.md`](../../docs/productized-state.md).
