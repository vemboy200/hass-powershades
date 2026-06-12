"""PowerShades device coordinator."""

import asyncio
import logging
import socket
import struct
import threading
import time
from datetime import timedelta
from typing import Callable, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed


from .const import DOMAIN
from .udp import crc16_xmodem

_LOGGER = logging.getLogger(__name__)

OP_JOG_UP = 0x03
OP_JOG_DOWN = 0x04
OP_JOG_STOP = 0x05
OP_SET_POSITION = 0x1A
OP_GET_STATUS = 0x1D
OP_SET_LIMIT = 0x01
OP_CLEAR_LIMITS = 0x1E
OP_STEP_UP = 0x23
OP_STEP_DOWN = 0x24

# Limit types
LIMIT_UPPER = 0x0000
LIMIT_LOWER = 0x0001

UDP_PORT = 42


class PowerShadesDevice:
    """PowerShades device coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the PowerShades device."""
        self.hass = hass
        self.entry = entry
        self.ip_address = entry.data.get("ip")
        self.entry_id = entry.entry_id
        self.serial_number = entry.data.get("serial")
        self.device_name = entry.data.get("name")

        # Device state
        self._position: Optional[int] = None
        self._battery_voltage: Optional[int] = None
        self._available = True
        self._last_status_request = 0
        self._last_status_response = time.time()  # Start with current time
        self._sequence_counter = 0
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3

        # UDP listener
        self._udp_listener: Optional[UDPListener] = None
        self._listener_thread: Optional[threading.Thread] = None

        # Entity callbacks
        self._entity_callbacks: Dict[str, Callable] = {}

        # Movement state tracking for toggle functionality
        self._is_opening = False
        self._is_closing = False

        # Data coordinator for periodic updates - fixed 10 second interval
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"powershades_{self.ip_address}",
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=10),
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        # Use device name if available, otherwise fall back to IP
        if self.device_name:
            name = f"PowerShade {self.device_name}"
        else:
            name = f"PowerShade {self.ip_address}"

        # Use serial number as identifier if available
        if self.serial_number:
            identifiers = {(DOMAIN, str(self.serial_number))}
        else:
            identifiers = {(DOMAIN, self.entry_id)}

        return DeviceInfo(
            identifiers=identifiers,
            name=name,
            manufacturer="PowerShades",
            model="Motorized Window Cover",
            serial_number=str(self.serial_number) if self.serial_number else None,
        )

    @property
    def position(self) -> Optional[int]:
        """Return current position."""
        return self._position

    @property
    def battery_voltage(self) -> Optional[int]:
        """Return battery voltage in mV."""
        return self._battery_voltage

    @property
    def battery_percentage(self) -> Optional[int]:
        """Return battery percentage."""
        if self._battery_voltage is None:
            return None

        # Convert voltage to percentage (assuming 3.0V = 0%, 4.2V = 100%)
        # This is a rough estimate - adjust based on your battery specs
        voltage_v = self._battery_voltage / 1000.0
        if voltage_v <= 3.0:
            return 0
        elif voltage_v >= 4.2:
            return 100
        else:
            return int(((voltage_v - 3.0) / (4.2 - 3.0)) * 100)

    @property
    def available(self) -> bool:
        """Return if device is available."""
        # Consider device available if we've received a response in the last 2 minutes
        # instead of the previous 1 minute threshold
        time_since_response = time.time() - self._last_status_response
        if time_since_response < 120:  # 2 minutes
            return True
        _LOGGER.debug(
            "Device %s unavailable: last response %.1f seconds ago, " "_available=%s",
            self.ip_address,
            time_since_response,
            self._available,
        )
        return self._available

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return self._is_opening

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return self._is_closing

    def set_movement_state(self, is_opening: bool, is_closing: bool):
        """Set the movement state of the cover."""
        self._is_opening = is_opening
        self._is_closing = is_closing
        _LOGGER.debug(
            "Device %s movement state updated: opening=%s, closing=%s",
            self.ip_address,
            is_opening,
            is_closing,
        )
        # Notify entities immediately when movement state changes
        self._notify_entities()

    async def async_start(self):
        """Start the device."""
        # Start UDP listener
        self._udp_listener = UDPListener(self)
        self._listener_thread = threading.Thread(
            target=self._udp_listener.run, daemon=True
        )
        self._listener_thread.start()

        # Start coordinator
        await self.coordinator.async_config_entry_first_refresh()

        # If position is unknown after startup, request it immediately
        if self._position is None:
            _LOGGER.info(
                "Device %s position unknown after startup, requesting status",
                self.ip_address,
            )
            await self.async_request_status_with_retry(max_retries=3)

    async def async_stop(self):
        """Stop the device."""
        if self._udp_listener:
            self._udp_listener.stop()
        if self._listener_thread:
            self._listener_thread.join(timeout=5)

    def register_entity_callback(self, entity_id: str, callback: Callable):
        """Register an entity callback for updates."""
        self._entity_callbacks[entity_id] = callback
        # Immediately notify the new entity of the current state
        try:
            _LOGGER.debug("Immediately notifying entity callback for %s", entity_id)
            callback()
        except Exception as e:
            _LOGGER.error("Error in immediate entity callback: %s", e)

    def unregister_entity_callback(self, entity_id: str):
        """Unregister an entity callback."""
        self._entity_callbacks.pop(entity_id, None)

    @callback
    def _notify_entities(self):
        """Notify all registered entities of state changes safely."""
        _LOGGER.debug(
            "Current entity callbacks: %s", list(self._entity_callbacks.keys())
        )

        # Dynamically find where Home Assistant's instance is stored in this class
        hass = getattr(self, "hass", getattr(self, "_hass", None))

        for entity_id, callback_func in self._entity_callbacks.items():
            try:
                _LOGGER.debug("Notifying entity callback for %s", entity_id)

                # If we have the hass event loop available, bounce execution onto it
                if hass and hasattr(hass, "loop"):
                    hass.loop.call_soon_threadsafe(callback_func)
                else:
                    # Fallback if hass isn't instantiated yet during initial setup
                    callback_func()

            except Exception as e:
                _LOGGER.error("Error in entity callback: %s", e)

    async def _async_update_data(self):
        """Update device data."""
        # Check if device is responding - be more lenient with timing
        if time.time() - self._last_status_response > 180:  # No response for 3 minutes
            if self._available:
                _LOGGER.warning(
                    "Device %s not responding, marking as unavailable", self.ip_address
                )
                self._available = False
                self._notify_entities()
        else:
            if not self._available:
                _LOGGER.info(
                    "Device %s responding again, marking as available", self.ip_address
                )
                self._available = True
                self._notify_entities()

        # Request status with retry logic
        _LOGGER.debug("Device %s: Starting periodic status request", self.ip_address)
        await self.async_request_status_with_retry()

        # If device is available but position is unknown, be more aggressive
        if self._available and self._position is None:
            _LOGGER.debug(
                "Device %s available but position unknown, requesting status again",
                self.ip_address,
            )
            # Request status again with more retries for unknown position
            await self.async_request_status_with_retry(max_retries=3)
        elif self._available and self._position is not None:
            _LOGGER.debug(
                "Device %s: Current position is %d%%, continuing normal polling",
                self.ip_address,
                self._position,
            )

        return {
            "position": self._position,
            "battery_voltage": self._battery_voltage,
            "battery_percentage": self.battery_percentage,
            "available": self._available,
        }

    async def async_request_status_with_retry(self, max_retries: int = 2):
        """Request status from device with retry logic."""
        # Rate limiting to prevent overwhelming the device
        if time.time() - self._last_status_request < 0.5:
            _LOGGER.debug("Rate limiting status request")
            return  # Rate limiting

        self._last_status_request = time.time()

        if not self._udp_listener:
            return

        for attempt in range(max_retries + 1):
            try:
                packet = self._build_status_request_packet()
                self._udp_listener.send_command(packet)

                # Wait for response
                await asyncio.sleep(0.5)

                # Check if we got a response
                if time.time() - self._last_status_response < 2.0:
                    self._consecutive_failures = 0
                    break
                else:
                    _LOGGER.debug(
                        "No status response received on attempt %d", attempt + 1
                    )

            except Exception as e:
                _LOGGER.error(
                    "Error requesting status on attempt %d: %s", attempt + 1, e
                )

            if attempt < max_retries:
                await asyncio.sleep(1.0)  # Wait before retry

        # If all attempts failed, increment failure counter
        if time.time() - self._last_status_response >= 2.0:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_consecutive_failures:
                if self._available:
                    _LOGGER.warning(
                        "Device %s failed to respond after %d attempts",
                        self.ip_address,
                        self._consecutive_failures,
                    )
                    self._available = False
                    self._notify_entities()

    async def async_request_status(self):
        """Request status from device (legacy method for compatibility)."""
        await self.async_request_status_with_retry()

    async def async_set_position(self, position: int):
        """Set cover position."""
        if self._udp_listener:
            packet = self._build_set_position_packet(position)
            self._udp_listener.send_command(packet)

            # Request status after position change with shorter delay
            await asyncio.sleep(1)
            await self.async_request_status_with_retry()

    async def async_stop_cover(self):
        """Stop cover movement."""
        if self._udp_listener:
            packet = self._build_simple_packet(OP_JOG_STOP)
            self._udp_listener.send_command(packet)

    async def async_set_upper_limit(self):
        """Set the upper limit (fully open position)."""
        if self._udp_listener:
            packet = self._build_set_limit_packet(LIMIT_UPPER)
            self._udp_listener.send_command(packet)
            _LOGGER.info("Setting upper limit for device %s", self.ip_address)

    async def async_set_lower_limit(self):
        """Set the lower limit (fully closed position)."""
        if self._udp_listener:
            packet = self._build_set_limit_packet(LIMIT_LOWER)
            self._udp_listener.send_command(packet)
            _LOGGER.info("Setting lower limit for device %s", self.ip_address)

    async def async_clear_limits(self):
        """Clear both upper and lower limits."""
        if self._udp_listener:
            packet = self._build_simple_packet(OP_CLEAR_LIMITS)
            self._udp_listener.send_command(packet)
            _LOGGER.info("Clearing limits for device %s", self.ip_address)

    async def async_step_up(self):
        """Move the motor up one step (for trimming limits)."""
        if self._udp_listener:
            packet = self._build_simple_packet(OP_STEP_UP)
            self._udp_listener.send_command(packet)
            _LOGGER.debug("Stepping up for device %s", self.ip_address)

    async def async_step_down(self):
        """Move the motor down one step (for trimming limits)."""
        if self._udp_listener:
            packet = self._build_simple_packet(OP_STEP_DOWN)
            self._udp_listener.send_command(packet)
            _LOGGER.debug("Stepping down for device %s", self.ip_address)

    async def async_toggle(self):
        """Toggle the shade based on current state."""
        _LOGGER.debug("Toggling shade for device %s", self.ip_address)

        # Check if the cover is currently moving (opening or closing)
        if self._is_opening:
            _LOGGER.debug("Cover is opening, stopping it")
            # Clear movement states immediately
            self._is_opening = False
            self._is_closing = False
            # Notify entities of state change
            self._notify_entities()
            await self.async_stop_cover()
            return

        if self._is_closing:
            _LOGGER.debug("Cover is closing, stopping it")
            # Clear movement states immediately
            self._is_opening = False
            self._is_closing = False
            # Notify entities of state change
            self._notify_entities()
            await self.async_stop_cover()
            return

        # Clear any lingering movement states before checking position
        self._is_opening = False
        self._is_closing = False

        # Check if the cover is fully open
        if self.position == 100:
            _LOGGER.debug("Cover is open, closing it")
            # Set closing state
            self._is_opening = False
            self._is_closing = True
            # Notify entities of state change
            self._notify_entities()
            await self.async_set_position(0)  # Close
            return

        # Check if the cover is fully closed
        if self.position == 0:
            _LOGGER.debug("Cover is closed, opening it")
            # Set opening state
            self._is_opening = True
            self._is_closing = False
            # Notify entities of state change
            self._notify_entities()
            await self.async_set_position(100)  # Open
            return

        # For intermediate positions, use the 50% logic
        if self.position is None:
            _LOGGER.warning(
                "Cannot toggle: position unknown for device %s", self.ip_address
            )
            return

        if self.position > 50:
            _LOGGER.debug("Cover is partially open (>50%%), closing it")
            # Set closing state
            self._is_opening = False
            self._is_closing = True
            # Notify entities of state change
            self._notify_entities()
            await self.async_set_position(0)  # Close
        else:
            _LOGGER.debug("Cover is partially closed (<=50%%), opening it")
            # Set opening state
            self._is_opening = True
            self._is_closing = False
            # Notify entities of state change
            self._notify_entities()
            await self.async_set_position(100)  # Open

    def update_status(self, position: int, battery_voltage: int):
        """Update device status from UDP response."""
        self._last_status_response = time.time()

        # Mark device as available when we receive a response
        if not self._available:
            self._available = True
            _LOGGER.info("Device %s responding, marking as available", self.ip_address)

        if self._position != position:
            self._position = position

        if self._battery_voltage != battery_voltage:
            self._battery_voltage = battery_voltage

        # Reset failure counter on successful response
        if self._consecutive_failures > 0:
            self._consecutive_failures = 0

        # Always notify entities and update coordinator
        self._notify_entities()
        self.coordinator.async_set_updated_data(
            {
                "position": self._position,
                "battery_voltage": self._battery_voltage,
                "battery_percentage": self.battery_percentage,
                "available": self._available,
            }
        )

        _LOGGER.debug(
            "Device %s status updated: position=%d, battery=%d mV, available=%s",
            self.ip_address,
            position,
            battery_voltage,
            self._available,
        )

    def _build_simple_packet(
        self, op: int, sequence: Optional[int] = None, channel: int = 0x00
    ) -> bytes:
        """Build a simple UDP packet."""
        # Packet structure: length(2) + crc(2) + op(1) + seq(1) + channel(1) + reserved(1)
        length = 0  # No payload for simple packets
        reserved = 0

        # Use sequence counter if not provided
        if sequence is None:
            self._sequence_counter = (self._sequence_counter + 1) % 256
            sequence = self._sequence_counter

        # Build the data for CRC calculation: Op + Sequence + Channel + Reserved + Payload
        crc_data = struct.pack("<BBBB", op, sequence, channel, reserved)
        crc = crc16_xmodem(crc_data)

        # Build the complete packet: Length + CRC + Op + Sequence + Channel + Reserved
        packet = struct.pack("<HHBBBB", length, crc, op, sequence, channel, reserved)

        _LOGGER.debug(
            "Building simple packet: length=%d, crc=0x%04X, op=0x%02X, seq=%d, "
            "channel=%d, reserved=%d, packet=%s",
            length,
            crc,
            op,
            sequence,
            channel,
            reserved,
            packet.hex(),
        )
        return packet

    def _build_status_request_packet(
        self, sequence: Optional[int] = None, channel: int = 0x00
    ) -> bytes:
        """Build status request packet."""
        return self._build_simple_packet(OP_GET_STATUS, sequence, channel)

    def _build_set_limit_packet(
        self, limit_type: int, sequence: Optional[int] = None, channel: int = 0x00
    ) -> bytes:
        """Build set limit packet."""
        # Packet structure: length(2) + crc(2) + op(1) + seq(1) + channel(1) + reserved(1) + payload(2)
        length = 2  # Payload size
        reserved = 0

        # Use sequence counter if not provided
        if sequence is None:
            self._sequence_counter = (self._sequence_counter + 1) % 256
            sequence = self._sequence_counter

        # Build payload: Limit Type(2)
        payload = struct.pack("<H", limit_type)

        # Build the data for CRC calculation: Op + Sequence + Channel + Reserved + Payload
        crc_data = (
            struct.pack("<BBBB", OP_SET_LIMIT, sequence, channel, reserved) + payload
        )
        crc = crc16_xmodem(crc_data)

        # Build the complete packet: Length + CRC + Op + Sequence + Channel + Reserved + Payload
        packet = (
            struct.pack(
                "<HHBBBB", length, crc, OP_SET_LIMIT, sequence, channel, reserved
            )
            + payload
        )

        _LOGGER.debug(
            "Building set limit packet: length=%d, crc=0x%04X, op=0x%02X, "
            "seq=%d, channel=%d, limit_type=0x%04X, packet=%s",
            length,
            crc,
            OP_SET_LIMIT,
            sequence,
            channel,
            limit_type,
            packet.hex(),
        )
        return packet

    def _build_set_position_packet(
        self, percent: int, sequence: Optional[int] = None, channel: int = 0x00
    ) -> bytes:
        """Build set position packet."""
        # Packet structure: length(2) + crc(2) + op(1) + seq(1) + channel(1) + reserved(1) + payload(10)
        length = 10  # Payload size
        reserved = 0

        # Use sequence counter if not provided
        if sequence is None:
            self._sequence_counter = (self._sequence_counter + 1) % 256
            sequence = self._sequence_counter

        # Build payload: Mask(2) + Percent(2) + Tilt(2) + ChannelMask(4)
        mask = 0x0001  # MASK_PERCENT
        tilt = 0
        channel_mask = 0  # Use channel, not mask
        payload = struct.pack("<HhhI", mask, percent, tilt, channel_mask)

        # Build the data for CRC calculation: Op + Sequence + Channel + Reserved + Payload
        crc_data = (
            struct.pack("<BBBB", OP_SET_POSITION, sequence, channel, reserved) + payload
        )
        crc = crc16_xmodem(crc_data)

        # Build the complete packet: Length + CRC + Op + Sequence + Channel + Reserved + Payload
        packet = (
            struct.pack(
                "<HHBBBB", length, crc, OP_SET_POSITION, sequence, channel, reserved
            )
            + payload
        )

        _LOGGER.debug(
            "Building set position packet: length=%d, crc=0x%04X, op=0x%02X, "
            "seq=%d, channel=%d, percent=%d, mask=0x%04X, tilt=%d, channel_mask=0x%08X, packet=%s",
            length,
            crc,
            OP_SET_POSITION,
            sequence,
            channel,
            percent,
            mask,
            tilt,
            channel_mask,
            packet.hex(),
        )
        return packet


