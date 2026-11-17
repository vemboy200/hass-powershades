"""Tests for the PowerShades switch platform."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import (
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
    status_packet,
)

RESET_SPEED_AFTER_MOVE_ENTITY_ID = (
    "switch.powershade_bedroom_shade_reset_speed_after_move"
)


async def _setup_entry_with_model_version(hass: HomeAssistant, model_version: int):
    """Set up a config entry with a specific Get Device ID model_version,
    like test_sensor.py's helper."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    return await _setup_entry(
        hass, AsyncMock(side_effect=_fake_request(model_version)), entry
    )


def _fake_request(model_version: int):
    """Return an async_request side effect for a given model_version."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_packet(model_version=model_version)
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet()
        return build_packet(op)

    return fake_request


async def _setup_entry(
    hass: HomeAssistant, request: AsyncMock, entry: MockConfigEntry | None = None
) -> MockConfigEntry:
    """Set up a config entry with the given mocked async_request."""
    if entry is None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
            unique_id=str(TEST_SERIAL),
        )
        entry.add_to_hass(hass)

    with (
        patch.object(PowerShadesConnection, "async_connect", AsyncMock()),
        patch.object(PowerShadesConnection, "async_request", request),
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


async def test_retired_cloud_switch_removed_from_registry(
    hass: HomeAssistant,
) -> None:
    """The retired Allow Cloud Connection switch is removed from the
    registry on setup, and setup never reads Feature Disables any more."""
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"{DOMAIN}_{TEST_SERIAL}_allow_cloud_connection",
        suggested_object_id="powershade_bedroom_shade_allow_cloud_connection",
    )
    assert registry.async_get(stale.entity_id) is not None

    request = AsyncMock(side_effect=_fake_request(model_version=0))
    await _setup_entry(hass, request)

    assert registry.async_get(stale.entity_id) is None
    assert OP_DISABLES not in [call.args[0] for call in request.call_args_list]


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
