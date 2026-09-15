"""Repairs for the PowerShades integration."""

from __future__ import annotations

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import TRUSTED_SERVER_HOSTNAME
from .coordinator import PowerShadesConfigEntry


class UntrustedServerHostnameRepairFlow(RepairsFlow):
    """One-click reset of Server Hostname back to PowerShades' own domain."""

    def __init__(self, entry: PowerShadesConfigEntry) -> None:
        """Create flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Handle the first step of a fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Reset the hostname on confirm, showing the current (untrusted)
        value so the user can see what's about to change."""
        coordinator = self.entry.runtime_data
        errors: dict[str, str] | None = None
        if user_input is not None:
            try:
                await coordinator.async_set_server_hostname(TRUSTED_SERVER_HOSTNAME)
            except HomeAssistantError:
                errors = {"base": "reset_failed"}
            else:
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            errors=errors,
            description_placeholders={
                "hostname": coordinator.server_hostname or "unknown",
                "expected": TRUSTED_SERVER_HOSTNAME,
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a fix flow for a PowerShades repair issue."""
    if (
        issue_id.startswith("untrusted_server_hostname_")
        and data is not None
        and isinstance(entry_id := data.get("entry_id"), str)
        and (entry := hass.config_entries.async_get_entry(entry_id)) is not None
    ):
        return UntrustedServerHostnameRepairFlow(entry)
    raise ValueError(f"unknown repair {issue_id}")  # pragma: no cover
