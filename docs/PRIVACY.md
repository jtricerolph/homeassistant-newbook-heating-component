# Privacy Configuration

## Guest Name Data Retention

The Newbook integration creates guest name sensors (e.g., `sensor.101_guest_name`) that contain personally identifiable information (PII). For privacy compliance and data minimization, it's recommended to limit how long this information is stored in your Home Assistant history.

## Recommended Configuration

Add the following to your Home Assistant `configuration.yaml` to limit guest name history to 48 hours:

```yaml
recorder:
  # Exclude guest name sensors from long-term statistics
  exclude:
    entity_globs:
      - sensor.*_guest_name

  # Auto-purge guest name history after 2 days
  auto_purge: true
  purge_keep_days: 2
  commit_interval: 1
```

### Option 1: Exclude Guest Names Entirely (Most Private)

This option prevents guest names from being recorded in the database at all:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_guest_name
```

**Pros:**
- Maximum privacy - no guest names stored in database
- Reduces database size
- Guest names still visible in real-time on dashboards

**Cons:**
- No history graphs for guest name sensors
- Cannot review past guest names in history

### Option 2: Short Retention Period (Balanced)

This option keeps guest names for 48 hours then automatically purges them:

```yaml
recorder:
  # Global purge settings
  auto_purge: true
  purge_keep_days: 30  # Keep most data for 30 days

  # Specific entities with shorter retention
  exclude:
    entity_globs:
      - sensor.*_guest_name  # Exclude from main database

  # Alternative: Use custom component to purge specific entities
  # Note: This requires manual purge service calls or automation
```

### Option 3: Privacy-Focused Automation (Advanced)

Create an automation to regularly purge guest name history:

```yaml
automation:
  - alias: "Purge Guest Name History"
    trigger:
      - platform: time
        at: "03:00:00"  # Run daily at 3 AM
    action:
      - service: recorder.purge_entities
        data:
          entity_globs:
            - sensor.*_guest_name
          keep_days: 2  # Keep only last 2 days
```

**Note:** The `recorder.purge_entities` service requires Home Assistant 2023.4 or later.

## Additional Privacy Measures

### 1. Disable Guest Name Sensors for Specific Rooms

If certain rooms handle VIP or sensitive guests, you can disable the guest name sensor entirely:

1. Go to **Settings** → **Devices & Services** → **Entities**
2. Search for the room's guest name sensor (e.g., `sensor.presidential_suite_guest_name`)
3. Click the sensor and disable it

### 2. Exclude from Logbook

Prevent guest names from appearing in the logbook:

```yaml
logbook:
  exclude:
    entity_globs:
      - sensor.*_guest_name
```

### 3. Exclude from History Panel

Hide guest names from the history panel:

```yaml
history:
  exclude:
    entity_globs:
      - sensor.*_guest_name
```

### 4. Complete Privacy Configuration Example

Here's a complete privacy-focused configuration:

```yaml
# configuration.yaml

recorder:
  # Don't record guest names at all
  exclude:
    entity_globs:
      - sensor.*_guest_name

  # Auto-purge old data
  auto_purge: true
  purge_keep_days: 30
  commit_interval: 1

logbook:
  # Don't show guest names in logbook
  exclude:
    entity_globs:
      - sensor.*_guest_name

history:
  # Don't show guest names in history panel
  exclude:
    entity_globs:
      - sensor.*_guest_name
```

## GDPR Compliance

For hotels operating in the EU or handling EU citizen data, consider these additional measures:

### Data Subject Access Requests (DSAR)

If a guest requests their data:

1. Check the database purge schedule to determine data retention
2. Use Home Assistant's database viewer or SQL queries to extract guest-specific data
3. Provide data in a machine-readable format (JSON/CSV)

### Right to Erasure

If a guest requests data deletion:

1. Use the recorder purge service to remove specific guest data:
   ```yaml
   service: recorder.purge
   data:
     keep_days: 0
     repack: true
   ```

2. Or manually purge from the database using SQLite/PostgreSQL commands

### Data Minimization

The integration only stores:
- Guest name (from booking system)
- Booking dates
- Room assignments

No additional PII is collected beyond what's necessary for heating automation.

## Encrypted Backups

If you backup your Home Assistant instance, ensure guest data is encrypted:

1. Use Home Assistant Cloud encrypted backups, or
2. Encrypt local backups with GPG/age, or
3. Use encrypted backup storage (encrypted NAS/cloud storage)

## Database Security

Protect the Home Assistant database containing guest information:

1. Enable authentication on the database (if using external DB)
2. Use strong passwords
3. Enable SSL/TLS for database connections
4. Restrict database access to localhost or specific IPs
5. Regular security updates

## Questions?

If you have questions about privacy configuration or GDPR compliance, please open an issue on [GitHub](https://github.com/jtricerolph/homeassistant-newbook-heating-component/issues).
