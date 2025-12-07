# Newbook Hotel Management Integration for Home Assistant

A comprehensive Home Assistant custom integration for automating hotel heating control based on Newbook PMS (Property Management System) bookings. Automatically manages Shelly TRV (Thermostatic Radiator Valve) devices to pre-heat rooms before guest arrivals and reduce heating after departures.

[![GitHub Release](https://img.shields.io/github/v/release/jtricerolph/homeassistant-newbook-heating-component)](https://github.com/jtricerolph/homeassistant-newbook-heating-component/releases)
[![License](https://img.shields.io/github/license/jtricerolph/homeassistant-newbook-heating-component)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

## 🌟 Features

### Core Functionality
- **Automatic Room Discovery**: Dynamically discovers hotel rooms from Newbook API `sites_list`
- **Smart Heating Schedules**: Pre-heats rooms before guest arrivals, reduces heating after departures
- **Guest Temperature Respect**: Detects and respects guest temperature adjustments during their stay
- **Walk-in Support**: Handles bookings that appear directly with 'arrived' status
- **Negative Offsets**: Supports stopping heating before checkout time
- **State Machine Logic**: Manages room states (vacant → booked → heating_up → occupied → cooling_down)

### TRV Management
- **Shelly TRV Support**: Native MQTT integration with Shelly TRV devices
- **Source Detection**: Distinguishes guest adjustments (button/app) from automation (MQTT)
- **Health Monitoring**: Tracks TRV responsiveness with 4 health states
- **Smart Retry System**: Exponential backoff retry (30s to 30min) for unreliable devices
- **Battery Monitoring**: Tracks battery levels with configurable alerts
- **Valve Synchronization**: Optional room-level temperature sync with bathroom exclusion

### Per-Room Configuration
- **Auto Mode**: Enable/disable automation per room
- **Temperature Settings**: Configurable occupied/vacant temperatures
- **Heating/Cooling Offsets**: Customize pre-heat and cooling timings
- **Bathroom Independence**: Option to exclude bathroom valves from sync
- **Manual Override**: Force specific temperatures when needed

### Integration Entities (17 per room)
**Sensors (11)**:
- Booking status, guest name, arrival/departure times
- Current night / total nights
- Heating/cooling start times
- Booking reference, pax count, room state

**Binary Sensors (1)**:
- Should heat indicator

**Numbers (4)**:
- Heating offset (minutes before arrival)
- Cooling offset (minutes after departure, can be negative)
- Occupied temperature
- Vacant temperature

**Switches (3)**:
- Auto mode on/off
- Sync all valves in room
- Exclude bathroom from sync

### Services
- `newbook.refresh_bookings` - Manually refresh booking data
- `newbook.set_room_auto_mode` - Enable/disable auto mode for a room
- `newbook.force_room_temperature` - Force specific temperature (disables auto)
- `newbook.sync_room_valves` - Manually sync all valves in a room
- `newbook.retry_unresponsive_trvs` - Retry failed TRVs

### Auto-Generated Dashboards
- **Home Overview**: Grid of all rooms with heating status
- **Per-Room Detail**: Booking info, TRV controls, settings per room
- **Battery Monitoring**: All TRV batteries with threshold alerts
- **TRV Health**: Health status tracking for all devices

## 📋 Requirements

- Home Assistant 2023.1 or newer
- Newbook PMS account with API access
- MQTT broker (Mosquitto recommended)
- Shelly TRV devices with MQTT configured
- WiFi network with good coverage

## 🚀 Quick Start

### 1. Install via HACS (Recommended)

1. Add this repository as a custom repository in HACS:
   - Go to **HACS** → **Integrations** → **⋮** (menu) → **Custom repositories**
   - Repository: `https://github.com/jtricerolph/homeassistant-newbook-heating-component`
   - Category: **Integration**
   - Click **Add**

2. Install the integration:
   - Search for "Newbook Hotel Management"
   - Click **Download**
   - Restart Home Assistant

### 2. Manual Installation

1. Download the latest release
2. Extract to `custom_components/newbook/`
3. Restart Home Assistant

### 3. Configure Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Newbook Hotel Management"
3. Follow the 5-step configuration wizard:
   - **Step 1**: Newbook API credentials
   - **Step 2**: Polling settings
   - **Step 3**: Default room temperatures and offsets
   - **Step 4**: TRV monitoring settings
   - **Step 5**: Valve sync defaults

### 4. Configure Shelly TRVs

Follow the [MQTT Setup Guide](docs/MQTT_SETUP.md) to configure your Shelly TRV devices with the correct naming convention:

```
shellies/room-{ROOM_ID}-{LOCATION}-trv
```

Examples:
- `shellies/room-101-bedroom-trv`
- `shellies/room-101-bathroom-trv`
- `shellies/room-205-bedroom-trv`

See [Shelly Quick Reference](docs/SHELLY_QUICK_REFERENCE.md) for configuration templates.

## 📖 Documentation

- **[Installation Guide](docs/INSTALLATION.md)** - Detailed installation instructions
- **[Configuration Guide](docs/CONFIGURATION.md)** - All settings explained
- **[Heating Logic](docs/HEATING_LOGIC.md)** - How heating automation works
- **[MQTT Setup](docs/MQTT_SETUP.md)** - Complete MQTT and Shelly TRV setup
- **[Shelly Quick Reference](docs/SHELLY_QUICK_REFERENCE.md)** - Quick configuration guide
- **[Privacy & Data Retention](docs/PRIVACY.md)** - Guest data privacy configuration
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[API Reference](docs/API_REFERENCE.md)** - Services, entities, and events

## 🎯 How It Works

### State Machine

The integration manages each room through a state machine:

```
VACANT (16°C)
  ↓
BOOKED (16°C)
  ↓
HEATING_UP (22°C) ← Starts 2 hours before arrival
  ↓
OCCUPIED (22°C) ← Guest arrived
  ↓
COOLING_DOWN (16°C) ← Guest departed
  ↓
VACANT (16°C)
```

### Smart Scheduling

- Uses **earlier** of actual or default arrival time
- Uses **later** of actual or default departure time
- Supports **negative cooling offsets** (e.g., -30 = stop heating 30 min before checkout)
- Detects **walk-in bookings** and immediately starts heating

### Guest Temperature Respect

The integration only sets temperatures at **state transitions**, never during occupied state. This ensures guest temperature adjustments are respected throughout their stay.

**Source Detection** via MQTT:
- `button` or `WS` → Guest adjustment → Respected
- `mqtt` or `http` → Automation → May sync to other valves

## 🛠️ Configuration Examples

### Standard Hotel Room
```yaml
Room 101:
  - climate.room_101_bedroom_trv
  - climate.room_101_bathroom_trv

Settings:
  - Auto mode: ON
  - Sync setpoints: ON
  - Exclude bathroom: ON
  - Occupied temp: 22°C
  - Vacant temp: 16°C
  - Heating offset: 120 minutes
  - Cooling offset: -30 minutes
```

### Suite with 2 Bedrooms
```yaml
Room 301:
  - climate.room_301_bedroom1_trv
  - climate.room_301_bedroom2_trv
  - climate.room_301_bathroom_trv

Settings:
  - Sync setpoints: ON (both bedrooms heat together)
  - Exclude bathroom: ON (bathroom independent)
```

## 📊 Dashboard Examples

### Home Overview
Grid of all rooms showing:
- Room number and guest name
- Heating status (red=heating, blue=idle)
- Auto/manual mode badge
- Click to view room details

### Room Detail
Complete control for each room:
- Booking information
- Heating schedule
- Individual TRV controls
- Temperature settings
- Manual override buttons

## ⚠️ Important Notes

### TRV Response Times
Shelly TRVs are battery-powered and sleep to conserve power:
- **Normal response**: 30 seconds to 5 minutes
- **Sleep interval**: 10-15 minutes
- **Don't expect instant responses** like AC units

The integration automatically retries with exponential backoff for up to 30 minutes.

### WiFi Signal Requirements
- **Good signal**: -60 to -70 dBm
- **Minimum**: -70 dBm
- **Below -80 dBm**: Add WiFi extender

Check signal in Shelly web interface → Device Info

### Battery Life
- **Excellent**: 80-100%
- **Good**: 50-80%
- **Low**: 20-50% (plan replacement)
- **Critical**: Below 20% (replace immediately)

## 🐛 Troubleshooting

### TRV Not Responding
1. Check WiFi signal strength (> -70 dBm)
2. Check battery level (> 20%)
3. Verify MQTT topic format
4. Use `newbook.retry_unresponsive_trvs` service

### Wrong Entity Names
Entities must follow format: `climate.room_{ROOM_ID}_{location}_trv`

Fix by:
1. Renaming entity in Home Assistant, OR
2. Reconfiguring MQTT topic in Shelly device

### Integration Not Updating
1. Check Newbook API credentials
2. Verify API region is correct
3. Check Home Assistant logs for errors
4. Use `newbook.refresh_bookings` service

See [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for more solutions.

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for use with [Newbook PMS](https://www.newbook.cloud/)
- Designed for [Shelly TRV](https://www.shelly.com/en/products/shop/shelly-trv) devices
- Powered by [Home Assistant](https://www.home-assistant.io/)

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues)
- **Documentation**: [docs/](docs/)
- **Newbook Support**: https://www.newbook.cloud/support
- **Shelly Support**: https://www.shelly.com/en/support

## 📈 Roadmap

Future enhancements under consideration:
- [ ] Additional PMS integrations (Opera, Mews, etc.)
- [ ] Support for other TRV brands (Zigbee, Z-Wave)
- [ ] Energy usage tracking
- [ ] Advanced scheduling rules
- [ ] Multi-property management

---

**Made with ❤️ for the hospitality industry**
