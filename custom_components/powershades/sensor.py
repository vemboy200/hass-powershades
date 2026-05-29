"""PowerShades sensor platform."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PowerShades sensors from a config entry."""
    device = hass.data[DOMAIN][config_entry.entry_id]

    # Create sensor entities
    sensors = [
        PowerShadesBatterySensor(device),
        PowerShadesVoltageSensor(device),
    ]
    async_add_entities(sensors)


class PowerShadesBatterySensor(SensorEntity):
    """PowerShades battery percentage sensor."""

    def __init__(self, device):
        """Initialize the PowerShades battery sensor."""
        self.device = device
        self._attr_name = None  # Use device name instead

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_battery"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_battery"

        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self):
        """Return device info."""
        return self.device.device_info

    @property
    def native_value(self) -> int | None:
        """Return the battery percentage."""
        return self.device.battery_percentage

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        _LOGGER.debug("Registering entity callback for %s", self.entity_id)
        # Register for updates from the device
        self.device.register_entity_callback(self.entity_id, self.async_write_ha_state)
        # Force a state update
        await self.async_update_ha_state(force_refresh=True)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        _LOGGER.debug("Unregistering entity callback for %s", self.entity_id)
        # Unregister from device updates
        self.device.unregister_entity_callback(self.entity_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        avail = self.device.available
        _LOGGER.debug(
            "Entity %s available property called, returning %s", self.entity_id, avail
        )
        return avail


class PowerShadesVoltageSensor(SensorEntity):
    """PowerShades battery voltage sensor."""

    def __init__(self, device):
        """Initialize the PowerShades voltage sensor."""
        self.device = device
        self._attr_name = None  # Use device name instead

        # Use serial number for unique ID if available
        if device.serial_number:
            self._attr_unique_id = f"{DOMAIN}_{device.serial_number}_voltage"
        else:
            self._attr_unique_id = f"{DOMAIN}_{device.entry_id}_voltage"

        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.MILLIVOLT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self):
        """Return device info."""
        return self.device.device_info

    @property
    def native_value(self) -> int | None:
        """Return the battery voltage in millivolts."""
        return self.device.battery_voltage

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        _LOGGER.debug("Registering entity callback for %s", self.entity_id)
        # Register for updates from the device
        self.device.register_entity_callback(self.entity_id, self.async_write_ha_state)
        # Force a state update
        await self.async_update_ha_state(force_refresh=True)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        _LOGGER.debug("Unregistering entity callback for %s", self.entity_id)
        # Unregister from device updates
        self.device.unregister_entity_callback(self.entity_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        avail = self.device.available
        _LOGGER.debug(
            "Entity %s available property called, returning %s", self.entity_id, avail
        )
        return avail
