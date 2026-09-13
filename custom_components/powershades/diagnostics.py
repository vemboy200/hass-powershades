"""Diagnostics support for PowerShades."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from pyowershades import POE_ERROR_CODES

from .coordinator import PowerShadesConfigEntry

TO_REDACT = {"ip", "mac", "serial", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PowerShadesConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    coordinator_data = asdict(coordinator.data) if coordinator.data else None
    if coordinator_data is not None:
        # error_list is raw PoEErrorCode numbers - add the decoded names
        # alongside them so the download is actually readable.
        coordinator_data["error_list_decoded"] = [
            POE_ERROR_CODES.get(code, f"Unknown ({code})")
            for code in coordinator_data["error_list"]
        ]

    return {
        "entry_data": async_redact_data(
            {**entry.data, "unique_id": entry.unique_id}, TO_REDACT
        ),
        "coordinator_data": coordinator_data,
    }
