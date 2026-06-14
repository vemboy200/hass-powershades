"""Tests for the PowerShades config flow."""

from unittest.mock import patch

import pytest

from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_INTEGRATION_DISCOVERY,
    SOURCE_USER,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.powershades.const import DOMAIN
from custom_components.powershades.udp import PowerShadesTimeoutError

from pytest_homeassistant_custom_component.common import MockConfigEntry

TEST_IP = "192.168.1.50"


async def test_manual_flow_success(
    hass: HomeAssistant, mock_discover_devices, mock_device_info, mock_setup_entry
) -> None:
    """No devices discovered, user enters an IP manually and it works."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PowerShade Bedroom Shade"
    assert result["data"] == {
        "ip": TEST_IP,
        "serial": 12345,
        "name": "Bedroom Shade",
        "model": 1,
    }


async def test_manual_flow_cannot_connect(
    hass: HomeAssistant, mock_discover_devices
) -> None:
    """The device does not respond to the probe."""
    with patch(
        "custom_components.powershades.config_flow.async_get_device_info",
        side_effect=PowerShadesTimeoutError,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"ip": TEST_IP}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_manual_flow_invalid_ip(
    hass: HomeAssistant, mock_discover_devices
) -> None:
    """An invalid IPv4 address is rejected before probing the device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": "not-an-ip"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"ip": "invalid_ip"}


