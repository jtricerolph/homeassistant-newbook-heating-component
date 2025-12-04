# Installation Guide

Complete installation instructions for the Newbook Hotel Management integration.

## Prerequisites

Before installing, ensure you have:

- ✅ Home Assistant 2023.1 or newer
- ✅ MQTT broker installed and configured (Mosquitto recommended)
- ✅ Newbook PMS account with API access
- ✅ Newbook API credentials (username, password, API key)
- ✅ At least one Shelly TRV device
- ✅ WiFi network with good coverage in all rooms

## Installation Methods

### Method 1: HACS (Recommended)

HACS (Home Assistant Community Store) makes installation and updates easy.

#### Step 1: Add Custom Repository

1. Open **HACS** in Home Assistant
2. Click **Integrations**
3. Click the **⋮** (three dots) in the top right corner
4. Select **Custom repositories**
5. Enter the repository details:
   - **Repository**: `https://github.com/jtricerolph/homeassistant-newbook-heating-component`
   - **Category**: Select **Integration**
6. Click **Add**

#### Step 2: Install Integration

1. Search for "Newbook Hotel Management" in HACS
2. Click on the integration
3. Click **Download**
4. Select the latest version
5. Wait for download to complete

#### Step 3: Restart Home Assistant

1. Go to **Settings** → **System** → **Restart**
2. Wait for Home Assistant to restart (1-2 minutes)

### Method 2: Manual Installation

If you don't use HACS or prefer manual installation:

#### Step 1: Download Files

1. Download the latest release from GitHub:
   - Go to https://github.com/jtricerolph/homeassistant-newbook-heating-component/releases
   - Download the latest `.zip` file

2. Extract the archive

#### Step 2: Copy Files

1. Copy the `custom_components/newbook` folder to your Home Assistant configuration directory:
   ```
   /config/custom_components/newbook/
   ```

2. The final directory structure should look like:
   ```
   /config/
   ├── custom_components/
   │   └── newbook/
   │       ├── __init__.py
   │       ├── manifest.json
   │       ├── api.py
   │       ├── config_flow.py
   │       ├── coordinator.py
   │       ├── sensor.py
   │       ├── binary_sensor.py
   │       ├── number.py
   │       ├── switch.py
   │       ├── services.py
   │       ├── heating_controller.py
   │       ├── trv_monitor.py
   │       ├── booking_processor.py
   │       ├── room_manager.py
   │       ├── dashboard_generator.py
   │       ├── const.py
   │       ├── strings.json
   │       └── translations/
   │           └── en.json
   ```

#### Step 3: Restart Home Assistant

Restart Home Assistant to load the new integration.

### Method 3: Git Clone (For Developers)

If you want to track updates or contribute:

```bash
cd /config/custom_components
git clone https://github.com/jtricerolph/homeassistant-newbook-heating-component.git newbook-temp
mv newbook-temp/custom_components/newbook ./newbook
rm -rf newbook-temp
```

Then restart Home Assistant.

## Integration Configuration

After installation and restart, configure the integration:

### Step 1: Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for "Newbook Hotel Management"
4. Click on the integration

### Step 2: Configuration Wizard

The integration uses a 5-step configuration wizard:

#### **Step 1: API Credentials**

Enter your Newbook API credentials:

| Field | Description | Example |
|-------|-------------|---------|
| **Username** | Your Newbook username | `myhotel@example.com` |
| **Password** | Your Newbook password | `********` |
| **API Key** | Your Newbook API key | `abc123xyz...` |
| **Region** | Your Newbook region | `AU`, `EU`, `US`, or `NZ` |

**Where to find your API key:**
1. Log into Newbook admin panel
2. Go to **Settings** → **API Access**
3. Copy your API key

#### **Step 2: Polling Settings**

Configure how often to check for booking updates:

| Setting | Default | Description |
|---------|---------|-------------|
| **Refresh Interval** | 10 minutes | How often to poll Newbook API |

**Recommendations:**
- **Busy hotels**: 5-10 minutes (more responsive to changes)
- **Quiet hotels**: 15-30 minutes (reduce API calls)
- **Very busy**: Consider webhook integration (future feature)

#### **Step 3: Default Room Settings**

Set default values for all rooms (can be customized per-room later):

