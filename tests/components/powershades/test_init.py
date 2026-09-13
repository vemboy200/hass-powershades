"""Tests for setting up and unloading the PowerShades integration."""

import struct
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pyowershades import (
    OP_GET_DEBUG_INFO,
    OP_GET_DEVICE_ID,
    OP_GET_SERIAL,
    OP_GET_STATUS,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    build_packet,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powershades.const import DOMAIN
from custom_components.powershades.coordinator import PowerShadesCoordinator

from .conftest import (
    TEST_IP,
    TEST_NAME,
    TEST_SERIAL,
    debug_info_packet,
    device_id_packet,
    status_packet,
)


async def test_setup_entry_success(hass: HomeAssistant, config_entry) -> None:
    """A working device sets up successfully with a coordinator and entities."""
    assert config_entry.state is ConfigEntryState.LOADED
    assert isinstance(config_entry.runtime_data, PowerShadesCoordinator)
    assert config_entry.runtime_data.data.position == 50

    assert len(hass.states.async_all("cover")) == 1
    assert len(hass.states.async_all("button")) > 0


async def test_setup_entry_not_ready(hass: HomeAssistant) -> None:
    """The entry retries setup if the device doesn't respond."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    with (
        patch.object(PowerShadesConnection, "async_connect", AsyncMock()),
        patch.object(
            PowerShadesConnection,
            "async_request",
            AsyncMock(side_effect=fake_request),
        ),
        patch.object(PowerShadesConnection, "close") as mock_close,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    mock_close.assert_called_once()

    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, f"cannot_connect_{entry.entry_id}")


async def test_setup_entry_clears_cannot_connect_issue(hass: HomeAssistant) -> None:
    """A repair issue from a previous failed setup is cleared on success."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    issue_registry = ir.async_get(hass)
    issue_id = f"cannot_connect_{entry.entry_id}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="cannot_connect",
        translation_placeholders={"name": entry.title, "ip": TEST_IP},
    )
    assert issue_registry.async_get_issue(DOMAIN, issue_id)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
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

    assert entry.state is ConfigEntryState.LOADED
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_unload_entry(hass: HomeAssistant, config_entry) -> None:
    """Unloading the entry unloads platforms and closes the connection."""
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED

    cover_states = hass.states.async_all("cover")
    assert len(cover_states) == 1
    assert cover_states[0].state == "unavailable"

    PowerShadesConnection.close.assert_called_once()


async def test_setup_entry_fills_in_missing_model(hass: HomeAssistant) -> None:
    """A first-time setup with no stored model backfills it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    # model, pad, pad, direction, serial low, serial high, dhcp_enabled
    serial_payload = struct.pack("<BBBBIIB", 1, 0, 0, 0, TEST_SERIAL, 0, 0)
    serial_payload += b"\x00" * (24 - 8 - len(serial_payload))
    serial_packet = build_packet(OP_GET_SERIAL, payload=serial_payload)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_SERIAL:
            return serial_packet
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

    assert entry.data["model"] == 1


async def test_setup_entry_fetches_firmware_version(hass: HomeAssistant) -> None:
    """Setup fetches the active bank's firmware revision, not persisted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    device_id_reply = device_id_packet(low_rev=97, high_rev=109, status_bits=2)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_reply
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

    coordinator = entry.runtime_data
    assert coordinator.firmware_version == "109"
    assert coordinator.device_info["sw_version"] == "109"
    assert coordinator.hw_version == "Gen 1"
    assert coordinator.device_info["hw_version"] == "Gen 1"


@pytest.mark.parametrize(
    ("model_version", "expected_hw_version"),
    [
        (0, "Gen 1"),
        (2, "Gen 2"),
        (5, "Model version 5"),
    ],
)
async def test_setup_entry_fetches_hw_version(
    hass: HomeAssistant, model_version: int, expected_hw_version: str
) -> None:
    """Setup derives the hardware generation from Get Device ID's
    model_version, with an unrecognized value falling back to showing
    the raw number rather than a guessed label."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 1},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    device_id_reply = device_id_packet(model_version=model_version)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
        if op == OP_GET_DEVICE_ID:
            return device_id_reply
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

    coordinator = entry.runtime_data
    assert coordinator.hw_version == expected_hw_version


async def test_setup_entry_warns_on_rf_gateway(hass: HomeAssistant) -> None:
    """A device that identifies as an RF Gateway raises a repair issue."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 100},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
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

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(
        DOMAIN, f"rf_gateway_unsupported_{entry.entry_id}"
    )
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable


async def test_setup_entry_no_rf_gateway_issue_for_poe_shade(
    hass: HomeAssistant, config_entry
) -> None:
    """A normal PoE Shade never gets the RF Gateway repair issue."""
    issue_registry = ir.async_get(hass)
    assert (
        issue_registry.async_get_issue(
            DOMAIN, f"rf_gateway_unsupported_{config_entry.entry_id}"
        )
        is None
    )


async def test_unload_entry_clears_rf_gateway_issue(hass: HomeAssistant) -> None:
    """Unloading an RF Gateway entry clears its repair issue."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": TEST_SERIAL, "name": TEST_NAME, "model": 100},
        unique_id=str(TEST_SERIAL),
    )
    entry.add_to_hass(hass)

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_STATUS:
            return status_packet()
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

        issue_registry = ir.async_get(hass)
        issue_id = f"rf_gateway_unsupported_{entry.entry_id}"
        assert issue_registry.async_get_issue(DOMAIN, issue_id)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
