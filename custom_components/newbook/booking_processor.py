"""Booking data processing and heating schedule calculations."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
from typing import Any

from .const import (
    ACTIVE_BOOKING_STATUSES,
    BOOKING_STATUS_ARRIVED,
    BOOKING_STATUS_DEPARTED,
    CONF_COOLING_OFFSET_MINUTES,
    CONF_DEFAULT_ARRIVAL_TIME,
    CONF_DEFAULT_DEPARTURE_TIME,
    CONF_HEATING_OFFSET_MINUTES,
    DEFAULT_ARRIVAL_TIME,
    DEFAULT_COOLING_OFFSET,
    DEFAULT_DEPARTURE_TIME,
    DEFAULT_HEATING_OFFSET,
    ROOM_STATE_BOOKED,
    ROOM_STATE_COOLING_DOWN,
    ROOM_STATE_HEATING_UP,
    ROOM_STATE_OCCUPIED,
    ROOM_STATE_VACANT,
)

_LOGGER = logging.getLogger(__name__)


class BookingProcessor:
    """Process booking data and calculate heating schedules."""

    def __init__(self, config: dict[str, Any], room_settings: dict[str, Any]) -> None:
        """Initialize the booking processor."""
        self.config = config
        self.room_settings = room_settings

    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        try:
            return datetime.strptime(time_str, "%H:%M:%S").time()
        except (ValueError, TypeError):
            try:
                return datetime.strptime(time_str, "%H:%M").time()
            except (ValueError, TypeError):
                _LOGGER.error("Invalid time format: %s", time_str)
                return time(15, 0)  # Default to 3 PM

    def _parse_datetime(self, datetime_str: str) -> datetime | None:
        """Parse datetime string to datetime object."""
        if not datetime_str:
            return None

        try:
            return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                return datetime.strptime(datetime_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                _LOGGER.error("Invalid datetime format: %s", datetime_str)
                return None

    def get_room_setting(
        self, room_id: str, setting_key: str, default: Any
    ) -> Any:
        """Get a per-room setting value."""
        return self.room_settings.get(room_id, {}).get(setting_key, default)

    def get_default_arrival_time(self) -> time:
        """Get default arrival time from config."""
        time_str = self.config.get(CONF_DEFAULT_ARRIVAL_TIME, DEFAULT_ARRIVAL_TIME)
        return self._parse_time(time_str)

    def get_default_departure_time(self) -> time:
        """Get default departure time from config."""
        time_str = self.config.get(
            CONF_DEFAULT_DEPARTURE_TIME, DEFAULT_DEPARTURE_TIME
        )
        return self._parse_time(time_str)

    def calculate_heating_schedule(
        self, room_id: str, booking_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate heating schedule for a booking.

        Returns:
            dict with:
            - heating_start: datetime when heating should start
            - cooling_start: datetime when heating should stop
            - arrival: actual arrival datetime
            - departure: actual departure datetime
        """
        if not booking_data:
            return {}

        # Get actual booking times
        arrival_dt = self._parse_datetime(booking_data.get("booking_arrival"))
        departure_dt = self._parse_datetime(booking_data.get("booking_departure"))

        if not arrival_dt or not departure_dt:
            _LOGGER.warning("Invalid arrival/departure times for room %s", room_id)
            return {}

        # Get default times
        default_arrival_time = self.get_default_arrival_time()
        default_departure_time = self.get_default_departure_time()

        # Use earlier of actual or default arrival time
        actual_arrival_time = arrival_dt.time()
        earliest_arrival_time = min(actual_arrival_time, default_arrival_time)
        arrival_datetime = datetime.combine(arrival_dt.date(), earliest_arrival_time)

        # Use later of actual or default departure time
        actual_departure_time = departure_dt.time()
        latest_departure_time = max(actual_departure_time, default_departure_time)
        departure_datetime = datetime.combine(
            departure_dt.date(), latest_departure_time
        )

        # Get offsets from room settings
        heating_offset = self.get_room_setting(
            room_id,
            CONF_HEATING_OFFSET_MINUTES,
            self.config.get(CONF_HEATING_OFFSET_MINUTES, DEFAULT_HEATING_OFFSET),
        )
        cooling_offset = self.get_room_setting(
            room_id,
            CONF_COOLING_OFFSET_MINUTES,
            self.config.get(CONF_COOLING_OFFSET_MINUTES, DEFAULT_COOLING_OFFSET),
        )

        # Calculate heating start time (subtract offset)
        heating_start = arrival_datetime - timedelta(minutes=heating_offset)

        # Calculate cooling start time (add offset, can be negative)
        cooling_start = departure_datetime + timedelta(minutes=cooling_offset)

        _LOGGER.debug(
            "Room %s heating schedule: heat from %s to %s",
            room_id,
            heating_start.isoformat(),
            cooling_start.isoformat(),
        )

        return {
            "heating_start": heating_start,
            "cooling_start": cooling_start,
            "arrival": arrival_datetime,
            "departure": departure_datetime,
        }

    def determine_room_state(
        self,
        room_id: str,
        booking_data: dict[str, Any] | None,
        schedule: dict[str, Any],
    ) -> str:
        """Determine current room state based on booking and schedule.

        Priority order:
        1. Booking status (arrived/departed override everything)
        2. Time-based state (heating_up/occupied based on schedule)
        3. Vacant if no booking
        """
        now = datetime.now()

        # No booking = vacant
        if not booking_data:
            return ROOM_STATE_VACANT

        booking_status_raw = booking_data.get("booking_status", "")
        booking_status = booking_status_raw.lower()

        _LOGGER.debug(
            "Room %s booking status: raw='%s', lowercased='%s', ARRIVED='%s', DEPARTED='%s'",
            room_id,
            booking_status_raw,
            booking_status,
            BOOKING_STATUS_ARRIVED,
            BOOKING_STATUS_DEPARTED,
        )

        # Priority 1: Explicit departed status
        if booking_status == BOOKING_STATUS_DEPARTED:
            _LOGGER.debug("Room %s: Status is DEPARTED, returning COOLING_DOWN", room_id)
            return ROOM_STATE_COOLING_DOWN

        # Priority 2: Explicit arrived status
        if booking_status == BOOKING_STATUS_ARRIVED:
            _LOGGER.debug("Room %s: Status is ARRIVED, returning OCCUPIED", room_id)
            return ROOM_STATE_OCCUPIED

        # Priority 3: Time-based state determination
        if not schedule:
            # Booking exists but no valid schedule
            return ROOM_STATE_BOOKED

        heating_start = schedule.get("heating_start")
        cooling_start = schedule.get("cooling_start")
        arrival = schedule.get("arrival")

        if not heating_start or not cooling_start:
            return ROOM_STATE_BOOKED

        # Check if we're in the heating up phase
        if heating_start <= now < arrival:
            return ROOM_STATE_HEATING_UP

        # Check if we're in occupied period (after arrival, before cooling)
        if arrival <= now < cooling_start:
            return ROOM_STATE_OCCUPIED

        # Check if we're in cooling down phase
        if now >= cooling_start:
            return ROOM_STATE_COOLING_DOWN

        # Before heating starts = booked but not heating yet
        if now < heating_start:
            return ROOM_STATE_BOOKED

        return ROOM_STATE_VACANT

    def should_heat(
        self,
        room_id: str,
        booking_data: dict[str, Any] | None,
        room_state: str,
        auto_mode: bool = True,
    ) -> bool:
        """Determine if room should be heating now.

        Args:
            room_id: Room identifier
            booking_data: Current booking data
            room_state: Current room state
            auto_mode: Whether auto mode is enabled

        Returns:
            True if room should be heated
        """
        # Auto mode must be enabled
        if not auto_mode:
            return False

        # No booking = no heating
        if not booking_data:
            return False

        # Check booking status is active
        booking_status_raw = booking_data.get("booking_status", "")
        booking_status = booking_status_raw.lower()
        is_active = booking_status in ACTIVE_BOOKING_STATUSES

        _LOGGER.debug(
            "Room %s should_heat: status='%s' (raw='%s'), is_active=%s, room_state='%s', auto_mode=%s",
            room_id,
            booking_status,
            booking_status_raw,
            is_active,
            room_state,
            auto_mode,
        )

        if booking_status not in ACTIVE_BOOKING_STATUSES:
            _LOGGER.debug("Room %s: Booking status not active, not heating", room_id)
            return False

        # Heat in these states
        should_heat = room_state in [ROOM_STATE_HEATING_UP, ROOM_STATE_OCCUPIED]
        _LOGGER.debug("Room %s: Should heat = %s", room_id, should_heat)
        return should_heat

    def calculate_current_night(self, booking_data: dict[str, Any] | None) -> int:
        """Calculate which night of the stay we're currently on.

        Returns 0 if no booking, 1 on first night, 2 on second night, etc.
        """
        if not booking_data:
            return 0

        arrival_str = booking_data.get("booking_arrival")
        if not arrival_str:
            return 0

        arrival = self._parse_datetime(arrival_str)
        if not arrival:
            return 0

        today = datetime.now()
        nights_elapsed = (today.date() - arrival.date()).days + 1

        return max(0, nights_elapsed)

    def calculate_total_nights(self, booking_data: dict[str, Any] | None) -> int:
        """Calculate total nights for the booking.

        Returns 0 if no booking.
        """
        if not booking_data:
            return 0

        arrival_str = booking_data.get("booking_arrival")
        departure_str = booking_data.get("booking_departure")

        if not arrival_str or not departure_str:
            return 0

        arrival = self._parse_datetime(arrival_str)
        departure = self._parse_datetime(departure_str)

        if not arrival or not departure:
            return 0

        nights = (departure.date() - arrival.date()).days
        return max(0, nights)

    def detect_status_change(
        self,
        room_id: str,
        old_status: str | None,
        new_status: str | None,
    ) -> tuple[bool, str | None]:
        """Detect if booking status has changed.

        Returns:
            (status_changed: bool, change_type: str | None)
            change_type can be: 'arrived', 'departed', or None
        """
        if old_status == new_status:
            return False, None

        # Detect arrival
        if (
            old_status
            and old_status != BOOKING_STATUS_ARRIVED
            and new_status == BOOKING_STATUS_ARRIVED
        ):
            _LOGGER.info("Room %s: Guest has arrived (status change)", room_id)
            return True, "arrived"

        # Detect departure
        if new_status == BOOKING_STATUS_DEPARTED:
            _LOGGER.info("Room %s: Guest has departed (status change)", room_id)
            return True, "departed"

        # Handle walk-in (booking appears with arrived status)
        if not old_status and new_status == BOOKING_STATUS_ARRIVED:
            _LOGGER.info("Room %s: Walk-in booking detected", room_id)
            return True, "walk_in"

        return False, None

    def get_room_flow_type(
        self,
        room_id: str,
        bookings: list[dict[str, Any]],
        target_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Determine the booking flow type for a room on a specific date.

        Args:
            room_id: Room identifier
            bookings: List of all bookings for the room
            target_date: Date to check (defaults to today)

        Returns:
            dict with:
            - type: 'vacant', 'arrive', 'depart', 'stay_over', 'depart_arrive'
            - arriving_booking: booking dict if arriving
            - departing_booking: booking dict if departing
            - staying_booking: booking dict if staying over
        """
        if target_date is None:
            target_date = datetime.now()

        target_date_str = target_date.date().isoformat()

        arriving = None
        departing = None
        staying = None

        for booking in bookings:
            arrival = self._parse_datetime(booking.get("booking_arrival"))
            departure = self._parse_datetime(booking.get("booking_departure"))

            if not arrival or not departure:
                continue

            arrival_date = arrival.date().isoformat()
            departure_date = departure.date().isoformat()

            # Check if arriving today
            if arrival_date == target_date_str:
                arriving = booking

            # Check if departing today (but didn't arrive today)
            if departure_date == target_date_str and arrival_date < target_date_str:
                departing = booking

            # Check if staying through (not arriving or departing today)
            if arrival_date < target_date_str and departure_date > target_date_str:
                staying = booking

        # Determine flow type
        if arriving and departing:
            return {
                "type": "depart_arrive",
                "arriving_booking": arriving,
                "departing_booking": departing,
            }
        elif arriving:
            return {"type": "arrive", "booking": arriving}
        elif departing:
            return {"type": "depart", "booking": departing}
        elif staying:
            return {"type": "stay_over", "booking": staying}

        return {"type": "vacant"}
