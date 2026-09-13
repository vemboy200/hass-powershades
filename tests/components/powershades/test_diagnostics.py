"""Tests for PowerShades diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.powershades import coordinator as coordinator_module

from .conftest import TEST_IP, TEST_NAME, TEST_SERIAL


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry,
) -> None:
    """Diagnostics redact identifying info and include coordinator state."""
    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    entry_data = result["entry_data"]
    assert entry_data["ip"] == "**REDACTED**"
    assert entry_data["mac"] == "**REDACTED**"
    assert entry_data["serial"] == "**REDACTED**"
    assert entry_data["unique_id"] == "**REDACTED**"
    assert entry_data["name"] == TEST_NAME
    assert entry_data["model"] == 1

    assert result["coordinator_data"]["position"] == 50
    assert result["coordinator_data"]["error_list"] == []
    assert result["coordinator_data"]["error_list_decoded"] == []

    # Sanity check the test fixture didn't change underneath us
    assert config_entry.data["ip"] == TEST_IP
    assert config_entry.unique_id == str(TEST_SERIAL)


async def test_diagnostics_decodes_error_list(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry,
) -> None:
    """error_list codes are decoded into readable PoEErrorCode names."""
    coordinator = config_entry.runtime_data
    coordinator.async_set_updated_data(
        coordinator_module.PowerShadesData(error_list=[9, 21])
    )

    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    assert result["coordinator_data"]["error_list"] == [9, 21]
    assert result["coordinator_data"]["error_list_decoded"] == [
        "TCP_Keep_Alive",
        "Enter_Sleep_Mode",
    ]
