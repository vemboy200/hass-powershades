"""PowerShades switch platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .entity import PowerShadesEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades switches from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [PowerShadesAllowCloudConnectionSwitch(coordinator)]
    # The cover's Slow/Medium/Fast speed presets only exist on Gen 1
    # (see cover.py's supported_speeds), so resetting speed after a move
    # is meaningless anywhere else.
    if coordinator.hw_version == "Gen 1":
        entities.append(PowerShadesResetSpeedAfterMoveSwitch(coordinator))
    async_add_entities(entities)


class PowerShadesAllowCloudConnectionSwitch(PowerShadesEntity, SwitchEntity):
    """Controls whether the shade may connect to PowerShades' cloud."""

    _attr_translation_key = "allow_cloud_connection"
    _attr_icon = "mdi:cloud"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "allow_cloud_connection")

    @property
    def is_on(self) -> bool | None:
        """Return whether the shade's cloud connectivity is enabled."""
        return self.coordinator.allow_cloud_connection

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allow the shade to connect to PowerShades' cloud."""
        await self.coordinator.async_set_allow_cloud_connection(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Block the shade from connecting to PowerShades' cloud."""
        await self.coordinator.async_set_allow_cloud_connection(False)


class PowerShadesResetSpeedAfterMoveSwitch(
    PowerShadesEntity, SwitchEntity, RestoreEntity
):
    """Controls whether a speed-carrying cover move resets the motor
    speed back afterward.

    Purely an integration-side preference - the device has no concept
    of this, so there's nothing to read back on startup. RestoreEntity
    recalls the last value the user set instead; off by default so
    existing behavior (the preset speed sticks, same as the Speed
    number entity always has) doesn't change under anyone who hasn't
    opted in.
    """

    _attr_translation_key = "reset_speed_after_move"
    _attr_icon = "mdi:speedometer-slow"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "reset_speed_after_move")

    async def async_added_to_hass(self) -> None:
        """Restore the last-set value, if any."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self.coordinator.reset_speed_after_move = last_state.state == STATE_ON

    @property
    def is_on(self) -> bool:
        """Return whether resetting speed after a move is enabled."""
        return self.coordinator.reset_speed_after_move

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable resetting speed after a speed-carrying move."""
        self.coordinator.reset_speed_after_move = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable resetting speed after a speed-carrying move."""
        self.coordinator.reset_speed_after_move = False
        self.async_write_ha_state()
