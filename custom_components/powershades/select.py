"""PowerShades select platform."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .entity import PowerShadesEntity

PARALLEL_UPDATES = 0

# Spread across the confirmed valid range (40-100) - the app's own
# floor and ceiling, not arbitrary round numbers.
SPEED_PRESETS = {
    "slow": 40,
    "medium": 70,
    "fast": 100,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades selects from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([PowerShadesSpeedPresetSelect(coordinator)])


class PowerShadesSpeedPresetSelect(PowerShadesEntity, SelectEntity):
    """Sets the shade's motor speed to a slow/medium/fast preset.

    A shortcut over the Speed number entity for automations - e.g. slow
    for a quiet nighttime close, fast for a manually-triggered one.
    Enabled by default and uncategorized (Control), matching the Speed
    number entity it drives.
    """

    _attr_translation_key = "speed_preset"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, "speed_preset")
        self._attr_options = list(SPEED_PRESETS)

    @property
    def current_option(self) -> str | None:
        """Return the preset matching the shade's current speed.

        None if the current speed doesn't exactly match a preset (e.g.
        it was set to a custom value via the Speed number entity, or
        hasn't been read yet).
        """
        percent = self.coordinator.motor_speed_percent
        if percent is None:
            return None
        for name, value in SPEED_PRESETS.items():
            if value == percent:
                return name
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the shade's motor speed to the chosen preset."""
        await self.coordinator.async_set_motor_speed(SPEED_PRESETS[option])
