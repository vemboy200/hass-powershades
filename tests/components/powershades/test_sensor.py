"""Tests for the PowerShades sensor platform."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import (
    OP_GET_DEBUG_INFO,
    OP_GET_DEVICE_ID,
    OP_GET_STATUS,
    PowerShadesConnection,
    battery_percentage,
    build_packet,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powershades import coordinator as coordinator_module
from custom_components.powershades.const import DOMAIN

from .conftest import (
    TEST_IP,
    TEST_NAME,
    TEST_SERIAL,
    debug_info_packet,
    device_id_packet,
    status_packet,
)

LED_COLOR_ENTITY_ID = "sensor.powershade_bedroom_shade_led_color"
ERROR_ENTITY_ID = "sensor.powershade_bedroom_shade_error"
RPM_POWER_ENTITY_IDS = (
    "sensor.powershade_bedroom_shade_current_rpm",
    "sensor.powershade_bedroom_shade_motor_power",
)
DESIRED_RPM_ENTITY_ID = "sensor.powershade_bedroom_shade_desired_rpm"


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
    """With both LEDs off, the sensor reports off with the outline icon."""
    state = hass.states.get(LED_COLOR_ENTITY_ID)
    assert state.state == "off"
    assert state.attributes["icon"] == "mdi:led-outline"


async def test_led_color_green(hass: HomeAssistant, config_entry) -> None:
    """Only the green LED on reports green."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(io_green_led=True, io_red_led=False)
    )
    await hass.async_block_till_done()

    state = hass.states.get(LED_COLOR_ENTITY_ID)
    assert state.state == "green"
    assert state.attributes["icon"] == "mdi:led-on"


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


async def test_error_enabled_by_default(hass: HomeAssistant, config_entry) -> None:
    """The error sensor is enabled by default, like LED color."""
    registry = er.async_get(hass)
    entry = registry.async_get(ERROR_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled


async def test_error_none_by_default(hass: HomeAssistant, config_entry) -> None:
    """With no logged errors, the sensor reports none with a check icon."""
    state = hass.states.get(ERROR_ENTITY_ID)
    assert state.state == "none"
    assert state.attributes["icon"] == "mdi:check-circle"


async def test_error_shows_most_recent_code(hass: HomeAssistant, config_entry) -> None:
    """With multiple logged errors, the last one in the list is shown,
    with the alert icon."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(error_list=[9, 21])
    )
    await hass.async_block_till_done()

    state = hass.states.get(ERROR_ENTITY_ID)
    assert state.state == "enter_sleep_mode"
    assert state.attributes["icon"] == "mdi:alert-circle"


async def test_error_unknown_code(hass: HomeAssistant, config_entry) -> None:
    """A code outside 1-33 reports unknown rather than crashing or
    reporting an invalid ENUM state."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(error_list=[255])
    )
    await hass.async_block_till_done()

    state = hass.states.get(ERROR_ENTITY_ID)
    assert state.state == "unknown"
    assert state.attributes["icon"] == "mdi:alert-circle"


async def test_rpm_and_power_disabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """Current RPM and Motor Power are disabled by default, like
    battery/voltage."""
    registry = er.async_get(hass)

    for entity_id in RPM_POWER_ENTITY_IDS:
        entry = registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled


async def test_rpm_and_power_values_when_enabled(
    hass: HomeAssistant, config_entry
) -> None:
    """Once enabled, the sensors report velocity and motor duty cycle
    from Debug Info."""
    registry = er.async_get(hass)
    for entity_id in RPM_POWER_ENTITY_IDS:
        registry.async_update_entity(entity_id, disabled_by=None)

    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(
                velocity_rpm=42, desired_rpm=60, motor_duty_cycle=75
            )
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    current_rpm, motor_power = (
        hass.states.get(entity_id) for entity_id in RPM_POWER_ENTITY_IDS
    )
    assert current_rpm.state == "42"
    assert current_rpm.attributes["icon"] == "mdi:speedometer"
    assert motor_power.state == "75"
    assert motor_power.attributes["icon"] == "mdi:engine"


async def test_desired_rpm_not_created_on_gen1(
    hass: HomeAssistant, config_entry
) -> None:
    """Gen 1 (the fixture's default) never gets a Desired RPM sensor -
    Gen 1's Set template forces SpeedControlEnable off, so the field is
    a confirmed-dead constant 0 there, not useful diagnostics."""
    registry = er.async_get(hass)
    assert registry.async_get(DESIRED_RPM_ENTITY_ID) is None


async def _setup_entry_with_model_version(hass: HomeAssistant, model_version: int):
    """Set up a config entry with a specific Get Device ID model_version,
    like test_init.py's test_setup_entry_fetches_hw_version."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_packet(model_version=model_version)
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(desired_rpm=33)
        return build_packet(op)

    with (
        patch.object(PowerShadesConnection, "async_connect", AsyncMock()),
        patch.object(
            PowerShadesConnection,
            "async_request",
            AsyncMock(side_effect=fake_request),
        ),
        patch.object(PowerShadesConnection, "close"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_desired_rpm_created_disabled_by_default_on_gen2(
    hass: HomeAssistant,
) -> None:
    """On Gen 2, Desired RPM is registered, but disabled by default like
    the other rarely-useful diagnostic telemetry sensors - unverified
    against real Gen 2 hardware."""
    await _setup_entry_with_model_version(hass, model_version=2)

    registry = er.async_get(hass)
    entry = registry.async_get(DESIRED_RPM_ENTITY_ID)
    assert entry is not None
    assert entry.disabled


async def test_desired_rpm_value_when_enabled_on_gen2(hass: HomeAssistant) -> None:
    """Once enabled on Gen 2, the sensor reports Debug Info's desired_rpm."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_packet(model_version=2)
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(desired_rpm=33)
        return build_packet(op)

    with (
        patch.object(PowerShadesConnection, "async_connect", AsyncMock()),
        patch.object(
            PowerShadesConnection,
            "async_request",
            AsyncMock(side_effect=fake_request),
        ),
        patch.object(PowerShadesConnection, "close"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        registry.async_update_entity(DESIRED_RPM_ENTITY_ID, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(DESIRED_RPM_ENTITY_ID)
    assert state is not None
    assert state.state == "33"
    assert state.attributes["icon"] == "mdi:speedometer"
