# Shelly TRV Quick Reference Guide

Quick reference for configuring Shelly TRV devices for Newbook Hotel Management integration.

## Naming Convention Template

```
shellies/room-{ROOM_ID}-{LOCATION}-trv
```

## Configuration Examples

| Room | Location | MQTT Topic | Device Name | Entity ID |
|------|----------|-----------|-------------|-----------|
| 101 | Bedroom | `shellies/room-101-bedroom-trv` | Room 101 Bedroom TRV | `climate.room_101_bedroom_trv` |
| 101 | Bathroom | `shellies/room-101-bathroom-trv` | Room 101 Bathroom TRV | `climate.room_101_bathroom_trv` |
| 205 | Bedroom | `shellies/room-205-bedroom-trv` | Room 205 Bedroom TRV | `climate.room_205_bedroom_trv` |
| 301 | Bedroom 1 | `shellies/room-301-bedroom1-trv` | Room 301 Bedroom 1 TRV | `climate.room_301_bedroom1_trv` |
| 301 | Bedroom 2 | `shellies/room-301-bedroom2-trv` | Room 301 Bedroom 2 TRV | `climate.room_301_bedroom2_trv` |

## Shelly TRV MQTT Settings

Access Shelly device via:
- **Web**: `http://[SHELLY-IP]`
- **App**: Shelly Smart Control app

### Settings Path
**Settings → Internet & Security → Advanced - Developer Settings → MQTT**

### Configuration

```
☑ Enable MQTT

Server: homeassistant.local:1883
        (or broker IP: 192.168.1.x:1883)

Username: homeassistant
Password: [your-mqtt-password]

Client ID: [leave default]

Topic Prefix: shellies/room-[ROOM]-[LOCATION]-trv
              Example: shellies/room-101-bedroom-trv

☑ MQTT Status Update Enabled
☑ Periodic connection
☑ Use MQTT for commands

Sleep Time: 10 minutes (recommended)
            15 minutes (default)
            5 minutes (faster, shorter battery life)
```

## WiFi Signal Strength Guidelines

| Signal (dBm) | Quality | Action |
|--------------|---------|--------|
| -50 to -60 | Excellent | ✓ No action needed |
| -60 to -70 | Good | ✓ Acceptable |
| -70 to -80 | Fair | ⚠ Monitor for issues |
| -80 to -90 | Poor | ❌ Add WiFi extender |
| Below -90 | Very Poor | ❌ Will not work reliably |

**Check signal**: Shelly web interface → Device Info

## Battery Level Guidelines

| Level | Status | Action |
|-------|--------|--------|
| 80-100% | Excellent | ✓ No action |
| 50-80% | Good | ✓ Monitor |
| 20-50% | Low | ⚠ Plan replacement |
| Below 20% | Critical | ❌ Replace immediately |

## Expected Response Times

| Action | Time | Notes |
|--------|------|-------|
| Temperature change | 30s - 5min | Normal for battery devices |
| Status update | 5-15min | Based on sleep interval |
| Emergency override | 30s - 2min | Integration retries |
| Full sync | Up to 30min | All TRVs in room |

## MQTT Topics Structure

### Published by Shelly TRV

```
shellies/room-101-bedroom-trv/online                    → true/false
shellies/room-101-bedroom-trv/thermostat/0/temperature  → Current temp
shellies/room-101-bedroom-trv/thermostat/0/target_t    → Target temp + source
shellies/room-101-bedroom-trv/sensor/battery           → Battery %
```

### Subscribed by Shelly TRV

```
shellies/room-101-bedroom-trv/thermostat/0/command/target_t  ← Set temperature
```

## Source Detection Values

When temperature changes, MQTT payload includes source:

| Source | Meaning | Integration Action |
|--------|---------|-------------------|
| `button` | Guest pressed buttons on TRV | ✓ Respect, don't override |
| `WS` | Guest used Shelly app | ✓ Respect, don't override |
| `mqtt` | Home Assistant command | ✓ May sync to other valves |
| `http` | API command | ✓ May sync to other valves |

## Integration Services

### Manual Control Services

```yaml
# Refresh booking data
service: newbook.refresh_bookings

# Enable/disable auto mode
service: newbook.set_room_auto_mode
data:
  room_id: "101"
  enabled: true

# Force specific temperature (disables auto)
service: newbook.force_room_temperature
data:
  room_id: "101"
  temperature: 22

# Manually sync all valves in room
service: newbook.sync_room_valves
data:
  room_id: "101"
  temperature: 22

# Retry unresponsive TRVs
service: newbook.retry_unresponsive_trvs
```

