"""Tests for the PowerShades data update coordinator."""

import struct
from unittest import mock
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from pyowershades import (
    ADMIN_ACCESS_PAYLOAD,
    CLOUD_UPDATE_CHECK_PAYLOAD,
    CLOUD_UPDATE_INSTALL_PAYLOAD,
    DISABLE_TCP_CLOUD,
    LIMIT_LOWER,
    LIMIT_UPPER,
    OP_ADMIN_ACCESS,
    OP_CLEAR_LIMITS,
    OP_CLOUD_UPDATE,
    OP_DISABLES,
    OP_GET_DEBUG_INFO,
    OP_GET_SERIAL,
    OP_GET_STATUS,
    OP_INDICATE,
    OP_JOG_DOWN,
    OP_JOG_STOP,
    OP_JOG_UP,
    OP_POE_MOTOR_PARAMS,
    OP_REBOOT,
    OP_SAVE_LIMITS,
    OP_SET_LIMIT,
    OP_SET_POSITION,
    OP_SET_SERVER_HOSTNAME,
    OP_STEP_DOWN,
    OP_STEP_UP,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    StatusReply,
    build_set_limit_payload,
    build_set_position_payload,
    build_set_server_hostname_payload,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powershades import coordinator as coordinator_module
from custom_components.powershades.const import DOMAIN
from custom_components.powershades.coordinator import PowerShadesCoordinator

from .conftest import (
    TEST_IP,
    TEST_NAME,
    TEST_SERIAL,
    cloud_update_packet,
    debug_info_packet,
    disables_packet,
    motor_params_packet,
    serial_packet,
    status_packet,
)


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


@pytest.mark.parametrize(
    ("position", "motor_state", "expected"),
    [
        (0, 12, 0),  # closing, already fully closed -> stopped
        (100, 2, 0),  # opening, already fully open -> stopped
        (0, 2, 2),  # opening away from closed is real movement
        (100, 12, 12),  # closing away from open is real movement
        (50, 12, 12),  # mid-travel is left alone
    ],
)
def test_data_from_status_settles_motor_state_at_limit(
    coordinator, position: int, motor_state: int, expected: int
) -> None:
    """A push reaching a limit clears the stale carried-forward
    motor_state rather than showing the cover still moving until the
    next poll."""
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(motor_state=motor_state)
    )
    data = coordinator._data_from_status(
        StatusReply(position=position, battery_mv=3700)
    )
    assert data.motor_state == expected


async def test_async_update_data_settles_motor_state_at_limit(coordinator) -> None:
    """A poll still reporting closing at 0% is treated as stopped."""
    coordinator.connection.async_request = AsyncMock(
        return_value=debug_info_packet(motor_state=12, current_percent=0)
    )
    data = await coordinator._async_update_data()
    assert data.position == 0
    assert data.motor_state == 0


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


async def test_async_fetch_disables_state(coordinator) -> None:
    """Fetching Disables decodes the TCP/cloud bit and stashes the raw
    byte for a future read-modify-write."""
    await coordinator.async_fetch_disables_state()

    assert coordinator.allow_cloud_connection is True
    assert coordinator._disables_raw == 0x01


async def test_async_fetch_disables_state_timeout_leaves_unset(coordinator) -> None:
    """A timeout leaves allow_cloud_connection unset (best-effort)."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_fetch_disables_state()

    assert coordinator.allow_cloud_connection is None


async def test_async_set_allow_cloud_connection_preserves_other_bits(
    coordinator,
) -> None:
    """Turning cloud connectivity off only flips that bit, keeping
    whatever other Feature Disables the device already has set."""
    sent_payloads = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_DISABLES:
            if payload:
                sent_payloads.append(payload)
                return disables_packet(tcp_cloud_disabled=True, other_bits=0x01 | 0x04)
            return disables_packet(tcp_cloud_disabled=False, other_bits=0x01 | 0x04)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_set_allow_cloud_connection(False)

    assert sent_payloads == [bytes([0x01 | 0x04 | DISABLE_TCP_CLOUD])]
    assert coordinator.allow_cloud_connection is False


async def test_async_set_allow_cloud_connection_failure_raises(coordinator) -> None:
    """If the device doesn't confirm the change, the failure is raised."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_allow_cloud_connection(True)

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "cloud_connection_not_confirmed"
    assert exc_info.value.translation_placeholders == {
        "ip_address": coordinator.ip_address
    }


async def test_async_fetch_motor_speed(coordinator) -> None:
    """Fetching motor speed reads MotorPowerUP from the device."""
    await coordinator.async_fetch_motor_speed()

    assert coordinator.motor_speed_percent == 100


