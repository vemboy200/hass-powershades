"""PowerShades data update coordinator."""

from __future__ import annotations

import asyncio
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
    ADMIN_ACCESS_PAYLOAD,
    CLOUD_UPDATE_CHECK_PAYLOAD,
    CLOUD_UPDATE_INSTALL_PAYLOAD,
    GET_SHADE_NAME_PAYLOAD,
    LIMIT_LOWER,
    LIMIT_UPPER,
    MODEL_NAMES,
    OP_ADMIN_ACCESS,
    OP_CLEAR_LIMITS,
    OP_CLOUD_UPDATE,
    OP_DISABLES,
    OP_GET_DEBUG_INFO,
    OP_GET_SERIAL,
    OP_GET_SHADE_NAME,
    OP_INDICATE,
    OP_JOG_DOWN,
    OP_JOG_STOP,
    OP_JOG_UP,
    OP_POE_MOTOR_PARAMS,
    OP_REBOOT,
    OP_SAVE_LIMITS,
    OP_SET_LIMIT,
    OP_SET_POSITION,
    OP_SET_SERVER_HOSTNAME,
    OP_STEP_DOWN,
    OP_STEP_UP,
    DebugInfoReply,
    PowerShadesConnection,
    PowerShadesTimeoutError,
    StatusReply,
    battery_percentage,
    build_set_disables_payload,
    build_set_limit_payload,
    build_set_motor_speed_payload_gen1,
    build_set_name_payload,
    build_set_position_payload,
    build_set_server_hostname_payload,
    parse_cloud_update_reply,
    parse_debug_info_reply,
    parse_disables_reply,
    parse_motor_parameters_reply,
    parse_serial_reply,
    parse_shade_name_reply,
)

from .const import DOMAIN, TRUSTED_SERVER_HOSTNAME

_LOGGER = logging.getLogger(__name__)

type PowerShadesConfigEntry = ConfigEntry[PowerShadesCoordinator]

