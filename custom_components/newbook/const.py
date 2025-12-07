"""Constants for the Newbook Hotel Management integration."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "newbook"

# API Configuration
API_BASE_URL: Final = "https://api.newbook.cloud/rest/"
DEFAULT_REGION: Final = "au"
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=10)

# Configuration Keys
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_API_KEY: Final = "api_key"
CONF_REGION: Final = "region"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Default Room Settings
CONF_DEFAULT_ARRIVAL_TIME: Final = "default_arrival_time"
CONF_DEFAULT_DEPARTURE_TIME: Final = "default_departure_time"
CONF_HEATING_OFFSET_MINUTES: Final = "heating_offset_minutes"
CONF_COOLING_OFFSET_MINUTES: Final = "cooling_offset_minutes"
CONF_OCCUPIED_TEMPERATURE: Final = "occupied_temperature"
CONF_VACANT_TEMPERATURE: Final = "vacant_temperature"

# TRV Monitoring Settings
CONF_MAX_RETRY_ATTEMPTS: Final = "max_retry_attempts"
CONF_COMMAND_TIMEOUT: Final = "command_timeout"
CONF_BATTERY_WARNING_THRESHOLD: Final = "battery_warning_threshold"
CONF_BATTERY_CRITICAL_THRESHOLD: Final = "battery_critical_threshold"

# Valve Sync Settings
CONF_SYNC_SETPOINTS_DEFAULT: Final = "sync_setpoints_default"
CONF_EXCLUDE_BATHROOM_DEFAULT: Final = "exclude_bathroom_default"

# Room/Category Exclusions
CONF_EXCLUDED_ROOMS: Final = "excluded_rooms"
CONF_EXCLUDED_CATEGORIES: Final = "excluded_categories"
CONF_CATEGORY_SORT_ORDER: Final = "category_sort_order"

# Defaults
DEFAULT_ARRIVAL_TIME: Final = "15:00:00"
DEFAULT_DEPARTURE_TIME: Final = "10:00:00"
DEFAULT_HEATING_OFFSET: Final = 120  # minutes
DEFAULT_COOLING_OFFSET: Final = -30  # minutes (negative = before checkout)
DEFAULT_OCCUPIED_TEMP: Final = 22.0  # °C
DEFAULT_VACANT_TEMP: Final = 16.0  # °C
DEFAULT_MAX_RETRY_ATTEMPTS: Final = 10
DEFAULT_COMMAND_TIMEOUT: Final = 60  # seconds
DEFAULT_BATTERY_WARNING: Final = 30  # %
DEFAULT_BATTERY_CRITICAL: Final = 15  # %
DEFAULT_SYNC_SETPOINTS: Final = True
DEFAULT_EXCLUDE_BATHROOM: Final = True

# Booking Statuses
BOOKING_STATUS_CONFIRMED: Final = "confirmed"
BOOKING_STATUS_UNCONFIRMED: Final = "unconfirmed"
BOOKING_STATUS_ARRIVED: Final = "arrived"
BOOKING_STATUS_DEPARTED: Final = "departed"
BOOKING_STATUS_CANCELLED: Final = "cancelled"
BOOKING_STATUS_NO_SHOW: Final = "no_show"
BOOKING_STATUS_QUOTE: Final = "quote"
BOOKING_STATUS_WAITLIST: Final = "waitlist"
BOOKING_STATUS_OWNER_OCCUPIED: Final = "owner_occupied"

# Active booking statuses (trigger heating)
ACTIVE_BOOKING_STATUSES: Final = [
    BOOKING_STATUS_CONFIRMED,
    BOOKING_STATUS_UNCONFIRMED,
    BOOKING_STATUS_ARRIVED,
]

# Room States
ROOM_STATE_VACANT: Final = "vacant"
ROOM_STATE_BOOKED: Final = "booked"
ROOM_STATE_HEATING_UP: Final = "heating_up"
ROOM_STATE_OCCUPIED: Final = "occupied"
ROOM_STATE_COOLING_DOWN: Final = "cooling_down"

# TRV Health States
TRV_HEALTH_HEALTHY: Final = "healthy"
TRV_HEALTH_DEGRADED: Final = "degraded"
TRV_HEALTH_POOR: Final = "poor"
TRV_HEALTH_UNRESPONSIVE: Final = "unresponsive"

# MQTT Topics
MQTT_TOPIC_PATTERN: Final = "shellies/room-{room_id}-{location}-trv/#"
MQTT_SETPOINT_TOPIC: Final = "shellies/room-{room_id}-{location}-trv/thermostat/0/command/target_t"

# Shelly MQTT Autodiscovery
MQTT_DISCOVERY_PREFIX: Final = "homeassistant"
SHELLY_ANNOUNCE_TOPIC: Final = "shellies/announce"
SHELLY_ONLINE_TOPIC: Final = "shellies/+/online"
SHELLY_STATUS_TOPIC: Final = "shellies/+/status"

# TRV Command Sources
TRV_SOURCE_BUTTON: Final = "button"
TRV_SOURCE_WS: Final = "WS"
TRV_SOURCE_MQTT: Final = "mqtt"
TRV_SOURCE_HTTP: Final = "http"

# Guest-initiated sources (don't sync)
GUEST_SOURCES: Final = [TRV_SOURCE_BUTTON, TRV_SOURCE_WS]

# Automation-initiated sources (can sync)
AUTOMATION_SOURCES: Final = [TRV_SOURCE_MQTT, TRV_SOURCE_HTTP]

# Retry delays (seconds) for TRV commands
RETRY_DELAYS: Final = [30, 60, 120, 300, 300, 600, 600, 900, 900, 1800]

# Events
EVENT_TRV_UNRESPONSIVE: Final = f"{DOMAIN}_trv_unresponsive"
EVENT_TRV_FAILED: Final = f"{DOMAIN}_trv_failed"
EVENT_TRV_DEGRADED: Final = f"{DOMAIN}_trv_degraded"
EVENT_ROOM_STATUS_CHANGED: Final = f"{DOMAIN}_room_status_changed"

# Services
SERVICE_REFRESH_BOOKINGS: Final = "refresh_bookings"
SERVICE_SET_ROOM_AUTO_MODE: Final = "set_room_auto_mode"
SERVICE_FORCE_ROOM_TEMPERATURE: Final = "force_room_temperature"
SERVICE_SYNC_ROOM_VALVES: Final = "sync_room_valves"
SERVICE_RETRY_UNRESPONSIVE_TRVS: Final = "retry_unresponsive_trvs"
SERVICE_CREATE_DASHBOARDS: Final = "create_dashboards"

# Platforms
PLATFORMS: Final = ["sensor", "binary_sensor", "number", "switch"]
