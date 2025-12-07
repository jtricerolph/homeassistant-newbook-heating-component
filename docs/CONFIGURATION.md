# Configuration Guide

Complete configuration reference for the Newbook Hotel Management integration.

## Table of Contents

- [Initial Configuration](#initial-configuration)
- [Per-Room Settings](#per-room-settings)
- [Global Settings](#global-settings)
- [TRV Monitoring Settings](#trv-monitoring-settings)
- [Advanced Configuration](#advanced-configuration)
- [Configuration Examples](#configuration-examples)

## Initial Configuration

The integration uses a 5-step configuration wizard during initial setup. See [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions.

### Modifying Integration Settings

To change integration-level settings after initial setup:

1. Go to **Settings** → **Devices & Services**
2. Find "Newbook Hotel Management"
3. Click **Configure**
4. Modify settings as needed
5. Integration will reload automatically

## Per-Room Settings

Each discovered room gets 17 configurable entities. Settings can be adjusted per-room.

### Number Entities

#### `number.room_XXX_heating_offset_minutes`

**Description**: Minutes before arrival to start pre-heating

**Default**: `120` (2 hours)

**Range**: `0` to `480` minutes (0-8 hours)

**Usage**:
```yaml
service: number.set_value
target:
  entity_id: number.room_101_heating_offset_minutes
data:
  value: 180  # 3 hours pre-heat
```

**Recommendations by Room Type**:
| Room Type | Offset | Reason |
|-----------|--------|--------|
| Standard room | 120 min | Normal insulation |
| Suite | 180 min | Larger space, more time needed |
| Poorly insulated | 240 min | Extra time for heat-up |
| Well insulated | 60 min | Retains heat well |
| Summer | 30-60 min | Less heating needed |
| Winter | 180-240 min | More heating needed |

#### `number.room_XXX_cooling_offset_minutes`

**Description**: Minutes after departure to stop heating (can be negative)

**Default**: `-30` (30 minutes BEFORE checkout)

**Range**: `-120` to `240` minutes

**Usage**:
```yaml
service: number.set_value
target:
  entity_id: number.room_101_cooling_offset_minutes
data:
  value: -60  # Stop heating 1 hour before checkout
```

**How Negative Offsets Work**:
- **Negative value** (e.g., `-30`): Stop heating BEFORE checkout
  - Guest checks out at 10:00
  - Heating stops at 09:30
  - Saves energy as room cools before departure

- **Positive value** (e.g., `60`): Continue heating AFTER checkout
  - Guest checks out at 10:00
  - Heating continues until 11:00
  - Useful for back-to-back bookings

- **Zero** (`0`): Stop heating exactly at checkout time

**Recommendations**:
| Scenario | Offset | Reason |
|----------|--------|--------|
| Same-day turnaround | `-30` to `-60` | Save energy |
| Next-day booking | `0` | Stop at checkout |
| Back-to-back bookings | `60` to `120` | Keep warm for next guest |
| Energy saving priority | `-60` to `-120` | Maximum savings |

#### `number.room_XXX_occupied_temperature`

**Description**: Target temperature when room is occupied

**Default**: `22°C`

**Range**: `16°C` to `28°C`

**Usage**:
```yaml
service: number.set_value
target:
  entity_id: number.room_101_occupied_temperature
data:
  value: 21  # Guest comfort temperature
```

**Recommendations**:
| Season/Climate | Temperature | Notes |
|----------------|-------------|-------|
| Winter | 21-23°C | Comfort in cold weather |
| Summer | 20-22°C | Less heating needed |
| Warm climate | 19-21°C | Lower target acceptable |
| Cold climate | 22-24°C | Higher for comfort |

#### `number.room_XXX_vacant_temperature`

**Description**: Target temperature when room is vacant

**Default**: `16°C`

**Range**: `10°C` to `22°C`

**Usage**:
```yaml
service: number.set_value
target:
  entity_id: number.room_101_vacant_temperature
data:
  value: 14  # Lower for energy savings
```

**Recommendations**:
| Priority | Temperature | Energy Savings |
|----------|-------------|----------------|
| Maximum savings | 12-14°C | High (30-40%) |
| Balanced | 15-17°C | Medium (20-30%) |
| Quick recovery | 18-20°C | Low (10-20%) |

**Warning**: Don't set too low in winter to avoid:
- Frozen pipes
- Mold/damp issues
- Slow heat-up times

### Switch Entities

#### `switch.room_XXX_auto_mode`

**Description**: Enable/disable automatic heating control

**Default**: `ON`

**States**:
- **ON**: Integration automatically controls heating based on bookings
- **OFF**: Manual control only, automation disabled

**Usage**:
```yaml
# Enable auto mode
service: switch.turn_on
target:
  entity_id: switch.room_101_auto_mode

# Disable auto mode (for manual control)
service: switch.turn_off
target:
  entity_id: switch.room_101_auto_mode
```

**When to Disable**:
- Room under maintenance
- Testing TRV functionality
- Overriding for special guest
- Troubleshooting heating issues

#### `switch.room_XXX_sync_setpoints`

**Description**: Enable/disable temperature synchronization across all valves in room

**Default**: `ON`

**States**:
- **ON**: All valves in room update to same temperature when automation changes setpoint
- **OFF**: Each valve operates independently

**Usage**:
```yaml
# Enable sync (all valves together)
service: switch.turn_on
target:
  entity_id: switch.room_101_sync_setpoints

# Disable sync (independent control)
service: switch.turn_off
target:
  entity_id: switch.room_101_sync_setpoints
```

**Behavior**:
| Sync | Automation Change | Guest Change | Result |
|------|-------------------|--------------|--------|
| ON | ✓ Syncs all valves | ✗ Never synced | Consistent room temp |
| OFF | ✗ No sync | ✗ Never synced | Independent valves |

**Recommendations**:
- **Standard room with multiple radiators**: ON (consistent temperature)
- **Suite with separate zones**: OFF (independent control)
- **Rooms with uneven heating**: OFF (adjust per-radiator)

#### `switch.room_XXX_exclude_bathroom_from_sync`

**Description**: Exclude bathroom valves from room synchronization

**Default**: `ON`

**States**:
- **ON**: Bathroom valve excluded from sync (independent)
- **OFF**: Bathroom valve included in sync

**Usage**:
```yaml
# Exclude bathroom (independent towel drying)
service: switch.turn_on
target:
  entity_id: switch.room_101_exclude_bathroom_from_sync

# Include bathroom (sync with bedroom)
service: switch.turn_off
target:
  entity_id: switch.room_101_exclude_bathroom_from_sync
```

**Use Cases**:
| Scenario | Setting | Reason |
|----------|---------|--------|
| Towel drying | ON | Guest can use bathroom radiator independently |
| Energy saving | ON | Don't heat bathroom when not needed |
| Small bathroom | OFF | Include in room heating |
| Cold bathroom | OFF | Ensure adequate heating |

**Note**: Only applies when `sync_setpoints` is ON

## Global Settings

Settings that apply to the entire integration (all rooms).

### API Settings

#### Scan Interval

**Description**: How often to poll Newbook API for booking updates

**Default**: `10 minutes`

**Range**: `5` to `60` minutes

**Location**: Integration configuration → Step 2

**Considerations**:
| Interval | Responsiveness | API Load | Recommendation |
|----------|----------------|----------|----------------|
| 5 min | High | High | Very busy hotels |
| 10 min | Good | Medium | Standard hotels |
| 15 min | Medium | Low | Quiet hotels |
| 30+ min | Low | Very low | Test environments |

#### Default Arrival/Departure Times

**Description**: Fallback times when booking doesn't specify exact times

**Defaults**:
- Arrival: `15:00`
- Departure: `10:00`

**Location**: Integration configuration → Step 3

**Usage**:
- Used when Newbook booking has only date (no time)
- Combined with actual times when available
- Integration uses **earlier** arrival and **later** departure

## TRV Monitoring Settings

Settings for managing unreliable TRV devices.

### Max Retry Attempts

**Description**: Maximum number of retry attempts for unresponsive TRVs

**Default**: `10`

**Range**: `3` to `20`

**Location**: Integration configuration → Step 4

**Retry Schedule**:
```
Attempt 1:  30 seconds
Attempt 2:  60 seconds
Attempt 3:  2 minutes
Attempt 4:  5 minutes
Attempt 5:  10 minutes
Attempt 6-10: 30 minutes each
```

**Total retry time** (default 10 attempts): ~2.5 hours

### Command Timeout

**Description**: Seconds to wait for TRV acknowledgment before considering command failed

**Default**: `60 seconds`

**Range**: `30` to `300` seconds

**Location**: Integration configuration → Step 4

**Recommendations**:
| TRV Sleep Interval | Timeout | Reason |
|-------------------|---------|--------|
| 5 minutes | 60s | Fast response expected |
| 10 minutes | 90s | Standard |
| 15 minutes | 120s | Slower response times |

### Battery Thresholds

#### Warning Threshold

**Description**: Battery level to show warnings

**Default**: `30%`

**Range**: `20%` to `50%`

**Location**: Integration configuration → Step 4

**Actions at threshold**:
- Warning log message
- `binary_sensor.room_XXX_YYY_trv_battery_warning` turns ON
- Dashboard shows warning

#### Critical Threshold

**Description**: Battery level for critical alerts

**Default**: `15%`

**Range**: `10%` to `30%`

**Location**: Integration configuration → Step 4

**Actions at threshold**:
- Critical log message
- `binary_sensor.room_XXX_YYY_trv_battery_critical` turns ON
- Dashboard shows critical alert
- Should trigger recharge immediately

## Advanced Configuration

### Manual Service Calls

For advanced automation and manual control:

#### Force Room Temperature

Manually override room temperature (disables auto mode):

```yaml
service: newbook.force_room_temperature
data:
  room_id: "101"
  temperature: 24
```

**Effect**:
- Sets all TRVs in room to specified temperature
- Disables auto mode for that room
- Overrides any booking-based control

**Use cases**:
- VIP guest requests specific temperature
- Maintenance override
- Emergency heating

#### Sync Room Valves

Manually synchronize all valves in a room:

```yaml
service: newbook.sync_room_valves
data:
  room_id: "101"
  temperature: 22
```

**Effect**:
- Sets all valves (including bathroom if not excluded)
- Does NOT disable auto mode
- One-time sync operation

#### Enable/Disable Auto Mode

Programmatically control auto mode:

```yaml
# Enable auto mode
service: newbook.set_room_auto_mode
data:
  room_id: "101"
  enabled: true

# Disable auto mode
service: newbook.set_room_auto_mode
data:
  room_id: "101"
  enabled: false
```

#### Retry Unresponsive TRVs

Manually trigger retry for all failed TRVs:

```yaml
service: newbook.retry_unresponsive_trvs
```

**Use cases**:
- After WiFi outage
- After MQTT broker restart
- When TRVs show unresponsive status

#### Refresh Bookings

Force immediate booking data refresh:

```yaml
service: newbook.refresh_bookings
```

**Use cases**:
- After making manual booking changes in Newbook
- Testing booking updates
- Troubleshooting sync issues

## Configuration Examples

### Example 1: Energy-Efficient Configuration

Maximize energy savings:

```yaml
# Per-room settings
number.room_101_heating_offset_minutes: 60      # Only 1 hour pre-heat
number.room_101_cooling_offset_minutes: -90     # Stop 1.5h before checkout
number.room_101_occupied_temperature: 20        # Lower occupied temp
number.room_101_vacant_temperature: 14          # Very low vacant temp

switch.room_101_auto_mode: on                   # Auto control
switch.room_101_sync_setpoints: on              # Sync for consistency
switch.room_101_exclude_bathroom_from_sync: on  # Don't heat bathroom
```

### Example 2: Comfort-First Configuration

Prioritize guest comfort:

```yaml
# Per-room settings
number.room_101_heating_offset_minutes: 180     # 3 hours pre-heat
number.room_101_cooling_offset_minutes: 0       # Keep until checkout
number.room_101_occupied_temperature: 23        # Warm occupied temp
number.room_101_vacant_temperature: 18          # Higher vacant temp (quick recovery)

switch.room_101_auto_mode: on
switch.room_101_sync_setpoints: on
switch.room_101_exclude_bathroom_from_sync: off # Include bathroom heating
```

### Example 3: Suite with Multiple Zones

Independent control for different areas:

```yaml
# Per-room settings
number.room_301_heating_offset_minutes: 180
number.room_301_cooling_offset_minutes: -30
number.room_301_occupied_temperature: 22
number.room_301_vacant_temperature: 16

switch.room_301_auto_mode: on
switch.room_301_sync_setpoints: off              # Independent valve control
switch.room_301_exclude_bathroom_from_sync: on   # Still exclude bathroom
```

### Example 4: Maintenance Mode

Disable automation for maintenance:

```yaml
# Disable auto mode
service: switch.turn_off
target:
  entity_id: switch.room_101_auto_mode

# Optionally set manual temperature
service: newbook.force_room_temperature
data:
  room_id: "101"
  temperature: 16  # Minimum during maintenance
```

## Best Practices

1. **Start Conservative**: Begin with default settings and adjust based on results

2. **Monitor First Week**: Watch energy usage, guest feedback, and TRV behavior

3. **Seasonal Adjustments**: Change offsets and temperatures based on season

4. **Per-Room Tuning**: Different rooms may need different settings based on:
   - Insulation quality
   - Room size
   - Sun exposure
   - Guest preferences

5. **Balance Comfort and Cost**: Find sweet spot between:
   - Guest satisfaction (comfort)
   - Energy costs
   - Environmental impact

6. **Regular Review**: Monthly review of:
   - Energy usage trends
   - Guest complaints
   - TRV health status
   - Battery recharge needs

## Configuration Backup

To backup your configuration:

1. **Per-Room Settings**: Stored in Home Assistant's entity registry
   - Backup Home Assistant config directory
   - Settings persist across restarts

2. **Integration Config**: Stored in `.storage/core.config_entries`
   - Included in Home Assistant snapshots
   - Can reconfigure via UI if needed

3. **Recommended**: Use Home Assistant's built-in snapshot feature
   ```
   Settings → System → Backups → Create Backup
   ```

## Troubleshooting Configuration

### Settings Not Taking Effect

1. Check logs for errors
2. Verify entity_id is correct
3. Restart integration if needed
4. Ensure auto mode is enabled (for automated changes)

### Temperature Not Reaching Target

1. Check TRV health status
2. Verify WiFi signal strength
3. Check battery levels
4. Increase heating offset
5. Verify room has active booking

### Valves Not Syncing

1. Verify `switch.room_XXX_sync_setpoints` is ON
2. Check `switch.room_XXX_exclude_bathroom_from_sync` setting
3. Ensure changes are automation-initiated (guest changes never sync)
4. Check logs for sync command confirmation

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more detailed troubleshooting steps.
