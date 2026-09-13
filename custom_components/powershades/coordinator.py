"""PowerShades data update coordinator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from pyowershades import (
    GET_SHADE_NAME_PAYLOAD,
    LIMIT_LOWER,
    LIMIT_UPPER,
    MODEL_NAMES,
    OP_CLEAR_LIMITS,
    OP_DISABLES,
    OP_GET_DEBUG_INFO,
    OP_GET_SHADE_NAME,
    OP_INDICATE,
    OP_JOG_DOWN,
    OP_JOG_STOP,
    OP_JOG_UP,
    OP_REBOOT,
    OP_SAVE_LIMITS,
    OP_SET_LIMIT,
    OP_SET_POSITION,
    OP_STEP_DOWN,
    OP_STEP_UP,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    StatusReply,
    battery_percentage,
    build_set_disables_payload,
    build_set_limit_payload,
    build_set_name_payload,
    build_set_position_payload,
    parse_debug_info_reply,
    parse_disables_reply,
    parse_shade_name_reply,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type PowerShadesConfigEntry = ConfigEntry[PowerShadesCoordinator]


@dataclass(frozen=True)
class PowerShadesData:
    """State of one PowerShades device."""

    position: int | None = None
    battery_mv: int | None = None
    battery_percentage: int | None = None
    io_green_led: bool | None = None
    io_red_led: bool | None = None
    io_motor_sleep: bool | None = None
    io_poe_status: bool | None = None
    motor_state: int | None = None
    error_list: list[int] = field(default_factory=list)
    velocity_rpm: int | None = None
    desired_rpm: int | None = None
    motor_duty_cycle: int | None = None


class PowerShadesCoordinator(DataUpdateCoordinator[PowerShadesData]):
    """Coordinator polling one PowerShades device and handling its pushes."""

    config_entry: PowerShadesConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PowerShadesConfigEntry,
        connection: PowerShadesConnection,
    ) -> None:
        """Initialize the coordinator."""
        self.connection = connection
        self.ip_address: str = entry.data["ip"]
        self.entry_id = entry.entry_id
        self.serial_number = entry.data.get("serial")
        self.device_name = entry.data.get("name")
        self.mac_address: str | None = entry.data.get("mac")
        self.model: int | None = entry.data.get("model")
        self.firmware_version: str | None = None
        self.hw_version: str | None = None
        # Feature Disables (op 0x35) - configuration, not telemetry, so
        # it's only fetched once at setup and again after this
        # integration writes a change, not on every regular poll.
        self.allow_cloud_connection: bool | None = None
        self._disables_raw: int | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"PowerShades {self.ip_address}",
            update_interval=timedelta(seconds=10),
        )
        connection.set_status_callback(self._handle_status_push)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        if self.device_name:
            name = f"PowerShade {self.device_name}"
        else:
            name = f"PowerShade {self.ip_address}"

        # The entry_id is always present and never changes, so it's a
        # stable primary identifier. The serial is added once known so
        # devices set up before serials were stored (identified only by
        # entry_id) and devices set up after (identified only by serial)
        # converge onto the same device registry entry once both are
        # present - the registry merges identifier sets onto a matching
        # existing device rather than requiring an exact match.
        identifiers = {(DOMAIN, self.entry_id)}
        if self.serial_number:
            identifiers.add((DOMAIN, str(self.serial_number)))

        model_name = (
            MODEL_NAMES.get(self.model, "Motorized Window Cover")
            if self.model is not None
            else "Motorized Window Cover"
        )

        return DeviceInfo(
            identifiers=identifiers,
            connections=(
                {(CONNECTION_NETWORK_MAC, self.mac_address)}
                if self.mac_address
                else set()
            ),
            name=name,
            manufacturer="PowerShades",
            model=model_name,
            serial_number=str(self.serial_number) if self.serial_number else None,
            sw_version=self.firmware_version,
            hw_version=self.hw_version,
        )

    def _data_from_status(self, status: StatusReply) -> PowerShadesData:
        # Status pushes only carry position/battery - the Get Debug Info
        # fields (io_green_led, io_red_led, io_motor_sleep, io_poe_status,
        # motor_state, error_list, velocity_rpm, desired_rpm,
        # motor_duty_cycle) are only refreshed by our own poll cycle, so
        # carry the last known values forward here.
        return PowerShadesData(
            position=status.position,
            battery_mv=status.battery_mv,
            battery_percentage=battery_percentage(status.battery_mv),
            io_green_led=self.data.io_green_led if self.data is not None else None,
            io_red_led=self.data.io_red_led if self.data is not None else None,
            io_motor_sleep=self.data.io_motor_sleep if self.data is not None else None,
            io_poe_status=self.data.io_poe_status if self.data is not None else None,
            motor_state=self.data.motor_state if self.data is not None else None,
            error_list=self.data.error_list if self.data is not None else [],
            velocity_rpm=self.data.velocity_rpm if self.data is not None else None,
            desired_rpm=self.data.desired_rpm if self.data is not None else None,
            motor_duty_cycle=(
                self.data.motor_duty_cycle if self.data is not None else None
            ),
        )

    @callback
    def _handle_status_push(self, status: StatusReply) -> None:
        """Handle a status packet (runs on the event loop).

        Sets data directly instead of calling async_set_updated_data(),
        which also cancels and reschedules the poll timer. Get Debug Info
        (motor_state, io_green_led, io_red_led) has no push equivalent and
        is only ever refreshed by that poll, so letting frequent pushes
        keep deferring it would delay those fields for no benefit.
        """
        self.data = self._data_from_status(status)
        self.last_update_success = True
        self.async_update_listeners()

    @override
    async def _async_update_data(self) -> PowerShadesData:
        """Poll the device for status via a single Debug Info request.

        Debug Info carries position and battery in addition to
        motor_state/io_green_led/io_red_led, so there's no need to also
        poll Get Status - it's only still used for real-time push, since
        the shade only ever sends that op unsolicited.
        """
        try:
            raw = await self.connection.async_request(OP_GET_DEBUG_INFO)
        except PowerShadesTimeoutError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_timeout",
                translation_placeholders={
                    "ip_address": self.ip_address,
                    "error": str(err),
                },
            ) from err
        debug_info = parse_debug_info_reply(raw)
        if debug_info is None:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_malformed_reply",
                translation_placeholders={"ip_address": self.ip_address},
            )
        position = (
            debug_info.current_percent
            if 0 <= debug_info.current_percent <= 100
            else None
        )
        data = PowerShadesData(
            position=position,
            battery_mv=debug_info.battery_mv,
            battery_percentage=battery_percentage(debug_info.battery_mv),
            io_green_led=debug_info.io_green_led,
            io_red_led=debug_info.io_red_led,
            io_motor_sleep=debug_info.io_motor_sleep,
            io_poe_status=debug_info.io_poe_status,
            motor_state=debug_info.motor_state,
            error_list=debug_info.error_list,
            velocity_rpm=debug_info.velocity_rpm,
            desired_rpm=debug_info.desired_rpm,
            motor_duty_cycle=debug_info.motor_duty_cycle,
        )
        # Poll faster while the position is unknown
        self.update_interval = timedelta(seconds=5 if data.position is None else 10)
        return data

    async def _async_command(self, op: int, payload: bytes = b"") -> None:
        """Send a command and await the device's echo reply (ACK).

        Every command is acknowledged with a reply carrying the same op
        and sequence; the reply payload itself is meaningless (PoE
        shades may send a generic reply packet).
        """
        try:
            await self.connection.async_request(op, payload)
        except PowerShadesTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_not_acknowledged",
                translation_placeholders={"ip_address": self.ip_address},
            ) from err

    async def async_set_position(self, position: int) -> None:
        """Move the shade to a position (0=closed, 100=open)."""
        await self._async_command(OP_SET_POSITION, build_set_position_payload(position))
        # Refresh immediately so the real motor state (not just the next
        # scheduled poll) reflects the move starting right away.
        await self.async_request_refresh()

    async def async_stop(self) -> None:
        """Stop shade movement."""
        await self._async_command(OP_JOG_STOP)
        await self.async_request_refresh()

    async def async_toggle(self) -> None:
        """Toggle the shade: stop if moving, otherwise open/close."""
        data = self.data
        if data is None or data.position is None:
            _LOGGER.warning("Cannot toggle shade %s: position unknown", self.ip_address)
            return
        if data.motor_state:
            await self.async_stop()
        elif data.position > 50:
            await self.async_set_position(0)
        else:
            await self.async_set_position(100)

    async def async_jog_up(self) -> None:
        """Jog the shade up until it reaches a limit or is stopped."""
        await self._async_command(OP_JOG_UP)
        await self.async_request_refresh()

    async def async_jog_down(self) -> None:
        """Jog the shade down until it reaches a limit or is stopped."""
        await self._async_command(OP_JOG_DOWN)
        await self.async_request_refresh()

    async def async_identify(self) -> None:
        """Make the shade motor indicate (wiggle) to identify it."""
        await self._async_command(OP_INDICATE)

    async def async_set_upper_limit(self) -> None:
        """Set the upper limit (fully open position)."""
        await self._async_command(OP_SET_LIMIT, build_set_limit_payload(LIMIT_UPPER))
        _LOGGER.info("Set upper limit for %s", self.ip_address)

    async def async_set_lower_limit(self) -> None:
        """Set the lower limit (fully closed position)."""
        await self._async_command(OP_SET_LIMIT, build_set_limit_payload(LIMIT_LOWER))
        _LOGGER.info("Set lower limit for %s", self.ip_address)

    async def async_clear_limits(self) -> None:
        """Clear both limits."""
        await self._async_command(OP_CLEAR_LIMITS)
        _LOGGER.info("Cleared limits for %s", self.ip_address)

    async def async_reboot(self) -> None:
        """Reboot the shade's controller."""
        await self._async_command(OP_REBOOT)
        _LOGGER.info("Rebooted %s", self.ip_address)

    async def async_save_limits(self) -> None:
        """Persist the currently-set limits to the device's flash storage."""
        await self._async_command(OP_SAVE_LIMITS)
        _LOGGER.info("Saved limits for %s", self.ip_address)

    async def async_step_up(self) -> None:
        """Move the motor up one step (for trimming limits)."""
        await self._async_command(OP_STEP_UP)

    async def async_step_down(self) -> None:
        """Move the motor down one step (for trimming limits)."""
        await self._async_command(OP_STEP_DOWN)

    async def async_fetch_disables_state(self) -> None:
        """Fetch the current Feature Disables byte.

        Best-effort: leaves allow_cloud_connection unset on failure or a
        malformed reply, matching _async_fetch_device_id_info's approach
        to other setup-time-only info.
        """
        try:
            reply = await self.connection.async_request(OP_DISABLES)
        except PowerShadesTimeoutError:
            return
        disables = parse_disables_reply(reply)
        if disables is None:
            return
        self._disables_raw = disables.raw
        self.allow_cloud_connection = not disables.tcp_cloud_disabled
        self.async_update_listeners()

    async def async_set_allow_cloud_connection(self, allow: bool) -> None:
        """Enable or disable the shade's TCP/cloud connectivity.

        Reads the current Feature Disables byte first and only flips the
        TCP/cloud bit - a blind write would silently clear whichever
        other Feature Disables bits the device already has set (e.g. via
        the official app).
        """
        await self.async_fetch_disables_state()
        if self._disables_raw is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cloud_connection_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            )
        payload = build_set_disables_payload(
            self._disables_raw, tcp_cloud_disabled=not allow
        )
        try:
            reply = await self.connection.async_request(OP_DISABLES, payload)
        except PowerShadesTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cloud_connection_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            ) from err
        disables = parse_disables_reply(reply)
        if disables is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cloud_connection_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            )
        self._disables_raw = disables.raw
        self.allow_cloud_connection = not disables.tcp_cloud_disabled
        self.async_update_listeners()
        _LOGGER.info("Set allow_cloud_connection=%s for %s", allow, self.ip_address)

    async def async_set_shade_name(self, name: str) -> None:
        """Rename the shade on the device and sync the new name into HA."""
        await self._async_command(OP_GET_SHADE_NAME, build_set_name_payload(name))

        # Read the name back to confirm the device stored it
        try:
            reply = await self.connection.async_request(
                OP_GET_SHADE_NAME, GET_SHADE_NAME_PAYLOAD
            )
        except PowerShadesTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="rename_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            ) from err
        confirmed = parse_shade_name_reply(reply)
        if not confirmed:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="rename_empty_name",
                translation_placeholders={"ip_address": self.ip_address},
            )

        self.device_name = confirmed
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, "name": confirmed},
            title=f"PowerShade {confirmed}",
        )
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers=self.device_info["identifiers"]
        )
        if device is not None:
            device_registry.async_update_device(
                device.id, name=f"PowerShade {confirmed}"
            )
        _LOGGER.info("Renamed shade %s to %r", self.ip_address, confirmed)
