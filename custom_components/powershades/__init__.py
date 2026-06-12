"""The PowerShades integration."""

import socket
import logging
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import (
    ConfigEntryNotReady,
)  # Added for Quality Scale guard

from .const import DOMAIN
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["cover", "button"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the PowerShades component."""
    hass.data.setdefault(DOMAIN, {})

    # Set up services
    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PowerShades from a config entry."""
    ip_address = entry.data.get("ip")

    _LOGGER.info(
        "Verifying connectivity to PowerShades device at %s on startup",
        ip_address,
    )

    # Quality Scale Guard: Verify the saved IP address is reachable before setting up platforms
    try:
        from .udp import build_get_serial_packet

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)  # 2-second quick check

        packet = build_get_serial_packet()
        sock.sendto(packet, (ip_address, 42))

        # Try to receive a heartbeat byte back to confirm life
        data, addr = sock.recvfrom(256)
        sock.close()
    except (socket.timeout, socket.error) as ex:
        _LOGGER.warning(
            "PowerShades device at %s is unreachable on port 42. Postponing setup",
            ip_address,
        )
        raise ConfigEntryNotReady(
            f"Could not connect to PowerShades at {ip_address}"
        ) from ex

    # 1. Initialize your actual device class mapping
    from .device import PowerShadesDevice

    device = PowerShadesDevice(hass, entry)

    # 2. Store the rich device object inside hass.data so cover/button platforms can extract it
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = device

    # 3. Start the device (UDP listener + coordinator) so state and commands work
    await device.async_start()

    # 4. Hand off setup execution to cover.py and button.py platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device = hass.data[DOMAIN].get(entry.entry_id)
    if device:
        await device.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_unload(hass: HomeAssistant) -> bool:
    """Unload the PowerShades component."""
    await async_unload_services(hass)
    return True
