"""Fixtures for PowerShades tests."""

import struct
from unittest.mock import AsyncMock, patch

import pytest
from pyowershades import (
    OP_GET_DEBUG_INFO,
    OP_GET_DEVICE_ID,
    OP_GET_SHADE_NAME,
    OP_GET_STATUS,
    PowerShadesConnection,
    build_packet,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powershades.const import DOMAIN

TEST_IP = "192.168.1.50"
TEST_SERIAL = 12345
TEST_NAME = "Bedroom Shade"


@pytest.fixture(autouse=True)
def mock_background_discovery():
    """Prevent periodic background discovery from touching real sockets."""
    with patch(
        "custom_components.powershades.discovery.async_discover_devices",
        return_value=[],
    ):
        yield


@pytest.fixture
def mock_setup_entry():
    """Bypass full entry setup, e.g. for config flow tests."""
    with patch("custom_components.powershades.async_setup_entry", return_value=True):
        yield


@pytest.fixture
def mock_discover_devices():
    """Mock broadcast discovery, returning no devices by default."""
    with patch(
        "custom_components.powershades.config_flow.async_discover_devices",
        return_value=[],
    ) as mock:
        yield mock


@pytest.fixture
def mock_device_info():
    """Mock probing a device for its serial number and name."""
    with patch(
        "custom_components.powershades.config_flow.async_get_device_info",
        return_value={"serial": 12345, "name": "Bedroom Shade", "model": 1},
    ) as mock:
        yield mock


def status_packet(position: int = 50, battery_mv: int = 3700) -> bytes:
    """Build a Get Status reply packet with the given position and battery."""
    payload = struct.pack(
        "<hhHHIIIhII", position, 0, 0, battery_mv, 0, 0, 0, 20, position, 0
    )
    return build_packet(OP_GET_STATUS, payload=payload)


def shade_name_packet(name: str) -> bytes:
    """Build a Get PoE Shade Name reply packet."""
    payload = b"\x00" + name.encode("ascii").ljust(50, b"\x00")
    return build_packet(OP_GET_SHADE_NAME, payload=payload)


def debug_info_packet(
    *,
    green_led: bool = False,
    red_led: bool = False,
    motor_sleep: bool = False,
    poe_status: bool = True,
    motor_state: int = 0,
    current_percent: int = 50,
    battery_mv: int = 3700,
    error_codes: list[int] | None = None,
    velocity_rpm: int = 0,
    desired_rpm: int = 0,
    motor_duty_cycle: int = 0,
) -> bytes:
    """Build a Get Debug Info reply packet."""
    error_text = "".join(f"{code}," for code in (error_codes or []))
    error_bytes = error_text.encode("ascii").ljust(50, b"\x00")[:50]
    payload = struct.pack(
        "<8BHhhhiiiiiIIff50s6B",
        0,
        motor_state,
        0,
        0,
        0,
        0,
        0,
        0,  # 8 leading status bytes
        battery_mv,  # BatteryVoltage
        0,
        current_percent,
        motor_duty_cycle,  # target/current percent, motor duty cycle
        0,
        0,
        0,
        0,
        0,  # hall counts
        velocity_rpm,
        desired_rpm,  # velocity/desired RPM
        0.0,
        0.0,  # thermistor temp, motor current
        error_bytes,  # error list
        int(red_led),
        int(green_led),
        int(motor_sleep),
        0,
        0,
        int(poe_status),  # LEDs / IO booleans
    )
    return build_packet(OP_GET_DEBUG_INFO, payload=payload)


def device_id_packet(
    *, low_rev: int = 0, high_rev: int = 0, status_bits: int = 0
) -> bytes:
    """Build a Get Device ID reply packet."""
    payload = struct.pack(
        "<BB2IHHHHI3iBIII50sB",
        0,  # model
        status_bits,
        0,
        0,  # serial_raw
        low_rev,
        high_rev,
        0,
        0,  # low_crc, high_crc
        0,  # device_count
        0,
        0,
        0,  # end_stop_raw
        0,  # dhcp_enabled
        0,
        0,
        0,  # ip/subnet/gateway
        b"\x00" * 50,  # server_hostname
        0,  # model_version
    )
    return build_packet(OP_GET_DEVICE_ID, payload=payload)


@pytest.fixture
def mock_connection():
    """Mock the UDP connection so setup never touches real sockets."""

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_SHADE_NAME:
            return shade_name_packet(TEST_NAME)
        if op == OP_GET_DEBUG_INFO:
            return debug_info_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_packet()
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
        yield


@pytest.fixture
async def config_entry(hass, mock_connection):
    """Set up a loaded PowerShades config entry with a mocked connection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "ip": TEST_IP,
            "serial": TEST_SERIAL,
            "name": TEST_NAME,
            "model": 1,
            "mac": "d8:3a:f5:11:22:33",
        },
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
