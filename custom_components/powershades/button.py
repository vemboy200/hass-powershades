"""PowerShades button platform."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades buttons from a config entry."""
    device = hass.data[DOMAIN][config_entry.entry_id]

    # Create button entities
    buttons = [
        PowerShadesToggleButton(device),
        PowerShadesSetUpperLimitButton(device),
        PowerShadesSetLowerLimitButton(device),
        PowerShadesClearLimitsButton(device),
        PowerShadesStepUpButton(device),
        PowerShadesStepDownButton(device),
    ]

    async_add_entities(buttons)


class PowerShadesButtonBase(ButtonEntity):
    """Base class for PowerShades button entities."""

    # Moves ALL inheriting buttons to the Configuration section
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device):
        """Initialize the PowerShades button."""
        self.device = device
        self._attr_device_info = device.device_info
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.device.available


class PowerShadesToggleButton(PowerShadesButtonBase):
    """Button to toggle PowerShades device between open and closed."""

    def __init__(self, device):
        """Initialize the toggle button."""
        super().__init__(device)
        self._attr_name = "Toggle Shade"

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_toggle"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_toggle"

        self._attr_icon = "mdi:swap-vertical"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.async_toggle()


class PowerShadesSetUpperLimitButton(PowerShadesButtonBase):
    """Button to set upper limit for PowerShades device."""

    def __init__(self, device):
        """Initialize the set upper limit button."""
        super().__init__(device)
        self._attr_name = "Set Upper Limit"

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_set_upper_limit"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_set_upper_limit"

        self._attr_icon = "mdi:arrow-up-bold-circle"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.async_set_upper_limit()


class PowerShadesSetLowerLimitButton(PowerShadesButtonBase):
    """Button to set lower limit for PowerShades device."""

    def __init__(self, device):
        """Initialize the set lower limit button."""
        super().__init__(device)
        self._attr_name = "Set Lower Limit"

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_set_lower_limit"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_set_lower_limit"

        self._attr_icon = "mdi:arrow-down-bold-circle"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.async_set_lower_limit()


class PowerShadesClearLimitsButton(PowerShadesButtonBase):
    """Button to clear limits for PowerShades device."""

    def __init__(self, device):
        """Initialize the clear limits button."""
        super().__init__(device)
        self._attr_name = "Clear Limits"

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_clear_limits"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_clear_limits"

        self._attr_icon = "mdi:eraser"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.async_clear_limits()


class PowerShadesStepUpButton(PowerShadesButtonBase):
    """Button to step up for PowerShades device."""

    def __init__(self, device):
        """Initialize the step up button."""
        super().__init__(device)
        self._attr_name = "Step Up"

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_step_up"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_step_up"

        self._attr_icon = "mdi:arrow-up"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.async_step_up()


class PowerShadesStepDownButton(PowerShadesButtonBase):
    """Button to step down for PowerShades device."""

    def __init__(self, device):
        """Initialize the step down button."""
        super().__init__(device)
        self._attr_name = "Step Down"

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_step_down"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_step_down"

        self._attr_icon = "mdi:arrow-down"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.async_step_down()