# How often to poll Debug Info while waiting for a speed-carrying move to
# finish, and how long to wait before giving up. Tighter than the normal
# 10s/5s poll cycle on purpose - the speed reset should follow the actual
# stop closely, not lag behind by up to a full poll interval.
_RESET_SPEED_POLL_INTERVAL = 2
_RESET_SPEED_MAX_WAIT = 120


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
        # PoE Motor Parameters (op 0x27) - also configuration, fetched
        # once at setup and again after a write, not on every poll.
        self.motor_speed_percent: int | None = None
        # Cover speed-preset reset behavior - purely integration-side
        # preferences with no device-side equivalent, owned by the
        # switch/number entities themselves (RestoreEntity/RestoreNumber)
        # and mirrored here so cover.py can read them without an
        # entity-to-entity lookup.
        self.reset_speed_after_move: bool = False
        self.reset_speed_to_percent: int = 100
        # Cloud Update Check/Trigger (op 0x44) - purely user-triggered
        # (via the Check for Updates button), never fetched automatically
        # at setup or on a poll, matching this integration's local-only
        # philosophy elsewhere: this op asks the device itself to reach
        # out to PowerShades' cloud, so it only happens when asked.
        self.latest_firmware_version: str | None = None
        # Get Serial Number's server_hostname field (config, not
        # telemetry - fetched once at setup, like model/hw_version).
        # None means either it was never configured (the vendor's own
        # default) or the fetch failed - both treated as "nothing to
        # warn about" by _async_check_server_hostname in __init__.py.
        self.server_hostname: str | None = None
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

    def _data_from_debug_info(self, debug_info: DebugInfoReply) -> PowerShadesData:
        position = (
            debug_info.current_percent
            if 0 <= debug_info.current_percent <= 100
            else None
        )
        return PowerShadesData(
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
        return self._data_from_debug_info(debug_info)

    async def _async_wait_for_stop(self) -> bool:
        """Poll Debug Info at a tight interval until the shade goes idle.

        motor_state is the authoritative "still moving" signal, but it's
        only refreshed by polling (push replies carry position but not
        motor_state, per _handle_status_push), so this also cross-checks
        that position has stopped changing between two consecutive polls
        before treating a single idle reading as a real stop rather than
        a momentary lull. Returns False if the shade never settles within
        _RESET_SPEED_MAX_WAIT.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _RESET_SPEED_MAX_WAIT
        last_position: int | None = None
        while loop.time() < deadline:
            try:
                raw = await self.connection.async_request(OP_GET_DEBUG_INFO)
            except PowerShadesTimeoutError:
                await asyncio.sleep(_RESET_SPEED_POLL_INTERVAL)
                continue
            debug_info = parse_debug_info_reply(raw)
            if debug_info is not None:
                data = self._data_from_debug_info(debug_info)
                self.async_set_updated_data(data)
                if not debug_info.motor_state and data.position == last_position:
                    return True
                last_position = data.position
            await asyncio.sleep(_RESET_SPEED_POLL_INTERVAL)
        return False

    async def async_reset_speed_after_move(self, target_percent: int) -> None:
        """Wait for the current move to finish, then reset the motor speed.

        Meant to be run as a background task (fire-and-forget from
        cover.py) rather than awaited inline - blocking a cover service
        call for the shade's whole travel time would be wrong. If HA
        restarts mid-move this task is simply lost and the speed stays
        pinned to the preset until the next speed-carrying move.
        """
        if not await self._async_wait_for_stop():
            _LOGGER.warning(
                "Timed out waiting for %s to stop before resetting speed",
                self.ip_address,
            )
            return
        try:
            await self.async_set_motor_speed(target_percent)
        except HomeAssistantError:
            _LOGGER.warning("Failed to reset speed for %s after move", self.ip_address)

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

    async def async_fetch_motor_speed(self) -> None:
        """Fetch the shade's currently configured motor speed (0x27).

        Reads are not admin-gated, unlike writes. Best-effort: leaves
        motor_speed_percent unset on failure or a malformed reply.
        """
        try:
            reply = await self.connection.async_request(OP_POE_MOTOR_PARAMS)
        except PowerShadesTimeoutError:
            return
        result = parse_motor_parameters_reply(reply)
        if result is None:
            return
        self.motor_speed_percent = result.motor_power_up
        self.async_update_listeners()

    async def async_set_motor_speed(self, percent: int) -> None:
        """Set the shade's motor speed - the "Speed (%)" field in the
        vendor's own app (MotorPowerUP/DOWN, not DesiredRpmUP/DOWN).

        Gen 1 only: Gen 1 and Gen 2 firmware handle this write
        completely differently (confirmed from the vendor app's own
        model-version branch) and Gen 2's behavior hasn't been verified,
        so this refuses on anything other than a confirmed Gen 1 device
        rather than guess.

        Admin-gated: Admin Access (op 0x3C, a fixed factory key) must be
        sent immediately before the Set, every time - confirmed from the
        vendor app never caching an unlock. No read-before-write is
        needed here (unlike Feature Disables): Gen 1 firmware discards
        whatever was previously configured for every field except
        MotorPowerUP/DOWN, so there's nothing to preserve.
        """
        if self.hw_version != "Gen 1":
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="motor_speed_gen1_only",
                translation_placeholders={
                    "ip_address": self.ip_address,
                    "hw_version": self.hw_version or "unknown",
                },
            )
        payload = build_set_motor_speed_payload_gen1(percent)
        try:
            await self.connection.async_request(OP_ADMIN_ACCESS, ADMIN_ACCESS_PAYLOAD)
            reply = await self.connection.async_request(OP_POE_MOTOR_PARAMS, payload)
        except PowerShadesTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="motor_speed_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            ) from err
        result = parse_motor_parameters_reply(reply)
        if result is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="motor_speed_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            )
        self.motor_speed_percent = result.motor_power_up
        self.async_update_listeners()
        _LOGGER.info("Set motor speed=%s%% for %s", percent, self.ip_address)

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

    async def async_check_for_update(self) -> None:
        """Ask the device to check its own cloud dashboard for newer
        firmware (op 0x44, flag 1).

        Not admin-gated, unlike PoE Motor Parameters - the vendor app
        sends this standalone. Only ever runs when explicitly asked
        (this button, or the update entity's own refresh) - never
        automatically at setup or on a poll - since it's the one command
        in this whole integration that causes the device itself to reach
        out to PowerShades' cloud.
        """
        try:
            reply = await self.connection.async_request(
                OP_CLOUD_UPDATE, CLOUD_UPDATE_CHECK_PAYLOAD
            )
        except PowerShadesTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_check_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            ) from err
        result = parse_cloud_update_reply(reply)
        if result is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_check_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            )
        self.latest_firmware_version = str(result.result)
        self.async_update_listeners()
        _LOGGER.info(
            "Latest firmware reported for %s: %s",
            self.ip_address,
            self.latest_firmware_version,
        )

    async def async_install_update(self) -> None:
        """Trigger the device to install the latest firmware from its
        own cloud dashboard (op 0x44, flag 2).

        Re-reads server_hostname fresh (via Get Serial Number) right
        before checking it, rather than trusting whatever was cached at
        setup - that setting (op 0x0B, unauthenticated) controls where
        this op actually connects, and it could have been changed at any
        point after setup finished. A timeout on that fresh read falls
        back to the last known value instead of blocking on an unrelated
        connectivity hiccup. Refuses outright if the result isn't
        PowerShades' own domain: this is a hard block, not a warning that
        can be clicked through - the repair issue
        _async_check_server_hostname raises at setup is the proactive
        half of this, this is the point-of-use backstop. Use the
        powershades.set_server_hostname service (see async_set_server_hostname
        below) to correct it. A None server_hostname (never configured,
        or every read so far has failed) doesn't block - that's the
        vendor's own default, not evidence of tampering.

        The vendor app's own trigger button doesn't wait for or read a
        reply at all - but every other command in this integration is
        acknowledged the same way (_async_command), so this still awaits
        that ack rather than assuming success blind. If this op turns
        out not to send one on real hardware, that will surface as a
        clear failure here rather than as a silent no-op.
        """
        try:
            serial_reply = await self.connection.async_request(OP_GET_SERIAL)
        except PowerShadesTimeoutError:
            serial_reply = None
        parsed = parse_serial_reply(serial_reply) if serial_reply else None
        if parsed is not None:
            self.server_hostname = parsed["server_hostname"]
        if self.server_hostname and self.server_hostname != TRUSTED_SERVER_HOSTNAME:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="untrusted_server_hostname_blocked",
                translation_placeholders={
                    "ip_address": self.ip_address,
                    "hostname": self.server_hostname,
                },
            )
        await self._async_command(OP_CLOUD_UPDATE, CLOUD_UPDATE_INSTALL_PAYLOAD)
        _LOGGER.info("Triggered firmware install for %s", self.ip_address)

    async def async_set_server_hostname(self, hostname: str) -> None:
        """Set the device's Server Hostname (op 0x0B) and confirm by
        reading it back.

        This is the only way to correct the untrusted-server-hostname
        repair issue from inside HA - most usefully by setting it back
        to TRUSTED_SERVER_HOSTNAME, though this also works as a general
        "set it to whatever" service matching what the setting itself
        actually is. The vendor app's own handler doesn't read a reply
        for this command (same fire-and-forget pattern as Cloud Update's
        trigger) - this still awaits the normal generic ack via
        _async_command like every other write in this integration, then
        re-reads Get Serial Number to confirm the device actually stored
        the new value, rather than trusting the ack alone. This write
        (and whether a reply comes back at all) is unverified against
        real hardware - see pyowershades' docs/PROTOCOL.md.
        """
        await self._async_command(
            OP_SET_SERVER_HOSTNAME, build_set_server_hostname_payload(hostname)
        )
        try:
            reply = await self.connection.async_request(OP_GET_SERIAL)
        except PowerShadesTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="server_hostname_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            ) from err
        parsed = parse_serial_reply(reply) if reply else None
        if parsed is None or parsed["server_hostname"] != hostname:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="server_hostname_not_confirmed",
                translation_placeholders={"ip_address": self.ip_address},
            )
        self.server_hostname = parsed["server_hostname"]
        _LOGGER.info("Set server hostname to %r for %s", hostname, self.ip_address)
