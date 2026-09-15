"""Constants for the PowerShades integration."""

DOMAIN = "powershades"

RF_GATEWAY_ISSUE_URL = (
    "https://github.com/vemboy200/hass-powershades/issues/new?template=rf_support.yml"
)

# The only legitimate value for the device's Server Hostname setting
# (op 0x0B, unauthenticated) - confirmed via a real capture of
# Get Serial Number's server_hostname field. Anything else means the
# device's cloud-facing commands (Cloud Update Check/Trigger among them)
# are talking to somewhere other than PowerShades.
TRUSTED_SERVER_HOSTNAME = "dashboard.powershades.com"
