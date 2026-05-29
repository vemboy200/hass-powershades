"""PowerShades services."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up PowerShades services."""

    async def async_toggle_shade(call: ServiceCall) -> None:
        """Toggle PowerShades device between open and closed."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            _LOGGER.error("No entity_id provided")
            return

        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(entity_id)
        if not entity or entity.platform != DOMAIN:
            _LOGGER.error("Invalid entity_id: %s", entity_id)
            return

        config_entry_id = entity.config_entry_id
        device = hass.data[DOMAIN].get(config_entry_id)
        if not device:
            _LOGGER.error("Device not found for entity: %s", entity_id)
            return

        await device.async_toggle()

    async def async_set_upper_limit(call: ServiceCall) -> None:
        """Set upper limit for PowerShades device."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            _LOGGER.error("No entity_id provided")
            return

        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(entity_id)
        if not entity or entity.platform != DOMAIN:
            _LOGGER.error("Invalid entity_id: %s", entity_id)
            return

        config_entry_id = entity.config_entry_id
        device = hass.data[DOMAIN].get(config_entry_id)
        if not device:
            _LOGGER.error("Device not found for entity: %s", entity_id)
            return

        await device.async_set_upper_limit()

    async def async_set_lower_limit(call: ServiceCall) -> None:
        """Set lower limit for PowerShades device."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            _LOGGER.error("No entity_id provided")
            return

        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(entity_id)
        if not entity or entity.platform != DOMAIN:
            _LOGGER.error("Invalid entity_id: %s", entity_id)
            return

        config_entry_id = entity.config_entry_id
        device = hass.data[DOMAIN].get(config_entry_id)
        if not device:
            _LOGGER.error("Device not found for entity: %s", entity_id)
            return

        await device.async_set_lower_limit()

    async def async_clear_limits(call: ServiceCall) -> None:
        """Clear limits for PowerShades device."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            _LOGGER.error("No entity_id provided")
            return

        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(entity_id)
        if not entity or entity.platform != DOMAIN:
            _LOGGER.error("Invalid entity_id: %s", entity_id)
            return

        config_entry_id = entity.config_entry_id
        device = hass.data[DOMAIN].get(config_entry_id)
        if not device:
            _LOGGER.error("Device not found for entity: %s", entity_id)
            return

        await device.async_clear_limits()

    async def async_step_up(call: ServiceCall) -> None:
        """Step up for PowerShades device."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            _LOGGER.error("No entity_id provided")
            return

        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(entity_id)
        if not entity or entity.platform != DOMAIN:
            _LOGGER.error("Invalid entity_id: %s", entity_id)
            return

        config_entry_id = entity.config_entry_id
        device = hass.data[DOMAIN].get(config_entry_id)
        if not device:
            _LOGGER.error("Device not found for entity: %s", entity_id)
            return

        await device.async_step_up()

    async def async_step_down(call: ServiceCall) -> None:
        """Step down for PowerShades device."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            _LOGGER.error("No entity_id provided")
            return

        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(entity_id)
        if not entity or entity.platform != DOMAIN:
            _LOGGER.error("Invalid entity_id: %s", entity_id)
            return

        config_entry_id = entity.config_entry_id
        device = hass.data[DOMAIN].get(config_entry_id)
        if not device:
            _LOGGER.error("Device not found for entity: %s", entity_id)
            return

        await device.async_step_down()

    # Register services
    hass.services.async_register(DOMAIN, "toggle_shade", async_toggle_shade)
    hass.services.async_register(DOMAIN, "set_upper_limit", async_set_upper_limit)
    hass.services.async_register(DOMAIN, "set_lower_limit", async_set_lower_limit)
    hass.services.async_register(DOMAIN, "clear_limits", async_clear_limits)
    hass.services.async_register(DOMAIN, "step_up", async_step_up)
    hass.services.async_register(DOMAIN, "step_down", async_step_down)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload PowerShades services."""
    hass.services.async_remove(DOMAIN, "toggle_shade")
    hass.services.async_remove(DOMAIN, "set_upper_limit")
    hass.services.async_remove(DOMAIN, "set_lower_limit")
    hass.services.async_remove(DOMAIN, "clear_limits")
    hass.services.async_remove(DOMAIN, "step_up")
    hass.services.async_remove(DOMAIN, "step_down")
