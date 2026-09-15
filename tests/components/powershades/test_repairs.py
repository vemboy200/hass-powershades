"""Tests for the PowerShades repair flows."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pyowershades import OP_GET_SERIAL, PowerShadesTimeoutError

from custom_components.powershades.const import TRUSTED_SERVER_HOSTNAME
from custom_components.powershades.repairs import (
    UntrustedServerHostnameRepairFlow,
    async_create_fix_flow,
)

from .conftest import serial_packet


async def test_create_fix_flow_resolves_entry(
    hass: HomeAssistant, config_entry
) -> None:
    """The dispatcher resolves the entry from the issue's data and
    returns the right flow class."""
    flow = await async_create_fix_flow(
        hass,
        f"untrusted_server_hostname_{config_entry.entry_id}",
        {"entry_id": config_entry.entry_id},
    )

    assert isinstance(flow, UntrustedServerHostnameRepairFlow)
    assert flow.entry is config_entry


async def test_create_fix_flow_rejects_unknown_issue(
    hass: HomeAssistant, config_entry
) -> None:
    """An unrecognized issue id is a programming error, not something to
    silently ignore."""
    with pytest.raises(ValueError, match="unknown repair"):
        await async_create_fix_flow(
            hass, "some_other_issue", {"entry_id": config_entry.entry_id}
        )


async def test_confirm_step_shows_current_and_expected_hostname(
    hass: HomeAssistant, config_entry
) -> None:
    """The form shown before confirming displays what's currently set
    and what it will be reset to."""
    coordinator = config_entry.runtime_data
    coordinator.server_hostname = "evil.example.com"
    flow = UntrustedServerHostnameRepairFlow(config_entry)

    result = await flow.async_step_confirm()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {
        "hostname": "evil.example.com",
        "expected": TRUSTED_SERVER_HOSTNAME,
    }


async def test_confirm_step_success_resets_hostname(
    hass: HomeAssistant, config_entry
) -> None:
    """Submitting the form resets the hostname and completes the flow."""
    coordinator = config_entry.runtime_data
    coordinator.server_hostname = "evil.example.com"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_SERIAL:
            return serial_packet(server_hostname=TRUSTED_SERVER_HOSTNAME)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    flow = UntrustedServerHostnameRepairFlow(config_entry)

    result = await flow.async_step_confirm(user_input={})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert coordinator.server_hostname == TRUSTED_SERVER_HOSTNAME


async def test_confirm_step_failure_shows_error_and_stays_open(
    hass: HomeAssistant, config_entry
) -> None:
    """If the reset can't be confirmed, the flow shows an error and lets
    the user retry rather than silently completing."""
    coordinator = config_entry.runtime_data
    coordinator.server_hostname = "evil.example.com"

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        raise PowerShadesTimeoutError("no reply")

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)
    flow = UntrustedServerHostnameRepairFlow(config_entry)

    result = await flow.async_step_confirm(user_input={})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["errors"] == {"base": "reset_failed"}
    assert coordinator.server_hostname == "evil.example.com"


async def test_async_step_init_goes_to_confirm(
    hass: HomeAssistant, config_entry
) -> None:
    """The flow's first step goes straight to the confirm form."""
    flow = UntrustedServerHostnameRepairFlow(config_entry)

    result = await flow.async_step_init()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
