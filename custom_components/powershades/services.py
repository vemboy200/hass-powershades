"""PowerShades services."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> PowerShadesCoordinator:
    """Resolve the coordinator for the entity targeted by a service call."""
    entity_id = call.data[ATTR_ENTITY_ID]
    entity = er.async_get(hass).async_get(entity_id)
    if entity is None or entity.platform != DOMAIN or entity.config_entry_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
            translation_placeholders={"entity_id": entity_id},
        )
    entry: PowerShadesConfigEntry | None = hass.config_entries.async_get_entry(
        entity.config_entry_id
    )
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"entity_id": entity_id},
        )
    return entry.runtime_data


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up PowerShades services.

    set_shade_name is the only service left - every other former service
    (toggle, jog, step, limits) duplicates a button entity that already
    exists and takes no parameters, so there's nothing a service adds
    over just pressing the button.
    """

    async def set_shade_name(call: ServiceCall) -> None:
        name = call.data["name"].strip()
        if not name or len(name) > 50 or not name.isascii():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_shade_name",
            )
        await _get_coordinator(hass, call).async_set_shade_name(name)

    hass.services.async_register(
        DOMAIN,
        "set_shade_name",
        set_shade_name,
        schema=SERVICE_SCHEMA.extend({vol.Required("name"): cv.string}),
    )
