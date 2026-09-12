"""The PowerShades integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from pyowershades import (
    OP_GET_SERIAL,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    parse_serial_reply,
)

from .const import DOMAIN
from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .discovery import async_start_discovery
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.COVER, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def _async_backfill_model(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    coordinator: PowerShadesCoordinator,
) -> None:
    """Backfill the model for entries that predate it being stored.

    Called right after a successful first refresh, so the device is
    known reachable. Best-effort: silently keeps the entry unchanged on
    lookup failure. The MAC address isn't backfilled this way - it's
    only ever known when a device is found via DHCP discovery, which
    already carries the sender's MAC for free.
    """
    if entry.data.get("model") is not None:
        return
    try:
        reply = await coordinator.connection.async_request(OP_GET_SERIAL)
    except PowerShadesTimeoutError:
        return
    parsed = parse_serial_reply(reply) if reply else None
    if parsed is None:
        return
    coordinator.model = parsed["model"]
    _LOGGER.debug(
        "Backfilled model for shade %s: %s", entry.data["ip"], parsed["model"]
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "model": parsed["model"]}
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the PowerShades component."""
    async_setup_services(hass)
    async_start_discovery(hass)
    return True


def _cannot_connect_issue_id(entry: PowerShadesConfigEntry) -> str:
    """Return the repair issue ID for a setup-failure of this entry."""
    return f"cannot_connect_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: PowerShadesConfigEntry) -> bool:
    """Set up PowerShades from a config entry."""
    connection = PowerShadesConnection(entry.data["ip"])
    await connection.async_connect()

    coordinator = PowerShadesCoordinator(hass, entry, connection)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        connection.close()
        ir.async_create_issue(
            hass,
            DOMAIN,
            _cannot_connect_issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="cannot_connect",
            translation_placeholders={"name": entry.title, "ip": entry.data["ip"]},
        )
        raise

    ir.async_delete_issue(hass, DOMAIN, _cannot_connect_issue_id(entry))

    entry.runtime_data = coordinator
    entry.async_on_unload(connection.close)

    await _async_backfill_model(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PowerShadesConfigEntry
) -> bool:
    """Unload a config entry."""
    ir.async_delete_issue(hass, DOMAIN, _cannot_connect_issue_id(entry))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
