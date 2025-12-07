# Heating Automation Logic

## When Does Heating Start and Stop?

### Heating Decision Flow

The `should_heat` binary sensor evaluates **THREE conditions** that ALL must be true:

1. **Auto Mode Enabled** (`switch.{room}_auto_mode` = ON)
2. **Active Booking Status** (booking status must be `confirmed`, `unconfirmed`, or `arrived`)
3. **Correct Room State** (room state must be `heating_up` or `occupied`)

```
Auto Mode ON  →  Active Booking  →  Correct State  →  HEAT
     ↓                  ↓                   ↓
    OFF            departed/cancelled     vacant      →  NO HEAT
```

## Room State Determination Logic

Room states are determined with the following **priority order**:

### Priority 1: Explicit Booking Status (Overrides Time)

| Booking Status | Room State | Heats? |
|----------------|------------|--------|
| `departed` | `cooling_down` | ❌ NO |
| `arrived` | `occupied` | ✅ YES |

**Note:** When status is `arrived`, heating should work **immediately** regardless of time.

### Priority 2: Time-Based States (For confirmed/unconfirmed bookings)

Assuming booking status is `confirmed` or `unconfirmed`:

| Time Period | Room State | Heats? |
|-------------|------------|--------|
| Before heating_start | `booked` | ❌ NO |
| heating_start → arrival | `heating_up` | ✅ YES |
| arrival → cooling_start | `occupied` | ✅ YES |
| After cooling_start | `cooling_down` | ❌ NO |

### Priority 3: No Booking

| Condition | Room State | Heats? |
|-----------|------------|--------|
| No active booking | `vacant` | ❌ NO |

## Heating Schedule Calculation

The system calculates these key times:

```python
# Example: Guest checks in today at 15:00, checks out tomorrow at 10:00
# Default arrival time: 15:00
# Default departure time: 10:00
# Heating offset: 120 minutes (2 hours)
# Cooling offset: -30 minutes (30 min before checkout)

arrival = datetime(2025, 12, 07, 15, 0)        # 3:00 PM today
departure = datetime(2025, 12, 08, 10, 0)      # 10:00 AM tomorrow

# Calculated times:
heating_start = arrival - 120 min              # 1:00 PM today
cooling_start = departure + (-30 min)          # 9:30 AM tomorrow
```

### Key Formula:
- **heating_start** = arrival - heating_offset_minutes
- **cooling_start** = departure + cooling_offset_minutes
- **Cooling offset can be negative** to stop heating BEFORE checkout

## Common Issues and Diagnostics

### Issue 1: Guest Arrived but Not Heating

**Possible Causes:**

1. **Auto Mode is OFF**
   - Check: `switch.{room}_auto_mode` should be ON
   - Fix: Turn on auto mode switch

2. **Booking Status Not "arrived"**
   - Check: `sensor.{room}_booking_status`
   - Expected: Should show "arrived"
   - Issue: PMS may not have updated status yet

3. **Room State Stuck in Wrong State**
   - Check: `sensor.{room}_room_state`
   - Expected: Should show "occupied" for arrived guests
   - Debug: Check Home Assistant logs for state calculation

4. **Schedule Calculation Failed**
   - Check: `sensor.{room}_heating_start` and `sensor.{room}_arrival`
   - Expected: Should have valid datetime values
   - Issue: Invalid booking dates from API

### Issue 2: Heating Started Too Early/Late

**Check These Settings:**

1. **Heating Offset**
   - Entity: `number.{room}_heating_offset`
   - Default: 120 minutes (2 hours before arrival)
   - Adjust: Increase to start earlier, decrease to start later

2. **Arrival Time Calculation**
   - System uses **earlier** of actual arrival time OR default arrival time
   - Check: `sensor.{room}_arrival` for calculated time
   - Default: 15:00 (3 PM) from config

### Issue 3: Heating Didn't Stop After Checkout

**Check These:**

1. **Booking Status**
   - Check: `sensor.{room}_booking_status`
   - Should be: `departed` or booking should be removed
   - Issue: PMS hasn't updated status

2. **Cooling Offset**
   - Entity: `number.{room}_cooling_offset`
   - Default: -30 minutes (stops 30 min BEFORE checkout)
   - Check: `sensor.{room}_cooling_start`

3. **Old Booking Not Filtered**
   - As of v0.2.3, past bookings should be filtered
   - Check logs for "departure date filtering" messages

## Diagnostic Steps

### Step 1: Check Entity States

Open Home Assistant → Developer Tools → States, and check these entities for the room:

```yaml
# Required entities to check:
switch.{room}_auto_mode                    # Must be ON
sensor.{room}_booking_status               # Should be "arrived", "confirmed", or "unconfirmed"
sensor.{room}_room_state                   # Should be "heating_up" or "occupied" to heat
binary_sensor.{room}_should_heat           # Final heating decision
sensor.{room}_heating_start                # When pre-heat begins
sensor.{room}_arrival                      # Expected arrival time
sensor.{room}_cooling_start                # When cooling begins
sensor.{room}_departure                    # Checkout time
```

