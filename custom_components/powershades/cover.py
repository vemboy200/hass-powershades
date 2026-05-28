"""PowerShades cover platform."""
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades cover from a config entry."""
    device = hass.data[DOMAIN][config_entry.entry_id]

    # Create cover entity with coordinator
    cover = PowerShadesCover(device.coordinator, device)
    async_add_entities([cover])


class PowerShadesCover(CoordinatorEntity, CoverEntity):
    """PowerShades cover entity."""

    def __init__(self, coordinator, device):
        """Initialize the PowerShades cover."""
        super().__init__(coordinator)
        self.device = device

        # Use device name if available, otherwise fall back to IP
        if device.device_name:
            friendly_name = f"PowerShade {device.device_name}"
        else:
            friendly_name = f"PowerShade {device.ip_address}"

        # Set both the name and friendly name
        self._attr_name = friendly_name
        # This tells HA to use our name for entity ID generation
        self._attr_has_entity_name = False

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_cover"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_cover"
        self._attr_device_class = CoverDeviceClass.SHADE  # Changed from CURTAIN
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        # Cover state tracking
        self._is_opening = False
        self._is_closing = False
        self._last_position = None
        self._target_position = None
        self._is_stopping = False  # Flag to prevent movement state updates after stop

        # Last known values for when device becomes unavailable
        self._last_known_position = None
        self._last_known_battery_voltage = None
        self._last_known_battery_percentage = None

        # State request tracking
        self._last_state_request = 0
        self._state_request_interval = 5  # Request state every 5 seconds if unknown

    @property
    def device_info(self):
        """Return device info."""
        return self.device.device_info

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        if self.device.available:
            # Device is available, use current position
            position = self.device.position
            if position is not None:
                self._last_known_position = position
            return position
        else:
            # Device unavailable, return last known position if available
            if self._last_known_position is not None:
                _LOGGER.debug(
                    "Device %s unavailable, using last known position: %d",
                    self.entity_id, self._last_known_position)
                return self._last_known_position
            return None

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        # Only show opening if device is available
        if not self.device.available:
            return False
        return self._is_opening

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        # Only show closing if device is available
        if not self.device.available:
            return False
        return self._is_closing

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.device.available

    @property
    def assumed_state(self) -> bool:
        """Return True if we do optimistic updates."""
        # Return True to prevent Home Assistant from disabling buttons
        # based on position. This allows users to always control the cover
        # regardless of current position (e.g., close further when at 29%)
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {}

        # Battery information
        if self.device.available:
            # Device available, use current values
            if self.device.battery_voltage is not None:
                attrs["battery_voltage_mv"] = self.device.battery_voltage
                self._last_known_battery_voltage = self.device.battery_voltage
            if self.device.battery_percentage is not None:
                attrs["battery_percentage"] = self.device.battery_percentage
                self._last_known_battery_percentage = self.device.battery_percentage
        else:
            # Device unavailable, use last known values
            if self._last_known_battery_voltage is not None:
                attrs["battery_voltage_mv"] = self._last_known_battery_voltage
                attrs["battery_voltage_mv_stale"] = True
            if self._last_known_battery_percentage is not None:
                attrs["battery_percentage"] = self._last_known_battery_percentage
                attrs["battery_percentage_stale"] = True

        # Target position (only show if device is available)
        if self.device.available and self._target_position is not None:
            attrs["target_position"] = self._target_position

        # Device status
        attrs["device_available"] = self.device.available
        if self._last_known_position is not None:
            attrs["last_known_position"] = self._last_known_position

        return attrs

    def _update_movement_state(self, new_position: int | None):
        """Update the movement state based on position changes."""
        if new_position is None:
            # Position unknown, reset movement states
            self._is_opening = False
            self._is_closing = False
            self._target_position = None
            self._is_stopping = False
            return

        if self._last_position is None:
            # First position update, no movement state
            self._last_position = new_position
            self._is_opening = False
            self._is_closing = False
            self._is_stopping = False
            return

        # If we're in stopping state, don't update movement states
        # This prevents the position update from setting movement states back
        if self._is_stopping:
            _LOGGER.debug("Cover %s is stopping, ignoring position update: %d",
                          self.entity_id, new_position)
            self._last_position = new_position
            return

        # Check if position changed
        if new_position != self._last_position:
            if new_position > self._last_position:
                # Position increased - opening
                self._is_opening = True
                self._is_closing = False
                _LOGGER.debug("Cover %s is opening: %d -> %d",
                              self.entity_id, self._last_position, new_position)
            elif new_position < self._last_position:
                # Position decreased - closing
                self._is_opening = False
                self._is_closing = True
                _LOGGER.debug("Cover %s is closing: %d -> %d",
                              self.entity_id, self._last_position, new_position)

            # Check if we've reached the target position
            if (self._target_position is not None and
                    abs(new_position - self._target_position) <= 2):  # Within 2% tolerance
                self._is_opening = False
                self._is_closing = False
                self._target_position = None
                _LOGGER.debug("Cover %s reached target position %d",
                              self.entity_id, new_position)
        else:
            # Position unchanged - check if we should stop movement states
            if self._target_position is not None and abs(new_position - self._target_position) <= 2:
                self._is_opening = False
                self._is_closing = False
                self._target_position = None
                _LOGGER.debug("Cover %s stopped at position %d",
                              self.entity_id, new_position)

        self._last_position = new_position

        # Update device movement state
        self.device.set_movement_state(self._is_opening, self._is_closing)

    async def _request_state_if_unknown(self):
        """Request state from device if position is unknown."""
        import time

        # Only request if position is unknown and device is available
        if (self.device.position is None and
            self.device.available and
                time.time() - self._last_state_request > self._state_request_interval):

            _LOGGER.debug(
                "Requesting state for cover %s (position unknown)", self.entity_id)
            self._last_state_request = time.time()

            # Use the device's existing status request method
            await self.device.async_request_status_with_retry()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot open cover %s: device unavailable", self.entity_id)
            return

        self._target_position = 100
        self._is_opening = True
        self._is_closing = False
        self._is_stopping = False  # Clear stopping flag

        # Update device movement state
        self.device.set_movement_state(True, False)

        await self.device.async_set_position(100)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot close cover %s: device unavailable", self.entity_id)
            return

        self._target_position = 0
        self._is_opening = False
        self._is_closing = True
        self._is_stopping = False  # Clear stopping flag

        # Update device movement state
        self.device.set_movement_state(False, True)

        await self.device.async_set_position(0)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot stop cover %s: device unavailable", self.entity_id)
            return

        # Clear movement states immediately
        was_moving = self._is_opening or self._is_closing
        self._is_opening = False
        self._is_closing = False
        self._target_position = None
        self._is_stopping = True  # Set stopping flag

        # Update device movement state
        self.device.set_movement_state(False, False)

        # Send stop command to device
        await self.device.async_stop_cover()

        # Force immediate state update
        self._force_state_update()

        # If the cover was moving, request current position
        if was_moving:
            _LOGGER.debug(
                "Cover %s stopped, requesting current position", self.entity_id)
            # Request current position from device
            await self.device.async_request_status_with_retry()
            # Force another state update after position request
            self._force_state_update()
            # Clear stopping flag after position request
            self._is_stopping = False

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot set position for cover %s: device unavailable", self.entity_id)
            return

        position = kwargs.get("position")
        if position is not None:
            self._target_position = position
            self._is_stopping = False  # Clear stopping flag
            # Determine movement direction
            current_pos = self.device.position
            if current_pos is not None:
                if position > current_pos:
                    self._is_opening = True
                    self._is_closing = False
                elif position < current_pos:
                    self._is_opening = False
                    self._is_closing = True
                else:
                    self._is_opening = False
                    self._is_closing = False
            else:
                # Position unknown, assume opening if target > 50, closing if < 50
                if position > 50:
                    self._is_opening = True
                    self._is_closing = False
                else:
                    self._is_opening = False
                    self._is_closing = True

            # Update device movement state
            self.device.set_movement_state(self._is_opening, self._is_closing)

            await self.device.async_set_position(position)
            self.async_write_ha_state()

    async def async_set_upper_limit(self) -> None:
        """Set the upper limit (fully open position)."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot set upper limit for cover %s: device unavailable", self.entity_id)
            return
        await self.device.async_set_upper_limit()

    async def async_set_lower_limit(self) -> None:
        """Set the lower limit (fully closed position)."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot set lower limit for cover %s: device unavailable", self.entity_id)
            return
        await self.device.async_set_lower_limit()

    async def async_clear_limits(self) -> None:
        """Clear both upper and lower limits."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot clear limits for cover %s: device unavailable", self.entity_id)
            return
        await self.device.async_clear_limits()

    async def async_step_up(self) -> None:
        """Move the motor up one step (for trimming limits)."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot step up for cover %s: device unavailable", self.entity_id)
            return
        await self.device.async_step_up()

    async def async_step_down(self) -> None:
        """Move the motor down one step (for trimming limits)."""
        if not self.device.available:
            _LOGGER.warning(
                "Cannot step down for cover %s: device unavailable", self.entity_id)
            return
        await self.device.async_step_down()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Register callback with device for state updates
        self.device.register_entity_callback(
            self.entity_id, self._handle_device_update)

        # Force a state update
        await self.async_update_ha_state(force_refresh=True)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        # Unregister callback with device
        self.device.unregister_entity_callback(self.entity_id)
        await super().async_will_remove_from_hass()

    def _force_state_update(self) -> None:
        """Force an immediate state update."""
        # Force the state to be written to Home Assistant
        self.async_write_ha_state()
        # Schedule another update to ensure it's processed
        self.hass.async_create_task(
            self.async_update_ha_state(force_refresh=True))

    def _handle_device_update(self) -> None:
        """Handle device state updates (called by device callback)."""
        _LOGGER.debug("Cover %s received device update callback",
                      self.entity_id)

        # Sync with device movement state
        if self.device.is_opening != self._is_opening or self.device.is_closing != self._is_closing:
            _LOGGER.debug(
                "Cover %s syncing movement state from device callback: "
                "entity(opening=%s, closing=%s) -> device(opening=%s, "
                "closing=%s)",
                self.entity_id, self._is_opening, self._is_closing,
                self.device.is_opening, self.device.is_closing)
            self._is_opening = self.device.is_opening
            self._is_closing = self.device.is_closing

        # Force immediate state update
        self._force_state_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update movement state based on position changes
        self._update_movement_state(self.device.position)

        # Sync with device movement state to handle toggle commands
        if self.device.is_opening != self._is_opening or self.device.is_closing != self._is_closing:
            _LOGGER.debug(
                "Cover %s syncing movement state with device: "
                "entity(opening=%s, closing=%s) -> device(opening=%s, "
                "closing=%s)",
                self.entity_id, self._is_opening, self._is_closing,
                self.device.is_opening, self.device.is_closing)
            self._is_opening = self.device.is_opening
            self._is_closing = self.device.is_closing

# FIX: Wrap the coordinator state write in a lambda to protect the loop
        self.hass.loop.call_soon_threadsafe(
            lambda: self.async_write_ha_state()
        )

    async def async_update(self) -> None:
        """Update the entity state."""
        # Request state if position is unknown
        await self._request_state_if_unknown()
        # Call parent update method
        await super().async_update()
