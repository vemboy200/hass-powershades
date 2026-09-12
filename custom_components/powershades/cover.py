"""PowerShades cover platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
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
    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the PowerShades cover."""
        super().__init__(coordinator, "cover")

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

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.async_set_position(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.async_set_position(0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.coordinator.async_stop()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        await self.coordinator.async_set_position(kwargs[ATTR_POSITION])
