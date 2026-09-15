"""Tests for the PowerShades number platform."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import (
    ADMIN_ACCESS_PAYLOAD,
    OP_ADMIN_ACCESS,
    OP_GET_DEBUG_INFO,
    OP_GET_DEVICE_ID,
    OP_GET_STATUS,
    OP_POE_MOTOR_PARAMS,
    PowerShadesConnection,
    build_packet,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powershades.const import DOMAIN

from .conftest import (
    TEST_IP,
    TEST_NAME,
    TEST_SERIAL,
    debug_info_packet,
    device_id_packet,
    motor_params_packet,
    status_packet,
)

MOTOR_SPEED_ENTITY_ID = "number.powershade_bedroom_shade_speed"
RESET_SPEED_TO_ENTITY_ID = "number.powershade_bedroom_shade_reset_speed_to"


async def test_motor_speed_enabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """Unlike the other admin-gated/diagnostic entities, this one is
    enabled by default - it's meant for active, everyday use."""
    registry = er.async_get(hass)
    entry = registry.async_get(MOTOR_SPEED_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled
    assert entry.entity_category is None


async def test_motor_speed_reflects_fetched_value(
    hass: HomeAssistant, config_entry
) -> None:
    """The number's current value comes from a Get PoE Motor Parameters
    fetched at setup, not Debug Info."""
    state = hass.states.get(MOTOR_SPEED_ENTITY_ID)
    assert state.state == "100"  # conftest's motor_params_packet default


async def test_set_motor_speed_sends_admin_access_and_set(
    hass: HomeAssistant, config_entry
) -> None:
    """Setting the number sends Admin Access immediately before a Set
    PoE Motor Parameters command, using the Gen 1 fixed template."""
    coordinator = config_entry.runtime_data
    coordinator.hw_version = "Gen 1"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=70)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": MOTOR_SPEED_ENTITY_ID, "value": 70},
        blocking=True,
    )

    coordinator.connection.async_request.assert_any_call(
        OP_ADMIN_ACCESS, ADMIN_ACCESS_PAYLOAD
    )
    state = hass.states.get(MOTOR_SPEED_ENTITY_ID)
    assert state.state == "70"


async def _setup_entry_with_model_version(
    hass: HomeAssistant, model_version: int, motor_power_up: int = 100
):
    """Set up a config entry with a specific Get Device ID model_version
    and motor speed, like test_sensor.py's helper."""
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
            return debug_info_packet()
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=motor_power_up)
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


async def test_reset_speed_to_created_on_gen1(
    hass: HomeAssistant, config_entry
) -> None:
    """Gen 1 (the fixture's default) gets the Reset Speed To number,
    matching the cover's own speed presets being Gen 1 only."""
    registry = er.async_get(hass)
    entry = registry.async_get(RESET_SPEED_TO_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled
    assert entry.entity_category is not None


async def test_reset_speed_to_not_created_on_gen2(hass: HomeAssistant) -> None:
    """Gen 2 never gets the number - the cover never advertises SPEED
    there, so there's nothing to reset to."""
    await _setup_entry_with_model_version(hass, model_version=2)

    registry = er.async_get(hass)
    assert registry.async_get(RESET_SPEED_TO_ENTITY_ID) is None


async def test_reset_speed_to_seeds_from_fetched_motor_speed(
    hass: HomeAssistant,
) -> None:
    """With nothing yet restored, the number seeds from whatever the
    Speed number reads at setup, not a hardcoded default."""
    await _setup_entry_with_model_version(hass, model_version=0, motor_power_up=70)

    state = hass.states.get(RESET_SPEED_TO_ENTITY_ID)
    assert state.state == "70"


async def test_set_reset_speed_to_updates_coordinator_only(
    hass: HomeAssistant, config_entry
) -> None:
    """Setting the number is purely local - it never touches the
    device, unlike the Speed number."""
    coordinator = config_entry.runtime_data
    coordinator.connection.async_request.reset_mock()

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": RESET_SPEED_TO_ENTITY_ID, "value": 55},
        blocking=True,
    )

    assert coordinator.reset_speed_to_percent == 55
    assert hass.states.get(RESET_SPEED_TO_ENTITY_ID).state == "55"
    coordinator.connection.async_request.assert_not_called()


async def test_reset_speed_to_survives_restart(hass: HomeAssistant) -> None:
    """The number has no device-side state to read back, so a restart
    (simulated here via reload) must restore the user's last explicit
    choice via RestoreNumber rather than reseeding from the current
    Speed value."""
    entry = await _setup_entry_with_model_version(hass, model_version=0)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": RESET_SPEED_TO_ENTITY_ID, "value": 45},
        blocking=True,
    )
    assert hass.states.get(RESET_SPEED_TO_ENTITY_ID).state == "45"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_packet(model_version=0)
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet()
        if op == OP_POE_MOTOR_PARAMS:
            # A different value than the restored 45, to prove the
            # restored choice wins over reseeding from this.
            return motor_params_packet(motor_power_up=90)
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
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(RESET_SPEED_TO_ENTITY_ID).state == "45"
    assert entry.runtime_data.reset_speed_to_percent == 45