### Step 2: Check Logs

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.newbook: debug
    custom_components.newbook.heating_controller: debug
    custom_components.newbook.booking_processor: debug
```

Look for these log messages:
- `"Heating should be ON for room X"` or `"Heating should be OFF for room X"`
- `"Room X state: {state}"`
- `"Booking status for room X: {status}"`

### Step 3: Manual Refresh

Sometimes the coordinator hasn't refreshed recently:

1. Go to Developer Tools → Services
2. Call service: `newbook.refresh_bookings`
3. Wait 10 seconds
4. Re-check entity states

### Step 4: Check Booking Data

View the raw booking data:

1. Go to Developer Tools → States
2. Find `sensor.{room}_booking_reference`
3. Click to view attributes
4. Check `booking_arrival`, `booking_departure`, and `booking_status`

## Expected Behavior Examples

### Example 1: Walk-in Guest (Immediate Heating)

```
Scenario: Guest walks in at 10:00 AM, PMS marks as "arrived"

Timeline:
10:00 AM - PMS updated, status = "arrived"
         → Room state = "occupied" (immediate)
         → Should heat = YES (if auto mode ON)
         → TRVs set to occupied temperature
```

### Example 2: Advance Booking (Pre-Heat)

```
Scenario: Guest booked for 3:00 PM arrival today
Settings: Heating offset = 120 min (2 hours)

Timeline:
12:00 PM - Room state changes to "booked" → No heating
 1:00 PM - Heating start time reached
         → Room state = "heating_up"
         → Should heat = YES
         → TRVs set to occupied temperature
 3:00 PM - Guest arrives, PMS marks "arrived"
         → Room state = "occupied"
         → Continues heating
10:00 AM - Next day, guest checks out
 9:30 AM - Cooling start (30 min before checkout)
         → Room state = "cooling_down"
         → Should heat = NO
         → TRVs set to vacant temperature
```

### Example 3: Multi-Day Stay

```
Scenario: Guest checks in today, checks out in 3 days

Day 1:
 1:00 PM - Pre-heating starts
 3:00 PM - Guest arrives, marked "arrived"
         → Heating continues

Day 2-3:
 All day - Status remains "arrived"
         → Room state = "occupied"
         → Continues heating

Day 4:
10:00 AM - Guest departs, PMS marks "departed"
         → Room state = "cooling_down"
         → Heating stops
```

## Code References

The heating logic is split across these files:

1. **booking_processor.py**
   - `calculate_heating_schedule()` - Calculates heating/cooling times
   - `determine_room_state()` - Determines current room state
   - `should_heat()` - Final heating decision

2. **heating_controller.py**
   - `async_update_room_heating()` - Executes heating changes
   - Calls TRV monitor to set temperatures

3. **binary_sensor.py**
   - `NewbookShouldHeatBinarySensor` - Exposes heating decision as binary sensor

4. **const.py**
   - `ACTIVE_BOOKING_STATUSES` - Which statuses trigger heating
   - `ROOM_STATE_*` - State constants

## Debugging Arrived Bookings Specifically

If a guest has "arrived" status but heating isn't working:

### Check 1: Auto Mode
```yaml
Developer Tools → States → switch.{room}_auto_mode
Expected: "on"
```

### Check 2: Booking Status (Case Sensitive!)
```yaml
Developer Tools → States → sensor.{room}_booking_status
Expected: "arrived" (lowercase)
Actual might be: "Arrived" (capitalized) ← This would break!
```

**Fix:** The code lowercases the status (line 233 in booking_processor.py), so this should work, but verify in logs.

### Check 3: Room State
```yaml
Developer Tools → States → sensor.{room}_room_state
Expected: "occupied"
```

If this shows "booked" instead of "occupied", there's a bug in the state determination logic.

### Check 4: Should Heat Binary Sensor
```yaml
Developer Tools → States → binary_sensor.{room}_should_heat
Expected: "on"
```

This is the final result. If this is "off", check the attributes for the reason.

## Getting Help

If heating still doesn't work after checking all of the above:

1. **Collect diagnostic info:**
   - Screenshot of all entities for the room
   - Home Assistant logs with debug enabled
   - Sample booking data from `sensor.{room}_booking_reference` attributes

2. **Open an issue:**
   - https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues
   - Include diagnostic info
   - Mention your version (currently 0.2.4)

## Version-Specific Notes

### v0.2.3+
- Added departure date filtering to prevent old bookings from triggering heating
- Past bookings (>1 day past checkout) are now ignored

### v0.2.0+
- Fixed category field mapping
- Booking status comparison is case-insensitive (lowercased)
