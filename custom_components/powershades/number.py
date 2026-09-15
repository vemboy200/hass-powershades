"""PowerShades number platform."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE, EntityCategory
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
    entities: list[NumberEntity] = [PowerShadesMotorSpeedNumber(coordinator)]
    # Same Gen 1-only restriction as the cover's speed presets and the
    # Reset Speed After Move switch - nothing to reset to on Gen 2.
    if coordinator.hw_version == "Gen 1":
        entities.append(PowerShadesResetSpeedToNumber(coordinator))
    async_add_entities(entities)


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


class PowerShadesResetSpeedToNumber(PowerShadesEntity, RestoreNumber):
    """Sets the speed a speed-carrying cover move resets back to
    afterward, when Reset Speed After Move is enabled.

    Purely an integration-side preference - the device has no concept
    of this, so RestoreNumber recalls the user's last explicit choice.
    On first-ever setup, with nothing yet to restore, it seeds from
    whatever the Speed number reads at that point, falling back to 100
    if that read failed.
    """

    _attr_translation_key = "reset_speed_to"
    _attr_icon = "mdi:speedometer-slow"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = _MIN_SPEED_PERCENT
    _attr_native_max_value = _MAX_SPEED_PERCENT
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, "reset_speed_to")

    async def async_added_to_hass(self) -> None:
        """Restore the last-set value, or seed from the current speed."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None and last_data.native_value is not None:
            self.coordinator.reset_speed_to_percent = int(last_data.native_value)
        else:
            self.coordinator.reset_speed_to_percent = (
                self.coordinator.motor_speed_percent or _MAX_SPEED_PERCENT
            )

    @property
    def native_value(self) -> float:
        """Return the speed to reset to."""
        return self.coordinator.reset_speed_to_percent

    async def async_set_native_value(self, value: float) -> None:
        """Set the speed to reset to."""
        self.coordinator.reset_speed_to_percent = int(value)
        self.async_write_ha_state()
