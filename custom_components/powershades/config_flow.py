import logging
import socket
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .udp import async_get_device_name

_LOGGER = logging.getLogger(__name__)


class PowerShadesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PowerShades."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        super().__init__()
        self.device_info = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial user setup step by going straight to manual entry."""
        return await self.async_step_manual_entry(user_input)

    async def async_step_manual_entry(self, user_input=None) -> FlowResult:
        """Handle manual IP entry and query the device directly for verification."""
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
                    device_info = None

                    _LOGGER.info(
                        "Connecting directly to PowerShades device at %s to verify connectivity",
                        ip_address,
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
                        except socket.timeout:
                            _LOGGER.warning("No response from %s on port 42", ip_address)
                        finally:
                            sock.close()
                    except Exception as e:
                        _LOGGER.error(
                            "Error communicating with device at %s: %s",
                            ip_address,
                            e,
                        )

                    # Quality Scale Guard: Reject entry creation if the socket connection dropped/timed out
                    if device_info is None:
                        errors["base"] = "cannot_connect"
                    else:
                        unique_id = str(device_info["serial"])
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        device_name = await async_get_device_name(self.hass, ip_address)
                        title = (
                            f"PowerShade {device_name}"
                            if device_name
                            else f"PowerShade {ip_address}"
                        )

                        return self.async_create_entry(
                            title=title,
                            data={
                                "ip": ip_address,
                                "serial": device_info["serial"],
                                "name": device_name,
                            },
                        )

        return self.async_show_form(
            step_id="manual_entry",
            data_schema=vol.Schema({vol.Required("ip"): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return PowerShadesOptionsFlow(config_entry)


class PowerShadesOptionsFlow(config_entries.OptionsFlow):
    """Handle PowerShades options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
