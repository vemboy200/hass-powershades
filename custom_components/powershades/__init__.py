"""The PowerShades integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .services import async_setup_services, async_unload_services

PLATFORMS: list[str] = ["cover", "button"]  # Add button platform


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the PowerShades component."""
    hass.data.setdefault(DOMAIN, {})

    # Set up services
    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PowerShades from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create device coordinator
    from .device import PowerShadesDevice

    device = PowerShadesDevice(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = device

    # Start the device
    await device.async_start()

    # Set up all platforms for this config entry
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop the device
    device = hass.data[DOMAIN].get(entry.entry_id)
    if device:
        await device.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_unload(hass: HomeAssistant) -> bool:
    """Unload the PowerShades component."""
    # Unload services
    await async_unload_services(hass)
    return True
