import logging
import socket
import struct
import time
import asyncio
from homeassistant.components import network

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 42
BROADCAST_IP = "255.255.255.255"
GET_SERIAL_OPCODE = 0x00
GET_DEVICE_NAME_OPCODE = 0x3A
GET_SHADE_NAME_OPCODE = 0x34

# Discovery settings
DISCOVERY_TIMEOUT = 5.0
DISCOVERY_RETRIES = 2
DEVICE_NAME_TIMEOUT = 2.0

CrcTable = [
    0x0000,
    0x1021,
    0x2042,
    0x3063,
    0x4084,
    0x50A5,
    0x60C6,
    0x70E7,
    0x8108,
    0x9129,
    0xA14A,
    0xB16B,
    0xC18C,
    0xD1AD,
    0xE1CE,
    0xF1EF,
    0x1231,
    0x0210,
    0x3273,
    0x2252,
    0x52B5,
    0x4294,
    0x72F7,
    0x62D6,
    0x9339,
    0x8318,
    0xB37B,
    0xA35A,
    0xD3BD,
    0xC39C,
    0xF3FF,
    0xE3DE,
    0x2462,
    0x3443,
    0x0420,
    0x1401,
    0x64E6,
    0x74C7,
    0x44A4,
    0x5485,
    0xA56A,
    0xB54B,
    0x8528,
    0x9509,
    0xE5EE,
    0xF5CF,
    0xC5AC,
    0xD58D,
    0x3653,
    0x2672,
    0x1611,
    0x0630,
    0x76D7,
    0x66F6,
    0x5695,
    0x46B4,
    0xB75B,
    0xA77A,
    0x9719,
    0x8738,
    0xF7DF,
    0xE7FE,
    0xD79D,
    0xC7BC,
    0x48C4,
    0x58E5,
    0x6886,
    0x78A7,
    0x0840,
    0x1861,
    0x2802,
    0x3823,
    0xC9CC,
    0xD9ED,
    0xE98E,
    0xF9AF,
    0x8948,
    0x9969,
    0xA90A,
    0xB92B,
    0x5AF5,
    0x4AD4,
    0x7AB7,
    0x6A96,
    0x1A71,
    0x0A50,
    0x3A33,
    0x2A12,
    0xDBFD,
    0xCBDC,
    0xFBBF,
    0xEB9E,
    0x9B79,
    0x8B58,
    0xBB3B,
    0xAB1A,
    0x6CA6,
    0x7C87,
    0x4CE4,
    0x5CC5,
    0x2C22,
    0x3C03,
    0x0C60,
    0x1C41,
    0xEDAE,
    0xFD8F,
    0xCDEC,
    0xDDCD,
    0xAD2A,
    0xBD0B,
    0x8D68,
    0x9D49,
    0x7E97,
    0x6EB6,
    0x5ED5,
    0x4EF4,
    0x3E13,
    0x2E32,
    0x1E51,
    0x0E70,
    0xFF9F,
    0xEFBE,
    0xDFDD,
    0xCFFC,
    0xBF1B,
    0xAF3A,
    0x9F59,
    0x8F78,
    0x9188,
    0x81A9,
    0xB1CA,
    0xA1EB,
    0xD10C,
    0xC12D,
    0xF14E,
    0xE16F,
    0x1080,
    0x00A1,
    0x30C2,
    0x20E3,
    0x5004,
    0x4025,
    0x7046,
    0x6067,
    0x83B9,
    0x9398,
    0xA3FB,
    0xB3DA,
    0xC33D,
    0xD31C,
    0xE37F,
    0xF35E,
    0x02B1,
    0x1290,
    0x22F3,
    0x32D2,
    0x4235,
    0x5214,
    0x6277,
    0x7256,
    0xB5EA,
    0xA5CB,
    0x95A8,
    0x8589,
    0xF56E,
    0xE54F,
    0xD52C,
    0xC50D,
    0x34E2,
    0x24C3,
    0x14A0,
    0x0481,
    0x7466,
    0x6447,
    0x5424,
    0x4405,
    0xA7DB,
    0xB7FA,
    0x8799,
    0x97B8,
    0xE75F,
    0xF77E,
    0xC71D,
    0xD73C,
    0x26D3,
    0x36F2,
    0x0691,
    0x16B0,
    0x6657,
    0x7676,
    0x4615,
    0x5634,
    0xD94C,
    0xC96D,
    0xF90E,
    0xE92F,
    0x99C8,
    0x89E9,
    0xB98A,
    0xA9AB,
    0x5844,
    0x4865,
    0x7806,
    0x6827,
    0x18C0,
    0x08E1,
    0x3882,
    0x28A3,
    0xCB7D,
    0xDB5C,
    0xEB3F,
    0xFB1E,
    0x8BF9,
    0x9BD8,
    0xABBB,
    0xBB9A,
    0x4A75,
    0x5A54,
    0x6A37,
    0x7A16,
    0x0AF1,
    0x1AD0,
    0x2AB3,
    0x3A92,
    0xFD2E,
    0xED0F,
    0xDD6C,
    0xCD4D,
    0xBDAA,
    0xAD8B,
    0x9DE8,
    0x8DC9,
    0x7C26,
    0x6C07,
    0x5C64,
    0x4C45,
    0x3CA2,
    0x2C83,
    0x1CE0,
    0x0CC1,
    0xEF1F,
    0xFF3E,
    0xCF5D,
    0xDF7C,
    0xAF9B,
    0xBFBA,
    0x8FD9,
    0x9FF8,
    0x6E17,
    0x7E36,
    0x4E55,
    0x5E74,
    0x2E93,
    0x3EB2,
    0x0ED1,
    0x1EF0,
]


