"""Tests for the PowerShades cover platform."""

import struct
from unittest.mock import AsyncMock, patch

from homeassistant.components.cover import (
    ATTR_SPEED,
    CoverEntityCapabilityAttribute,
    CoverEntityFeature,
)
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from pyowershades import (
    ADMIN_ACCESS_PAYLOAD,
    OP_ADMIN_ACCESS,
    OP_GET_DEBUG_INFO,
    OP_JOG_STOP,
    OP_POE_MOTOR_PARAMS,
    OP_SET_POSITION,
    build_set_motor_speed_payload_gen1,
    build_set_position_payload,
)

from custom_components.powershades import coordinator as coordinator_module
from custom_components.powershades.cover import SPEED_PRESETS

from .conftest import debug_info_packet, motor_params_packet

# Same field layout the outgoing Set PoE Motor Parameters payload uses -
# see build_set_motor_speed_payload_gen1's docstring.
_SET_MOTOR_PARAMS_FORMAT = "<4BhhIIHHhhIIHHhhBBHH"

ENTITY_ID = "cover.powershade_bedroom_shade"


async def test_cover_initial_state(hass: HomeAssistant, config_entry) -> None:
    """The cover reflects the position reported by the device."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "open"
    assert state.attributes["current_position"] == 50
    assert state.attributes[ATTR_FRIENDLY_NAME] == "PowerShade Bedroom Shade"


async def test_cover_closed_state(hass: HomeAssistant, config_entry) -> None:
    """A position of 0 is reported as closed."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(coordinator_module.PowerShadesData(position=0))
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "closed"


async def test_cover_opening_state(hass: HomeAssistant, config_entry) -> None:
    """motor_state 1/2 (moving up) is reported as opening."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(position=50, motor_state=2)
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "opening"


async def test_cover_closing_state(hass: HomeAssistant, config_entry) -> None:
    """motor_state 11/12 (moving down) is reported as closing."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(position=50, motor_state=12)
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "closing"


async def test_open_cover(hass: HomeAssistant, config_entry) -> None:
    """Opening the cover sets the position to 100."""
    coordinator = config_entry.runtime_data
    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )

    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(100)
    )


async def test_close_cover(hass: HomeAssistant, config_entry) -> None:
    """Closing the cover sets the position to 0."""
    coordinator = config_entry.runtime_data
    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": ENTITY_ID}, blocking=True
    )

    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(0)
    )


async def test_stop_cover(hass: HomeAssistant, config_entry) -> None:
    """Stopping the cover sends the jog stop command."""
    coordinator = config_entry.runtime_data
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": ENTITY_ID}, blocking=True
    )

    coordinator.connection.async_request.assert_any_call(OP_JOG_STOP, b"")


async def test_set_cover_position(hass: HomeAssistant, config_entry) -> None:
    """Setting a specific position sends that position to the device."""
    coordinator = config_entry.runtime_data
    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 30},
        blocking=True,
    )

    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(30)
    )


async def test_cover_supports_speed_on_gen1(hass: HomeAssistant, config_entry) -> None:
    """Gen 1 (the fixture's default) advertises the speed presets."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["supported_features"] & CoverEntityFeature.SPEED
    assert state.attributes[CoverEntityCapabilityAttribute.SUPPORTED_SPEEDS] == list(
        SPEED_PRESETS
    )


async def test_cover_speed_not_supported_on_gen2(
    hass: HomeAssistant, config_entry
) -> None:
    """Gen 2's Set behavior is unverified, so speed isn't advertised there."""
    coordinator = config_entry.runtime_data
    coordinator.hw_version = "Gen 2"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert not state.attributes["supported_features"] & CoverEntityFeature.SPEED
    assert CoverEntityCapabilityAttribute.SUPPORTED_SPEEDS not in state.attributes


async def test_open_cover_with_speed_sets_motor_speed_first(
    hass: HomeAssistant, config_entry
) -> None:
    """Opening with a speed sets the shade's speed before moving it."""
    coordinator = config_entry.runtime_data
    original_side_effect = coordinator.connection.async_request.side_effect
    calls: list[tuple[int, bytes]] = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=SPEED_PRESETS["fast"])
        return await original_side_effect(op, payload, timeout=timeout, retries=retries)

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "cover",
        "open_cover",
        {"entity_id": ENTITY_ID, ATTR_SPEED: "fast"},
        blocking=True,
    )

    ops = [op for op, _ in calls]
    admin_index = ops.index(OP_ADMIN_ACCESS)
    motor_index = ops.index(OP_POE_MOTOR_PARAMS)
    position_index = ops.index(OP_SET_POSITION)
    assert admin_index < motor_index < position_index
    assert calls[admin_index] == (OP_ADMIN_ACCESS, ADMIN_ACCESS_PAYLOAD)
    assert calls[motor_index] == (
        OP_POE_MOTOR_PARAMS,
        build_set_motor_speed_payload_gen1(SPEED_PRESETS["fast"]),
    )
    assert calls[position_index] == (OP_SET_POSITION, build_set_position_payload(100))


