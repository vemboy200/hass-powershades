"""PowerShades number platform."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .entity import PowerShadesEntity

PARALLEL_UPDATES = 0

# Confirmed range from the vendor's own app (frmMain.cs): it refuses to
# send anything below 40, and 100 is the practical ceiling.
_MIN_SPEED_PERCENT = 40
_MAX_SPEED_PERCENT = 100


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades numbers from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([PowerShadesMotorSpeedNumber(coordinator)])


class PowerShadesMotorSpeedNumber(PowerShadesEntity, NumberEntity):
    """Sets the shade's motor speed - the "Speed (%)" field in the
    vendor's own app. Enabled by default and uncategorized (Control),
    not Configuration - this is meant for active, day-to-day use (e.g.
    a slower speed for night automations, faster for manual use), not a
    rarely-touched setting.
    """

    _attr_translation_key = "motor_speed"
    _attr_icon = "mdi:speedometer-medium"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = _MIN_SPEED_PERCENT
    _attr_native_max_value = _MAX_SPEED_PERCENT
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, "motor_speed")

    @property
    def native_value(self) -> float | None:
        """Return the shade's currently configured motor speed."""
        return self.coordinator.motor_speed_percent

    async def async_set_native_value(self, value: float) -> None:
        """Set the shade's motor speed."""
        await self.coordinator.async_set_motor_speed(int(value))
