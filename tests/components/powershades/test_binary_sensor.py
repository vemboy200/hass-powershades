"""Tests for the PowerShades binary sensor platform."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.powershades import coordinator as coordinator_module

MOTOR_RUNNING_ENTITY_ID = "binary_sensor.powershade_bedroom_shade_motor_running"
CHARGING_ENTITY_ID = "binary_sensor.powershade_bedroom_shade_charging"


async def test_binary_sensors_enabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """Both binary sensors are enabled by default."""
    registry = er.async_get(hass)

    for entity_id in (MOTOR_RUNNING_ENTITY_ID, CHARGING_ENTITY_ID):
        entry = registry.async_get(entity_id)
        assert entry is not None
        assert not entry.disabled


async def test_motor_running_reflects_sleep_state(
    hass: HomeAssistant, config_entry
) -> None:
    """Motor Running is the inverse of io_motor_sleep."""
    coordinator = config_entry.runtime_data

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_motor_sleep=False)
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOTOR_RUNNING_ENTITY_ID).state == "on"

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_motor_sleep=True)
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOTOR_RUNNING_ENTITY_ID).state == "off"


async def test_charging_reflects_poe_status(hass: HomeAssistant, config_entry) -> None:
    """Charging mirrors io_poe_status directly."""
    coordinator = config_entry.runtime_data

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_poe_status=True)
    )
    await hass.async_block_till_done()
    assert hass.states.get(CHARGING_ENTITY_ID).state == "on"

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_poe_status=False)
    )
    await hass.async_block_till_done()
    assert hass.states.get(CHARGING_ENTITY_ID).state == "off"
