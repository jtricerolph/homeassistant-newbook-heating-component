"""Sensor platform for Newbook integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ROOM_STATE_VACANT,
    SIGNAL_TRV_DISCOVERED,
    SIGNAL_TRV_STATUS_UPDATED,
)
from .coordinator import NewbookDataUpdateCoordinator
from .room_manager import RoomManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newbook sensors from a config entry."""
    coordinator: NewbookDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    # Create system-level sensors (created once)
    system_entities = [
        NewbookSystemStatusSensor(coordinator, entry.entry_id),
        NewbookLastUpdateSensor(coordinator, entry.entry_id),
        NewbookRoomsDiscoveredSensor(coordinator, entry.entry_id),
        NewbookActiveBookingsSensor(coordinator, entry.entry_id),
        NewbookTRVHealthHealthySensor(hass, entry.entry_id),
        NewbookTRVHealthDegradedSensor(hass, entry.entry_id),
        NewbookTRVHealthPoorSensor(hass, entry.entry_id),
        NewbookTRVHealthUnresponsiveSensor(hass, entry.entry_id),
        NewbookTRVHealthCalibrationErrorSensor(hass, entry.entry_id),
    ]
    async_add_entities(system_entities)

    # Track discovered rooms for THIS platform only
    discovered_rooms: set[str] = set()

    @callback
    def async_add_sensors() -> None:
        """Add sensors for all discovered rooms."""
        entities = []
        rooms = coordinator.get_all_rooms()

        for room_id, room_info in rooms.items():
            if room_id not in discovered_rooms:
                # Create all sensor types for this room
                entities.extend(
                    [
                        NewbookRoomStatusSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookGuestNameSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookArrivalSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookDepartureSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookCurrentNightSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookTotalNightsSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookHeatingStartTimeSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookCoolingStartTimeSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookBookingReferenceSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookPaxSensor(coordinator, room_id, room_info, entry.entry_id),
                        NewbookRoomStateSensor(coordinator, room_id, room_info, entry.entry_id),
                    ]
                )
                discovered_rooms.add(room_id)

        if entities:
            async_add_entities(entities)

    # Add sensors for initially discovered rooms
    async_add_sensors()

    # Listen for coordinator updates to discover new rooms
    coordinator.async_add_listener(async_add_sensors)

    # Track discovered TRVs for target temp sensors
    discovered_trvs: set[str] = set()

    @callback
    def async_add_trv_sensor(trv_info: dict) -> None:
        """Add TRV sensors when TRV is discovered via MQTT."""
        entity_id = trv_info["entity_id"]
        if entity_id in discovered_trvs:
            return

        _LOGGER.info("Creating TRV sensors for: %s", entity_id)
        discovered_trvs.add(entity_id)

        # Create both target temp and responsiveness sensors
        sensors = [
            NewbookTRVTargetTempSensor(
                hass,
                entry.entry_id,
                trv_info["site_id"],
                trv_info["location"],
                trv_info["mac"],
                entity_id,
            ),
            NewbookTRVResponsivenessSensor(
                hass,
                entry.entry_id,
                trv_info["site_id"],
                trv_info["location"],
                trv_info["mac"],
                entity_id,
            ),
        ]
        async_add_entities(sensors)

    # Listen for TRV discovery signals
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{SIGNAL_TRV_DISCOVERED}_{entry.entry_id}",
            async_add_trv_sensor,
        )
    )


class NewbookRoomSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Newbook room sensors."""

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._room_info = room_info
        self._entry_id = entry_id
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping entities."""
        return {
            "identifiers": {(DOMAIN, self._room_id)},
            "name": self._room_info.get("site_name", f"Room {self._room_id}"),
            "manufacturer": "Newbook",
            "model": self._room_info.get("site_category_name", "Hotel Room"),
            "suggested_area": self._room_info.get("site_name", f"Room {self._room_id}"),
        }

    def _get_booking_data(self) -> dict[str, Any] | None:
        """Get current booking data for the room."""
        return self.coordinator.get_room_booking(self._room_id)


