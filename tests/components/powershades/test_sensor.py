"""Tests for the PowerShades sensor platform."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import battery_percentage

from custom_components.powershades import coordinator as coordinator_module

LED_COLOR_ENTITY_ID = "sensor.powershade_bedroom_shade_led_color"


async def test_sensors_disabled_by_default(hass: HomeAssistant, config_entry) -> None:
    """Battery and voltage sensors are registered but disabled by default."""
    registry = er.async_get(hass)

    battery_entry = registry.async_get("sensor.powershade_bedroom_shade_battery")
    voltage_entry = registry.async_get("sensor.powershade_bedroom_shade_voltage")

    assert battery_entry is not None
    assert battery_entry.disabled
    assert voltage_entry is not None
    assert voltage_entry.disabled


async def test_sensor_values_when_enabled(hass: HomeAssistant, config_entry) -> None:
    """Once enabled, the sensors report the battery percentage and voltage."""
    registry = er.async_get(hass)

    for object_id in ("battery", "voltage"):
        registry.async_update_entity(
            f"sensor.powershade_bedroom_shade_{object_id}", disabled_by=None
        )

    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    voltage_state = hass.states.get("sensor.powershade_bedroom_shade_voltage")
    battery_state = hass.states.get("sensor.powershade_bedroom_shade_battery")

    assert voltage_state.state == "3700"
    assert battery_state.state == str(battery_percentage(3700))


async def test_led_color_enabled_by_default(hass: HomeAssistant, config_entry) -> None:
    """The LED color sensor is enabled by default, unlike battery/voltage."""
    registry = er.async_get(hass)
    entry = registry.async_get(LED_COLOR_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled


async def test_led_color_off_by_default(hass: HomeAssistant, config_entry) -> None:
    """With both LEDs off, the sensor reports off."""
    state = hass.states.get(LED_COLOR_ENTITY_ID)
    assert state.state == "off"


async def test_led_color_green(hass: HomeAssistant, config_entry) -> None:
    """Only the green LED on reports green."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_green_led=True, io_red_led=False)
    )
    await hass.async_block_till_done()

    state = hass.states.get(LED_COLOR_ENTITY_ID)
    assert state.state == "green"


async def test_led_color_red(hass: HomeAssistant, config_entry) -> None:
    """Only the red LED on reports red."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_green_led=False, io_red_led=True)
    )
    await hass.async_block_till_done()

    state = hass.states.get(LED_COLOR_ENTITY_ID)
    assert state.state == "red"


async def test_led_color_yellow(hass: HomeAssistant, config_entry) -> None:
    """Both LEDs on together report yellow."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_green_led=True, io_red_led=True)
    )
    await hass.async_block_till_done()

    state = hass.states.get(LED_COLOR_ENTITY_ID)
    assert state.state == "yellow"
