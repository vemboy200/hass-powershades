"""Tests for the PowerShades select platform."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import OP_POE_MOTOR_PARAMS

from .conftest import motor_params_packet

SPEED_PRESET_ENTITY_ID = "select.powershade_bedroom_shade_speed_preset"


async def test_speed_preset_enabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """Enabled by default, matching the Speed number entity it drives."""
    registry = er.async_get(hass)
    entry = registry.async_get(SPEED_PRESET_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled
    assert entry.entity_category is None


async def test_speed_preset_matches_fast_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """The fixture's default motor speed (100) matches the fast preset."""
    state = hass.states.get(SPEED_PRESET_ENTITY_ID)
    assert state.state == "fast"


async def test_speed_preset_unknown_for_custom_value(
    hass: HomeAssistant, config_entry
) -> None:
    """A speed that doesn't match any preset shows as unknown, not a
    made-up closest match."""
    coordinator = config_entry.runtime_data

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=55)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    await coordinator.async_fetch_motor_speed()
    await hass.async_block_till_done()

    state = hass.states.get(SPEED_PRESET_ENTITY_ID)
    assert state.state == "unknown"


async def test_select_slow_preset_sets_motor_speed(
    hass: HomeAssistant, config_entry
) -> None:
    """Selecting a preset calls through to the shared motor speed
    setter with the preset's percentage."""
    coordinator = config_entry.runtime_data
    coordinator.hw_version = "Gen 1"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=40)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SPEED_PRESET_ENTITY_ID, "option": "slow"},
        blocking=True,
    )

    state = hass.states.get(SPEED_PRESET_ENTITY_ID)
    assert state.state == "slow"