async def test_async_set_motor_speed_sends_admin_access_then_set(
    coordinator,
) -> None:
    """Setting a speed sends Admin Access immediately before the Set,
    as an atomic pair, using the exact Gen 1 fixed template."""
    coordinator.hw_version = "Gen 1"
    calls: list[tuple[int, bytes]] = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=70)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_set_motor_speed(70)

    # Admin Access immediately before the Set, in that order.
    ops = [op for op, _ in calls]
    assert ops == [OP_ADMIN_ACCESS, OP_POE_MOTOR_PARAMS]

    admin_call = calls[0]
    assert admin_call[1] == ADMIN_ACCESS_PAYLOAD

    # The outgoing Set payload is a different (longer) shape than a
    # reply - it has a leading ParamType byte the reply doesn't - so
    # unpack it directly rather than through parse_motor_parameters_reply.
    set_call = calls[1]
    fields = struct.unpack("<4BhhIIHHhhIIHHhhBBHH", set_call[1])
    assert fields[0] == 1  # ParamType: Set
    assert fields[1] == 0  # SpeedControlEnable: off
    assert fields[10] == 70  # MotorPowerUP
    assert fields[16] == 70  # MotorPowerDOWN

    assert coordinator.motor_speed_percent == 70
    assert coordinator.motor_speed_percent == 70


async def test_async_set_motor_speed_rejects_non_gen1(coordinator) -> None:
    """Refuses to guess at Gen 2's different (unverified) behavior."""
    coordinator.hw_version = "Gen 2"

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_motor_speed(70)

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "motor_speed_gen1_only"
    assert exc_info.value.translation_placeholders == {
        "ip_address": coordinator.ip_address,
        "hw_version": "Gen 2",
    }


async def test_async_set_motor_speed_failure_raises(coordinator) -> None:
    """If the Set fails, the failure is raised with the right key."""
    coordinator.hw_version = "Gen 1"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_motor_speed(70)

    assert exc_info.value.translation_key == "motor_speed_not_confirmed"


async def test_async_wait_for_stop_true_once_idle_and_position_stable(
    coordinator,
) -> None:
    """Waits through movement (motor_state nonzero, position changing),
    then requires the idle reading to repeat with an unchanged position
    before treating it as a real stop rather than a momentary lull."""
    replies = iter(
        [
            debug_info_packet(motor_state=2, current_percent=60),
            debug_info_packet(motor_state=2, current_percent=80),
            debug_info_packet(motor_state=0, current_percent=100),
            debug_info_packet(motor_state=0, current_percent=100),
        ]
    )
    calls = 0

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        nonlocal calls
        calls += 1
        return next(replies)

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with mock.patch.object(coordinator_module, "_RESET_SPEED_POLL_INTERVAL", 0):
        result = await coordinator._async_wait_for_stop()

    assert result is True
    assert calls == 4
    assert coordinator.data.position == 100


async def test_async_wait_for_stop_false_on_timeout(coordinator) -> None:
    """Gives up rather than waiting forever if the shade never settles."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        return debug_info_packet(motor_state=2, current_percent=50)

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with (
        mock.patch.object(coordinator_module, "_RESET_SPEED_POLL_INTERVAL", 0),
        mock.patch.object(coordinator_module, "_RESET_SPEED_MAX_WAIT", 0),
    ):
        result = await coordinator._async_wait_for_stop()

    assert result is False


async def test_async_reset_speed_after_move_sets_speed_once_stopped(
    coordinator,
) -> None:
    """Once the shade settles, the motor speed is reset to the given
    target via the normal admin-gated Set."""
    coordinator.hw_version = "Gen 1"
    replies = iter(
        [
            debug_info_packet(motor_state=0, current_percent=100),
            debug_info_packet(motor_state=0, current_percent=100),
        ]
    )

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_DEBUG_INFO:
            return next(replies)
        if op == OP_POE_MOTOR_PARAMS:
            return motor_params_packet(motor_power_up=100)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with mock.patch.object(coordinator_module, "_RESET_SPEED_POLL_INTERVAL", 0):
        await coordinator.async_reset_speed_after_move(100)

    coordinator.connection.async_request.assert_any_call(
        OP_ADMIN_ACCESS, ADMIN_ACCESS_PAYLOAD
    )
    assert coordinator.motor_speed_percent == 100


async def test_async_reset_speed_after_move_skips_set_on_timeout(coordinator) -> None:
    """If the shade never settles, the speed is left alone rather than
    resetting it mid-move."""
    coordinator.hw_version = "Gen 1"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet(motor_state=2, current_percent=50)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with (
        mock.patch.object(coordinator_module, "_RESET_SPEED_POLL_INTERVAL", 0),
        mock.patch.object(coordinator_module, "_RESET_SPEED_MAX_WAIT", 0),
    ):
        await coordinator.async_reset_speed_after_move(100)

    ops = [call.args[0] for call in coordinator.connection.async_request.call_args_list]
    assert OP_POE_MOTOR_PARAMS not in ops


async def test_async_check_for_update_stores_result(coordinator) -> None:
    """Checking for updates sends the check flag and stores the raw
    revision number the device reports."""
    calls: list[tuple[int, bytes]] = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_CLOUD_UPDATE:
            return cloud_update_packet(result=512)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_check_for_update()

    assert calls == [(OP_CLOUD_UPDATE, CLOUD_UPDATE_CHECK_PAYLOAD)]
    assert coordinator.latest_firmware_version == "512"


async def test_async_check_for_update_failure_raises(coordinator) -> None:
    """If the device doesn't reply, the failure is raised rather than
    silently leaving the old value in place."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_check_for_update()

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "update_check_not_confirmed"
    assert exc_info.value.translation_placeholders == {
        "ip_address": coordinator.ip_address
    }


