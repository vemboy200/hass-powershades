"""Tests for the PowerShades switch platform."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import (
    DISABLE_TCP_CLOUD,
    OP_DISABLES,
    OP_GET_DEBUG_INFO,
    OP_GET_DEVICE_ID,
    OP_GET_STATUS,
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
    disables_packet,
    status_packet,
)

ALLOW_CLOUD_CONNECTION_ENTITY_ID = (
    "switch.powershade_bedroom_shade_allow_cloud_connection"
)
RESET_SPEED_AFTER_MOVE_ENTITY_ID = (
    "switch.powershade_bedroom_shade_reset_speed_after_move"
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


async def _setup_entry_with_model_version(hass: HomeAssistant, model_version: int):
    """Set up a config entry with a specific Get Device ID model_version,
    like test_sensor.py's helper."""
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


async def test_reset_speed_after_move_created_on_gen1(
    hass: HomeAssistant, config_entry
) -> None:
    """Gen 1 (the fixture's default) gets the Reset Speed After Move
    switch, matching the cover's own speed presets being Gen 1 only."""
    registry = er.async_get(hass)
    entry = registry.async_get(RESET_SPEED_AFTER_MOVE_ENTITY_ID)

    assert entry is not None
    assert not entry.disabled
    assert hass.states.get(RESET_SPEED_AFTER_MOVE_ENTITY_ID).state == "off"


async def test_reset_speed_after_move_not_created_on_gen2(
    hass: HomeAssistant,
) -> None:
    """Gen 2 never gets the switch - the cover never advertises SPEED
    there, so there's nothing to reset."""
    await _setup_entry_with_model_version(hass, model_version=2)

    registry = er.async_get(hass)
    assert registry.async_get(RESET_SPEED_AFTER_MOVE_ENTITY_ID) is None


async def test_turn_on_reset_speed_after_move(
    hass: HomeAssistant, config_entry
) -> None:
    """Turning the switch on updates the coordinator's flag that
    cover.py reads to decide whether to schedule a reset."""
    coordinator = config_entry.runtime_data

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": RESET_SPEED_AFTER_MOVE_ENTITY_ID},
        blocking=True,
    )

    assert coordinator.reset_speed_after_move is True
    assert hass.states.get(RESET_SPEED_AFTER_MOVE_ENTITY_ID).state == "on"


async def test_turn_off_reset_speed_after_move(
    hass: HomeAssistant, config_entry
) -> None:
    """Turning the switch back off clears the coordinator's flag."""
    coordinator = config_entry.runtime_data
    coordinator.reset_speed_after_move = True

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": RESET_SPEED_AFTER_MOVE_ENTITY_ID},
        blocking=True,
    )

    assert coordinator.reset_speed_after_move is False
    assert hass.states.get(RESET_SPEED_AFTER_MOVE_ENTITY_ID).state == "off"


async def test_reset_speed_after_move_survives_restart(hass: HomeAssistant) -> None:
    """The switch has no device-side state to read back, so a restart
    (simulated here via reload) must restore the last value via
    RestoreEntity rather than resetting to the off default."""
    entry = await _setup_entry_with_model_version(hass, model_version=0)

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": RESET_SPEED_AFTER_MOVE_ENTITY_ID},
        blocking=True,
    )
    assert hass.states.get(RESET_SPEED_AFTER_MOVE_ENTITY_ID).state == "on"

    with (
        patch.object(PowerShadesConnection, "async_connect", AsyncMock()),
        patch.object(
            PowerShadesConnection,
            "async_request",
            AsyncMock(
                side_effect=lambda op, payload=b"", timeout=None, retries=None: (
                    status_packet()
                    if op == OP_GET_STATUS
                    else (
                        device_id_packet()
                        if op == OP_GET_DEVICE_ID
                        else (
                            debug_info_packet()
                            if op == OP_GET_DEBUG_INFO
                            else build_packet(op)
                        )
                    )
                )
            ),
        ),
        patch.object(PowerShadesConnection, "close"),
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(RESET_SPEED_AFTER_MOVE_ENTITY_ID).state == "on"
    assert entry.runtime_data.reset_speed_after_move is True
