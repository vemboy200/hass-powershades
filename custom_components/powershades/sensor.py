"""PowerShades sensor platform."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import (
    PowerShadesConfigEntry,
    PowerShadesCoordinator,
    PowerShadesData,
)
from .entity import PowerShadesEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

LED_COLOR_OPTIONS = ["off", "green", "red", "yellow"]


def _led_color(data: PowerShadesData) -> str | None:
    """Combine the green/red LEDs into a single color - both on is yellow."""
    if data.io_green_led is None or data.io_red_led is None:
        return None
    if data.io_green_led and data.io_red_led:
        return "yellow"
    if data.io_green_led:
        return "green"
    if data.io_red_led:
        return "red"
    return "off"


@dataclass(frozen=True, kw_only=True)
class PowerShadesSensorDescription(SensorEntityDescription):
    """Describes a PowerShades sensor."""

    value_fn: Callable[[PowerShadesData], StateType]


SENSORS: tuple[PowerShadesSensorDescription, ...] = (
    PowerShadesSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.battery_percentage,
    ),
    PowerShadesSensorDescription(
        key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.battery_mv,
    ),
    PowerShadesSensorDescription(
        key="led_color",
        translation_key="led_color",
        device_class=SensorDeviceClass.ENUM,
        options=LED_COLOR_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_led_color,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        PowerShadesSensor(coordinator, description) for description in SENSORS
    )


class PowerShadesSensor(PowerShadesEntity, SensorEntity):
    """PowerShades diagnostic sensor."""

    entity_description: PowerShadesSensorDescription

    def __init__(
        self,
        coordinator: PowerShadesCoordinator,
        description: PowerShadesSensorDescription,
    ) -> None:
        """Initialize the PowerShades sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
