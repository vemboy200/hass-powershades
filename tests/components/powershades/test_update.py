"""Tests for the PowerShades update platform."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import CLOUD_UPDATE_INSTALL_PAYLOAD, OP_CLOUD_UPDATE

from custom_components.powershades import coordinator as coordinator_module

from .conftest import cloud_update_packet

ENTITY_ID = "update.powershade_bedroom_shade_firmware"


async def test_update_entity_created_and_enabled(
    hass: HomeAssistant, config_entry
) -> None:
    """The firmware update entity is registered and enabled by default."""
    registry = er.async_get(hass)
    entry = registry.async_get(ENTITY_ID)

    assert entry is not None
    assert not entry.disabled


async def test_installed_version_reflects_firmware_version(
    hass: HomeAssistant, config_entry
) -> None:
    """installed_version comes from the coordinator's firmware_version,
    like the device info card's sw_version."""
    coordinator = config_entry.runtime_data
    coordinator.firmware_version = "109"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["installed_version"] == "109"


async def test_latest_version_unknown_until_checked(
    hass: HomeAssistant, config_entry
) -> None:
    """Before Check for Updates is ever pressed, latest_version (and so
    the overall state) is unknown, not a false "no update" or "update
    available"."""
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["latest_version"] is None
    assert state.state == "unknown"


async def test_state_off_when_versions_match(hass: HomeAssistant, config_entry) -> None:
    """Equal installed/latest versions report no update available."""
    coordinator = config_entry.runtime_data
    coordinator.firmware_version = "100"
    coordinator.latest_firmware_version = "100"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "off"


async def test_state_on_when_latest_is_newer(hass: HomeAssistant, config_entry) -> None:
    """A higher latest_version than installed_version reports an update
    is available."""
    coordinator = config_entry.runtime_data
    coordinator.firmware_version = "100"
    coordinator.latest_firmware_version = "200"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "on"


async def test_latest_version_updates_after_check_for_updates(
    hass: HomeAssistant, config_entry
) -> None:
    """Pressing Check for Updates (button.py) is reflected here too,
    since both read the same coordinator attribute."""
    coordinator = config_entry.runtime_data

    async def fake_request(op, payload=b"", timeout=None, retries=None):
        if op == OP_CLOUD_UPDATE:
            return cloud_update_packet(result=321)
        return b""

    coordinator.connection.async_request = AsyncMock(side_effect=fake_request)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.powershade_bedroom_shade_check_for_updates"},
        blocking=True,
    )

    assert hass.states.get(ENTITY_ID).attributes["latest_version"] == "321"


async def test_in_progress_reflects_tcp_firmware_update_error_code(
    hass: HomeAssistant, config_entry
) -> None:
    """in_progress is a best-effort signal from the TCP_Firmware_Update
    PoE error code (5) showing up in Debug Info's error list."""
    coordinator = config_entry.runtime_data

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(error_list=[5])
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes["in_progress"] is True

    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(error_list=[9])
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes["in_progress"] is False


async def test_install_triggers_coordinator(hass: HomeAssistant, config_entry) -> None:
    """Calling update.install triggers the device's own cloud install."""
    coordinator = config_entry.runtime_data
    # Core's own update.install service refuses to run unless it thinks
    # an update is actually available.
    coordinator.firmware_version = "100"
    coordinator.latest_firmware_version = "200"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    await hass.services.async_call(
        "update",
        "install",
        {"entity_id": ENTITY_ID},
        blocking=True,
    )

    coordinator.connection.async_request.assert_any_call(
        OP_CLOUD_UPDATE, CLOUD_UPDATE_INSTALL_PAYLOAD
    )
