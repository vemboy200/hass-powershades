"""Tests for the PowerShades services."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from pyowershades import (
    OP_GET_SERIAL,
    OP_SET_SERVER_HOSTNAME,
    build_set_server_hostname_payload,
)

from custom_components.powershades.const import DOMAIN, TRUSTED_SERVER_HOSTNAME

from .conftest import serial_packet

ENTITY_ID = "cover.powershade_bedroom_shade"


async def test_set_server_hostname_calls_coordinator(
    hass: HomeAssistant, config_entry
) -> None:
    """The service sends the write and confirmation read through the
    coordinator, like calling async_set_server_hostname directly."""
    coordinator = config_entry.runtime_data

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_SERIAL:
            return serial_packet(server_hostname="dashboard.powershades.com")
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        DOMAIN,
        "set_server_hostname",
        {"entity_id": ENTITY_ID, "hostname": "dashboard.powershades.com"},
        blocking=True,
    )

    coordinator.connection.async_request.assert_any_call(
        OP_SET_SERVER_HOSTNAME,
        build_set_server_hostname_payload("dashboard.powershades.com"),
    )
    assert coordinator.server_hostname == "dashboard.powershades.com"


@pytest.mark.parametrize(
    "hostname",
    ["", "   ", "a" * 121, "not-ascii-é"],
)
async def test_set_server_hostname_rejects_invalid_input(
    hass: HomeAssistant, config_entry, hostname: str
) -> None:
    """Empty, over-length, or non-ASCII hostnames are rejected before
    anything is sent to the device."""
    coordinator = config_entry.runtime_data
    coordinator.connection.async_request.reset_mock()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_server_hostname",
            {"entity_id": ENTITY_ID, "hostname": hostname},
            blocking=True,
        )

    coordinator.connection.async_request.assert_not_called()


async def test_set_server_hostname_clears_untrusted_repair_issue(
    hass: HomeAssistant, config_entry
) -> None:
    """Correcting the hostname via the service clears the
    untrusted-server-hostname repair issue right away, not just on the
    next reload - this is the whole point of the service."""
    coordinator = config_entry.runtime_data
    coordinator.server_hostname = "evil.example.com"
    from custom_components.powershades import _async_check_server_hostname

    _async_check_server_hostname(hass, config_entry, coordinator)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    issue_id = f"untrusted_server_hostname_{config_entry.entry_id}"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_GET_SERIAL:
            return serial_packet(server_hostname=TRUSTED_SERVER_HOSTNAME)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        DOMAIN,
        "set_server_hostname",
        {"entity_id": ENTITY_ID, "hostname": TRUSTED_SERVER_HOSTNAME},
        blocking=True,
    )

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