class NewbookRoomStatusSensor(NewbookRoomSensorBase):
    """Sensor for room booking status."""

    _attr_icon = "mdi:bed"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_booking_status"
        self._attr_name = "Booking Status"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        booking = self._get_booking_data()
        if not booking:
            return ROOM_STATE_VACANT

        # TODO: Implement proper state machine logic in Phase 5
        # For now, return basic status
        return booking.get("booking_status", ROOM_STATE_VACANT)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        booking = self._get_booking_data()
        if not booking:
            return {"occupied": False}

        return {
            "occupied": True,
            "booking_id": booking.get("booking_id"),
            "booking_status": booking.get("booking_status"),
        }


class NewbookGuestNameSensor(NewbookRoomSensorBase):
    """Sensor for guest name."""

    _attr_icon = "mdi:account"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_guest_name"
        self._attr_name = "Guest Name"

    @property
    def native_value(self) -> str:
        """Return the guest name or Vacant."""
        booking = self._get_booking_data()
        return booking.get("guest_name", "Vacant") if booking else "Vacant"


class NewbookArrivalSensor(NewbookRoomSensorBase):
    """Sensor for arrival datetime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:airplane-landing"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_arrival"
        self._attr_name = "Arrival"

    @property
    def native_value(self) -> datetime | None:
        """Return the arrival datetime."""
        booking = self._get_booking_data()
        if not booking:
            return None

        arrival_str = booking.get("booking_arrival")
        if arrival_str:
            try:
                naive_dt = datetime.strptime(arrival_str, "%Y-%m-%d %H:%M:%S")
                return dt_util.as_local(naive_dt)
            except (ValueError, TypeError):
                return None
        return None


class NewbookDepartureSensor(NewbookRoomSensorBase):
    """Sensor for departure datetime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:airplane-takeoff"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_departure"
        self._attr_name = "Departure"

    @property
    def native_value(self) -> datetime | None:
        """Return the departure datetime."""
        booking = self._get_booking_data()
        if not booking:
            return None

        departure_str = booking.get("booking_departure")
        if departure_str:
            try:
                naive_dt = datetime.strptime(departure_str, "%Y-%m-%d %H:%M:%S")
                return dt_util.as_local(naive_dt)
            except (ValueError, TypeError):
                return None
        return None


class NewbookCurrentNightSensor(NewbookRoomSensorBase):
    """Sensor for current night of stay."""

    _attr_icon = "mdi:weather-night"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_current_night"
        self._attr_name = "Current Night"
        self._attr_native_unit_of_measurement = "nights"

    @property
    def native_value(self) -> int:
        """Return the current night number."""
        booking = self._get_booking_data()
        if not booking:
            return 0

        # Calculate current night based on arrival date
        arrival_str = booking.get("booking_arrival")
        if not arrival_str:
            return 0

        try:
            arrival = datetime.strptime(arrival_str, "%Y-%m-%d %H:%M:%S")
            today = datetime.now()
            nights_elapsed = (today.date() - arrival.date()).days + 1
            return max(0, nights_elapsed)
        except (ValueError, TypeError):
            return 0


class NewbookTotalNightsSensor(NewbookRoomSensorBase):
    """Sensor for total nights in stay."""

    _attr_icon = "mdi:calendar-range"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_total_nights"
        self._attr_name = "Total Nights"
        self._attr_native_unit_of_measurement = "nights"

    @property
    def native_value(self) -> int:
        """Return the total nights of the stay."""
        booking = self._get_booking_data()
        if not booking:
            return 0

        arrival_str = booking.get("booking_arrival")
        departure_str = booking.get("booking_departure")

        if not arrival_str or not departure_str:
            return 0

        try:
            arrival = datetime.strptime(arrival_str, "%Y-%m-%d %H:%M:%S")
            departure = datetime.strptime(departure_str, "%Y-%m-%d %H:%M:%S")
            nights = (departure.date() - arrival.date()).days
            return max(0, nights)
        except (ValueError, TypeError):
            return 0