def crc16_xmodem(data: bytes) -> int:
    """Calculate CRC16-XMODEM checksum."""
    crc = 0
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ CrcTable[((crc >> 8) ^ b) & 0xFF]
    return crc


def build_get_serial_packet(sequence=0x01, channel=0x00):
    """Build Get Serial Number packet."""
    length = 0
    op = GET_SERIAL_OPCODE
    reserved = 0
    crc_data = struct.pack("<BBBB", op, sequence, channel, reserved)
    crc = crc16_xmodem(crc_data)
    packet = struct.pack("<HHBBBB", length, crc, op, sequence, channel, reserved)
    return packet


def build_get_device_name_packet(sequence=0x01, channel=0x00):
    """Build Get Device Name packet for RF Gateway and channels."""
    length = 0
    op = GET_DEVICE_NAME_OPCODE
    reserved = 0
    crc_data = struct.pack("<BBBB", op, sequence, channel, reserved)
    crc = crc16_xmodem(crc_data)
    packet = struct.pack("<HHBBBB", length, crc, op, sequence, channel, reserved)
    return packet


def build_get_shade_name_packet(sequence=0x01, channel=0x00):
    """Build Get PoE Shade Name packet."""
    length = 1  # 1 byte payload for Get/Set flag
    op = GET_SHADE_NAME_OPCODE
    reserved = 0
    get_set = 0  # 0 = Get, 1 = Set
    crc_data = struct.pack("<BBBBB", op, sequence, channel, reserved, get_set)
    crc = crc16_xmodem(crc_data)
    packet = struct.pack(
        "<HHBBBBB", length, crc, op, sequence, channel, reserved, get_set
    )
    return packet


def parse_serial_reply(data: bytes):
    """Parse Get Serial Number reply packet."""
    # See protocol doc for offsets
    if len(data) < 24:
        return None
    length, crc, op, seq, channel, reserved = struct.unpack("<HHBBBB", data[:8])
    model = data[8]
    serial_low = struct.unpack("<I", data[12:16])[0]
    serial_high = struct.unpack("<I", data[16:20])[0]
    ip_bytes = data[24:28]
    ip_addr = ".".join(str(b) for b in ip_bytes[::-1])
    return {
        "model": model,
        "serial": (serial_high << 32) | serial_low,
        "ip": ip_addr,
        "raw": data,
    }


def parse_device_name_reply(data: bytes):
    """Parse Get Device Name reply packet."""
    if len(data) < 58:  # 8 bytes header + 50 bytes device name
        return None
    length, crc, op, seq, channel, reserved = struct.unpack("<HHBBBB", data[:8])
    device_name_bytes = data[8:58]
    # Remove null bytes and decode
    device_name = (
        device_name_bytes.split(b"\x00")[0].decode("ascii", errors="ignore").strip()
    )
    return {"device_name": device_name, "channel": channel, "raw": data}


def parse_shade_name_reply(data: bytes):
    """Parse Get PoE Shade Name reply packet."""
    if len(data) < 59:  # 8 bytes header + 1 byte get/set + 50 bytes device name
        return None
    length, crc, op, seq, channel, reserved, get_set = struct.unpack(
        "<HHBBBBB", data[:9]
    )
    device_name_bytes = data[9:59]
    # Remove null bytes and decode
    device_name = (
        device_name_bytes.split(b"\x00")[0].decode("ascii", errors="ignore").strip()
    )
    return {"device_name": device_name, "get_set": get_set, "raw": data}


