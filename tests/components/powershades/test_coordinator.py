"""Tests for the PowerShades data update coordinator."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from pyowershades import (
    LIMIT_LOWER,
    LIMIT_UPPER,
    OP_CLEAR_LIMITS,
    OP_GET_DEBUG_INFO,
    OP_GET_STATUS,
    OP_INDICATE,
    OP_JOG_DOWN,
    OP_JOG_STOP,
    OP_JOG_UP,
    OP_REBOOT,
    OP_SAVE_LIMITS,
    OP_SET_LIMIT,
    OP_SET_POSITION,
    OP_STEP_DOWN,
    OP_STEP_UP,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    StatusReply,
    build_set_limit_payload,
    build_set_position_payload,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powershades import coordinator as coordinator_module
from custom_components.powershades.const import DOMAIN
from custom_components.powershades.coordinator import PowerShadesCoordinator

from .conftest import TEST_IP, TEST_NAME, TEST_SERIAL, debug_info_packet, status_packet


@pytest.fixture
def coordinator(hass, mock_connection):
    """A coordinator with a mocked connection, not yet started."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)
    connection = PowerShadesConnection(TEST_IP)
    return PowerShadesCoordinator(hass, entry, connection)


def test_data_from_status_basic(coordinator) -> None:
    """A status packet is turned into position/battery data."""
    data = coordinator._data_from_status(StatusReply(position=42, battery_mv=3700))
    assert data.position == 42
    assert data.battery_mv == 3700
    assert data.battery_percentage is not None


def test_data_from_status_carries_forward_debug_info(coordinator) -> None:
    """Status pushes don't carry io_green_led/io_red_led/motor_state/
    error_list - the last known values (from the coordinator's own
    Debug Info poll) are kept."""
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(
            io_green_led=True, io_red_led=True, motor_state=2, error_list=[9, 21]
        )
    )
    data = coordinator._data_from_status(StatusReply(position=50, battery_mv=3700))
    assert data.io_green_led is True
    assert data.io_red_led is True
    assert data.motor_state == 2
    assert data.error_list == [9, 21]


async def test_async_set_position_sends_command(coordinator) -> None:
    """Setting a position sends a Set Position command."""
    await coordinator.async_set_position(75)

    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(75)
    )


async def test_async_set_position_refreshes_motor_state(coordinator) -> None:
    """Setting a position refreshes immediately, picking up the real
    motor state instead of waiting for the next scheduled poll."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet(position=50)
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(motor_state=1)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_set_position(100)

    assert coordinator.data.motor_state == 1


async def test_async_set_position_failure_raises(coordinator) -> None:
    """If the device doesn't ack the command, the failure is raised."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_position(75)

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "command_not_acknowledged"
    assert exc_info.value.translation_placeholders == {
        "ip_address": coordinator.ip_address
    }


async def test_async_stop_sends_command(coordinator) -> None:
    """Stopping the shade sends the jog stop command."""
    await coordinator.async_stop()

    coordinator.connection.async_request.assert_any_call(OP_JOG_STOP, b"")


async def test_async_toggle_stops_when_moving(coordinator) -> None:
    """Toggling a shade that's already moving stops it."""
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(position=50, motor_state=2)
    )
    await coordinator.async_toggle()

    coordinator.connection.async_request.assert_any_call(OP_JOG_STOP, b"")


async def test_async_toggle_closes_when_mostly_open(coordinator) -> None:
    """Toggling a shade that's more than half open closes it."""
    coordinator.async_set_updated_data(coordinator_module.PowerShadesData(position=80))
    await coordinator.async_toggle()

    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(0)
    )


async def test_async_toggle_opens_when_mostly_closed(coordinator) -> None:
    """Toggling a shade that's at or below half open opens it."""
    coordinator.async_set_updated_data(coordinator_module.PowerShadesData(position=20))
    await coordinator.async_toggle()

    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(100)
    )


async def test_async_toggle_does_nothing_when_position_unknown(coordinator) -> None:
    """Toggling with an unknown position is a no-op."""
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(position=None)
    )
    await coordinator.async_toggle()

    for call in coordinator.connection.async_request.call_args_list:
        assert call.args[0] != OP_SET_POSITION


async def test_async_jog_up_and_down(coordinator) -> None:
    """Jog commands send the corresponding op codes."""
    await coordinator.async_jog_up()
    coordinator.connection.async_request.assert_any_call(OP_JOG_UP, b"")

    await coordinator.async_jog_down()
    coordinator.connection.async_request.assert_any_call(OP_JOG_DOWN, b"")


async def test_async_identify(coordinator) -> None:
    """Identify sends the indicate command."""
    await coordinator.async_identify()
    coordinator.connection.async_request.assert_any_call(OP_INDICATE, b"")


async def test_async_limits(coordinator) -> None:
    """Limit commands send the right limit type payloads."""
    await coordinator.async_set_upper_limit()
    coordinator.connection.async_request.assert_any_call(
        OP_SET_LIMIT, build_set_limit_payload(LIMIT_UPPER)
    )

    await coordinator.async_set_lower_limit()
    coordinator.connection.async_request.assert_any_call(
        OP_SET_LIMIT, build_set_limit_payload(LIMIT_LOWER)
    )

    await coordinator.async_clear_limits()
    coordinator.connection.async_request.assert_any_call(OP_CLEAR_LIMITS, b"")


async def test_async_step_up_and_down(coordinator) -> None:
    """Step commands send the corresponding op codes."""
    await coordinator.async_step_up()
    coordinator.connection.async_request.assert_any_call(OP_STEP_UP, b"")

    await coordinator.async_step_down()
    coordinator.connection.async_request.assert_any_call(OP_STEP_DOWN, b"")


async def test_async_reboot(coordinator) -> None:
    """Reboot sends the reboot command."""
    await coordinator.async_reboot()
    coordinator.connection.async_request.assert_any_call(OP_REBOOT, b"")


async def test_async_save_limits(coordinator) -> None:
    """Save Limits sends the save-limits command."""
    await coordinator.async_save_limits()
    coordinator.connection.async_request.assert_any_call(OP_SAVE_LIMITS, b"")


async def test_async_set_shade_name(coordinator) -> None:
    """Renaming the shade updates the coordinator and config entry."""
    await coordinator.async_set_shade_name("New Name")
    assert coordinator.device_name == TEST_NAME


async def test_async_update_data_polls_debug_info_only(coordinator) -> None:
    """A normal poll gets position, battery and motor state from one
    Debug Info request - Get Status is never sent when it succeeds."""
    data = await coordinator._async_update_data()
    assert data.position == 50
    assert data.motor_state == 0
    assert data.error_list == []
    assert coordinator.update_interval.total_seconds() == 10

    for call in coordinator.connection.async_request.call_args_list:
        assert call.args[0] != OP_GET_STATUS


async def test_async_update_data_decodes_error_list(coordinator) -> None:
    """A poll decodes Debug Info's error list into PoEErrorCode values."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(error_codes=[9, 21])
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    data = await coordinator._async_update_data()
    assert data.error_list == [9, 21]


async def test_async_update_data_raises_on_timeout(coordinator) -> None:
    """A polling timeout raises UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