class NewbookHeatingStartTimeSensor(NewbookRoomSensorBase):
    """Sensor for heating start time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_heating_start_time"
        self._attr_name = "Heating Start Time"

    @property
    def native_value(self) -> datetime | None:
        """Return the heating start time (arrival minus heating offset)."""
        booking = self._get_booking_data()
        if not booking:
            return None

        # Use booking processor to calculate schedule with proper offsets
        booking_processor = self.coordinator.booking_processor
        schedule = booking_processor.calculate_heating_schedule(self._room_id, booking)
        if schedule:
            heating_start = schedule.get("heating_start")
            if heating_start:
                return dt_util.as_local(heating_start)
        return None


class NewbookCoolingStartTimeSensor(NewbookRoomSensorBase):
    """Sensor for cooling start time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:radiator-off"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_cooling_start_time"
        self._attr_name = "Cooling Start Time"

    @property
    def native_value(self) -> datetime | None:
        """Return the cooling start time (departure plus cooling offset)."""
        booking = self._get_booking_data()
        if not booking:
            return None

        # Use booking processor to calculate schedule with proper offsets
        booking_processor = self.coordinator.booking_processor
        schedule = booking_processor.calculate_heating_schedule(self._room_id, booking)
        if schedule:
            cooling_start = schedule.get("cooling_start")
            if cooling_start:
                return dt_util.as_local(cooling_start)
        return None


class NewbookBookingReferenceSensor(NewbookRoomSensorBase):
    """Sensor for booking reference ID."""

    _attr_icon = "mdi:identifier"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_booking_reference"
        self._attr_name = "Booking Reference"

    @property
    def native_value(self) -> str | None:
        """Return the booking ID."""
        booking = self._get_booking_data()
        return booking.get("booking_id") if booking else None


class NewbookPaxSensor(NewbookRoomSensorBase):
    """Sensor for number of guests."""

    _attr_icon = "mdi:account-multiple"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_pax"
        self._attr_name = "Number of Guests"
        self._attr_native_unit_of_measurement = "guests"

    @property
    def native_value(self) -> int:
        """Return the number of guests."""
        booking = self._get_booking_data()
        return booking.get("pax", 0) if booking else 0


class NewbookRoomStateSensor(NewbookRoomSensorBase):
    """Sensor for room state."""

    _attr_icon = "mdi:state-machine"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, room_id, room_info, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_room_state"
        self._attr_name = "Room State"

    @property
    def native_value(self) -> str:
        """Return the current room state."""
        # Access heating_controller from hass.data using entry_id
        heating_controller = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("heating_controller")

        if heating_controller:
            return heating_controller.get_room_state(self._room_id)
        return ROOM_STATE_VACANT


class NewbookSystemSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Newbook system sensors."""

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_has_entity_name = False

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Newbook Hotel Management",
            "manufacturer": "Newbook",
            "model": "Hotel Heating Integration",
        }


class NewbookSystemStatusSensor(NewbookSystemSensorBase):
    """Sensor for system status."""

    _attr_icon = "mdi:information"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_system_status"
        self._attr_name = "Newbook System Status"

    @property
    def native_value(self) -> str:
        """Return the system status."""
        if self.coordinator.last_update_success:
            return "Online"
        return "Offline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "last_update_success": self.coordinator.last_update_success,
        }
        if self.coordinator.last_update_success and self.coordinator.data:
            attrs["last_update"] = self.coordinator.data.get("last_update")
        return attrs


class NewbookLastUpdateSensor(NewbookSystemSensorBase):
    """Sensor for last update time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_last_update"
        self._attr_name = "Newbook Last Update"

    @property
    def native_value(self) -> datetime | None:
        """Return the last update time."""
        if self.coordinator.last_update_success and self.coordinator.data:
            last_update_str = self.coordinator.data.get("last_update")
            if last_update_str:
                try:
                    naive_dt = datetime.fromisoformat(last_update_str)
                    return dt_util.as_local(naive_dt)
                except (ValueError, TypeError):
                    pass
        return None


class NewbookRoomsDiscoveredSensor(NewbookSystemSensorBase):
    """Sensor for number of discovered rooms."""

    _attr_icon = "mdi:bed-empty"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "rooms"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_rooms_discovered"
        self._attr_name = "Newbook Rooms Discovered"

    @property
    def native_value(self) -> int:
        """Return the number of discovered rooms."""
        rooms = self.coordinator.get_all_rooms()
        return len(rooms)


class NewbookActiveBookingsSensor(NewbookSystemSensorBase):
    """Sensor for number of active bookings."""

    _attr_icon = "mdi:calendar-check"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "bookings"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_active_bookings"
        self._attr_name = "Newbook Active Bookings"

    @property
    def native_value(self) -> int:
        """Return the number of active bookings."""
        if not self.coordinator.data:
            return 0

        bookings_dict = self.coordinator.data.get("bookings", {})
        # Bookings is a dict keyed by site_id, flatten to list
        all_bookings = []
        for site_bookings in bookings_dict.values():
            all_bookings.extend(site_bookings)

        # Count bookings that are not "departed"
        active = [b for b in all_bookings if b.get("booking_status", "").lower() != "departed"]
        return len(active)


