"""Tests for the PowerShades binary sensor platform."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import OP_GET_DEBUG_INFO, OP_GET_STATUS

from .conftest import debug_info_packet, status_packet

ENTITY_ID = "binary_sensor.powershade_bedroom_shade_green_led"


async def test_green_led_enabled_by_default(hass: HomeAssistant, config_entry) -> None:
    """The green LED sensor is registered and enabled by default."""
    registry = er.async_get(hass)
    entry = registry.async_get(ENTITY_ID)
    assert entry is not None
    assert not entry.disabled


async def test_green_led_off_by_default(hass: HomeAssistant, config_entry) -> None:
    """The green LED sensor is off when the device reports it off."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"


async def test_green_led_turns_on(hass: HomeAssistant, config_entry) -> None:
    """The green LED sensor follows the Get Debug Info reply."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(green_led=True)
        raise AssertionError(f"unexpected op {op}")

    coordinator = config_entry.runtime_data
    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "on"