| Setting | Default | Description |
|---------|---------|-------------|
| **Default Arrival Time** | 15:00 | Standard check-in time |
| **Default Departure Time** | 10:00 | Standard checkout time |
| **Heating Offset** | 120 minutes | Pre-heat time before arrival |
| **Cooling Offset** | -30 minutes | When to stop heating (negative = before checkout) |
| **Occupied Temperature** | 22°C | Target temp when occupied |
| **Vacant Temperature** | 16°C | Target temp when vacant |

**Notes:**
- **Negative cooling offset**: `-30` means stop heating 30 minutes BEFORE checkout
- **Positive cooling offset**: `60` means keep heating 60 minutes AFTER checkout
- Adjust based on:
  - Room size and insulation
  - Climate and season
  - Guest preferences
  - Energy costs

#### **Step 4: TRV Monitoring**

Configure TRV reliability monitoring:

| Setting | Default | Description |
|---------|---------|-------------|
| **Max Retry Attempts** | 10 | Maximum retries for unresponsive TRVs |
| **Command Timeout** | 60 seconds | How long to wait for TRV response |
| **Battery Warning Threshold** | 30% | Battery level to show warnings |
| **Battery Critical Threshold** | 15% | Battery level for critical alerts |

**Retry Schedule:**
- Attempt 1: 30 seconds
- Attempt 2: 60 seconds
- Attempt 3: 2 minutes
- Attempt 4: 5 minutes
- Attempt 5: 10 minutes
- Attempts 6-10: 30 minutes

Total retry time: ~2.5 hours before marking as unresponsive

#### **Step 5: Valve Sync Defaults**

Configure default valve synchronization behavior:

| Setting | Default | Description |
|---------|---------|-------------|
| **Sync Room Setpoints** | ON | Enable room-level valve sync by default |
| **Exclude Bathroom from Sync** | ON | Keep bathroom valves independent |

**Sync Behavior:**
- **ON + Exclude Bathroom**: Bedroom valves sync, bathroom independent (recommended)
- **ON + Include Bathroom**: All valves in room sync together
- **OFF**: Each valve operates independently

### Step 3: Verify Installation

After completing the wizard:

1. **Check Integration Status**:
   - Go to **Settings** → **Devices & Services**
   - Look for "Newbook Hotel Management"
   - Status should show "Connected"

2. **Check Logs**:
   - Go to **Settings** → **System** → **Logs**
   - Filter by "newbook"
   - Look for: `"Newbook integration setup complete"`
   - Should see room discovery messages

3. **Check for Rooms**:
   - After 1-2 minutes, rooms should be discovered
   - Check **Developer Tools** → **States**
   - Look for entities starting with `sensor.room_`

4. **Check System Sensors**:
   - `sensor.newbook_system_status` should show "Online"
   - `sensor.newbook_rooms_discovered` should show count > 0
   - `sensor.newbook_active_bookings` should show current booking count

## MQTT Broker Setup

The integration requires MQTT for Shelly TRV communication.

### Install Mosquitto Broker (Recommended)

1. Go to **Settings** → **Add-ons**
2. Click **Add-on Store**
3. Search for "Mosquitto broker"
4. Click **Install**
5. After installation, configure:

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

6. Click **Save**
7. Click **Start**
8. Enable **Start on boot**

### Configure MQTT Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "MQTT"
4. Configure:
   - **Broker**: `homeassistant.local` (or `127.0.0.1`)
   - **Port**: `1883`
   - **Username**: `homeassistant`
   - **Password**: Your broker password
5. Click **Submit**

### Verify MQTT Connection

1. Go to **Developer Tools** → **MQTT**
2. Subscribe to topic: `#` (all messages)
3. You should see MQTT traffic
4. Status should show "Connected"

## Shelly TRV Configuration

See [MQTT_SETUP.md](MQTT_SETUP.md) for complete Shelly TRV configuration guide.

### Quick Setup

For each Shelly TRV:

1. Access Shelly web interface: `http://[SHELLY-IP]`
2. Go to **Settings** → **Internet & Security** → **MQTT**
3. Configure:
   ```
   ☑ Enable MQTT
   Server: homeassistant.local:1883
   Username: homeassistant
   Password: [your-mqtt-password]
   Topic Prefix: shellies/room-[ROOM]-[LOCATION]-trv
   ```
