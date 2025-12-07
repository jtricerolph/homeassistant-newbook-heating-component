# MQTT and Shelly TRV Setup Guide

This guide will help you configure your Shelly TRV (Thermostatic Radiator Valve) devices to work with the Newbook Hotel Management integration via MQTT.

## Prerequisites

- Home Assistant with MQTT broker configured (Mosquitto recommended)
- Shelly TRV devices installed on radiators
- WiFi network accessible to Shelly devices
- Newbook Hotel Management integration installed

## Why MQTT?

The integration uses MQTT for several critical features:

1. **Source Detection**: Detect whether temperature changes come from guests (button press) or automation
2. **Reliability**: MQTT provides better reliability than HTTP polling for sleepy battery-powered devices
3. **Real-time Updates**: Instant notification of temperature changes and battery levels
4. **Lower Latency**: Faster response times for commands

## Part 1: MQTT Broker Setup

### Option A: Mosquitto Broker Add-on (Recommended)

1. Install the Mosquitto broker add-on:
   - Go to **Settings** → **Add-ons** → **Add-on Store**
   - Search for "Mosquitto broker"
   - Click **Install**

2. Configure the broker:
   ```yaml
   logins:
     - username: homeassistant
       password: YOUR_SECURE_PASSWORD_HERE
   customize:
     active: false
     folder: mosquitto
   certfile: fullchain.pem
   keyfile: privkey.pem
   require_certificate: false
   ```

3. Start the add-on and enable "Start on boot"

### Option B: External MQTT Broker

If using an external broker, add the MQTT integration:
- Go to **Settings** → **Devices & Services** → **Add Integration**
- Search for "MQTT"
- Enter your broker details:
  - Broker: `mqtt://YOUR_BROKER_IP:1883`
  - Username and password

## Part 2: Configure Home Assistant MQTT Integration

1. Go to **Settings** → **Devices & Services** → **MQTT**
2. Verify connection status is "Connected"
3. Test by publishing a message:
   - Go to **Developer Tools** → **MQTT**
   - Publish topic: `homeassistant/status`
   - Payload: `online`
   - You should see it in the MQTT log

## Part 3: Configure Shelly TRV Devices

### Naming Convention

**CRITICAL**: The integration relies on a specific naming convention to identify room valves.

#### Format

```
shellies/room-{ROOM_ID}-{LOCATION}-trv
```

#### Examples

- **Room 101 Bedroom TRV**: `shellies/room-101-bedroom-trv`
- **Room 101 Bathroom TRV**: `shellies/room-101-bathroom-trv`
- **Room 205 Bedroom TRV**: `shellies/room-205-bedroom-trv`

#### Naming Rules

1. **Always start with**: `shellies/room-`
2. **Room ID**: Use the exact room ID from Newbook (e.g., `101`, `205`, `301`)
3. **Location**: `bedroom` or `bathroom` (lowercase)
4. **Always end with**: `-trv`

### Step-by-Step Configuration

For **each** Shelly TRV device:

#### 1. Connect to Shelly Device

- Open the Shelly Smart Control app on your phone
- OR access via web browser: `http://[SHELLY-IP]`

#### 2. Enable MQTT

1. Go to **Settings** → **Internet & Security** → **Advanced - Developer Settings**
2. Enable **MQTT**
3. Configure MQTT settings:

```
MQTT Server: homeassistant.local:1883
(or your broker IP: 192.168.1.x:1883)

Username: homeassistant
Password: YOUR_MQTT_PASSWORD

Client ID: (leave default)

MQTT Topic Prefix: shellies/room-{ROOM_ID}-{LOCATION}-trv
Example: shellies/room-101-bedroom-trv
```

4. **Enable** the following:
   - ☑ MQTT Status Update Enabled
   - ☑ Periodic connection
   - ☑ Use MQTT for commands

5. Click **Save**

#### 3. Set Device Name

1. Go to **Settings** → **Device Name**
2. Set a descriptive name (this appears in Home Assistant):
   - Example: `Room 101 Bedroom TRV`
   - Format: `Room {ROOM_ID} {Location} TRV`

#### 4. WiFi Optimization

To improve reliability with weak WiFi:

1. **Go to Settings** → **WiFi**
2. **Reduce sleep time** if battery life permits:
   - Default: 15 minutes
   - Recommended: 10 minutes for better responsiveness
   - Minimum: 5 minutes (trades battery life for speed)

3. **Check WiFi signal strength**:
   - Should be at least -70 dBm
   - Below -80 dBm may cause connectivity issues
   - Consider WiFi extender if signal is poor

#### 5. Reboot Device

After configuration, reboot the Shelly TRV:
- Go to **Settings** → **Reboot Device**
- Wait 2-3 minutes for device to reconnect

## Part 4: Verify Home Assistant Discovery

After configuring your Shelly TRVs, they should auto-discover in Home Assistant:

### 1. Check MQTT Discovery

1. Go to **Developer Tools** → **MQTT**
2. Listen to topic: `homeassistant/#`
3. You should see discovery messages from your Shellys

### 2. Check Devices

1. Go to **Settings** → **Devices & Services** → **MQTT**
2. Click on the MQTT integration
3. You should see your Shelly TRV devices listed
4. Each TRV should create:
   - `climate.room_101_bedroom_trv` (Climate entity)
   - `sensor.room_101_bedroom_trv_battery` (Battery sensor)
   - `sensor.room_101_bedroom_trv_temperature` (Temperature sensor)

### 3. Verify Entity Names