async def async_discover_devices(hass, timeout=DISCOVERY_TIMEOUT):
    """Discover PowerShades devices on the network using UDP broadcast."""
    _LOGGER.info("Starting PowerShades device discovery...")

    adapters = await network.async_get_adapters(hass)
    packet = build_get_serial_packet()
    discovered = []
    sockets = []

    # Create sockets for each enabled network adapter
    for adapter in adapters:
        if not adapter["enabled"]:
            continue
        for ip_info in adapter["ipv4"]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(1.0)  # Shorter timeout for individual reads
                sock.bind((ip_info["address"], 0))
                sockets.append(sock)
                _LOGGER.debug(f"Bound socket to {ip_info['address']}")
            except Exception as e:
                _LOGGER.warning(f"Failed to bind socket to {ip_info['address']}: {e}")
                continue

    if not sockets:
        _LOGGER.warning("No network adapters available for discovery")
        return discovered

    # Send broadcast packets
    for sock in sockets:
        try:
            sock.sendto(packet, (BROADCAST_IP, UDP_PORT))
            _LOGGER.debug(f"Sent discovery packet from {sock.getsockname()}")
        except Exception as e:
            _LOGGER.warning(f"Failed to send discovery packet: {e}")

    # Listen for responses
    start_time = time.time()
    seen_devices = set()  # Track unique devices by IP

    while time.time() - start_time < timeout:
        for sock in sockets:
            try:
                data, addr = sock.recvfrom(256)
                if addr[0] not in seen_devices:
                    parsed = parse_serial_reply(data)
                    if parsed:
                        parsed["host"] = addr[0]
                        discovered.append(parsed)
                        seen_devices.add(addr[0])
                        _LOGGER.info(
                            f"Discovered device: {parsed['ip']} "
                            f"(Serial: {parsed['serial']})"
                        )
            except socket.timeout:
                continue
            except Exception as e:
                _LOGGER.debug(f"Error reading from socket: {e}")
                continue

    # Clean up sockets
    for sock in sockets:
        try:
            sock.close()
        except Exception:
            pass

    _LOGGER.info(f"Discovery complete. Found {len(discovered)} devices")
    return discovered


async def async_get_device_name(hass, ip_address, timeout=DEVICE_NAME_TIMEOUT):
    """Get device name from a PowerShades device with retry logic."""
    _LOGGER.debug(f"Getting device name from {ip_address}")

    for attempt in range(2):  # Try twice
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            # Try PoE Shade name command first (most common)
            packet = build_get_shade_name_packet()
            sock.sendto(packet, (ip_address, UDP_PORT))

            try:
                data, addr = sock.recvfrom(256)
                parsed = parse_shade_name_reply(data)
                if parsed and parsed["device_name"]:
                    sock.close()
                    _LOGGER.debug(f"Got PoE shade name: {parsed['device_name']}")
                    return parsed["device_name"]
            except socket.timeout:
                pass

            # If PoE shade name failed, try RF Gateway device name
            packet = build_get_device_name_packet()
            sock.sendto(packet, (ip_address, UDP_PORT))

            try:
                data, addr = sock.recvfrom(256)
                parsed = parse_device_name_reply(data)
                if parsed and parsed["device_name"]:
                    sock.close()
                    _LOGGER.debug(f"Got RF gateway name: {parsed['device_name']}")
                    return parsed["device_name"]
            except socket.timeout:
                pass

        except Exception as e:
            _LOGGER.debug(
                f"Error getting device name from {ip_address} "
                f"(attempt {attempt + 1}): {e}"
            )
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if attempt < 1:  # Wait before retry
            await asyncio.sleep(0.1)

    _LOGGER.debug(f"Could not get device name from {ip_address}")
    return None


async def async_verify_device(hass, ip_address, timeout=2.0):
    """Verify that a device is a PowerShades device by sending a serial request."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        packet = build_get_serial_packet()
        sock.sendto(packet, (ip_address, UDP_PORT))

        try:
            data, addr = sock.recvfrom(256)
            parsed = parse_serial_reply(data)
            if parsed and parsed["ip"] == ip_address:
                sock.close()
                return parsed
        except socket.timeout:
            pass
        finally:
            sock.close()
    except Exception as e:
        _LOGGER.debug(f"Error verifying device {ip_address}: {e}")

    return None
