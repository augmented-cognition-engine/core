"""ATC → EventBus bridge.

Maintains a product-level registry of active EventBus instances.
FlightRegistry emits atc_lock / atc_blocked / atc_release to every
bus registered for the relevant product_id.
"""

from __future__ import annotations

from collections import defaultdict

# product_id → list of active EventBus instances
_product_buses: dict[str, list] = defaultdict(list)


def register_product_bus(product_id: str, bus) -> None:
    _product_buses[product_id].append(bus)


def unregister_product_bus(product_id: str, bus) -> None:
    if product_id in _product_buses:
        _product_buses[product_id] = [b for b in _product_buses[product_id] if b is not bus]


def get_product_buses(product_id: str) -> list:
    return list(_product_buses.get(product_id, []))


def clear_product_buses() -> None:
    _product_buses.clear()
