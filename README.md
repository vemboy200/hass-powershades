# PowerShades Home Assistant Integration
The Home Assistant Powershades integration allows to control your [Powershades](https://powershades.com) shades. This integration is tested with PoE Powershades controllers. The underlying protocol also recognizes an RF hub, but its behavior with Home Assistant hasn't been verified, since the maintainer doesn't have access to that hardware.

If you have RF shades it is recommended you buy a [Bond Bridge](https://bondhome.io/) and connect your RF shades using that, then connect it to Home Assistant using the [built in integration](https://www.home-assistant.io/integrations/bond/). If you already have Powershade's RF Hub, please open an issue and report what the results are trying to connect the hub to Home Assistant using this integration.

This integration shares its UDP protocol implementation with the [minimal cover-only version of PowerShades submitted to Home Assistant core](https://github.com/home-assistant/core/pull/173830), via the [pyowershades](https://pypi.org/project/pyowershades/) PyPI library. This custom integration is where the fuller feature set (buttons, sensors, diagnostics, services) lives while those land in core as follow-up PRs one at a time.

## How you can use this integration
This intgeration can be used to control your Powershades shades, you can have it open in the morning to get you out of the bed, or close them at sunset for extra privacy. 
 
PoE Powershades do not come with a remote, so controlling them without a smart device is difficult. To fix this you can use a smart button (such as a Zigbee or Z-Wave button) with an automation to control your shade. This may be convient to you or others, including guests controlling your shades without having to open a smart device.

## Features

- **Cover Platform**: Control blinds as Home Assistant covers (open, close, set position, stop), with a real motor-reported opening/closing state, plus a Slow/Medium/Fast `speed` option on open/close/set position (Gen 1 only)
- **Button Platform**: Buttons for toggling, identifying, rebooting, limit calibration (jog, step, set/clear limits, save limits), and checking for firmware updates
- **Update Platform**: A Firmware update entity showing the installed version and the latest version last reported by the Check for Updates button, and letting you trigger an install
- **Sensor Platform**: Diagnostic battery percentage and voltage sensors (disabled by default), an LED color sensor (off/green/red/yellow, disabled by default) reflecting the shade's status LEDs, an Error sensor decoding the shade's logged error codes, Current RPM/Motor Power sensors (disabled by default) for live motor telemetry while moving, and a Desired RPM sensor (disabled by default, Gen 2 only)
- **Binary Sensor Platform**: Motor Awake and Charging diagnostic sensors (both disabled by default)
- **Number Platform**: A settable Speed (40-100%, enabled by default), for the shade's motor speed, and a Reset Speed To number (40-100%, enabled by default, Gen 1 only) controlling what the speed-carrying cover moves reset back to
- **Switch Platform**: Allow Cloud Connection (disabled by default), controlling whether the shade may connect to PowerShades' own cloud dashboard, and Reset Speed After Move (enabled by default, Gen 1 only), controlling whether the cover's Slow/Medium/Fast speed presets are automatically reset back afterward instead of sticking
- **Services**: `powershades.set_shade_name`, for renaming a shade
- **UDP Communication**: Direct UDP communication with PowerShades controllers
- **Config Flow**: Easy setup through Home Assistant's UI, with automatic and DHCP discovery
- **Local Control**: No cloud dependencies for normal operation - the one exception is Check for Updates/the Firmware update entity, which ask the shade itself to reach out to PowerShades' own cloud dashboard on your behalf

## Prerequisites

It is unknown if UDP communication is enabled by default on every PowerShades controller. If the integration's discovery doesn't find your shade and manual entry with its IP address gives a "cannot connect" error, you may need to enable UDP on the device yourself. If you figure out how to enable UDP on a shade that didn't have it on by default, please open an issue and explain how, so it can be documented here.

### Finding your shade's IP address

The integration's discovery step will usually find shades on your network automatically. If you need to enter an IP manually:

- **Via the PowerShades App (Recommended)**: Open the official PowerShades mobile app, navigate to your desired shade, select Enable Configuration, and confirm the prompt. Scroll down to view the assigned IP address.
- **Via Your Router's DHCP Client List**: Log into your network router's administration panel and check the connected devices list. Look for a device manufactured by "Wideband Labs LLC" — this is likely your PowerShades device.

## Installation

### HACS Installation (recommended)

This integration can be installed via HACS as a custom repository:

1. In HACS, go to **Settings** → **Repositories**
2. Click the **+** button to add a new repository
3. Enter the repository URL: `https://github.com/vemboy200/hass-powershades`
4. Select **Integration** as the category
5. Click **Add**
6. Once added, search for "PowerShades" in HACS
7. Click **Download**
8. Restart Home Assistant

**Note**: This integration uses semantic versioning with proper GitHub releases. See the [Releases](https://github.com/vemboy200/hass-powershades/releases) page for the latest version.

### Manual Installation (not recommended)

1. Download this repository (clone or download ZIP)
2. Copy the `custom_components/powershades` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Supported Devices
Any PoE Powershade shade with UDP communication enabled, on the same local network as Home Assistant.

⚠️ Note: The RF Powershades bridge is currently untested and may be unsupported. For RF Powershades, please use a [Bond Bridge](https://bondhome.io/).

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "PowerShades"
4. The integration scans your network and lists discovered shades — pick one, or choose manual entry and provide the shade's IP address
5. The device is verified before the entry is created; if it doesn't respond you'll get a "cannot connect" error

## Usage

### Cover Controls

Once configured, your PowerShades will appear as covers in Home Assistant. You can:

- **Open**: Fully open the blinds
- **Close**: Fully close the blinds  
- **Set Position**: Set blinds to a specific percentage (0-100)
- **Stop**: Stop blinds in their current position

### Button Controls

Each shade also gets buttons for:

- **Toggle Shade**: Open/close based on current position, or stop if moving (under Configuration - the cover entity already covers this for everyday use)
- **Identify**: Makes the shade motor wiggle so you can tell which physical shade this is (under Diagnostic)
- **Reboot**: Restarts the shade's controller (under Diagnostic)
- **Jog Up/Down, Set Upper/Lower Limit, Clear Limits, Step Up/Down, Save Limits**: Limit calibration tools (under the device's Configuration section). Typical workflow: jog near the desired position, step to fine-tune, set the limit, then save it so it persists to the device's flash storage. Set Upper/Lower Limit, Clear Limits, and Save Limits are disabled by default - enable them from the device page when you actually need to recalibrate - since an accidental press (e.g. Clear Limits, or Set Upper/Lower Limit while the shade isn't at the right physical position) can miscalibrate the shade's travel range and isn't easily undone. Jog and Step stay enabled since they're reversible (jog/step the other way undoes them).
- **Check for Updates**: Asks the shade to check its own cloud dashboard for newer firmware (under Diagnostic) - see Firmware Updates below.

### Diagnostic Entities

Battery percentage and battery voltage are available as diagnostic sensor entities (disabled by default — enable them from the device page). Note: in versions before 0.2.0 these values were exposed as attributes on the cover entity; templates referencing `battery_percentage`/`battery_voltage_mv` cover attributes should switch to the sensors.

An LED Color sensor (disabled by default — enable it from the device page) mirrors the shade's two physical status LEDs (green and red) as a single sensor with four states: `off`, `green`, `red`, and `yellow` (both LEDs on at once) — useful since these LEDs can turn on unpredictably and aren't otherwise visible unless you're standing in front of the shade.

An Error sensor (enabled by default) decodes the shade's logged error codes (`PoEErrorCode` values like `Motor_Stall`, `TCP_Keep_Alive`, `Battery_Low_Power_Down`) into a named state, with `mdi:check-circle` when there's no error and `mdi:alert-circle` otherwise. The shade can log more than one error at once, but this sensor can only show one - it shows the most recent entry in the list. A code the integration doesn't recognize shows as `unknown` rather than failing.

Two more diagnostic binary sensors are also available. **Motor Awake** (disabled by default — enable it from the device page) shows whether the motor driver (H-bridge) is powered, which the official PowerShades app labels "H-Bridge Power". In practice it's on while the motor is driving and off while the shade is idle. The cover's opening/closing state is still the better way to tell which direction the shade is moving. **Charging** (disabled by default, like the battery/voltage sensors - enable it from the device page) reflects whether PoE is present and negotiated normally; in practice this reads on almost the entire time the shade is reachable at all, since a full PoE loss also cuts power to the whole device, so it's mainly useful for catching a degraded or under-negotiated PoE link the shade is still limping along on.

**Current RPM** and **Motor Power** (disabled by default — enable from the device page) show live motor telemetry: the measured motor speed and its power level as a percentage. Both read 0 while the shade is idle.

**Desired RPM** (disabled by default, **Gen 2 only** — not created at all on Gen 1) would show the firmware's RPM-based speed-control target. It isn't offered on Gen 1 because Gen 1's Set template forces `SpeedControlEnable` off (see the Speed number entity below), so that control loop never runs there and the field reads a constant 0 regardless of actual motion - confirmed on real Gen 1 hardware, not just a guess. Whether it reports anything meaningful on Gen 2 is unverified - there's no Gen 2 unit to test against yet.

### Speed control

**Speed** (40-100%, enabled by default, Number platform) sets the shade's motor speed - the same "Speed (%)" field in the official PowerShades app. Unlike everything else in this integration, writing it requires unlocking a privileged command on the device first (Admin Access, a fixed factory key sent immediately before the actual command). The valid range is 40-100 - the official app itself refuses anything lower, so values below 40 are rejected before anything is sent. This is currently only implemented for **Gen 1** hardware: Gen 1 and Gen 2 firmware handle this write completely differently (confirmed from the official app's own code), and Gen 2's behavior hasn't been verified, so attempting this on a non-Gen-1 device raises an error instead of guessing. Unlike the disabled-by-default entities above, this one is enabled out of the box and left uncategorized (shown under Controls, not Configuration) - it's meant for active use, e.g. a slower speed for quiet nighttime automations and a faster one for manual operation.

The cover entity also supports a Slow/Medium/Fast `speed` option (40%/70%/100%) on `cover.open_cover`, `cover.close_cover`, and `cover.set_cover_position`, using Home Assistant's built-in [cover speed feature](https://github.com/home-assistant/architecture/discussions/789) - the shade's speed is set to match right before the move. This only appears on **Gen 1** hardware, for the same reason as the Speed number above, and requires **Home Assistant 2026.10 or later** (`hacs.json` declares this minimum version for HACS installs; there's no equivalent check for a manual install on an older core - the entity would just fail to reference `CoverEntityFeature.SPEED` on setup in that case).

Unlike some other integrations' equivalent of this feature, the shade's motor speed is a persistent device setting, not something scoped to a single move - so a speed-carrying move otherwise leaves every later move (manual switch, the official app, another automation without a `speed` argument) running at whatever preset was last used. Two more entities (Gen 1 only, same as above) let you control that: **Reset Speed After Move** (Switch platform, enabled by default) and **Reset Speed To** (Number platform, 40-100%, enabled by default, seeded from the current Speed value at setup). With the switch on, once a speed-carrying move actually finishes - detected by polling Debug Info more tightly than the normal 10-second cycle until the motor reports idle and the position stops changing - the speed is set back to the Reset Speed To value. If the shade never reports idle within 2 minutes, the reset is skipped and the preset speed is left as-is rather than guessing; if Home Assistant restarts mid-move, the same thing happens, since there's nothing to resume the wait after a restart.

Setting a speed, and the reset-after-move behavior above, haven't been verified against real hardware yet - the Gen 1 payload is built entirely from the decompiled vendor app, not a real capture of an actual speed change.

### Switches

**Allow Cloud Connection** (disabled by default — enable from the device page) controls whether the shade's own TCP connection to PowerShades' cloud dashboard is allowed. Turning it off doesn't affect local control through this integration at all - it only blocks the shade's separate outbound connection. This reads and writes the device's Feature Disables register directly, preserving every other bit in that register so it doesn't undo any other setting you've configured through the official app.

This is unverified against real hardware behavior (only confirmed from the vendor's own decompiled source, like most things not yet wire-tested) - see [pyowershades' docs/KNOWN_BEHAVIORS.md](https://github.com/vemboy200/Pyowershades/blob/main/docs/KNOWN_BEHAVIORS.md) for the open investigation this entity exists to help with.

### Firmware Updates

This is the "the shade fetches it from PowerShades' own cloud" kind of firmware update, not the "upload a firmware file yourself" kind - this integration never handles firmware bytes directly. Pressing **Check for Updates** (Button platform, enabled by default) asks the shade to query its own cloud dashboard and reports back a revision number, shown as the **Firmware** update entity's latest version; the entity's installed version is the same active-bank revision already shown on the device info page. Pressing Install on the update entity asks the shade to fetch and install that firmware itself - this integration doesn't transfer any firmware data.

Two things about this are unconfirmed, not just unverified, because the vendor's own app never needed to answer them: whether the "latest version" number is even on the same numeric scale as the installed version (the app only ever displays it to a human, never compares the two), and whether an install actually in progress is reliably reflected by the update entity's `in_progress` state - that's inferred from a `TCP_Firmware_Update` entry in the shade's general event log, which also logs unrelated events (stalls, reboots, CRC mismatches), so it's a best-effort signal, not a confirmed one. Until verified, a version mismatch shown here should be treated as "worth checking on PowerShades' own app," not as certain proof an update is waiting.

Checking for updates and installing are the only things in this integration that cause the shade itself to talk to PowerShades' cloud - see Local Control in Features above.

**Server hostname safety check.** Which server those two actions actually connect to is itself a device setting (Server Hostname, PowerShades' own protocol) with no authentication protecting it - anyone on your network could redirect it. The same hostname is also where the shade's own cloud connection goes if you've enabled **Allow Cloud Connection** above, which is what lets the official PowerShades app control the shade remotely (away from home) - so a redirected hostname isn't just a firmware-data risk, it could mean remote-control commands for the shade going to a server that isn't PowerShades' own. On every setup, this integration reads that setting back (via Get Serial Number) and compares it against PowerShades' real domain (`dashboard.powershades.com`); if it doesn't match, a Critical repair issue appears in Settings → Repairs explaining the mismatch, with a **Fix** button that resets it back in one click. Separately, every time you press **Install** on the Firmware update entity, it re-reads that setting fresh (rather than trusting whatever was seen at setup) and refuses to proceed if it isn't PowerShades' own domain - so a redirect that happens after setup, before the repair issue is next refreshed, still gets caught right at the moment it would matter. This is a hard block, not a warning you can click through. Checking for updates still works either way, but treat its result as untrustworthy until the repair issue is resolved. A hostname that was never configured at all (empty), or a fresh read that times out, is treated as the vendor's own default rather than evidence of tampering, and doesn't block anything.

### Services

Besides the standard cover services, the integration provides `powershades.set_shade_name` (renames the shade on the device itself; the Home Assistant device name follows) and `powershades.set_server_hostname` (sets the DNS hostname the shade resolves for its own outbound connections - see Server hostname safety check above; the Fix button on the repair issue calls this with PowerShades' own domain for you, but the service accepts any value if you have a specific reason to set something else). Toggling, jogging, stepping, and limit calibration are buttons instead (see Button Controls above) — as of v1.0.0 they're no longer also exposed as services, since a button already covers the exact same no-parameters action.


### Known Limitations

- PowerShades devices send replies and asynchronous move feedback only to the **last controller that sent them a command** (the "UDP subscriber"). Avoid running PowerShades Config.NET or another driver at the same time as Home Assistant — control still works, but live position feedback may intermittently lag until the next poll.
- This will cause a problem with other hubs using the UDP communication (ex: Control4) that rely soley on the push data, to have the wrong state of the shade.
Push data is sent every 10 seconds so updates are not instant
- The shade must be on the same network subnet as Home Assistant, or UDP broadcast traffic must be routed between subnets.
- Only PoE Shades are fully supported, so it is recommened that you connect your RF Powershades to Home Assistant using a Bond Bridge, and report what went wrong when adding your Powershades RF bridge.
- The Allow Cloud Connection switch only reads the device's Feature Disables setting at setup and right after you toggle it - not on every poll. If something other than this integration changes it (the official app, another controller, etc.), the switch can show a stale value until you toggle it again or reload the integration.
- Reset Speed After Move waits up to 2 minutes for the shade to report idle before resetting the speed; if Home Assistant restarts during that wait, the reset doesn't happen and the speed stays at whatever preset was last used until the next speed-carrying move overwrites it.
- The Firmware update entity's "update available" comparison is only as good as whether the shade's cloud dashboard reports a revision number on the same scale as the installed one - unconfirmed either way (see Firmware Updates above). Don't treat it as a reliable "you're up to date" signal yet.
- `powershades.set_server_hostname` (and the repair issue's Fix button, which calls it) is unverified against real hardware - the write itself hasn't been tested on a real device yet, only against the decompiled vendor source. It does read the value back afterward to confirm the device actually stored it, so a silent failure shouldn't be mistaken for success, but proceed carefully the first time you use it.

### Data Updates

The shade pushes its status to Home Assistant in real time whenever Home Assistant is the one controlling it (the "UDP subscriber"). On top of that, Home Assistant polls the shade every 10 seconds so that changes made by another controller — such as the PowerShades app or a Control4 system — are also picked up. Each poll cycle also makes a second, best-effort request (Get Debug Info) for the Green LED state and the real motor state used by the cover's opening/closing indication; if that second request times out the rest of the update still succeeds, just without refreshing those two values.

Home Assistant's `iot_class` manifest field only allows a single value, and this integration declares `local_push`. In practice though, its behavior has something in common with both of Home Assistant's local classifiers:

- **Local Push**: while Home Assistant is the "UDP subscriber", the shade pushes its status roughly every 10 seconds on its own, and also sends an extra push the instant it reaches the position it was told to move to — so Home Assistant finds out a move finished without waiting for its next poll.
- **Local Polling**: the 10-second poll is what catches position changes made by another controller — without it, those changes would go unnoticed until the next Home Assistant-issued command.

The cover's "Opening"/"Closing"/"Open"/"Closed" state is read directly from the device rather than guessed: `is_closed` comes straight from the reported position (0%), and the opening/closing indication comes from the shade's own `motor_state` field (idle, moving up, or moving down) obtained via Get Debug Info — no heuristic or position-delta guessing is involved.

All communication between Home Assistant and the shade is local and doesn't leave your house, which is kind of weird considering that in the official Powershades app, all data goes through their cloud. The one exception is Check for Updates and installing a firmware update (see Firmware Updates above) - those explicitly ask the shade itself to reach out to PowerShades' cloud, so they only happen if you press one of those buttons. The device will work without an internet connection in the short term. It is unknown how the device will behave without an internet connection long term.

### Automation Examples

Open a shade in the morning:

```yaml
alias: Open bedroom shade
description: ""
triggers:
  - trigger: time
    at: "07:00:00"
conditions: []
actions:
  - action: cover.open_cover
    target:
      entity_id: cover.bedroom_shade
mode: single
```

Close shades at dusk:

```yaml
alias: Close shades at dusk
description: ""
triggers:
  - trigger: state
    entity_id:
      - sensor.sun_next_dusk
conditions:
  - condition: state
    entity_id: cover.bedroom_shade
    state: "open"
actions:
  - action: cover.close_cover
    target:
      entity_id:
        - cover.bedroom_shade
mode: single
```

## Requirements

- A recent version of Home Assistant — the latest is recommended. The integration relies on modern APIs (config entry `runtime_data`, PEP 695 type aliases) that older releases don't have.
- PowerShades controller with UDP communication enabled

## Troubleshooting

### I got an error about it not being able to connect
- This means that Home Assistant could not communicate to the shade, make sure home assistant can access port 42 on your shade, and that UDP broadcasts can be routed between different subnets if needed.
- You entered a wrong IP address or you entered an IP address that was already in use by a config entry
### Cover entity shows as unavailable 
- This means that Home Assistant could not communicate to the shade, make sure home assistant can access port 42 on your shade, and that UDP broadcasts can be routed between different subnets if needed.
- It could also mean that your shade is not connected to your local network
- If it's only unavailable for anywhere from 10 seconds to a couple of minutes and then recovers on its own, that comes from the shade itself, not your network or Home Assistant. The shade briefly stops responding to local commands, then recovers at the same moment its green status LED lights up - you can see this by enabling the LED Color sensor (disabled by default) and comparing its history with the cover's. This is believed to be related to the shade's own connection to PowerShades' cloud dashboard. See [pyowershades' known behaviors](https://github.com/vemboy200/Pyowershades/blob/main/docs/KNOWN_BEHAVIORS.md) for the details.
### HACS Installation Issues

If you encounter errors when installing via HACS:

1. **Version Error**: Ensure the repository has a proper release tag (see the [Releases](https://github.com/vemboy200/hass-powershades/releases) page)
2. **Repository Not Found**: Verify the repository URL is correct and the repository is public
3. **Download Failed**: Try refreshing HACS and clearing the cache

### Debug Logging

Click this button in the integration menu in the top right enable debuging log

<img width="378" height="244" alt="Screenshot 2026-05-28 at 4 40 56 PM" src="https://github.com/user-attachments/assets/443bae92-4350-4ef5-bb4f-e13d6ad17e52" />

If you're confused by what I just showed you
- Navigate to Settings → Devices & Services and select the PowerShades integration.
- Click the three dots menu in the top right and select Enable debug logging.
  
Then trigger the error, and download the logs from Settings > System > Logs > Download logs
If you stop the debuging log from the Home Assistant Companion App it should automatically download

## Removing This Integration

Removing this integration is the same as most HACS integrations:

- Go to **Settings** → **Devices & Services** and select the PowerShades integration card.
- From the list of devices, select the PowerShades entry.
- Next to the entry, select the three-dot menu, then select **Delete**.
- Repeat steps 2 and 3 for every entry you have
- If installed through HACS, go to HACS, select the three-dot menu for this integration, then select **Remove**.
- If you did a manual installation, delete the `custom_components/powershades` folder,
- Then (regradless of installtion method) restart Home Assistant to clear the cache.

## Development

### Contributing

1. Fork this repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [dstocking](https://github.com/dstocking/powershades-homeassistant), the original author of this integration
- PowerShades for their UDP protocol documentation
- Home Assistant community for the integration framework

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/vemboy200/hass-powershades/issues) page.

