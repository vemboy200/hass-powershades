"""Tests for the PowerShades switch platform."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import DISABLE_TCP_CLOUD, OP_DISABLES

from .conftest import disables_packet

ALLOW_CLOUD_CONNECTION_ENTITY_ID = (
    "switch.powershade_bedroom_shade_allow_cloud_connection"
)


async def test_allow_cloud_connection_disabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """The switch is registered but disabled by default."""
    registry = er.async_get(hass)
    entry = registry.async_get(ALLOW_CLOUD_CONNECTION_ENTITY_ID)

    assert entry is not None
    assert entry.disabled


async def test_allow_cloud_connection_on_by_default_data(
    hass: HomeAssistant, config_entry
) -> None:
    """Once enabled, the switch reflects the fetched Disables state (the
    fixture's default reply has the TCP/cloud bit clear, i.e. allowed)."""
    registry = er.async_get(hass)
    registry.async_update_entity(ALLOW_CLOUD_CONNECTION_ENTITY_ID, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ALLOW_CLOUD_CONNECTION_ENTITY_ID)
    assert state.state == "on"


async def test_allow_cloud_connection_reflects_disabled_bit(
    hass: HomeAssistant, config_entry
) -> None:
    """When the device reports the TCP/cloud bit set, the switch is off."""
    registry = er.async_get(hass)
    registry.async_update_entity(ALLOW_CLOUD_CONNECTION_ENTITY_ID, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    # Reload replaces the coordinator/connection, so patch the new one
    # and re-fetch rather than reloading again with a different mock.
    coordinator = config_entry.runtime_data

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_DISABLES:
            return disables_packet(tcp_cloud_disabled=True)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    await coordinator.async_fetch_disables_state()
    await hass.async_block_till_done()

    state = hass.states.get(ALLOW_CLOUD_CONNECTION_ENTITY_ID)
    assert state.state == "off"


async def test_turn_off_sends_disables_command(
    hass: HomeAssistant, config_entry
) -> None:
    """Turning the switch off sets the TCP/cloud disable bit, preserving
    the other bit already in the fixture's default Disables byte."""
    registry = er.async_get(hass)
    registry.async_update_entity(ALLOW_CLOUD_CONNECTION_ENTITY_ID, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_DISABLES:
            if payload:
                return disables_packet(tcp_cloud_disabled=True)
            return disables_packet(tcp_cloud_disabled=False)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": ALLOW_CLOUD_CONNECTION_ENTITY_ID},
        blocking=True,
    )

    coordinator.connection.async_request.assert_any_call(
        OP_DISABLES, bytes([0x01 | DISABLE_TCP_CLOUD])
    )
    assert hass.states.get(ALLOW_CLOUD_CONNECTION_ENTITY_ID).state == "off"


async def test_turn_on_sends_disables_command(
    hass: HomeAssistant, config_entry
) -> None:
    """Turning the switch on clears the TCP/cloud disable bit."""
    registry = er.async_get(hass)
    registry.async_update_entity(ALLOW_CLOUD_CONNECTION_ENTITY_ID, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    disabled = {"value": True}

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_DISABLES:
            if payload:
                disabled["value"] = bool(payload[0] & DISABLE_TCP_CLOUD)
            return disables_packet(tcp_cloud_disabled=disabled["value"])
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    await coordinator.async_fetch_disables_state()
    await hass.async_block_till_done()
    assert hass.states.get(ALLOW_CLOUD_CONNECTION_ENTITY_ID).state == "off"

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": ALLOW_CLOUD_CONNECTION_ENTITY_ID},
        blocking=True,
    )

    coordinator.connection.async_request.assert_any_call(OP_DISABLES, bytes([0x01]))
    assert hass.states.get(ALLOW_CLOUD_CONNECTION_ENTITY_ID).state == "on"