async def test_set_cover_position_with_speed_sets_motor_speed_first(
    hass: HomeAssistant, config_entry
) -> None:
    """Setting a position with a speed sets speed before moving."""
    coordinator = config_entry.runtime_data
    original_side_effect = coordinator.connection.async_request.side_effect
    calls: list[tuple[int, bytes]] = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=SPEED_PRESETS["slow"])
        return await original_side_effect(op, payload, timeout=timeout, retries=retries)

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 30, ATTR_SPEED: "slow"},
        blocking=True,
    )

    ops = [op for op, _ in calls]
    admin_index = ops.index(OP_ADMIN_ACCESS)
    motor_index = ops.index(OP_POE_MOTOR_PARAMS)
    position_index = ops.index(OP_SET_POSITION)
    assert admin_index < motor_index < position_index
    assert calls[motor_index] == (
        OP_POE_MOTOR_PARAMS,
        build_set_motor_speed_payload_gen1(SPEED_PRESETS["slow"]),
    )
    assert calls[position_index] == (OP_SET_POSITION, build_set_position_payload(30))


async def test_open_cover_without_speed_does_not_touch_motor_speed(
    hass: HomeAssistant, config_entry
) -> None:
    """Opening without a speed doesn't send Admin Access/Motor Parameters."""
    coordinator = config_entry.runtime_data
    coordinator.connection.async_request.reset_mock()

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )

    ops = [call.args[0] for call in coordinator.connection.async_request.call_args_list]
    assert OP_ADMIN_ACCESS not in ops
    assert OP_POE_MOTOR_PARAMS not in ops


async def test_open_cover_with_speed_resets_after_move_when_enabled(
    hass: HomeAssistant, config_entry
) -> None:
    """With Reset Speed After Move on, the speed is set back once the
    shade actually finishes moving, rather than staying pinned to the
    preset - that's the whole point of the feature."""
    coordinator = config_entry.runtime_data
    coordinator.reset_speed_after_move = True
    coordinator.reset_speed_to_percent = 100

    calls: list[tuple[int, bytes]] = []
    debug_replies = iter(
        [
            debug_info_packet(motor_state=12, current_percent=80),  # initial refresh
            debug_info_packet(motor_state=12, current_percent=40),  # still moving
            debug_info_packet(motor_state=0, current_percent=0),  # idle, position moved
            debug_info_packet(motor_state=0, current_percent=0),  # idle, stable -> stop
        ]
    )

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_GET_DEBUG_INFO:
            return next(debug_replies)
        if op == OP_POE_MOTOR_PARAMS:
            if payload:
                fields = struct.unpack(_SET_MOTOR_PARAMS_FORMAT, payload)
                return motor_params_packet(motor_power_up=fields[10])
            return motor_params_packet(motor_power_up=100)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with patch.object(coordinator_module, "_RESET_SPEED_POLL_INTERVAL", 0):
        await hass.services.async_call(
            "cover",
            "close_cover",
            {"entity_id": ENTITY_ID, ATTR_SPEED: "slow"},
            blocking=True,
        )
        await hass.async_block_till_done()

    motor_param_writes = [
        payload for op, payload in calls if op == OP_POE_MOTOR_PARAMS and payload
    ]
    assert len(motor_param_writes) == 2
    first_fields = struct.unpack(_SET_MOTOR_PARAMS_FORMAT, motor_param_writes[0])
    assert first_fields[10] == SPEED_PRESETS["slow"]
    reset_fields = struct.unpack(_SET_MOTOR_PARAMS_FORMAT, motor_param_writes[-1])
    assert reset_fields[10] == 100
    assert coordinator.motor_speed_percent == 100


async def test_open_cover_with_speed_does_not_reset_when_disabled(
    hass: HomeAssistant, config_entry
) -> None:
    """With Reset Speed After Move off (the default), the preset speed
    sticks, matching the Speed number entity's own always-sticky
    behavior - no reset is scheduled at all."""
    coordinator = config_entry.runtime_data
    assert coordinator.reset_speed_after_move is False

    calls: list[tuple[int, bytes]] = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(motor_state=0, current_percent=100)
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=SPEED_PRESETS["fast"])
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "cover",
        "open_cover",
        {"entity_id": ENTITY_ID, ATTR_SPEED: "fast"},
        blocking=True,
    )
    await hass.async_block_till_done()

    motor_param_writes = [
        payload for op, payload in calls if op == OP_POE_MOTOR_PARAMS and payload
    ]
    assert len(motor_param_writes) == 1