async def test_manual_flow_duplicate(
    hass: HomeAssistant, mock_discover_devices
) -> None:
    """A shade with an already-configured IP cannot be added again."""
    entry = MockConfigEntry(domain=DOMAIN, data={"ip": TEST_IP})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_discovery_pick_device(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Discovered devices are offered for selection."""
    with patch(
        "custom_components.powershades.config_flow.async_discover_devices",
        return_value=[{"ip": TEST_IP, "serial": 12345, "model": 1}],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "pick_device"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": TEST_IP}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PowerShade Bedroom Shade"
    assert result["data"]["ip"] == TEST_IP
    assert result["data"]["serial"] == 12345


async def test_discovery_hides_already_configured_devices(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Devices that already have a config entry are not offered again."""
    configured = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 12345, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    configured.add_to_hass(hass)

    new_ip = "192.168.1.51"
    with patch(
        "custom_components.powershades.config_flow.async_discover_devices",
        return_value=[
            {"ip": TEST_IP, "serial": 12345, "model": 1},
            {"ip": new_ip, "serial": 67890, "model": 1},
        ],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick_device"
    assert new_ip in result["data_schema"].schema["device"].container
    assert TEST_IP not in result["data_schema"].schema["device"].container


async def test_discovery_hides_legacy_entry_by_ip(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """A device matching a legacy entry (no stored serial) is hidden too."""
    legacy = MockConfigEntry(domain=DOMAIN, data={"ip": TEST_IP})
    legacy.add_to_hass(hass)

    with patch(
        "custom_components.powershades.config_flow.async_discover_devices",
        return_value=[{"ip": TEST_IP, "serial": 12345, "model": 1}],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


async def test_dhcp_discovery(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """A device found via DHCP is confirmed and added."""
    discovery_info = DhcpServiceInfo(
        ip=TEST_IP,
        hostname="ps-bedroom",
        macaddress="d83af5112233",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PowerShade Bedroom Shade"
    assert result["data"] == {
        "ip": TEST_IP,
        "serial": 12345,
        "name": "Bedroom Shade",
        "mac": "d8:3a:f5:11:22:33",
        "model": 1,
    }


async def test_background_discovery_already_configured(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Background discovery of an already-configured device aborts."""
    configured = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 12345, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    configured.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"ip": TEST_IP, "serial": 12345, "model": 1},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_background_discovery_legacy_entry_same_ip(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Background discovery of a legacy entry's device (same IP) aborts."""
    legacy = MockConfigEntry(domain=DOMAIN, data={"ip": TEST_IP})
    legacy.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"ip": TEST_IP, "serial": 12345, "model": 1},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_same_ip(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Reconfiguring a modern entry with the same IP just refreshes metadata."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 12345, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["ip"] == TEST_IP


async def test_reconfigure_backfills_missing_serial(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """An entry with unique_id but no stored "serial" gets it backfilled.

    Some entries ended up with a unique_id set (from an earlier probe)
    but no "serial" key in their data, so their device page never
    showed a "Serial number". Reconfiguring fixes this.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["serial"] == 12345


async def test_reconfigure_manual_placeholder_migration(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """An entry with a "manual_<ip>" placeholder unique_id gets migrated.

    The very first version of the config flow used unique_id =
    f"manual_{ip.replace('.', '_')}" when the initial probe didn't return a
    serial. These entries are functionally legacy - they should be migrated
    to a real serial-based unique_id on reconfigure, not flagged as
    wrong_device.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "name": "Bedroom Shade", "model": 1},
        unique_id=f"manual_{TEST_IP.replace('.', '_')}",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "12345"
    assert entry.data["serial"] == 12345


async def test_reconfigure_ip_changed(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Reconfiguring a modern entry with a new IP updates the stored IP."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 12345, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    new_ip = "192.168.1.51"
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": new_ip}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["ip"] == new_ip


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Reconfiguring with an IP that now belongs to a different shade errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 99999, "name": "Other Shade", "model": 1},
        unique_id="99999",
    )
    entry.add_to_hass(hass)

    new_ip = "192.168.1.51"
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": new_ip}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "wrong_device"}
    assert entry.data["ip"] == TEST_IP


async def test_reconfigure_legacy_migration(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Reconfiguring a legacy entry backfills its serial and unique_id."""
    legacy = MockConfigEntry(domain=DOMAIN, data={"ip": TEST_IP})
    legacy.add_to_hass(hass)

    result = await legacy.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert legacy.unique_id == "12345"
    assert legacy.data["serial"] == 12345
    assert legacy.data["name"] == "Bedroom Shade"


async def test_reconfigure_legacy_collision(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """A legacy entry can't be migrated to a serial another entry already owns."""
    other = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": "192.168.1.99", "serial": 12345, "name": "Other", "model": 1},
        unique_id="12345",
    )
    other.add_to_hass(hass)
    legacy = MockConfigEntry(domain=DOMAIN, data={"ip": TEST_IP})
    legacy.add_to_hass(hass)

    result = await legacy.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": TEST_IP}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "already_configured"}
    assert legacy.unique_id is None


async def test_reconfigure_invalid_ip(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """An invalid IPv4 address is rejected before probing the device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 12345, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ip": "not-an-ip"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"ip": "invalid_ip"}


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    """The device does not respond to the reconfigure probe."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"ip": TEST_IP, "serial": 12345, "name": "Bedroom Shade", "model": 1},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    new_ip = "192.168.1.51"
    with patch(
        "custom_components.powershades.config_flow.async_get_device_info",
        side_effect=PowerShadesTimeoutError,
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"ip": new_ip}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.xfail(
    reason=(
        "Known limitation: a legacy entry (no stored serial/unique_id) "
        "can't be matched by background discovery once its IP also "
        "changes, since neither the IP nor unique_id check can find it. "
        "Creates a duplicate entry instead of aborting. The reconfigure "
        "flow provides a manual workaround (backfills the serial and "
        "updates the IP), but background discovery isn't fixed yet."
    ),
    strict=True,
)
async def test_background_discovery_legacy_entry_ip_changed(
    hass: HomeAssistant, mock_device_info, mock_setup_entry
) -> None:
    """Background discovery of a legacy entry's device after a DHCP IP change."""
    legacy = MockConfigEntry(domain=DOMAIN, data={"ip": TEST_IP})
    legacy.add_to_hass(hass)

    new_ip = "192.168.1.51"
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"ip": new_ip, "serial": 12345, "model": 1},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
