"""PowerShades switch platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .entity import PowerShadesEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades switches from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([PowerShadesAllowCloudConnectionSwitch(coordinator)])


class PowerShadesAllowCloudConnectionSwitch(PowerShadesEntity, SwitchEntity):
    """Controls whether the shade may connect to PowerShades' cloud."""

    _attr_translation_key = "allow_cloud_connection"
    _attr_icon = "mdi:cloud"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "allow_cloud_connection")

    @property
    def is_on(self) -> bool | None:
        """Return whether the shade's cloud connectivity is enabled."""
        return self.coordinator.allow_cloud_connection

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allow the shade to connect to PowerShades' cloud."""
        await self.coordinator.async_set_allow_cloud_connection(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Block the shade from connecting to PowerShades' cloud."""
        await self.coordinator.async_set_allow_cloud_connection(False)
