"""PowerShades update platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyowershades import POE_ERROR_CODES

from .coordinator import PowerShadesConfigEntry, PowerShadesCoordinator
from .entity import PowerShadesEntity

PARALLEL_UPDATES = 0

# TCP_Firmware_Update is a generic device-event log entry (also covers
# stalls, reboots, CRC mismatches, etc.), not something confirmed to be
# specific to a cloud-triggered install - see PowerShadesFirmwareUpdate's
# in_progress docstring below.
_TCP_FIRMWARE_UPDATE_ERROR_CODE = next(
    code for code, name in POE_ERROR_CODES.items() if name == "TCP_Firmware_Update"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PowerShadesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PowerShades update entity from a config entry."""
    async_add_entities([PowerShadesFirmwareUpdate(entry.runtime_data)])


class PowerShadesFirmwareUpdate(PowerShadesEntity, UpdateEntity):
    """Reports and triggers a PowerShades firmware update via the
    device's own cloud dashboard (op 0x44), not a local file upload.

    latest_version only ever changes when the Check for Updates button
    is pressed - it's never fetched automatically at setup or on a poll,
    matching this integration's local-only philosophy elsewhere (this is
    the one command that asks the device itself to reach out to
    PowerShades' cloud).
    """

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    # PROGRESS is required for HA core to actually use the in_progress
    # property below instead of an internal flag this integration never
    # sets - see UpdateEntity.in_progress's own docstring.
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, coordinator: PowerShadesCoordinator) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator, "firmware")

    @property
    def installed_version(self) -> str | None:
        """Return the active firmware bank's revision number."""
        return self.coordinator.firmware_version

    @property
    def latest_version(self) -> str | None:
        """Return the latest revision last reported by Check for Updates.

        This is the device's own raw revision number for the firmware on
        its cloud dashboard - not confirmed to be on the same numeric
        scale as installed_version, so a mismatch here isn't necessarily
        a real update being available. See CloudUpdateReply's docstring
        in pyowershades for the full caveat.
        """
        return self.coordinator.latest_firmware_version

    @property
    def in_progress(self) -> bool:
        """Return whether the device's own event log shows an in-progress
        firmware update.

        Best-effort: TCP_Firmware_Update is a generic device-event log
        entry, not confirmed to specifically mean "an install triggered
        by this entity is running" rather than some other firmware-update
        path (e.g. one started from the vendor's own app).
        """
        return _TCP_FIRMWARE_UPDATE_ERROR_CODE in self.coordinator.data.error_list

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Trigger the device to install the latest firmware."""
        await self.coordinator.async_install_update()
