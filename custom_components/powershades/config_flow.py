import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .udp import async_discover_devices, async_get_device_name
import socket
import logging

_LOGGER = logging.getLogger(__name__)


class PowerShadesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        super().__init__()
        self.discovered_devices = {}
        self.device_info = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_discovery()

    async def async_step_discovery(self, user_input=None) -> FlowResult:
        """Handle the discovery step."""
        if user_input is not None:
            if user_input.get("select_device"):
                # User selected a discovered device
                selected_ip = user_input["select_device"]
                device_info = self.discovered_devices.get(selected_ip)

                if device_info:
                    # Use serial number as unique ID
                    unique_id = str(device_info["serial"])
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    # Get device name
                    device_name = await async_get_device_name(self.hass, selected_ip)
                    if device_name:
                        title = f"PowerShade {device_name}"
                    else:
                        title = f"PowerShade {selected_ip}"

                    return self.async_create_entry(
                        title=title,
                        data={
                            "ip": selected_ip,
                            "serial": device_info["serial"],
                            "name": device_name,
                        },
                    )
            elif user_input.get("manual_entry"):
                # User wants to enter IP manually
                return await self.async_step_manual_entry()

        # Discover devices
        _LOGGER.info("Starting PowerShades device discovery...")
        discovered = await async_discover_devices(self.hass)

        # Store discovered devices for later use
        self.discovered_devices = {device["ip"]: device for device in discovered}

        if discovered:
            device_choices = {
                d["ip"]: f"{d['ip']} (Serial: {d['serial']})" for d in discovered
            }

            return self.async_show_form(
                step_id="discovery",
                data_schema=vol.Schema(
                    {
                        vol.Optional("select_device"): vol.In(device_choices),
                        vol.Optional("manual_entry"): bool,
                    }
                ),
                description_placeholders={
                    "devices": ", ".join(device_choices.values())
                },
            )
        else:
            # No devices found, go to manual entry
            return await self.async_step_manual_entry()

    async def async_step_manual_entry(self, user_input=None) -> FlowResult:
        """Handle manual IP entry."""
        errors = {}

        if user_input is not None:
            ip_address = user_input.get("ip")
            if ip_address:
                # Validate IP address format
                try:
                    socket.inet_aton(ip_address)
                except socket.error:
                    errors["ip"] = "invalid_ip"
                else:
                    # Try to get device info for unique ID
                    device_info = None

                    # First check if it's in our discovered devices
                    for device in self.discovered_devices.values():
                        if device["ip"] == ip_address:
                            device_info = device
                            break

                    # If not found in discovery, try direct communication
                    if not device_info:
                        _LOGGER.info(
                            f"Device {ip_address} not found in discovery, "
                            f"trying direct communication"
                        )
                        try:
                            from .udp import build_get_serial_packet, parse_serial_reply

                            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            sock.settimeout(2.0)

                            packet = build_get_serial_packet()
                            sock.sendto(packet, (ip_address, 42))

                            try:
                                data, addr = sock.recvfrom(256)
                                parsed = parse_serial_reply(data)
                                if parsed and parsed["ip"] == ip_address:
                                    device_info = parsed
                                    _LOGGER.info(
                                        f"Retrieved device info for {ip_address}: serial={parsed['serial']}"
                                    )
                            except socket.timeout:
                                _LOGGER.warning(
                                    f"No response from {ip_address} during direct serial request"
                                )
                            finally:
                                sock.close()
                        except Exception as e:
                            _LOGGER.error(
                                f"Error getting device info for {ip_address}: {e}"
                            )

                    if device_info:
                        # Use serial number as unique ID
                        unique_id = str(device_info["serial"])
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()
                    else:
                        # Generate a unique ID based on IP for now
                        unique_id = f"manual_{ip_address.replace('.', '_')}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                    # Get device name
                    device_name = await async_get_device_name(self.hass, ip_address)
                    if device_name:
                        title = f"PowerShade {device_name}"
                    else:
                        title = f"PowerShade {ip_address}"

                    return self.async_create_entry(
                        title=title,
                        data={
                            "ip": ip_address,
                            "serial": device_info["serial"] if device_info else None,
                            "name": device_name,
                        },
                    )

        return self.async_show_form(
            step_id="manual_entry",
            data_schema=vol.Schema(
                {
                    vol.Required("ip"): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return PowerShadesOptionsFlow(config_entry)


class PowerShadesOptionsFlow(config_entries.OptionsFlow):
    """Handle PowerShades options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
