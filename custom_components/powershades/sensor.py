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
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from pyowershades import POE_ERROR_CODES

from .coordinator import (
    PowerShadesConfigEntry,
    PowerShadesCoordinator,
    PowerShadesData,
)
from .entity import PowerShadesEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

LED_COLOR_OPTIONS = ["off", "green", "red", "yellow"]

# "none" (no error) and "unknown" (a code outside 1-33, e.g. from a firmware
# version not covered by POE_ERROR_CODES) aren't PoEErrorCode values
# themselves, but need to be valid ENUM options too.
ERROR_OPTIONS = [
    "none",
    "unknown",
    *(name.lower() for name in POE_ERROR_CODES.values()),
]


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


def _current_error(data: PowerShadesData) -> str:
    """Return the most recent error code's name, or "none".

    error_list can hold multiple codes at once, but this sensor can only
    show one - the most recently logged one (the last entry). Whether
    the device actually logs oldest-to-newest or newest-to-oldest isn't
    confirmed (every real capture so far has been empty), so this is a
    reasonable guess, not a verified fact.
    """
    if not data.error_list:
        return "none"
    name = POE_ERROR_CODES.get(data.error_list[-1])
    return name.lower() if name is not None else "unknown"


@dataclass(frozen=True, kw_only=True)
class PowerShadesSensorDescription(SensorEntityDescription):
    """Describes a PowerShades sensor."""

    value_fn: Callable[[PowerShadesData], StateType]
    icon_fn: Callable[[PowerShadesData], str | None] | None = None


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
        icon_fn=lambda data: (
            "mdi:led-outline" if _led_color(data) in (None, "off") else "mdi:led-on"
        ),
    ),
    PowerShadesSensorDescription(
        key="error",
        translation_key="error",
        device_class=SensorDeviceClass.ENUM,
        options=ERROR_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_current_error,
        icon_fn=lambda data: (
            "mdi:check-circle" if _current_error(data) == "none" else "mdi:alert-circle"
        ),
    ),
    PowerShadesSensorDescription(
        key="current_rpm",
        translation_key="current_rpm",
        icon="mdi:speedometer",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.velocity_rpm,
    ),
    PowerShadesSensorDescription(
        key="desired_rpm",
        translation_key="desired_rpm",
        # Distinct from Current RPM's speedometer - this is the setpoint
        # being aimed for, not a measured value.
        icon="mdi:target",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.desired_rpm,
    ),
    PowerShadesSensorDescription(
        key="motor_power",
        translation_key="motor_power",
        icon="mdi:engine",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.motor_duty_cycle,
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

    @property
    def icon(self) -> str | None:
        """Return a state-dependent icon, if this sensor has one."""
        if self.entity_description.icon_fn is None:
            return super().icon
        return self.entity_description.icon_fn(self.coordinator.data)
