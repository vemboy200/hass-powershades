"""Tests for the PowerShades button platform."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyowershades import (
    CLOUD_UPDATE_CHECK_PAYLOAD,
    LIMIT_LOWER,
    LIMIT_UPPER,
    OP_CLEAR_LIMITS,
    OP_CLOUD_UPDATE,
    OP_INDICATE,
    OP_JOG_DOWN,
    OP_JOG_UP,
    OP_REBOOT,
    OP_SAVE_LIMITS,
    OP_SET_LIMIT,
    OP_SET_POSITION,
    OP_STEP_DOWN,
    OP_STEP_UP,
    build_set_limit_payload,
    build_set_position_payload,
)


@pytest.mark.parametrize(
    ("key", "expected_call"),
    [
        ("identify", (OP_INDICATE, b"")),
        ("jog_up", (OP_JOG_UP, b"")),
        ("jog_down", (OP_JOG_DOWN, b"")),
        ("set_upper_limit", (OP_SET_LIMIT, build_set_limit_payload(LIMIT_UPPER))),
        ("set_lower_limit", (OP_SET_LIMIT, build_set_limit_payload(LIMIT_LOWER))),
        ("clear_limits", (OP_CLEAR_LIMITS, b"")),
        ("step_up", (OP_STEP_UP, b"")),
        ("step_down", (OP_STEP_DOWN, b"")),
        ("reboot", (OP_REBOOT, b"")),
        ("save_limits", (OP_SAVE_LIMITS, b"")),
        ("check_for_updates", (OP_CLOUD_UPDATE, CLOUD_UPDATE_CHECK_PAYLOAD)),
    ],
)
async def test_button_press_sends_command(
    hass: HomeAssistant, config_entry, key: str, expected_call: tuple
) -> None:
    """Pressing a button sends the expected command to the device."""
    entity_id = f"button.powershade_bedroom_shade_{key}"

    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    assert entry is not None
    if entry.disabled:
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )

    coordinator.connection.async_request.assert_any_call(*expected_call)


async def test_toggle_button_toggles_shade(hass: HomeAssistant, config_entry) -> None:
    """Pressing the toggle button stops or moves the shade depending on state."""
    coordinator = config_entry.runtime_data
    entity_id = "button.powershade_bedroom_shade_toggle_shade"

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )

    # Position starts at 50 (the "mostly closed" boundary), so toggling opens it.
    coordinator.connection.async_request.assert_any_call(
        OP_SET_POSITION, build_set_position_payload(100)
    )


@pytest.mark.parametrize(
    "key",
    ["set_upper_limit", "set_lower_limit", "clear_limits", "save_limits"],
)
async def test_limit_buttons_disabled_by_default(
    hass: HomeAssistant, config_entry, key: str
) -> None:
    """Set/Clear/Save Limits are disabled by default - unlike jog/step,
    these aren't easily reversible, so an accidental press could
    miscalibrate the shade's travel range."""
    registry = er.async_get(hass)
    entry = registry.async_get(f"button.powershade_bedroom_shade_{key}")

    assert entry is not None
    assert entry.disabled


@pytest.mark.parametrize("key", ["jog_up", "jog_down", "step_up", "step_down"])
async def test_jog_step_buttons_enabled_by_default(
    hass: HomeAssistant, config_entry, key: str
) -> None:
    """Jog/Step are enabled by default, unlike the limit buttons - they're
    reversible (jog/step the other way undoes them)."""
    registry = er.async_get(hass)
    entry = registry.async_get(f"button.powershade_bedroom_shade_{key}")

    assert entry is not None
    assert not entry.disabled


async def test_check_for_updates_enabled_by_default(
    hass: HomeAssistant, config_entry
) -> None:
    """Check for Updates is a safe, read-only cloud query, so it's
    enabled by default like reboot/identify."""
    registry = er.async_get(hass)
    entry = registry.async_get("button.powershade_bedroom_shade_check_for_updates")

    assert entry is not None
    assert not entry.disabled


async def test_check_for_updates_stores_latest_version(
    hass: HomeAssistant, config_entry
) -> None:
    """Pressing Check for Updates records the reported latest firmware
    revision on the coordinator."""
    coordinator = config_entry.runtime_data
    assert coordinator.latest_firmware_version is None

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.powershade_bedroom_shade_check_for_updates"},
        blocking=True,
    )

    assert coordinator.latest_firmware_version == "100"


async def test_button_unique_ids(hass: HomeAssistant, config_entry) -> None:
    """All buttons get a unique id namespaced with the serial number."""
    registry = er.async_get(hass)
    entity_id = "button.powershade_bedroom_shade_jog_up"
    entry = registry.async_get(entity_id)
    assert entry is not None
    assert entry.unique_id == "powershades_12345_jog_up"