The integration expects entities named:
```
climate.room_{ROOM_ID}_{location}_trv
```

Examples:
- `climate.room_101_bedroom_trv` ✓
- `climate.room_101_bathroom_trv` ✓
- `climate.room_205_bedroom_trv` ✓

If names don't match, you'll need to rename them in Home Assistant or reconfigure the Shelly MQTT topic.

## Part 5: Area Assignment

To organize your devices, assign them to areas:

1. Go to **Settings** → **Areas**
2. Create areas for each room:
   - Name: `Room 101`, `Room 102`, etc.

3. For each TRV device:
   - Go to the device page
   - Click **Add to Area**
   - Select the corresponding room area

The Newbook integration will automatically discover TRVs based on their entity IDs.

## Part 6: Test MQTT Communication

### Test 1: Temperature Command

1. Go to **Developer Tools** → **Services**
2. Call service: `climate.set_temperature`
3. Target: `climate.room_101_bedroom_trv`
4. Temperature: `22`
5. Check if TRV responds (may take 1-5 minutes due to sleep mode)

### Test 2: Source Detection

The integration detects whether temperature changes come from guests or automation:

1. **Physically** press buttons on the TRV to change temperature
2. Check logs: **Settings** → **System** → **Logs**
3. You should see: `"Guest adjusted room_101_bedroom_trv to XX°C (source: button)"`

4. Change temperature via Home Assistant
5. You should see: `"Automation adjusted room_101_bedroom_trv to XX°C (source: mqtt)"`

## Part 7: Troubleshooting

### TRV Not Discovered

**Check MQTT connection:**
```bash
# In Developer Tools → MQTT
# Subscribe to: shellies/room-101-bedroom-trv/#
```

You should see periodic updates. If not:
- Verify MQTT broker is running
- Check Shelly WiFi connection
- Verify MQTT credentials
- Reboot Shelly TRV

### Wrong Entity Names

If entities are named incorrectly:

**Option 1: Rename in Home Assistant**
1. Go to **Settings** → **Entities**
2. Find the TRV entity
3. Click entity → Change entity ID
4. Use format: `climate.room_{ROOM_ID}_{location}_trv`

**Option 2: Reconfigure Shelly MQTT topic**
1. Access Shelly device
2. Go to MQTT settings
3. Correct the topic prefix
4. Reboot device

### TRV Unresponsive

If TRVs don't respond to commands:

1. **Check WiFi signal**:
   - Access Shelly web interface
   - Check signal strength (should be > -70 dBm)
   - Add WiFi extender if needed

2. **Check battery level**:
   - Low battery (< 20%) causes unreliability
   - Recharge batteries

3. **Use retry service**:
   ```yaml
   service: newbook.retry_unresponsive_trvs
   ```

4. **Check TRV health**:
   - Go to Newbook TRV Health dashboard
   - Check response times and retry counts

### Slow Response

TRVs are battery-powered and sleep to conserve power:

- **Normal response time**: 30 seconds to 5 minutes
- **Sleep interval**: 10-15 minutes (configurable)
- **Integration retries**: Automatically retries up to 10 times
- **Patience required**: Don't expect instant responses like AC units

**To improve responsiveness:**
1. Reduce sleep time in Shelly settings (costs battery life)
2. Ensure strong WiFi signal
3. Use fresh batteries
4. Enable the integration's automatic retry system

### Source Detection Not Working

If the integration isn't detecting guest vs automation changes:

1. **Verify MQTT payload includes source**:
   ```bash
   # Subscribe to: shellies/room-101-bedroom-trv/thermostat/0/target_t
   ```

   Payload should include:
   ```json
   {"temp": 22, "source": "button"}
   ```

2. **Update Shelly firmware**:
   - Older firmware may not include source field
   - Update to latest version via Shelly app

## Summary Checklist

Before considering setup complete:

- [ ] MQTT broker installed and running
- [ ] Home Assistant MQTT integration connected
- [ ] All Shelly TRVs configured with correct MQTT topic format
- [ ] Devices appear in Home Assistant with correct entity IDs
- [ ] Entities assigned to appropriate room areas
- [ ] Test command successfully changes TRV temperature
- [ ] Guest adjustment detection working (source=button logged)
- [ ] Battery sensors visible and reporting
- [ ] WiFi signal strength acceptable (> -70 dBm)
- [ ] Newbook integration installed and configured

## Next Steps

Once MQTT setup is complete:

1. **Configure Newbook Integration**:
   - Go to **Settings** → **Integrations** → **Add Integration**
   - Search for "Newbook Hotel Management"
   - Enter your Newbook API credentials

2. **Verify Room Discovery**:
   - Check that integration discovers all rooms
   - Verify TRVs are associated with correct rooms

3. **Configure Room Settings**:
   - Adjust heating/cooling offsets per room
   - Set occupied/vacant temperatures
   - Enable/disable bathroom exclusion

4. **Test Automation**:
   - Create a test booking in Newbook
   - Verify integration updates heating automatically
   - Check TRV health dashboard

## Support

If you encounter issues:

1. **Check Integration Logs**:
   - Settings → System → Logs
   - Filter by "newbook"

2. **Check MQTT Logs**:
   - Developer Tools → MQTT
   - Subscribe to: `shellies/#` to see all Shelly messages

3. **GitHub Issues**:
   - https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues

4. **Common Issues**:
   - Weak WiFi signal: Add extenders
   - Wrong naming: Reconfigure MQTT topic
   - Slow response: Normal for battery devices
   - Unresponsive: Check battery levels and use retry service