4. Example topic prefixes:
   - `shellies/room-101-bedroom-trv`
   - `shellies/room-101-bathroom-trv`
   - `shellies/room-205-bedroom-trv`

5. Reboot the Shelly TRV

### Verify TRV Discovery

After configuring TRVs, verify they appear in Home Assistant:

1. Go to **Settings** → **Devices & Services** → **MQTT**
2. You should see your Shelly TRV devices listed
3. Check for climate entities:
   - `climate.room_101_bedroom_trv`
   - `climate.room_101_bathroom_trv`
   - etc.

## Post-Installation Checklist

- [ ] Integration shows "Connected" status
- [ ] Rooms discovered (check `sensor.newbook_rooms_discovered`)
- [ ] MQTT broker running
- [ ] All Shelly TRVs configured with correct topic format
- [ ] TRV entities visible in Home Assistant
- [ ] System sensors reporting data
- [ ] Dashboards generated in `/config/dashboards/newbook/`
- [ ] Logs show no errors
- [ ] First booking test successful

## Troubleshooting Installation Issues

### Integration Not Appearing

**Problem**: Can't find "Newbook Hotel Management" in Add Integration list

**Solutions**:
1. Verify files copied to `/config/custom_components/newbook/`
2. Check `manifest.json` exists and is valid
3. Restart Home Assistant again
4. Check logs for Python errors
5. Verify Home Assistant version (needs 2023.1+)

### Configuration Validation Errors

**Problem**: "Invalid username/password" or "API connection failed"

**Solutions**:
1. Verify credentials in Newbook admin panel
2. Check API key is correct (copy-paste to avoid typos)
3. Verify region selection matches your Newbook account
4. Test API manually: https://api-[region].newbook.cloud/
5. Check firewall isn't blocking API requests

### No Rooms Discovered

**Problem**: `sensor.newbook_rooms_discovered` shows 0

**Solutions**:
1. Check Newbook account has rooms configured
2. Verify `sites_list` API endpoint returns data
3. Check logs for API errors
4. Wait 10-15 minutes for first poll
5. Use `newbook.refresh_bookings` service to force update
6. Verify room IDs in Newbook match expected format

### MQTT Connection Failed

**Problem**: MQTT integration shows "Disconnected"

**Solutions**:
1. Verify Mosquitto broker is running
2. Check username/password are correct
3. Test connection from command line:
   ```bash
   mosquitto_sub -h homeassistant.local -p 1883 -u homeassistant -P [password] -t '#'
   ```
4. Check broker logs for errors
5. Verify port 1883 is not blocked by firewall

### Shelly TRVs Not Discovered

**Problem**: TRV entities not appearing in Home Assistant

**Solutions**:
1. Verify MQTT topic format: `shellies/room-[ID]-[location]-trv`
2. Check Shelly is connected to MQTT broker
3. Subscribe to topic in MQTT Developer Tools: `shellies/#`
4. Verify Shelly firmware is up to date
5. Check WiFi signal strength (should be > -70 dBm)
6. Reboot Shelly TRV device
7. Check MQTT integration has discovery enabled

## Getting Help

If you encounter issues not covered here:

1. **Check Logs**:
   - Settings → System → Logs → Filter by "newbook"

2. **Enable Debug Logging**:
   Add to `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.newbook: debug
   ```
   Restart Home Assistant

3. **GitHub Issues**:
   - https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues
   - Include:
     - Home Assistant version
     - Integration version
     - Relevant log excerpts
     - Steps to reproduce issue

4. **Documentation**:
   - [Configuration Guide](CONFIGURATION.md)
   - [MQTT Setup](MQTT_SETUP.md)
   - [Troubleshooting](TROUBLESHOOTING.md)

## Next Steps

After successful installation:

1. **Configure Room Settings**: Adjust per-room offsets and temperatures
2. **Test Heating Logic**: Create a test booking and verify heating updates
3. **Monitor TRV Health**: Check battery levels and response times
4. **Customize Dashboards**: Modify auto-generated dashboards to your needs
5. **Set Up Automations**: Create custom automations based on booking events

See [Configuration Guide](CONFIGURATION.md) for detailed configuration options.
