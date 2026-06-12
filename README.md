# PowerShades Home Assistant Integration

The Home Assistant Powershades integration allows to control your power over ethernet (PoE) [Powershades](https://powershades.com) shades. This integration is only tested with PoE Powershades, so support with the RF hub may be limited or nonexistent.

If you have RF shades it is recommended you buy a [Bond Bridge](https://bondhome.io/) and connect your RF shades using that, then connect it to Home Assistant using the [built in integration](https://www.home-assistant.io/integrations/bond/). If you already have Powershade's RF Hub, please open an issue and report what the results are trying to connect the hub to Home Assistant using this integration.

## How you can use this integration
This intgeration can be used to control your Powershades shades, you can have it open in the morning to get you out of the bed, or close them at sunset for extra privacy. 
 
PoE Powershades do not come with a remote, so controlling them without a smart device is difficult. To fix this you can use a smart button (such as a Zigbee or Z-Wave button) with an automation to control your shade. This may be convient to you or others, including guests controlling your shades without having to open a smart device.

 ## Prerequisites

Before setting up this integration make sure you can get the IP address of your powershade.

It is unknown (at least to me) if UDP communication is on by default, however the integration communicates to the blinds using UDP. If UDP is not enabled on your shade, you have to figure out how to enable it yourself. If you have figured out how to enable UDP, please open an issue and explain how you enabled UDP.

Once you have aquired the IP address of your shade, select manual entry, and put it in. Then Home Assistant will attempt to connect to the shade on port 42.

### How to get the IP Address of your shade

- Via the PowerShades App (Recommended): Open the official PowerShades mobile app, navigate to your desired shade, select Enable Configuration, and confirm the prompt. Scroll down to view the assigned IP address.

- Via Your Router's DHCP Client List: Log into your network router's administration panel and check the connected devices list. Look for a device manufactured by "Wideband Labs LLC" this may be your PowerShades device.


## Installation

### HACS Installation (recommended)

This integration can be installed via HACS as a custom repository:

- In HACS, go to **Settings** → **Repositories**
- Click the **+** button to add a new repository
- Enter the repository URL: `https://github.com/vemboy200/hass-powershades`
- Select **Integration** as the category
- Click **Add**
- Once added, search for "PowerShades" in HACS
- Click **Download**
- Restart Home Assistant

### Manual Installation (not recommended)

- Download this repository (clone or download ZIP)
- Copy the `custom_components/powershades` folder to your Home Assistant `config/custom_components/` directory
- Restart Home Assistant

## Supported Devices
Any PoE Powershade shade with UDP communication enabled on the same local network as Home Assistant

⚠️ Note: The RF Powershades bridge is currently untested and may be unsupported. For RF Powershades, please use a [Bond Bridge](https://bondhome.io/).

## Supported functionality 

### Cover entity (listed as controls)
A cover entity allows you to control the shade, with the following commands being supported.
  - Open cover
  - Stop Cover
  - Close Cover
  - Set cover position (Target percentage)
The Shade will instantly report to home Assistant that a command has been executed successfully, however the real % of the shade being opened is either broadcasted or polled every 10 seconds (more info in the Data Updates section)

### Button entites (listed as Configuration)
 - Clear Limits: Removes the predefined open and close limits of your shade
 - Set Lower Limit: Changes the place where the shade is considered "closed" to where it is now
 - Set Upper Limit: Changes the place where the shade is considered "Open" to where it is now
 - Step Up/Down: Moves the shade slightly up or down
 - Toggle Shade: Makes the shade move from Open to closed and from closed to fully open (requires two clicks [Issue #3](https://github.com/vemboy200/hass-powershades/issues/3))

### Battery Entity (not out yet will be listed as Diagnostic)
 - Tell you the Battery % of your shade
 - Has an Attribute saying its millivolatge

## Data Updates
While the UDP protocol allows for push updates it only happens when Home Assistant controls the device. When an external source (ex: Powershades App or Control4) controls the device, the only way to get the device's status is by polling. So Home Assistant polls the shade every 10 seconds.

All communication is local and the data does not leave your house, which is kind of weird considering that in the offical Powershades app, all data goes through their cloud. The device will work without an internet connection in the short term. It is unknown how the device will behave without an internet connection long term.

## Known limations 
Other than the [issues](https://github.com/vemboy200/hass-powershades/issues) listed on this repo, there are many limiations with the UDP communication
 - As mentioned before, push data are only sent to the device that activated the shade, so if an external source activates the shade polling is the only way to get the shade's data.
 - This will cause a problem with other hubs using the UDP communication (ex: Control4) that rely soley on the push data, to have the wrong state of the shade.
 - Push data is sent every 10 seconds so updates are not instant
 - The shade must be on the same network subnet as Home Assistant, or UDP broadcast traffic must be routed between subnets.
 - Only PoE Shades are fully supported, so it is recommened that you connect your RF Powershades to Home Assistant using a [Bond Bridge](https://bondhome.io/), and report what went wrong when adding your Powershades RF bridge.
 - Theres probably more that I forgot to mention, if you found a known limiation please post an issue on this repo about it

## Troubleshooting 
### I got an error about it not being able to connect
- This means that Home Assistant could not communicate to the shade, make sure home assistant can access port 42 on your shade, and that UDP broadcasts can be routed between different subnets if needed.
- You entered a wrong IP address or you entered an IP address that was already in use by a config entry
### Cover entity shows as unavailable 
- This means that Home Assistant could not communicate to the shade, make sure home assistant can access port 42 on your shade, and that UDP broadcasts can be routed between different subnets if needed.
- It could also mean that your shade is not connected to your local network
### Cover entity shows as unknown
- If you're getting unknown despite having a valid IP address, please open an issue with your debug log if possible
### Cover shows its still opening or closing despite it not moving
- [Issue #2](https://github.com/vemboy200/hass-powershades/issues/2)

## Debug Logging
Click this button in the integration menu in the top right enable debuging log

<img width="378" height="244" alt="Screenshot 2026-05-28 at 4 40 56 PM" src="https://github.com/user-attachments/assets/443bae92-4350-4ef5-bb4f-e13d6ad17e52" />

If you're confused by what I just showed you
- Navigate to Settings → Devices & Services and select the PowerShades integration.
- Click the three dots menu in the top right and select Enable debug logging.
  
Then trigger the error, and download the logs from Settings > System > Logs > Download logs
If you stop the debuging log from the Home Assistant Companion App it should automatically download

## Report Issues you find with the integration
-  Get the debug log and screenshot/screen recording of what caused the error (if applicable)
-  Raise your Issue [here](https://github.com/vemboy200/hass-powershades/issues)
-  Describe the issue
-  Put the debug log or screenshot/recording if necessary

## Automation Examples
Here are some automations I use with this integration
Heres one I use to open my shade in the morning
```yaml
 alias: wake up
description: ""
triggers:
  - trigger: time
    at: "07:00:00"
    weekday:
      - mon
      - tue
      - thu
      - wed
      - fri
    id: Shade
  - trigger: time
    at: "08:00:00"
    weekday:
      - sun
      - sat
    id: Shade
  - trigger: time
    at: "06:30:00"
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
    id: Lights
  - trigger: time
    at: "07:30:00"
    id: Lights
    weekday:
      - sun
      - sat
conditions:
  - condition: state
    entity_id: cover.bedroom_shade
    state:
      - closed
    enabled: false
actions:
  - choose:
      - conditions:
          - condition: trigger
            id:
              - Lights
        sequence:
          - action: light.turn_on
            metadata: {}
            target:
              entity_id: light.reccesed
            data:
              brightness_pct: 20
          - action: light.turn_on
            metadata: {}
            target:
              entity_id: light.reccesed
            data:
              brightness_pct: 50
              transition: 1800
      - conditions:
          - condition: trigger
            id:
              - Shade
        sequence:
          - action: cover.open_cover
            metadata: {}
            target:
              entity_id: cover.bedroom_shade
            data: {}
          - action: light.turn_on
            metadata: {}
            target:
              entity_id: light.reccesed
            data:
              brightness_pct: 0
              transition: 15
mode: single 
```
And close close them when it gets dark
```yaml
alias: Close shades
description: ""
triggers:
  - trigger: state
    entity_id:
      - sensor.sun_next_dusk
conditions:
  - condition: state
    entity_id: binary_sensor.bedroom_window
    state:
      - "off"
      - unavailable
      - unknown
  - condition: state
    entity_id: cover.bedroom_shade
    state:
      - open
actions:
  - action: cover.close_cover
    metadata: {}
    target:
      entity_id:
        - cover.bedroom_shade
    data: {}
mode: single

```
## Removing this integration

Removing this integration is the same compared to most hacs integrations

- Go to Settings > Devices & services and select the integration card.
- From the list of devices, select the Powershades integration.
- Next to the entry, select the three dots menu. Then, select Delete.
 
- If installed through HACS go to it select the three dots menu for this integration. Then, select Remove.

- If you did a manual installation, open your file editor
- Go to thecustom components folder
- Delete the powershades folder

- Then restart Home Assistant to clear the cache

## Contributing

- Fork this repository
- Create a feature branch
- Make your changes
- Test thoroughly
- Submit a pull request with detail about what your fork does

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- PowerShades for their UDP protocol documentation
- Home Assistant community for the integration framework
- [@dstocking](https://github.com/dstocking) for making the original repo of this integration that I forked from

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/vemboy200/hass-powershades/issues) page.

This integration is maintained by [@vemboy200](https://github.com/vemboy200) with the support of AI

## Plans
- Fix the issues I listed in the issues page
- Add a quality scale.yaml file and bring this integration to bronze quality
- Merge with home assistant core and make this a core integration
