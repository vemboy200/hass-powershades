# PowerShades Home Assistant Integration

A Home Assistant custom integration for controlling PowerShades motorized blinds via UDP communication.
This fork will be mainted by @vemboy200 with the help of AI
## Features

- **Cover Platform**: Control blinds as Home Assistant covers (open, close, set position)
- **Button Platform**: Additional buttons for specific blind operations
- **UDP Communication**: Direct UDP communication with PowerShades controllers
- **Config Flow**: Easy setup through Home Assistant's UI
- **Local Control**: No cloud dependencies, works entirely locally

## Installation

### HACS Installation

This integration can be installed via HACS as a custom repository:

1. In HACS, go to **Settings** → **Repositories**
2. Click the **+** button to add a new repository
3. Enter the repository URL: `https://github.com/vemboy200/hass-powershades`
4. Select **Integration** as the category
5. Click **Add**
6. Once added, search for "PowerShades" in HACS
7. Click **Download**
8. Restart Home Assistant

### Manual Installation

1. Download this repository (clone or download ZIP)
2. Copy the `custom_components/powershades` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "PowerShades"
4. Enter your PowerShades controller's IP address and port
4.5. Auto-discovery is broken so just manually enter the ip adress of you powershade(s) ill add a tutorial on how to get it when im not lazy
5. Configure your blinds

## Usage

### Cover Controls

Once configured, your PowerShades will appear as covers in Home Assistant. You can:

- **Open**: Fully open the blinds
- **Close**: Fully close the blinds  
- **Set Position**: Set blinds to a specific percentage (0-100)
- **Stop**: Stop blinds in their current position

### Button Controls

Additional buttons provide quick access to common operations:

- **Preset Positions**: Quick access to favorite positions
- **Group Operations**: Control multiple blinds simultaneously

## Requirements

- Home Assistant 2023.8.0 or newer
- PowerShades controller with UDP communication enabled

## Supported Devices

This integration supports PowerShades controllers that communicate via UDP protocol.

## Troubleshooting

### HACS Installation Issues

If you encounter errors when installing via HACS:

1. **Version Error**: Ensure the repository has a proper release tag
2. **Repository Not Found**: Verify the repository URL is correct and the repository is public
3. **Download Failed**: Try refreshing HACS and clearing the cache

### Debug Logging
Click this button in the integration menu top enable debuging log

<img width="378" height="244" alt="Screenshot 2026-05-28 at 4 40 56 PM" src="https://github.com/user-attachments/assets/443bae92-4350-4ef5-bb4f-e13d6ad17e52" />


### Contributing

1. Fork this repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request with detail about what your fork does

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- PowerShades for their UDP protocol documentation
- Home Assistant community for the integration framework

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/vemboy200/hass-powershades/issues) page.

Plans:
- Fix the issues i listed in the issues page
- add a quality scale.yaml file and bring this integration to bronze quality
- merge with home assistant core and make this a core integration



