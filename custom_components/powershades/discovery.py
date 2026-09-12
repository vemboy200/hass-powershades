"""Background discovery of PowerShades devices."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pyowershades import DiscoveredDevice
from pyowershades import async_discover_devices as _pyowershades_discover_devices

from homeassistant.components import network
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DISCOVERY_INTERVAL = timedelta(minutes=15)


async def async_discover_devices(hass: HomeAssistant) -> list[DiscoveredDevice]:
    """Discover PowerShades devices via UDP broadcast on all local adapters.

    `pyowershades` itself has no Home Assistant dependency, so it takes a
    plain list of local addresses to bind to rather than `hass` — this is
    the bridge that supplies that list from HA's own network helper.
    """
    adapters = await network.async_get_adapters(hass)
    local_addresses = [
        ip_info["address"]
        for adapter in adapters
        if adapter["enabled"]
        for ip_info in adapter["ipv4"]
    ]
    if not local_addresses:
        _LOGGER.warning("No network adapters available for discovery")
        return []
    return await _pyowershades_discover_devices(local_addresses)


@callback
def async_start_discovery(hass: HomeAssistant) -> None:
    """Start periodic background discovery of PowerShades devices."""

    async def _async_scan(*_: Any) -> None:
        devices = await async_discover_devices(hass)
        for device in devices:
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data=device,
            )
        # The broadcast made our short-lived discovery socket every
        # shade's "last UDP master", diverting async move feedback.
        # Poll once from each coordinator to re-assert its socket.
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            hass.async_create_task(entry.runtime_data.async_request_refresh())

    # Scan once after startup, then periodically. Battery shades sleep,
    # so a single scan can miss them — the interval catches stragglers.
    async_at_started(hass, _async_scan)
    async_track_time_interval(
        hass, _async_scan, DISCOVERY_INTERVAL, cancel_on_shutdown=True
    )
