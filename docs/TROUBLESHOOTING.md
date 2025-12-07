# Troubleshooting Guide

Solutions to common issues with the Newbook Hotel Management integration.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Integration Issues](#integration-issues)
- [TRV Communication Issues](#trv-communication-issues)
- [Heating Logic Issues](#heating-logic-issues)
- [MQTT Issues](#mqtt-issues)
- [API Connection Issues](#api-connection-issues)
- [Dashboard Issues](#dashboard-issues)
- [Diagnostic Tools](#diagnostic-tools)

## Installation Issues

### Integration Not Appearing in Add Integration List

**Symptoms**:
- Can't find "Newbook Hotel Management" when adding integration
- Integration doesn't show up in HACS

**Solutions**:

1. **Verify Installation**:
   ```bash
   ls /config/custom_components/newbook/
   ```
   Should show: `__init__.py`, `manifest.json`, etc.

2. **Check manifest.json**:
   ```bash
   cat /config/custom_components/newbook/manifest.json
   ```
   Should be valid JSON

3. **Restart Home Assistant**:
   - Settings → System → Restart
   - Wait 2-3 minutes

4. **Check Logs**:
   - Settings → System → Logs
   - Filter by "newbook"
   - Look for load errors

5. **Verify Home Assistant Version**:
   - Needs 2023.1 or newer
   - Settings → System → About

### Configuration Validation Errors

**Symptoms**:
- "Invalid username/password"
- "API connection failed"
- "Authentication error"

**Solutions**:

1. **Verify Credentials in Newbook**:
   - Log into Newbook admin panel manually
   - Verify username/password work there
   - Check API key in Settings → API Access

2. **Check Region Selection**:
   - AU: https://api-au.newbook.cloud
   - EU: https://api-eu.newbook.cloud
   - US: https://api-us.newbook.cloud
   - NZ: https://api-nz.newbook.cloud

3. **Test API Manually**:
   ```bash
   curl -u username:password -X POST \
     https://api-au.newbook.cloud/sites_list \
     -d "api_key=YOUR_API_KEY"
   ```

4. **Check Firewall**:
   - Ensure Home Assistant can reach Newbook API
   - Test from HA terminal: `ping api-au.newbook.cloud`

5. **API Key Format**:
   - Should be long alphanumeric string
   - No spaces or special characters
   - Copy-paste to avoid typos

## Integration Issues

### No Rooms Discovered

**Symptoms**:
- `sensor.newbook_rooms_discovered` shows `0`
- No room entities created
- Integration shows "Connected" but no data

**Solutions**:

1. **Check Newbook Account**:
   - Log into Newbook
   - Verify rooms exist in Sites/Properties
   - Check room IDs are alphanumeric

2. **Check API Response**:
   - Developer Tools → Services
   - Call: `newbook.refresh_bookings`
   - Check logs for API response

3. **Wait for First Poll**:
   - Initial discovery takes 10-15 minutes
   - Wait for first update_interval
   - Check `sensor.newbook_last_update`

4. **Enable Debug Logging**:
   Add to `configuration.yaml`:
   ```yaml
   logger:
     logs:
       custom_components.newbook: debug
   ```
   Restart and check logs

5. **Check Sites API**:
   Look for `sites_list` API call in logs
   Should show discovered rooms

### Entities Not Updating

**Symptoms**:
- Sensor values not changing
- Booking data stale
- `sensor.newbook_last_update` not updating

**Solutions**:

1. **Check System Status**:
   - `sensor.newbook_system_status` should be "Online"
   - Check `sensor.newbook_last_update` timestamp

2. **Force Refresh**:
   ```yaml
   service: newbook.refresh_bookings
   ```

3. **Check Integration Status**:
   - Settings → Devices & Services
   - "Newbook Hotel Management" should show "Connected"
   - If "Failed to connect", reconfigure

4. **Verify Scan Interval**:
   - Check integration options
   - Default is 10 minutes
   - Adjust if needed

5. **Check API Limits**:
   - Newbook may rate-limit API calls
   - Reduce scan frequency if needed
   - Check logs for 429 errors

### Room State Incorrect

**Symptoms**:
- Room shows wrong state (vacant/occupied/heating_up)
- `sensor.room_XXX_room_state` incorrect
- Heating not starting when expected

**Solutions**:

1. **Check Booking Status**:
   - `sensor.room_XXX_booking_status`
   - Should match Newbook admin panel
   - Statuses: vacant, booked, arrived, departed

2. **Check Timing**:
   - `sensor.room_XXX_heating_start_time`
   - `sensor.room_XXX_arrival_time`
   - Verify offsets: `number.room_XXX_heating_offset_minutes`

3. **Check Auto Mode**:
   - `switch.room_XXX_auto_mode` should be ON
   - If OFF, state won't update automatically

4. **Review State Machine Logic**:
   ```
   VACANT → No booking
   BOOKED → Booking exists, not time to heat yet
   HEATING_UP → Pre-heating before arrival
   OCCUPIED → Guest arrived
   COOLING_DOWN → Guest departed, cooling down
   ```

5. **Check Logs**:
   Look for state transition messages:
   ```
   Room 101: State transition vacant → heating_up
   ```

## TRV Communication Issues

### TRV Not Responding

**Symptoms**:
- TRV health status: "Unresponsive" or "Poor"
- Commands not taking effect
- Temperature not changing

**Solutions**:

1. **Check WiFi Signal**:
   - Access Shelly web: `http://[SHELLY-IP]`
   - Device Info → WiFi signal
   - Should be > -70 dBm
   - Add WiFi extender if < -80 dBm

2. **Check Battery Level**:
   - `sensor.room_XXX_YYY_trv_battery`
   - Should be > 20%
   - Recharge batteries if low

3. **Check MQTT Connection**:
   - Developer Tools → MQTT
   - Subscribe: `shellies/room-XXX-YYY-trv/#`
   - Should see periodic messages

4. **Verify TRV Sleep Settings**:
   - Shelly Settings → WiFi
   - Sleep interval: 10-15 minutes recommended
   - Lower = faster response but shorter battery

5. **Manual Retry**:
   ```yaml
   service: newbook.retry_unresponsive_trvs
   ```

6. **Check TRV Health Dashboard**:
   - View retry counts
   - Check last successful command
   - Review response times

7. **Reboot TRV**:
   - Shelly Settings → Reboot Device
   - Wait 2-3 minutes for reconnection

### TRV Slow to Respond

**Symptoms**:
- Commands take 5+ minutes to apply
- Multiple retries needed
- "Degraded" health status

**Solutions**:

1. **This is Normal**:
   - TRVs are battery-powered and sleep
   - 30s - 5min response is expected
   - Not as fast as AC/wired devices

2. **Reduce Sleep Interval** (trades battery life):
   - Shelly Settings → WiFi → Sleep Time
   - Change from 15min to 10min or 5min
   - Faster response but shorter battery

3. **Improve WiFi**:
   - Check signal strength
   - Add extender or move AP closer
   - Reduce interference

4. **Check Retry Settings**:
   - Integration config → Max Retry Attempts
   - Integration config → Command Timeout
   - Increase if needed

5. **Monitor Health Status**:
   - "Healthy": < 3 attempts (good)
   - "Degraded": 3-4 attempts (acceptable)
   - "Poor": 5-9 attempts (needs attention)
   - "Unresponsive": 10+ attempts (critical)

### Guest Temperature Changes Being Overridden

**Symptoms**:
- Guest adjusts temperature on TRV
- Temperature resets to automation value
- Guest complains heating doesn't respond

**Solutions**:

1. **This Shouldn't Happen During Occupancy**:
   - Integration only sets temps at state transitions
   - Never adjusts during "occupied" state
   - Check room state: `sensor.room_XXX_room_state`

2. **Verify Source Detection**:
   - Check logs for source detection:
   ```
   Guest adjusted room_101_bedroom_trv to 24°C (source: button)
   ```
   - Sources `button` and `WS` = guest (respected)
   - Sources `mqtt` and `http` = automation

3. **Check Shelly Firmware**:
   - Old firmware may not include source field
   - Update to latest via Shelly app
   - Required for proper source detection

4. **Check Valve Sync**:
   - If `switch.room_XXX_sync_setpoints` is ON
   - Guest changes to one valve won't sync to others
   - Automation changes will sync

5. **Verify Not in Transition**:
   - State transitions reset temps:
     - vacant → heating_up (sets occupied temp)
     - occupied → cooling_down (sets vacant temp)
   - This is expected behavior

### Wrong Entity Names

**Symptoms**:
- TRV entities have incorrect names
- Integration can't find TRVs
- `climate.room_XXX_YYY_trv` doesn't exist

**Solutions**:

1. **Check MQTT Topic Format**:
   Must be: `shellies/room-{ROOM_ID}-{LOCATION}-trv`

   Examples:
   - ✓ `shellies/room-101-bedroom-trv`
   - ✓ `shellies/room-205-bathroom-trv`
   - ✗ `shellies/shelly-trv-101` (wrong format)
   - ✗ `shellies/room_101_bedroom_trv` (underscores)

2. **Rename in Home Assistant**:
   - Settings → Entities
   - Find TRV entity
   - Click entity → Change Entity ID
   - Use format: `climate.room_{ROOM_ID}_{location}_trv`

3. **Reconfigure Shelly MQTT**:
   - Access Shelly: `http://[SHELLY-IP]`
   - Settings → MQTT → Topic Prefix
   - Set correct format
   - Reboot Shelly

4. **Check Entity Registry**:
   Developer Tools → States → Filter by "trv"
   Verify all TRV entities exist

## Heating Logic Issues

### Heating Not Starting

**Symptoms**:
- Room has booking but not heating
- `binary_sensor.room_XXX_should_heat` is OFF
- TRVs remain at vacant temperature

**Solutions**:

1. **Check Auto Mode**:
   - `switch.room_XXX_auto_mode` must be ON
   - Turn on if disabled

2. **Check Booking Status**:
   - `sensor.room_XXX_booking_status`
   - Must be valid booking status
   - Check Newbook admin panel

3. **Check Timing**:
   - `sensor.room_XXX_heating_start_time`
   - Must be in past for heating to start
   - Check current time vs heating_start_time

4. **Check Offsets**:
   - `number.room_XXX_heating_offset_minutes`
   - If too small, may not have reached heating_start_time
   - If too large, may be waiting to heat

5. **Check should_heat Sensor**:
   ```
   Developer Tools → States
   binary_sensor.room_101_should_heat
   ```
   Check attributes for why it's OFF

6. **Force Manual Test**:
   ```yaml
   service: newbook.sync_room_valves
   data:
     room_id: "101"
     temperature: 22
   ```

### Heating Starting Too Early/Late

**Symptoms**:
- Room heats hours before arrival
- Room still cold when guest arrives
- Energy wasted on early heating

**Solutions**:

1. **Adjust Heating Offset**:
   ```yaml
   service: number.set_value
   target:
     entity_id: number.room_101_heating_offset_minutes
   data:
     value: 120  # Adjust as needed
   ```

2. **Check Arrival Time Calculation**:
   - Integration uses EARLIER of actual or default arrival
   - If booking has actual time 16:00 but default is 15:00
   - Will heat based on 15:00 (earlier)
   - This is intentional to ensure room is ready

3. **Adjust Default Times**:
   - Integration config → Default Arrival Time
   - Set to match most common check-in time

4. **Monitor and Tune**:
   - Check actual heat-up times
   - Adjust offset based on:
     - Room size
     - Insulation
     - Season
     - Guest feedback

### Heating Not Stopping After Departure

**Symptoms**:
- Room continues heating after checkout
- Energy wasted on departed rooms
- `sensor.room_XXX_room_state` stuck in "occupied"

**Solutions**:

1. **Check Booking Status**:
   - `sensor.room_XXX_booking_status`
   - Should change to "departed" after checkout
   - Check Newbook booking status

2. **Check Cooling Offset**:
   - `number.room_XXX_cooling_offset_minutes`
   - Positive values continue heating after departure
   - Use negative for energy savings

3. **Force Refresh**:
   ```yaml
   service: newbook.refresh_bookings
   ```
   May have missed status update

4. **Check Status Change Detection**:
   Look in logs for:
   ```
   Room 101: Booking status changed from arrived to departed
   ```

5. **Manual Override**:
   ```yaml
   service: newbook.force_room_temperature
   data:
     room_id: "101"
     temperature: 16
   ```

## MQTT Issues

### MQTT Broker Disconnected

**Symptoms**:
- MQTT integration shows "Disconnected"
- TRVs not responding at all
- No MQTT traffic in Developer Tools

**Solutions**:

1. **Check Mosquitto Broker**:
   - Settings → Add-ons → Mosquitto broker
   - Should show "Running"
   - If stopped, click Start

2. **Verify MQTT Config**:
   - Settings → Devices & Services → MQTT
   - Check connection settings
   - Test connection

3. **Check Credentials**:
   ```bash
   mosquitto_sub -h homeassistant.local -p 1883 \
     -u homeassistant -P [password] -t '#'
   ```
   Should connect and show messages

4. **Check Firewall**:
   - Port 1883 must be open
   - Test: `telnet homeassistant.local 1883`

5. **Restart Broker**:
   - Settings → Add-ons → Mosquitto broker → Restart

### Shelly Not Connecting to MQTT

**Symptoms**:
- Shelly shows "MQTT Disconnected"
- No messages on MQTT topic
- TRV not discovered in HA

**Solutions**:

1. **Check Shelly MQTT Settings**:
   - Access: `http://[SHELLY-IP]`
   - Settings → MQTT
   - Verify:
     - ☑ Enable MQTT is checked
     - Server: homeassistant.local:1883
     - Username/password correct

2. **Check Network Connectivity**:
   - Shelly can ping HA server
   - On same network/VLAN
   - No firewall blocking

3. **Test MQTT Subscribe**:
   Developer Tools → MQTT → Subscribe:
   ```
   shellies/room-101-bedroom-trv/#
   ```
   Should see messages every 10-15 minutes

4. **Reboot Shelly**:
   - Settings → Reboot Device
   - Wait 2-3 minutes

5. **Check MQTT Broker Logs**:
   Settings → Add-ons → Mosquitto broker → Logs
   Look for connection attempts from Shelly

## API Connection Issues

### API Timeout Errors

**Symptoms**:
- "Request timeout" errors in logs
- Integration shows "Unavailable"
- `sensor.newbook_system_status` shows "Offline"

**Solutions**:

1. **Check Internet Connection**:
   - Verify HA has internet access
   - Test: `ping api-au.newbook.cloud`

2. **Check Newbook API Status**:
   - https://status.newbook.cloud
   - May be planned maintenance

3. **Increase Timeout**:
   API client has built-in timeout (currently 30s)
   If persistent, may need code adjustment

4. **Reduce Scan Frequency**:
   - Integration config → Scan Interval
   - Increase to 15-30 minutes
   - Reduces load on API

5. **Check DNS Resolution**:
   ```bash
   nslookup api-au.newbook.cloud
   ```
   Should resolve to IP

### Rate Limiting (429 Errors)

**Symptoms**:
- "Too many requests" in logs
- API calls being rejected
- HTTP 429 errors

**Solutions**:

1. **Increase Scan Interval**:
   - Integration config → Scan Interval
   - Set to 15+ minutes
   - Reduces API call frequency

2. **Contact Newbook**:
   - May have API rate limits on account
   - Request limit increase if needed

3. **Check for Multiple Instances**:
   - Ensure only one integration instance
   - Check no old/duplicate configs

4. **Wait and Retry**:
   - Rate limits usually reset after time
   - Wait 15-30 minutes
   - Should resume automatically

## Dashboard Issues

### Dashboards Not Generated

**Symptoms**:
- No dashboards in `/config/dashboards/newbook/`
- Dashboard files missing

**Solutions**:

1. **Check Rooms Discovered**:
   - Dashboards only generate after rooms found
   - `sensor.newbook_rooms_discovered` should be > 0

2. **Check Logs**:
   Look for:
   ```
   Generating dashboards for X discovered rooms
   ```

3. **Manual Trigger**:
   Reload integration:
   - Settings → Devices & Services
   - Newbook → Reload

4. **Check Permissions**:
   Verify HA can write to `/config/dashboards/` directory

5. **Check YAML Files**:
   ```bash
   ls /config/dashboards/newbook/
   ```
   Should show:
   - home_overview.yaml
   - battery_monitoring.yaml
   - trv_health.yaml
   - room_*.yaml (one per room)

### Dashboard Cards Not Showing

**Symptoms**:
- Dashboard loads but cards empty
- "Entity not found" errors
- Mushroom cards not working

**Solutions**:

1. **Install Mushroom Cards**:
   - Required for custom dashboard layouts
   - HACS → Frontend → Search "Mushroom"
   - Install and restart

2. **Check Entity IDs**:
   - Dashboard references specific entities
   - Verify entities exist in HA
   - Developer Tools → States

3. **Install Auto-Entities**:
   - HACS → Frontend → "Auto-entities"
   - Required for battery/health dashboards

4. **Clear Browser Cache**:
   - Ctrl+F5 to force refresh
   - Clear cache in browser settings

## Diagnostic Tools

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.newbook: debug
    custom_components.newbook.api: debug
    custom_components.newbook.coordinator: debug
    custom_components.newbook.heating_controller: debug
    custom_components.newbook.trv_monitor: debug
```

Restart Home Assistant

### Check Entity States

Developer Tools → States → Filter by:
- `sensor.room_` - Room sensors
- `binary_sensor.room_` - Room binary sensors
- `number.room_` - Room settings
- `switch.room_` - Room switches
- `climate.room_` - TRV devices
- `sensor.newbook_` - System sensors

### Test Services

Developer Tools → Services:

```yaml
# Test booking refresh
service: newbook.refresh_bookings

# Test TRV retry
service: newbook.retry_unresponsive_trvs

# Test room temperature
service: newbook.sync_room_valves
data:
  room_id: "101"
  temperature: 22
```

### Monitor MQTT Traffic

Developer Tools → MQTT:

```
# All Shelly messages
Subscribe: shellies/#

# Specific TRV
Subscribe: shellies/room-101-bedroom-trv/#

# All TRV status
Subscribe: shellies/room-+/+/trv/online

# Publish test (don't do this often)
Publish: shellies/room-101-bedroom-trv/thermostat/0/command/target_t
Payload: 22
```

### Check Integration Health

Monitor these sensors:
- `sensor.newbook_system_status` - Should be "Online"
- `sensor.newbook_last_update` - Should be recent
- `sensor.newbook_rooms_discovered` - Should match actual rooms
- `sensor.newbook_active_bookings` - Should match Newbook

### Export Logs

To share logs for support:

1. Settings → System → Logs
2. Filter by "newbook"
3. Copy relevant section
4. Remove any sensitive data (API keys, passwords)
5. Post to GitHub issue

## Getting Further Help

If issues persist:

1. **Check Documentation**:
   - [Installation Guide](INSTALLATION.md)
   - [Configuration Guide](CONFIGURATION.md)
   - [API Reference](API_REFERENCE.md)

2. **GitHub Issues**:
   - https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues
   - Search existing issues first
   - Include:
     - Home Assistant version
     - Integration version
     - Relevant logs (with sensitive data removed)
     - Steps to reproduce

3. **Enable Debug Logging**:
   - Capture detailed logs
   - Include in issue report

4. **System Information**:
   - Settings → System → About
   - Include HA version, OS version