class UDPListener:
    """UDP listener for PowerShades device."""

    def __init__(self, device: PowerShadesDevice):
        """Initialize UDP listener."""
        self.device = device
        self.socket: Optional[socket.socket] = None
        self.running = False

    def run(self):
        """Run the UDP listener."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(1.0)

        try:
            # Bind to any available port (don't try to bind to port 42)
            self.socket.bind(("", 0))

            self.running = True
            listener_port = self.socket.getsockname()[1]
            _LOGGER.info("UDP listener started on port %d", listener_port)

            while self.running:
                try:
                    data, addr = self.socket.recvfrom(256)
                    self._handle_status_response(data, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        _LOGGER.error("Error in UDP listener: %s", e)

        except Exception as e:
            _LOGGER.error("Failed to start UDP listener: %s", e)
        finally:
            if self.socket:
                self.socket.close()

    def stop(self):
        """Stop the UDP listener."""
        self.running = False
        if self.socket:
            self.socket.close()

    def send_command(self, packet: bytes):
        """Send UDP command to device."""
        if self.socket and self.running:
            try:
                self.socket.sendto(packet, (self.device.ip_address, UDP_PORT))
                _LOGGER.debug(
                    "Sent packet to %s:%d: %s",
                    self.device.ip_address,
                    UDP_PORT,
                    packet.hex(),
                )
            except Exception as e:
                _LOGGER.error("Failed to send packet: %s", e)

    def _handle_status_response(self, data: bytes, addr: tuple) -> None:
        """Handle status response from device."""
        try:
            _LOGGER.debug(
                "Received UDP packet from %s: length=%d, data=%s",
                addr[0],
                len(data),
                data.hex(),
            )

            if len(data) < 8:  # Minimum packet size
                _LOGGER.debug("Packet too short: %d bytes", len(data))
                return

            # Parse header: Length(2) + CRC(2) + Op(1) + Sequence(1) + Channel(1) + Reserved(1)
            length, crc, op, sequence, channel, reserved = struct.unpack(
                "<HHBBBB", data[:8]
            )

            _LOGGER.debug(
                "Packet header: length=%d, crc=0x%04X, op=0x%02X, seq=%d, channel=%d",
                length,
                crc,
                op,
                sequence,
                channel,
            )

            if op != OP_GET_STATUS:
                _LOGGER.debug("Not a status response, op=0x%02X", op)
                return  # Not a status response

            if len(data) < 8 + length:  # Check if we have enough data for payload
                _LOGGER.debug(
                    "Packet too short for payload: %d < %d", len(data), 8 + length
                )
                return

            # Parse payload according to specification
            payload = data[8 : 8 + length]
            _LOGGER.debug("Payload length: %d bytes", len(payload))

            # Handle different payload sizes - device seems to send 40 bytes
            if len(payload) >= 30:  # 30-byte or longer status packet
                # Parse the first 30 bytes as the standard status fields
                (
                    current_percent,
                    current_tilt,
                    current_memory,
                    battery_voltage,
                    time_val,
                    cycles,
                    stalls,
                    temperature,
                    raw_percent,
                    raw_tilt,
                ) = struct.unpack("<hhHHIIIhII", payload[:30])

                _LOGGER.debug(
                    "Status response: percent=%d, tilt=%d, battery=%d mV, "
                    "cycles=%d, stalls=%d",
                    current_percent,
                    current_tilt,
                    battery_voltage,
                    cycles,
                    stalls,
                )

                # Update device state using the correct method
                self.device.update_status(current_percent, battery_voltage)
            else:
                _LOGGER.debug(
                    "Payload too short for status packet: %d < 30", len(payload)
                )

        except Exception as e:
            _LOGGER.error("Error parsing status response: %s", e)
            _LOGGER.debug("Raw data: %s", data.hex())
