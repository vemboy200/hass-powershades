"""Tests for the PowerShades binary sensor platform."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.powershades import coordinator as coordinator_module

MOTOR_AWAKE_ENTITY_ID = "binary_sensor.powershade_bedroom_shade_motor_awake"
CHARGING_ENTITY_ID = "binary_sensor.powershade_bedroom_shade_charging"


async def test_motor_awake_enabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """Motor Awake is enabled by default."""
    registry = er.async_get(hass)
    entry = registry.async_get(MOTOR_AWAKE_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled


async def test_charging_disabled_by_default(hass: HomeAssistant, config_entry) -> None:
    """Charging is disabled by default, same as the battery/voltage sensors."""
    registry = er.async_get(hass)
    entry = registry.async_get(CHARGING_ENTITY_ID)

    assert entry is not None
    assert entry.disabled


async def test_motor_awake_reflects_sleep_state(
    hass: HomeAssistant, config_entry
) -> None:
    """Motor Awake is the inverse of io_motor_sleep."""
    coordinator = config_entry.runtime_data

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_motor_sleep=False)
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOTOR_AWAKE_ENTITY_ID).state == "on"

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_motor_sleep=True)
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOTOR_AWAKE_ENTITY_ID).state == "off"


async def test_charging_reflects_poe_status(hass: HomeAssistant, config_entry) -> None:
    """Charging mirrors io_poe_status directly, once enabled."""
    registry = er.async_get(hass)
    registry.async_update_entity(CHARGING_ENTITY_ID, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
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
