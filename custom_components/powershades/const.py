"""Constants for the PowerShades integration."""

DOMAIN = "powershades"

RF_GATEWAY_ISSUE_URL = (
    "https://github.com/vemboy200/hass-powershades/issues/new?template=rf_support.yml"
)

# The factory value of the device's Server Hostname setting (op 0x0B,
# unauthenticated) for each hardware generation. Gen 1's is confirmed via
# a real capture of Get Serial Number's server_hostname field; Gen 2's
# comes from the issue #17 reporter, whose Gen 2 shades lost cloud
# connectivity after being reset to Gen 1's value. Both are PowerShades'
# own servers, so either is accepted on any shade; anything else means
# the device's cloud-facing commands (Cloud Update Check/Trigger among
# them) are talking to somewhere other than PowerShades.
TRUSTED_SERVER_HOSTNAMES = {
    "Gen 1": "dashboard.powershades.com",
    "Gen 2": "cloudserver.powershades.com",
}