## Per-Room Settings

Configured via number entities:

```yaml
# Heating offset (minutes before arrival to start heating)
number.room_101_heating_offset_minutes: 120  # 2 hours

# Cooling offset (minutes after departure, can be negative)
number.room_101_cooling_offset_minutes: -30  # Stop 30min before checkout

# Occupied temperature
number.room_101_occupied_temperature: 22  # °C

# Vacant temperature
number.room_101_vacant_temperature: 16  # °C
```

Configured via switches:

```yaml
# Auto mode (enable/disable automation)
switch.room_101_auto_mode: on

# Sync all valves in room
switch.room_101_sync_setpoints: on

# Exclude bathroom from sync
switch.room_101_exclude_bathroom_from_sync: on
```

## Health States

| State | Meaning | Threshold |
|-------|---------|-----------|
| **Healthy** | Responding normally | < 3 retry attempts, < 5 retries/24h |
| **Degraded** | Slow but working | 3-4 attempts, 5-9 retries/24h |
| **Poor** | Unreliable | 5-9 attempts, 10+ retries/24h |
| **Unresponsive** | Not responding | 10+ attempts or no response in 30min |

## Troubleshooting Quick Fixes

| Problem | Quick Fix |
|---------|-----------|
| TRV not discovered | Check MQTT topic format, reboot TRV |
| Slow response | Normal - wait 2-5min, or reduce sleep time |
| No response | Check WiFi signal, battery level, use retry service |
| Wrong entity name | Rename entity or reconfigure MQTT topic |
| Not detecting guest changes | Update Shelly firmware for source support |
| Bathroom valve syncing | Enable "Exclude bathroom from sync" |
| All rooms heating at once | Stagger is automatic (10s delay between TRVs) |

## Testing Checklist

After configuration:

1. **MQTT Connection Test**:
   ```
   Developer Tools → MQTT → Subscribe: shellies/room-101-bedroom-trv/#
   Should see periodic messages
   ```

2. **Command Test**:
   ```
   climate.set_temperature on room TRV
   Wait 1-5 minutes
   Check TRV display for new temperature
   ```

3. **Source Detection Test**:
   ```
   Press buttons on physical TRV
   Check logs for: "Guest adjusted... (source: button)"
   ```

4. **Integration Test**:
   ```
   Create test booking in Newbook
   Wait for integration refresh (10 min)
   Verify heating updates automatically
   ```

## Common Room Layouts

### Standard Room (1 bedroom, 1 bathroom)
```
Room 101:
  - shellies/room-101-bedroom-trv (climate.room_101_bedroom_trv)
  - shellies/room-101-bathroom-trv (climate.room_101_bathroom_trv)

Settings:
  - Sync setpoints: ON
  - Exclude bathroom: ON
  - Result: Bedroom heats, bathroom independent
```

### Suite (2 bedrooms, 1 bathroom)
```
Room 301:
  - shellies/room-301-bedroom1-trv (climate.room_301_bedroom1_trv)
  - shellies/room-301-bedroom2-trv (climate.room_301_bedroom2_trv)
  - shellies/room-301-bathroom-trv (climate.room_301_bathroom_trv)

Settings:
  - Sync setpoints: ON
  - Exclude bathroom: ON
  - Result: Both bedrooms heat together, bathroom independent
```

### Studio (1 room, no bathroom TRV)
```
Room 205:
  - shellies/room-205-bedroom-trv (climate.room_205_bedroom_trv)

Settings:
  - Sync setpoints: N/A (only one valve)
  - Exclude bathroom: N/A
  - Result: Single valve controlled
```

## Support & Resources

- **Full Setup Guide**: [MQTT_SETUP.md](MQTT_SETUP.md)
- **Integration Docs**: [README.md](../README.md)
- **GitHub Issues**: https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues
- **Shelly Support**: https://www.shelly.com/en/support

## Pro Tips

1. **Label physical TRVs** with room numbers for easy identification
2. **Test one room first** before configuring all TRVs
3. **Document your WiFi signal strengths** during installation
4. **Keep spare batteries** on hand - TRVs use 2× AA batteries
5. **Set realistic expectations** - battery devices are slower than AC units
6. **Use stickers** on TRVs showing the room number and type (bedroom/bathroom)
7. **Monitor health dashboard** weekly to catch issues early
8. **Replace batteries annually** or when below 20%
9. **Consider WiFi extenders** in weak signal areas before problems arise
10. **Test during slow season** before peak occupancy