async def test_async_install_update_sends_trigger_flag(coordinator) -> None:
    """Triggering an install sends the install flag and awaits the
    normal command acknowledgment, like every other command here."""
    await coordinator.async_install_update()

    coordinator.connection.async_request.assert_any_call(
        OP_CLOUD_UPDATE, CLOUD_UPDATE_INSTALL_PAYLOAD
    )


async def test_async_install_update_failure_raises(coordinator) -> None:
    """If the device doesn't acknowledge the trigger, the failure is
    raised the same way as any other unacknowledged command."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_install_update()

    assert exc_info.value.translation_key == "command_not_acknowledged"


async def test_async_install_update_blocked_on_untrusted_hostname(coordinator) -> None:
    """Install re-reads server_hostname fresh and refuses outright if it
    isn't PowerShades' own domain - the actual install command is never
    sent to the device."""
    coordinator.server_hostname = "dashboard.powershades.com"  # stale, from setup

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_SERIAL:
            return serial_packet(server_hostname="evil.example.com")
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_install_update()

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "untrusted_server_hostname_blocked"
    assert exc_info.value.translation_placeholders == {
        "ip_address": coordinator.ip_address,
        "hostname": "evil.example.com",
    }
    # The stale cached value was updated to the freshly-read one.
    assert coordinator.server_hostname == "evil.example.com"
    ops = [call.args[0] for call in coordinator.connection.async_request.call_args_list]
    assert OP_CLOUD_UPDATE not in ops


async def test_async_install_update_allowed_on_trusted_hostname(coordinator) -> None:
    """Install proceeds normally when a fresh read confirms PowerShades'
    own domain (the coordinator fixture's default)."""
    await coordinator.async_install_update()

    coordinator.connection.async_request.assert_any_call(OP_GET_SERIAL)
    coordinator.connection.async_request.assert_any_call(
        OP_CLOUD_UPDATE, CLOUD_UPDATE_INSTALL_PAYLOAD
    )
    assert coordinator.server_hostname == "dashboard.powershades.com"


async def test_async_install_update_allowed_when_fresh_read_fails(
    coordinator,
) -> None:
    """If the fresh Get Serial Number read times out, install still
    proceeds using whatever was last known, rather than blocking on an
    unrelated connectivity hiccup."""
    assert coordinator.server_hostname is None

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_SERIAL:
            raise PowerShadesTimeoutError("no reply")
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_install_update()

    coordinator.connection.async_request.assert_any_call(
        OP_CLOUD_UPDATE, CLOUD_UPDATE_INSTALL_PAYLOAD
    )
    assert coordinator.server_hostname is None


async def test_async_set_server_hostname_confirms_by_reading_back(
    coordinator,
) -> None:
    """Setting the hostname sends the write, then reads Get Serial Number
    back to confirm the device actually stored it."""
    calls: list[tuple[int, bytes]] = []

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        calls.append((op, payload))
        if op == OP_GET_SERIAL:
            return serial_packet(server_hostname="dashboard.powershades.com")
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await coordinator.async_set_server_hostname("dashboard.powershades.com")

    ops = [op for op, _ in calls]
    write_index = ops.index(OP_SET_SERVER_HOSTNAME)
    read_index = ops.index(OP_GET_SERIAL)
    assert write_index < read_index
    assert calls[write_index] == (
        OP_SET_SERVER_HOSTNAME,
        build_set_server_hostname_payload("dashboard.powershades.com"),
    )
    assert coordinator.server_hostname == "dashboard.powershades.com"


async def test_async_set_server_hostname_write_not_acknowledged(coordinator) -> None:
    """If the write itself isn't acknowledged, the failure is raised the
    same way as any other unacknowledged command."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_server_hostname("dashboard.powershades.com")

    assert exc_info.value.translation_key == "command_not_acknowledged"


async def test_async_set_server_hostname_readback_timeout_raises(coordinator) -> None:
    """If the write is acknowledged but the confirmation read times out,
    the failure is raised rather than optimistically assuming success."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_SET_SERVER_HOSTNAME:
            return b""
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_server_hostname("dashboard.powershades.com")

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "server_hostname_not_confirmed"
    assert coordinator.server_hostname is None


async def test_async_set_server_hostname_readback_mismatch_raises(coordinator) -> None:
    """If the device reports back a different hostname than what was
    just written, that's treated as a failed write, not success."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_SERIAL:
            return serial_packet(server_hostname="something-else.example.com")
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_set_server_hostname("dashboard.powershades.com")

    assert exc_info.value.translation_key == "server_hostname_not_confirmed"
    assert coordinator.server_hostname is None
