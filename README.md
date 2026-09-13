# PowerShades Home Assistant Integration
The Home Assistant Powershades integration allows to control your [Powershades](https://powershades.com) shades. This integration is tested with PoE Powershades controllers. The underlying protocol also recognizes an RF hub, but its behavior with Home Assistant hasn't been verified, since the maintainer doesn't have access to that hardware.

If you have RF shades it is recommended you buy a [Bond Bridge](https://bondhome.io/) and connect your RF shades using that, then connect it to Home Assistant using the [built in integration](https://www.home-assistant.io/integrations/bond/). If you already have Powershade's RF Hub, please open an issue and report what the results are trying to connect the hub to Home Assistant using this integration.

This integration shares its UDP protocol implementation with the [minimal cover-only version of PowerShades submitted to Home Assistant core](https://github.com/home-assistant/core/pull/173830), via the [pyowershades](https://pypi.org/project/pyowershades/) PyPI library. This custom integration is where the fuller feature set (buttons, sensors, diagnostics, services) lives while those land in core as follow-up PRs one at a time.

## How you can use this integration
This intgeration can be used to control your Powershades shades, you can have it open in the morning to get you out of the bed, or close them at sunset for extra privacy. 
 
PoE Powershades do not come with a remote, so controlling them without a smart device is difficult. To fix this you can use a smart button (such as a Zigbee or Z-Wave button) with an automation to control your shade. This may be convient to you or others, including guests controlling your shades without having to open a smart device.

## Features

- **Cover Platform**: Control blinds as Home Assistant covers (open, close, set position, stop), with a real motor-reported opening/closing state
- **Button Platform**: Buttons for toggling, identifying, rebooting, and limit calibration (jog, step, set/clear limits, save limits)
- **Sensor Platform**: Diagnostic battery percentage and voltage sensors (disabled by default), an LED color sensor (off/green/red/yellow) reflecting the shade's status LEDs, an Error sensor decoding the shade's logged error codes, and Current RPM/Desired RPM/Motor Power sensors (disabled by default) for live motor telemetry while moving
- **Binary Sensor Platform**: Motor Awake and Charging diagnostic sensors
- **Services**: `powershades.set_shade_name`, for renaming a shade
- **UDP Communication**: Direct UDP communication with PowerShades controllers
- **Config Flow**: Easy setup through Home Assistant's UI, with automatic and DHCP discovery
- **Local Control**: No cloud dependencies, works entirely locally

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

### Diagnostic Entities

Battery percentage and battery voltage are available as diagnostic sensor entities (disabled by default — enable them from the device page). Note: in versions before 0.2.0 these values were exposed as attributes on the cover entity; templates referencing `battery_percentage`/`battery_voltage_mv` cover attributes should switch to the sensors.

An LED Color sensor (enabled by default) mirrors the shade's two physical status LEDs (green and red) as a single sensor with four states: `off`, `green`, `red`, and `yellow` (both LEDs on at once) — useful since these LEDs can turn on unpredictably and aren't otherwise visible unless you're standing in front of the shade.

An Error sensor (enabled by default) decodes the shade's logged error codes (`PoEErrorCode` values like `Motor_Stall`, `TCP_Keep_Alive`, `Battery_Low_Power_Down`) into a named state, with `mdi:check-circle` when there's no error and `mdi:alert-circle` otherwise. The shade can log more than one error at once, but this sensor can only show one - it shows the most recent entry in the list. A code the integration doesn't recognize shows as `unknown` rather than failing.

Two more diagnostic binary sensors are also available. **Motor Awake** (enabled by default) reflects a power-management state of the motor driver electronics - awake vs. low-power sleep after a period of inactivity - not whether the shade is actually moving; the shade can be fully idle and still "awake" simply from having been recently polled or commanded. Actual movement is what the cover's opening/closing state already tracks. **Charging** (disabled by default, like the battery/voltage sensors - enable it from the device page) reflects whether PoE is present and negotiated normally; in practice this reads on almost the entire time the shade is reachable at all, since a full PoE loss also cuts power to the whole device, so it's mainly useful for catching a degraded or under-negotiated PoE link the shade is still limping along on.

**Current RPM**, **Desired RPM**, and **Motor Power** (disabled by default — enable from the device page) show live motor telemetry: the measured motor speed, the speed the motor controller is trying to reach, and its power level as a percentage. All three read 0 while the shade is idle. Comparing Current RPM against Desired RPM can reveal the motor struggling to reach its target speed (e.g. under load or resistance).

### Services

Besides the standard cover services, the integration provides `powershades.set_shade_name` (renames the shade on the device itself; the Home Assistant device name follows). Toggling, jogging, stepping, and limit calibration are buttons instead (see Button Controls above) — as of v1.0.0 they're no longer also exposed as services, since a button already covers the exact same no-parameters action.


### Known Limitations

- PowerShades devices send replies and asynchronous move feedback only to the **last controller that sent them a command** (the "UDP subscriber"). Avoid running PowerShades Config.NET or another driver at the same time as Home Assistant — control still works, but live position feedback may intermittently lag until the next poll.
- This will cause a problem with other hubs using the UDP communication (ex: Control4) that rely soley on the push data, to have the wrong state of the shade.
Push data is sent every 10 seconds so updates are not instant
- The shade must be on the same network subnet as Home Assistant, or UDP broadcast traffic must be routed between subnets.
- Only PoE Shades are fully supported, so it is recommened that you connect your RF Powershades to Home Assistant using a Bond Bridge, and report what went wrong when adding your Powershades RF bridge.

### Data Updates

The shade pushes its status to Home Assistant in real time whenever Home Assistant is the one controlling it (the "UDP subscriber"). On top of that, Home Assistant polls the shade every 10 seconds (every 5 seconds while the position is unknown) so that changes made by another controller — such as the PowerShades app or a Control4 system — are also picked up. Each poll cycle also makes a second, best-effort request (Get Debug Info) for the Green LED state and the real motor state used by the cover's opening/closing indication; if that second request times out the rest of the update still succeeds, just without refreshing those two values.

Home Assistant's `iot_class` manifest field only allows a single value, and this integration declares `local_push`. In practice though, its behavior has something in common with both of Home Assistant's local classifiers:

- **Local Push**: while Home Assistant is the "UDP subscriber", the shade pushes its status roughly every 10 seconds on its own, and also sends an extra push the instant it reaches the position it was told to move to — so Home Assistant finds out a move finished without waiting for its next poll.
- **Local Polling**: the 10-second poll is what catches position changes made by another controller — without it, those changes would go unnoticed until the next Home Assistant-issued command.

The cover's "Opening"/"Closing"/"Open"/"Closed" state is read directly from the device rather than guessed: `is_closed` comes straight from the reported position (0%), and the opening/closing indication comes from the shade's own `motor_state` field (idle, moving up, or moving down) obtained via Get Debug Info — no heuristic or position-delta guessing is involved.

All communication is local and the data does not leave your house, which is kind of weird considering that in the offical Powershades app, all data goes through their cloud. The device will work without an internet connection in the short term. It is unknown how the device will behave without an internet connection long term.

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

## Changelog

### v1.0.0
- **Breaking change**: Removed the `powershades.toggle_shade`, `powershades.jog_up`/`jog_down`, `powershades.step_up`/`step_down`, and `powershades.set_upper_limit`/`set_lower_limit`/`clear_limits` services. Each one duplicated an existing button entity (Toggle Shade, Jog Up/Down, Step Up/Down, Set Upper/Lower Limit, Clear Limits) that takes no parameters, so there was nothing a service added over pressing the button - update any automations calling these services to press the equivalent button (`button.press`) instead. `powershades.set_shade_name` is unaffected, since it needs a name parameter a button can't provide
- **Breaking change**: Replaced the Green LED binary sensor with an LED Color sensor. The device actually has two status LEDs (green and red), and this makes both visible as one entity with four states (`off`/`green`/`red`/`yellow`, where yellow means both are lit) instead of only ever tracking the green one. Automations/dashboards referencing the old `binary_sensor.*_green_led` entity need to switch to the new `sensor.*_led_color` entity and its string states instead of on/off
- Added Motor Awake (enabled by default) and Charging (disabled by default) binary sensors (Diagnostic)
- Set Upper Limit, Set Lower Limit, Clear Limits, and Save Limits are now disabled by default - unlike Jog/Step, they aren't easily reversible, so an accidental press could miscalibrate the shade's travel range. This only affects newly-added shades - existing entries keep whatever enabled/disabled state their buttons already had
- Polling now uses a single Get Debug Info request per cycle instead of two separate requests - Get Debug Info already carries position and battery alongside motor_state and both LEDs, so Get Status is no longer actively polled. It's still used for the shade's own real-time push, since the shade only ever sends that op unsolicited
- Status pushes no longer reset the poll timer, so motor_state and the LED color sensor refresh on their normal schedule regardless of how often the shade pushes
- Declared the `pyowershades` package as a debug-logging source in the manifest, so enabling debug logging on the integration now also captures the library's own per-packet logs, not just the coordinator's
- The LED Color sensor now shows `mdi:led-outline` when off and `mdi:led-on` when lit, instead of a generic icon
- The diagnostics download now decodes the shade's error log (`PoEErrorCode` values) into readable names alongside the raw numbers, e.g. `TCP_Keep_Alive`, `Enter_Sleep_Mode`. Bumps the `pyowershades` dependency to 0.3.0, which added the decoder (`parse_error_list`, `POE_ERROR_CODES`) after reading how the official Config.NET app itself decodes this field
- Added an Error sensor (Diagnostic, enabled by default) showing the shade's most recently logged error code by name, with a `mdi:check-circle`/`mdi:alert-circle` icon. The device can log more than one error at a time, but this sensor can only show one
- Moved the Toggle Shade button to Configuration - it's not needed for everyday use since the cover entity already covers opening/closing/stopping. Like the entity-disabled-by-default changes above, this only affects newly-added shades; an existing Toggle Shade button keeps showing in the main entity list unless you change its category manually
- Added Current RPM (`mdi:speedometer`), Desired RPM (`mdi:target`), and Motor Power (`mdi:engine`) sensors (Diagnostic, disabled by default) for live motor telemetry - all three read 0 while idle
- Device info now also shows a hardware version (`Gen 1`/`Gen 2`) alongside the existing firmware revision, from Get Device ID's model-version byte. `0 = Gen 1` is confirmed against real hardware; `2 = Gen 2` is the working hypothesis from the decompiled config app, not yet checked against an actual Gen 2 unit. Any other value shows as `Model version N` rather than guessing

### v0.9.0
- Added Reboot and Save Limits buttons (Configuration)
- Added a Green LED binary sensor (Diagnostic) - the shade's status LED can turn on unpredictably, and this makes it visible in Home Assistant instead of only on the physical device
- The cover's opening/closing state is now read directly from the device instead of guessed from position changes over time. The Get Debug Info reply includes a real motor_state field (idle, moving up, or moving down), so there's no more heuristic involved - just a direct read
- Device info now shows the shade's active firmware revision
- **Dropped the getmac dependency**. MAC addresses are now only ever sourced from DHCP discovery info (a DHCP request already carries the sender's MAC, no lookup needed) instead of an ARP lookup after setup. Entries that already have a MAC stored keep showing it; it just won't be refreshed via ARP anymore for entries that got it that way
- Now depends on the [pyowershades](https://pypi.org/project/pyowershades/) PyPI package instead of an inline copy of the protocol code, so this integration and the equivalent Home Assistant core submission share one implementation

### v0.6.0
- Home Assistant now always assumes the state of the shade instead of only when its the UDP master
- Added quality_scale.yaml file
- Added stuff to make this integration sliver quality
  - Improved docs
  - More tests
  - Added entity.py
- Added icons and stuff
- Added a "Reconfigure" option (Settings → Devices & Services → PowerShades → the entry → Configure) to update a shade's IP address after a DHCP change, without deleting and re-adding the entry
- Reconfiguring also backfills the shade's serial number into the entry, so older entries now show a "Serial number" on their device page (purely informational, like the Enphase Envoy integration)
- New devices discovered in the background that match an already-configured legacy entry (by IP) are now hidden from the picker instead of offering a duplicate setup
- **Deprecation notice**: entries created before serial numbers were stored use an older identifier system (based on the entry's IP address, or in some very old entries an internal ID). Use the new "Reconfigure" option once on each such entry to migrate it to the serial-based system - note this will reset that entry's entities, so you may need to rename them and re-add them to dashboards/automations. Support for the old identifier system will be removed in v0.8.0; entries not migrated by then may need to be deleted and re-added

### v0.8.0
- **Breaking change**: removed support for the old IP-based identifier system described in the v0.6.0 deprecation notice. Entries that were never migrated via "Reconfigure" now fail reconfiguration with a "wrong device" error and should be deleted and re-added
- The "Reconfigure" option now rejects submitting the shade's current IP address with a clear error, instead of silently doing nothing
- Added Spanish and French translations
- Integration now meets Home Assistant's Platinum quality scale (full strict typing with mypy)

### v0.7.0
- Added a diagnostics download (Settings → Devices & Services → PowerShades → the entry → Download diagnostics), with the IP, MAC, serial number and unique ID redacted
- If a shade doesn't respond when Home Assistant starts, a repair notification now explains the problem and points at the "Reconfigure" option in case its IP address changed
- Button names and error messages are now translatable
- Integration now meets Home Assistant's Gold quality scale

### v0.4.1
- Status polls no longer time out (and flood the log with errors) on real hardware. Real shade firmware does not echo the request's sequence number on Get Status (0x1D) — it always replies with sequence 1 (verified against both a Wi-Fi and a PoE shade). Matching replies by (op, sequence) made every poll time out while its reply was processed as an unsolicited push, flapping the coordinator between success and failure and logging an error on nearly every 10-second poll cycle. Replies are now matched by opcode alone, which is safe because requests on a connection are serialized. The same mismatch could also make commands report "did not acknowledge" even though the shade executed them.

### v0.4.0 
#### Reliability
- Every command now waits for the device's acknowledgement reply and retries on loss — unacknowledged commands surface as errors in the UI instead of being silently dropped
- Replies are matched by op code and sequence number, so stale replies can't be mistaken for current ones
- All received packets are length- and CRC-validated; corrupt packets are discarded
- Fixed async move feedback being diverted after discovery scans (devices report to the last "UDP master" — each shade's coordinator now re-asserts itself after every broadcast)
#### New features
- Identify button (Diagnostic): wiggles the shade motor so you can tell which shade is which
- Jog Up / Jog Down buttons and services (Configuration): continuous movement for the limit-setting workflow — jog near the position, step to trim, set the limit
- powershades.set_shade_name service: renames the shade on the device itself, verifies by reading the name back, and updates the Home Assistant device name to match
- Device info now shows the real model (PoE Shade / RF Gateway) from the device's serial reply

### v0.3.0 
- Each shade's MAC address is registered as a device connection and shown on the device page in Home Assistant
- MAC sources: DHCP discovery info when the shade is found that way, otherwise an ARP lookup right after the first successful poll (new dependency: getmac)
- With MACs registered, Home Assistant now re-fires discovery when a known shade's DHCP lease changes — the integration updates the stored IP automatically, so shades keep working after DHCP reassigns addresses
  
### 0.2.0
- Rewrote UDP communication on asyncio (no more blocking calls or background threads in the event loop)
- Consolidated state handling into a single DataUpdateCoordinator
- Battery data moved from cover attributes to diagnostic sensor entities
- Config flow now verifies the device responds before creating an entry, and updates the stored IP when re-adding a known shade
- Added translations, proper service error reporting, and HACS metadata

### 0.1.0
- Initial release
- Basic cover and button platform support
- UDP communication implementation
- Config flow integration 
