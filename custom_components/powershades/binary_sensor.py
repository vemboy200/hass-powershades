"""PowerShades binary sensor platform."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    PowerShadesConfigEntry,
    PowerShadesCoordinator,
    PowerShadesData,
)
from .entity import PowerShadesEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PowerShadesBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a PowerShades binary sensor."""

    value_fn: Callable[[PowerShadesData], bool | None]


BINARY_SENSORS: tuple[PowerShadesBinarySensorDescription, ...] = (
    PowerShadesBinarySensorDescription(
        key="green_led",
        translation_key="green_led",
        device_class=BinarySensorDeviceClass.LIGHT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.io_green_led,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades binary sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        PowerShadesBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class PowerShadesBinarySensor(PowerShadesEntity, BinarySensorEntity):
    """PowerShades diagnostic binary sensor."""

    entity_description: PowerShadesBinarySensorDescription

    def __init__(
        self,
        coordinator: PowerShadesCoordinator,
        description: PowerShadesBinarySensorDescription,
    ) -> None:
        """Initialize the PowerShades binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the LED is on."""
        return self.entity_description.value_fn(self.coordinator.data)