class NewbookTRVHealthSensorBase(SensorEntity):
    """Base class for TRV health sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "TRVs"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Newbook Hotel Heating",
            "manufacturer": "Newbook",
            "model": "Hotel Heating Control",
        }

    def _get_health_summary(self) -> dict[str, Any]:
        """Get health summary from TRV monitor."""
        try:
            trv_monitor = self.hass.data[DOMAIN][self._entry_id].get("trv_monitor")
            if trv_monitor:
                return trv_monitor.get_health_summary()
        except (KeyError, AttributeError):
            pass
        return {"healthy": 0, "degraded": 0, "poor": 0, "unresponsive": 0}


class NewbookTRVHealthHealthySensor(NewbookTRVHealthSensorBase):
    """Sensor for number of healthy TRVs."""

    _attr_icon = "mdi:check-circle"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_trv_health_healthy"
        self._attr_name = "Newbook TRV Health Healthy"

    @property
    def native_value(self) -> int:
        """Return the number of healthy TRVs."""
        return self._get_health_summary().get("healthy", 0)


class NewbookTRVHealthDegradedSensor(NewbookTRVHealthSensorBase):
    """Sensor for number of degraded TRVs."""

    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_trv_health_degraded"
        self._attr_name = "Newbook TRV Health Degraded"

    @property
    def native_value(self) -> int:
        """Return the number of degraded TRVs."""
        return self._get_health_summary().get("degraded", 0)


class NewbookTRVHealthPoorSensor(NewbookTRVHealthSensorBase):
    """Sensor for number of poor health TRVs."""

    _attr_icon = "mdi:alert"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_trv_health_poor"
        self._attr_name = "Newbook TRV Health Poor"

    @property
    def native_value(self) -> int:
        """Return the number of poor health TRVs."""
        return self._get_health_summary().get("poor", 0)


class NewbookTRVHealthUnresponsiveSensor(NewbookTRVHealthSensorBase):
    """Sensor for number of unresponsive TRVs."""

    _attr_icon = "mdi:alert-octagon"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_trv_health_unresponsive"
        self._attr_name = "Newbook TRV Health Unresponsive"

    @property
    def native_value(self) -> int:
        """Return the number of unresponsive TRVs."""
        return self._get_health_summary().get("unresponsive", 0)


class NewbookTRVHealthCalibrationErrorSensor(NewbookTRVHealthSensorBase):
    """Sensor for number of TRVs with calibration errors."""

    _attr_icon = "mdi:wrench-clock"

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(hass, entry_id)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_trv_health_calibration_error"
        self._attr_name = "Newbook TRV Health Calibration Error"

    @property
    def native_value(self) -> int:
        """Return the number of TRVs with calibration errors."""
        return self._get_health_summary().get("calibration_error", 0)


class NewbookTRVTargetTempSensor(SensorEntity):
    """Per-TRV target temperature sensor with origin detection.

    This sensor shows the current target temperature from the device status,
    with an 'origin' attribute indicating whether the last change was from
    automation (HA) or guest (physical button/web UI).
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"
    _attr_has_entity_name = True
    _attr_should_poll = False  # We update via dispatcher signals

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        site_id: str,
        location: str,
        mac: str,
        climate_entity_id: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._site_id = site_id
        self._location = location
        self._mac = mac
        self._climate_entity_id = climate_entity_id

        self._attr_unique_id = f"shelly_{mac}_target_temp"
        self._attr_name = "Target Temperature"

        # Link to the TRV device (same device as climate entity)
        # MQTT discovery creates devices with identifiers as ("mqtt", "shelly_{mac}")
        self._attr_device_info = DeviceInfo(
            identifiers={("mqtt", f"shelly_{mac}")},
        )

    async def async_added_to_hass(self) -> None:
        """Register for status update signals when added to hass."""
        await super().async_added_to_hass()

        @callback
        def handle_status_update(updated_entity_id: str) -> None:
            """Handle TRV status update signal."""
            if updated_entity_id == self._climate_entity_id:
                self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_TRV_STATUS_UPDATED}_{self._entry_id}",
                handle_status_update,
            )
        )

    def _get_trv_health(self):
        """Get TRVHealth instance for this TRV."""
        try:
            trv_monitor = self.hass.data[DOMAIN][self._entry_id].get("trv_monitor")
            if trv_monitor:
                return trv_monitor.get_trv_health(self._climate_entity_id)
        except (KeyError, AttributeError):
            pass
        return None

    @property
    def native_value(self) -> float | None:
        """Return the current target temperature from device status."""
        health = self._get_trv_health()
        if health:
            return health.current_target_temp
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return origin and command tracking attributes."""
        health = self._get_trv_health()
        if not health:
            return {
                "origin": "unknown",
                "ha_last_command": None,
                "ha_command_time": None,
                "status_update_time": None,
            }

        return {
            "origin": health.target_temp_origin,
            "ha_last_command": health.ha_last_command_temp,
            "ha_command_time": (
                health.ha_last_command_time.isoformat()
                if health.ha_last_command_time
                else None
            ),
            "status_update_time": (
                health.status_update_time.isoformat()
                if health.status_update_time
                else None
            ),
            "climate_entity": self._climate_entity_id,
        }


class NewbookTRVResponsivenessSensor(SensorEntity):
    """Per-TRV responsiveness health sensor.

    Shows the health state of the TRV (healthy/degraded/poor/unresponsive/calibration_error)
    with response time statistics as attributes.
    """

    _attr_icon = "mdi:heart-pulse"
    _attr_has_entity_name = True
    _attr_should_poll = False  # We update via dispatcher signals

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        site_id: str,
        location: str,
        mac: str,
        climate_entity_id: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._site_id = site_id
        self._location = location
        self._mac = mac
        self._climate_entity_id = climate_entity_id

        self._attr_unique_id = f"shelly_{mac}_responsiveness"
        self._attr_name = "Responsiveness"

        # Link to the TRV device (same device as climate entity)
        # MQTT discovery creates devices with identifiers as ("mqtt", "shelly_{mac}")
        self._attr_device_info = DeviceInfo(
            identifiers={("mqtt", f"shelly_{mac}")},
        )

    async def async_added_to_hass(self) -> None:
        """Register for status update signals when added to hass."""
        await super().async_added_to_hass()

        @callback
        def handle_status_update(updated_entity_id: str) -> None:
            """Handle TRV status update signal."""
            if updated_entity_id == self._climate_entity_id:
                self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_TRV_STATUS_UPDATED}_{self._entry_id}",
                handle_status_update,
            )
        )

    def _get_trv_health(self):
        """Get TRVHealth instance for this TRV."""
        try:
            trv_monitor = self.hass.data[DOMAIN][self._entry_id].get("trv_monitor")
            if trv_monitor:
                return trv_monitor.get_trv_health(self._climate_entity_id)
        except (KeyError, AttributeError):
            pass
        return None

    @property
    def native_value(self) -> str:
        """Return the health state."""
        health = self._get_trv_health()
        if health:
            return health.health_state
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return response time statistics and health details."""
        health = self._get_trv_health()
        if not health:
            return {
                "avg_response_time": None,
                "min_response_time": None,
                "max_response_time": None,
                "total_commands_72h": 0,
                "failed_commands_72h": 0,
                "success_rate": None,
                "valve_position": None,
                "is_calibrated": None,
                "last_seen": None,
                "current_attempts": 0,
                "retry_count_24h": 0,
            }

        stats = health.get_response_stats_72h()

        return {
            "avg_response_time": (
                round(stats["avg_response_time"], 1)
                if stats["avg_response_time"]
                else None
            ),
            "min_response_time": (
                round(stats["min_response_time"], 1)
                if stats["min_response_time"]
                else None
            ),
            "max_response_time": (
                round(stats["max_response_time"], 1)
                if stats["max_response_time"]
                else None
            ),
            "total_commands_72h": stats["total_commands_72h"],
            "failed_commands_72h": stats["failed_commands_72h"],
            "success_rate": (
                round(stats["success_rate"], 1)
                if stats["success_rate"]
                else None
            ),
            "valve_position": health.valve_position,
            "is_calibrated": health.is_calibrated,
            "last_seen": (
                health.last_seen.isoformat()
                if health.last_seen
                else None
            ),
            "current_attempts": health.current_attempts,
            "retry_count_24h": health.retry_count_24h,
            "climate_entity": self._climate_entity_id,
        }
