"""PowerShades cover platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_SPEED,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .entity import PowerShadesEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Spread across the confirmed valid range (40-100) - the vendor app's own
# floor and ceiling, not arbitrary round numbers. Gen 1 only, same
# restriction as the Speed number entity.
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
    """Set up PowerShades cover from a config entry."""
    async_add_entities([PowerShadesCover(entry.runtime_data)])


class PowerShadesCover(PowerShadesEntity, CoverEntity):
    """PowerShades cover entity."""

    _attr_name = None
    _attr_translation_key = "cover"
    _attr_device_class = CoverDeviceClass.SHADE

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the PowerShades cover."""
        super().__init__(coordinator, "cover")

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return the supported features, adding Speed only on Gen 1."""
        features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )
        if self.supported_speeds:
            features |= CoverEntityFeature.SPEED
        return features

    @property
    def supported_speeds(self) -> list[str] | None:
        """Return the slow/medium/fast speed presets, Gen 1 only.

        Setting motor speed on Gen 2 is unverified against real hardware
        (see the Speed number entity), so Speed isn't advertised there.
        """
        if self.coordinator.hw_version != "Gen 1":
            return None
        return list(SPEED_PRESETS)

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self.coordinator.data.position

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.coordinator.data.position
        if position is None:
            return None
        return position == 0

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening.

        motor_state is direction*10 + phase (e.g. 1/2 = moving up,
        11/12 = moving down), reported directly by the device rather
        than inferred from position deltas.
        """
        motor_state = self.coordinator.data.motor_state
        return motor_state is not None and 0 < motor_state < 10

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        motor_state = self.coordinator.data.motor_state
        return motor_state is not None and motor_state >= 10

    async def _async_apply_speed(self, kwargs: dict[str, Any]) -> bool:
        """Set the shade's motor speed first, if a speed preset was given.

        The base CoverEntity already validates the speed against
        supported_speeds before calling us, so it's guaranteed to be a
        valid SPEED_PRESETS key here. Returns whether a speed was
        actually applied, so the caller knows whether a reset afterward
        is relevant at all.
        """
        speed = kwargs.get(ATTR_SPEED)
        if speed is None:
            return False
        await self.coordinator.async_set_motor_speed(SPEED_PRESETS[speed])
        return True

    def _maybe_schedule_speed_reset(self, speed_applied: bool) -> None:
        """Schedule resetting the motor speed once the move finishes.

        Fire-and-forget: waiting for the shade to stop can take as long
        as its full travel time, and blocking this service call for that
        long would be wrong. Only relevant if a speed preset was applied
        this call and the user has opted into Reset Speed After Move.
        """
        if not speed_applied or not self.coordinator.reset_speed_after_move:
            return
        self.hass.async_create_task(
            self.coordinator.async_reset_speed_after_move(
                self.coordinator.reset_speed_to_percent
            )
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        speed_applied = await self._async_apply_speed(kwargs)
        await self.coordinator.async_set_position(100)
        self._maybe_schedule_speed_reset(speed_applied)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        speed_applied = await self._async_apply_speed(kwargs)
        await self.coordinator.async_set_position(0)
        self._maybe_schedule_speed_reset(speed_applied)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.coordinator.async_stop()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        speed_applied = await self._async_apply_speed(kwargs)
        await self.coordinator.async_set_position(kwargs[ATTR_POSITION])
        self._maybe_schedule_speed_reset(speed_applied)
