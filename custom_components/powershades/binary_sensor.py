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
        key="motor_awake",
        translation_key="motor_awake",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Despite its name, IO_Motor_Sleep is an active-low sleep pin: the
        # official Config.NET app labels it "H-Bridge Power" and shows it
        # green when it reads 1, and on real hardware it reads 1 while the
        # motor is driving and 0 while idle. So the raw value already means
        # "awake" and must not be inverted.
        value_fn=lambda data: data.io_motor_sleep,
    ),
    PowerShadesBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Reads True whenever PoE is present and negotiated normally, which
        # in practice is true almost the entire time the shade is reachable
        # at all - a full PoE loss also means no power to answer polls. The
        # case this actually catches is a degraded/under-negotiated PoE
        # link the shade is still limping along on.
        value_fn=lambda data: data.io_poe_status,
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
        """Return true if the condition is met."""
        return self.entity_description.value_fn(self.coordinator.data)
