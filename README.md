# Newbook Hotel Management Integration for Home Assistant

A comprehensive Home Assistant custom integration for managing hotel room heating automation based on Newbook booking system data.

## Features

- **Dynamic Room Discovery**: Automatically discovers all rooms from Newbook API
- **Smart Heating Control**: Intelligent heating automation based on booking status
- **Guest Temperature Respect**: Detects and respects guest temperature adjustments
- **TRV Reliability Monitoring**: Advanced retry logic and health monitoring for Shelly TRV valves
- **Battery Monitoring**: Track TRV battery levels with configurable alerts
- **Individual Valve Control**: Per-valve control with optional room-level synchronization
- **Auto-Generated Dashboards**: Creates home overview, per-room, battery, and TRV health dashboards

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add `https://github.com/jtricerolph/homeassistant-newbook-heating-component` as an Integration
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/newbook` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "Newbook Hotel Management" and follow the configuration steps

## Configuration

The integration uses a multi-step configuration flow:

### Step 1: API Credentials
- **Username**: Your Newbook username
- **Password**: Your Newbook password
- **API Key**: Your Newbook API key
- **Region**: Select your region (AU, EU, US, NZ)

### Step 2: Polling Settings
- **Refresh Interval**: How often to check for booking updates (default: 10 minutes)

### Step 3: Default Room Settings
- **Default Arrival Time**: Standard check-in time (default: 15:00)
- **Default Departure Time**: Standard checkout time (default: 10:00)
- **Heating Offset**: Minutes before arrival to start heating (default: 120)
- **Cooling Offset**: Minutes after departure to stop heating (default: -30, can be negative)
- **Occupied Temperature**: Target temperature when occupied (default: 22°C)
- **Vacant Temperature**: Target temperature when vacant (default: 16°C)

### Step 4: TRV Monitoring
- **Max Retry Attempts**: Maximum retries for unresponsive TRVs (default: 10)
- **Command Timeout**: Seconds to wait for TRV response (default: 60)
- **Battery Warning Threshold**: Battery level for warnings (default: 30%)
- **Battery Critical Threshold**: Battery level for critical alerts (default: 15%)

### Step 5: Valve Sync
- **Sync Room Setpoints**: Enable room-level valve synchronization by default
- **Exclude Bathroom from Sync**: Keep bathroom valves independent by default

## Room States

The integration manages five room states:

1. **Vacant**: No booking, heating at minimum
2. **Booked**: Booking exists but not yet time to heat
3. **Heating Up**: Pre-heating before guest arrival
4. **Occupied**: Guest has arrived, maintains comfort temperature
5. **Cooling Down**: After departure, reducing to minimum

## Entities Created Per Room

### Sensors (Read-only)
- `sensor.room_XXX_booking_status` - Current room state
- `sensor.room_XXX_guest_name` - Guest name or "Vacant"
- `sensor.room_XXX_arrival` - Check-in datetime
- `sensor.room_XXX_departure` - Check-out datetime
- `sensor.room_XXX_current_night` - Current night of stay
- `sensor.room_XXX_total_nights` - Total stay length
- `sensor.room_XXX_heating_start_time` - When heating starts
- `sensor.room_XXX_cooling_start_time` - When heating stops

### Binary Sensors
- `binary_sensor.room_XXX_should_heat` - Whether heating should be active

### Number Settings (Configurable)
- `number.room_XXX_heating_offset_minutes` - Pre-arrival heating time
- `number.room_XXX_cooling_offset_minutes` - Post-departure cool time
- `number.room_XXX_occupied_temperature` - Occupied setpoint
- `number.room_XXX_vacant_temperature` - Vacant setpoint

### Switches
- `switch.room_XXX_auto_mode` - Enable/disable automatic heating
- `switch.room_XXX_sync_setpoints` - Enable room-level valve sync
- `switch.room_XXX_exclude_bathroom_from_sync` - Exclude bathroom valves

### TRV Monitoring (Per valve)
- `sensor.room_XXX_YYY_trv_health` - Health status (healthy/degraded/poor/unresponsive)
- `sensor.room_XXX_YYY_trv_battery` - Battery percentage
- `binary_sensor.room_XXX_YYY_trv_responsive` - Whether responding
- `binary_sensor.room_XXX_YYY_trv_battery_warning` - Battery warning
- `binary_sensor.room_XXX_YYY_trv_battery_critical` - Battery critical

## Services

### `newbook.refresh_bookings`
Manually refresh booking data from Newbook API.

### `newbook.set_room_auto_mode`
Enable or disable automatic heating for a room.
- `room_id`: Room number (e.g., "101")
- `enabled`: true/false

### `newbook.force_room_temperature`
Override and set room temperature (disables auto mode).
- `room_id`: Room number
- `temperature`: Target temperature

### `newbook.sync_room_valves`
Manually sync all valves in a room to the same temperature.
- `room_id`: Room number
- `temperature`: Target temperature

### `newbook.retry_unresponsive_trvs`
Retry sending commands to all unresponsive TRVs.

## Shelly TRV Setup

### MQTT Configuration

Configure your Shelly TRVs with MQTT using this naming convention:
- Topic pattern: `shellies/room-{ROOM_ID}-{LOCATION}-trv`
- Examples:
  - `shellies/room-101-bedroom-trv`
  - `shellies/room-101-bathroom-trv`

Home Assistant will auto-discover these as:
- `climate.room_101_bedroom_trv`
- `climate.room_101_bathroom_trv`

Valves will be automatically assigned to areas (e.g., "Room 101").

## How It Works

### Heating Logic

1. **Booking Detection**: Integration polls Newbook API for active bookings
2. **State Determination**: Determines room state based on booking status and timing
3. **Temperature Calculation**: Calculates when to start/stop heating based on arrival/departure times and offsets
4. **Smart Timing**: Uses earlier of actual or default arrival time, later of actual or default departure time
5. **Status Override**: Real-time booking status changes (arrived/departed) trigger immediate temperature adjustments
6. **Guest Respect**: Detects guest temperature changes via MQTT and doesn't override them during occupancy
7. **TRV Reliability**: Retries failed commands with exponential backoff, monitors health

### Walk-in Handling

If a booking appears with status "arrived" (walk-in, no pre-heating time):
- Integration immediately sets room to heating
- Doesn't wait for scheduled heating_start_time
- Ensures room is comfortable as quickly as possible

### Valve Synchronization

- When `sync_setpoints` is enabled, all valves in a room update together
- `exclude_bathroom_from_sync` keeps bathroom independent (useful for towel drying)
- Guest adjustments are never synced (detected via MQTT source)
- Only automation-initiated changes sync across valves

## Dashboards

The integration auto-generates four dashboards:

1. **Home Overview**: Grid of all rooms with status indicators
2. **Per-Room Detail**: Booking info, individual valves, settings
3. **Battery Status**: All TRV batteries, sortable and filterable
4. **TRV Health**: Health monitoring, response times, retry counts

## Troubleshooting

### TRVs Not Responding

- Check WiFi signal strength in problem areas
- Verify MQTT broker is running and Shellys are connected
- Check TRV battery levels
- Review TRV health dashboard for retry counts
- Use `newbook.retry_unresponsive_trvs` service

### Heating Not Starting

- Verify room has an active booking in Newbook
- Check `binary_sensor.room_XXX_should_heat` state
- Verify `switch.room_XXX_auto_mode` is ON
- Check heating_start_time calculation
- Review integration logs for errors

### Guest Temperature Changes Being Overridden

- This shouldn't happen during occupied state
- Check that MQTT source detection is working
- Review logs for setpoint change sources
- Verify heating controller only sets temps at state transitions

## Development Status

**Current Version**: 0.1.0 (Beta)

### Completed (Phase 1)
- ✅ Core integration structure
- ✅ Newbook API client
- ✅ Configuration flow
- ✅ Data coordinator

### In Progress (Phase 2)
- 🔄 Room discovery and entity creation
- ⏳ Sensor platforms
- ⏳ Number platforms
- ⏳ Switch platforms
- ⏳ Binary sensor platforms

### Planned
- Phase 3: Booking data processing
- Phase 4: TRV monitoring system
- Phase 5: Heating controller with state machine
- Phase 6: Valve sync system
- Phase 7: MQTT and Shelly documentation
- Phase 8: Dashboard generation
- Phase 9: Testing
- Phase 10: Full documentation

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.

## License

This project is licensed under the MIT License.

## Support

- **Issues**: https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues
- **Documentation**: https://github.com/jtricerolph/homeassistant-newbook-heating-component

## Credits

Developed by JTR for hotel room heating automation using Newbook booking system and Shelly TRV valves.
