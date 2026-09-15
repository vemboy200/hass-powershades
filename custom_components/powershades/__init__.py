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
    MODEL_RF_GATEWAY,
    OP_GET_DEVICE_ID,
    OP_GET_SERIAL,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    parse_device_id_reply,
    parse_serial_reply,
)

from .const import DOMAIN, RF_GATEWAY_ISSUE_URL, TRUSTED_SERVER_HOSTNAME
from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .discovery import async_start_discovery
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def _async_fetch_serial_info(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    coordinator: PowerShadesCoordinator,
) -> None:
    """Fetch Get Serial Number, backfilling model (for entries that
    predate it being stored) and refreshing server_hostname.

    Called right after a successful first refresh, so the device is
    known reachable. Runs on every setup, not just for legacy entries
    missing a model - server_hostname needs re-checking every time,
    since it can change at any point after setup (see
    _async_check_server_hostname). Best-effort: silently keeps
    everything unchanged on lookup failure. The MAC address isn't
    backfilled this way - it's only ever known when a device is found
    via DHCP discovery, which already carries the sender's MAC for free.
    """
    try:
        reply = await coordinator.connection.async_request(OP_GET_SERIAL)
    except PowerShadesTimeoutError:
        return
    parsed = parse_serial_reply(reply) if reply else None
    if parsed is None:
        return
    coordinator.server_hostname = parsed["server_hostname"]
    if entry.data.get("model") is None:
        coordinator.model = parsed["model"]
        _LOGGER.debug(
            "Backfilled model for shade %s: %s", entry.data["ip"], parsed["model"]
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "model": parsed["model"]}
        )


# model_version from Get Device ID. 0 = Gen 1 is confirmed by the
# hardware's owner; 2 = Gen 2 is the working hypothesis from the
# decompile but hasn't been checked against an actual Gen 2 unit.
_MODEL_VERSION_NAMES = {
    0: "Gen 1",
    2: "Gen 2",
}


async def _async_fetch_device_id_info(coordinator: PowerShadesCoordinator) -> None:
    """Fetch the active firmware bank's revision and hardware generation
    for the device info card.

    Neither is persisted to entry data (unlike model) - both are
    refreshed on every setup instead, since firmware can change after
    an update. Best-effort: silently leaves them unset on failure or
    (for firmware_version) an ambiguous active-bank flag.
    """
    try:
        reply = await coordinator.connection.async_request(OP_GET_DEVICE_ID)
    except PowerShadesTimeoutError:
        return
    device_id = parse_device_id_reply(reply)
    if device_id is None:
        return
    active_bank = device_id.status_bits & 3
    if active_bank == 1:
        coordinator.firmware_version = str(device_id.low_rev)
    elif active_bank == 2:
        coordinator.firmware_version = str(device_id.high_rev)
    coordinator.hw_version = _MODEL_VERSION_NAMES.get(
        device_id.model_version, f"Model version {device_id.model_version}"
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the PowerShades component."""
    async_setup_services(hass)
    async_start_discovery(hass)
    return True


def _rf_gateway_issue_id(entry: PowerShadesConfigEntry) -> str:
    """Return the repair issue ID for a device that is an RF Gateway."""
    return f"rf_gateway_unsupported_{entry.entry_id}"


def _async_check_rf_gateway(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    coordinator: PowerShadesCoordinator,
) -> None:
    """Warn if this entry's device identifies as an RF Gateway.

    This integration is only built and tested against PoE shades - an RF
    Gateway responding to the same opcodes is untested territory (see
    docs/PROTOCOL.md's Channel field for why it can respond at all).
    Non-fixable/informational only; the user can dismiss it from the
    Repairs page like any other issue.
    """
    issue_id = _rf_gateway_issue_id(entry)
    if coordinator.model != MODEL_RF_GATEWAY:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="rf_gateway_unsupported",
        translation_placeholders={"name": entry.title},
        learn_more_url=RF_GATEWAY_ISSUE_URL,
    )


def _server_hostname_issue_id(entry: PowerShadesConfigEntry) -> str:
    """Return the repair issue ID for an untrusted server hostname."""
    return f"untrusted_server_hostname_{entry.entry_id}"


def _async_check_server_hostname(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    coordinator: PowerShadesCoordinator,
) -> None:
    """Warn if this device's Server Hostname setting isn't PowerShades'
    own domain.

    That setting (op 0x0B, Set Server Hostname) controls where the
    device's cloud-facing commands actually connect - Cloud Update
    Check/Trigger among them - and it's completely unauthenticated, like
    every other command in this protocol. Checked at every setup,
    independent of whether Check for Updates has ever been pressed, so a
    redirected device is surfaced proactively rather than only being
    discovered the next time someone tries to use the firmware update
    feature. async_install_update also re-checks this itself as a hard
    block - this issue is the proactive warning, that's the backstop.
    Fixable via repairs.py's one-click reset flow (or the
    powershades.set_server_hostname service directly) - both call
    coordinator.async_set_server_hostname, which re-reads the device to
    confirm the write actually took before this issue is considered
    resolved.
    """
    issue_id = _server_hostname_issue_id(entry)
    if not coordinator.server_hostname or (
        coordinator.server_hostname == TRUSTED_SERVER_HOSTNAME
    ):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=ir.IssueSeverity.CRITICAL,
        translation_key="untrusted_server_hostname",
        translation_placeholders={
            "name": entry.title,
            "hostname": coordinator.server_hostname,
            "expected": TRUSTED_SERVER_HOSTNAME,
        },
        data={"entry_id": entry.entry_id},
    )


async def async_setup_entry(hass: HomeAssistant, entry: PowerShadesConfigEntry) -> bool:
    """Set up PowerShades from a config entry."""
    connection = PowerShadesConnection(entry.data["ip"])
    await connection.async_connect()

    coordinator = PowerShadesCoordinator(hass, entry, connection)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        connection.close()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(connection.close)

    await _async_fetch_serial_info(hass, entry, coordinator)
    await _async_fetch_device_id_info(coordinator)
    await coordinator.async_fetch_disables_state()
    await coordinator.async_fetch_motor_speed()
    _async_check_rf_gateway(hass, entry, coordinator)
    _async_check_server_hostname(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PowerShadesConfigEntry
) -> bool:
    """Unload a config entry."""
    ir.async_delete_issue(hass, DOMAIN, _rf_gateway_issue_id(entry))
    ir.async_delete_issue(hass, DOMAIN, _server_hostname_issue_id(entry))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
