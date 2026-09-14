"""Tests for the PowerShades number platform."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import ADMIN_ACCESS_PAYLOAD, OP_ADMIN_ACCESS, OP_POE_MOTOR_PARAMS

from .conftest import motor_params_packet

MOTOR_SPEED_ENTITY_ID = "number.powershade_bedroom_shade_speed"


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
