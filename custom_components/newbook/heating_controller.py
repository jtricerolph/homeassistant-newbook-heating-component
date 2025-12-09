"""Heating controller with state machine logic."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .booking_processor import BookingProcessor
from .const import (
    BOOKING_STATUS_ARRIVED,
    BOOKING_STATUS_DEPARTED,
    CONF_OCCUPIED_TEMPERATURE,
    CONF_VACANT_TEMPERATURE,
    DEFAULT_OCCUPIED_TEMP,
    DEFAULT_VACANT_TEMP,
    DOMAIN,
    EVENT_ROOM_STATUS_CHANGED,
    ROOM_STATE_BOOKED,
    ROOM_STATE_COOLING_DOWN,
    ROOM_STATE_HEATING_UP,
    ROOM_STATE_OCCUPIED,
    ROOM_STATE_VACANT,
)
from .coordinator import NewbookDataUpdateCoordinator
from .trv_monitor import TRVMonitor

_LOGGER = logging.getLogger(__name__)


class HeatingController:
    """Control heating based on booking data and room state."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: NewbookDataUpdateCoordinator,
        trv_monitor: TRVMonitor,
        config: dict[str, Any],
    ) -> None:
        """Initialize the heating controller."""
        self.hass = hass
        self.coordinator = coordinator
        self.trv_monitor = trv_monitor
        self.config = config
        self._room_states: dict[str, str] = {}  # Track current state per room
        self._last_booking_status: dict[str, str] = {}  # Track booking status changes

    def get_room_setting(
        self, room_id: str, setting_key: str, default: Any
    ) -> Any:
        """Get a per-room setting value."""
        room_settings = self.hass.data[DOMAIN].get("room_settings", {})
        return room_settings.get(room_id, {}).get(setting_key, default)

    def get_auto_mode(self, room_id: str) -> bool:
        """Check if auto mode is enabled for a room."""
        return self.get_room_setting(room_id, "auto_mode", True)

    def get_sync_setpoints(self, room_id: str) -> bool:
        """Check if setpoint sync is enabled for a room."""
        return self.get_room_setting(room_id, "sync_setpoints", True)

    def get_exclude_bathroom(self, room_id: str) -> bool:
        """Check if bathroom should be excluded from sync."""
        return self.get_room_setting(room_id, "exclude_bathroom_from_sync", True)

    def get_occupied_temp(self, room_id: str) -> float:
        """Get occupied temperature for a room."""
        return self.get_room_setting(
            room_id,
            CONF_OCCUPIED_TEMPERATURE,
            self.config.get(CONF_OCCUPIED_TEMPERATURE, DEFAULT_OCCUPIED_TEMP),
        )

    def get_vacant_temp(self, room_id: str) -> float:
        """Get vacant temperature for a room."""
        return self.get_room_setting(
            room_id,
            CONF_VACANT_TEMPERATURE,
            self.config.get(CONF_VACANT_TEMPERATURE, DEFAULT_VACANT_TEMP),
        )

    async def async_update_room_heating(self, room_id: str) -> None:
        """Update heating for a specific room based on current booking state.

        This is the main entry point for heating control logic.
        """
        # Get booking data
        booking = self.coordinator.get_room_booking(room_id)
        _LOGGER.debug(
            "Room %s: async_update_room_heating called - has_booking=%s, booking_data=%s",
            room_id,
            bool(booking),
            booking if booking else "None",
        )

        # Calculate heating schedule
        booking_processor = self.coordinator.booking_processor
        schedule = booking_processor.calculate_heating_schedule(room_id, booking) if booking else {}
        _LOGGER.debug("Room %s: Schedule calculated - %s", room_id, schedule if schedule else "empty")

        # Determine current room state (ALWAYS calculate, regardless of auto mode)
        new_state = booking_processor.determine_room_state(room_id, booking, schedule)
        old_state = self._room_states.get(room_id, ROOM_STATE_VACANT)
        _LOGGER.debug("Room %s: State determined - old=%s, new=%s", room_id, old_state, new_state)

        # Check for booking status changes (walk-in, early arrival, early departure)
        if booking:
            await self._handle_booking_status_change(room_id, booking, old_state, new_state)

        # Update stored state (ALWAYS update, even if auto mode is off)
        self._room_states[room_id] = new_state

        # Apply heating logic based on state (ONLY if auto mode is enabled)
        if self.get_auto_mode(room_id):
            await self._apply_heating_logic(room_id, new_state, old_state, booking, schedule)

    async def _handle_booking_status_change(
        self,
        room_id: str,
        booking: dict[str, Any],
        old_state: str,
        new_state: str,
    ) -> None:
        """Handle real-time booking status changes."""
        booking_status = booking.get("booking_status", "").lower()
        last_status = self._last_booking_status.get(room_id)

        # Detect status change
        if booking_status != last_status:
            booking_processor = self.coordinator.booking_processor
            status_changed, change_type = booking_processor.detect_status_change(
                room_id, last_status, booking_status
            )

            if status_changed:
                _LOGGER.info(
                    "Room %s: Booking status changed from %s to %s (type: %s)",
                    room_id,
                    last_status,
                    booking_status,
                    change_type,
                )

                # Fire event
                self.hass.bus.fire(
                    EVENT_ROOM_STATUS_CHANGED,
                    {
                        "room_id": room_id,
                        "old_status": last_status,
                        "new_status": booking_status,
                        "change_type": change_type,
                    },
                )

                # Handle immediate actions
                if change_type in ["arrived", "walk_in"]:
                    # Guest has arrived - ensure heating is on
                    await self._set_room_heating(room_id, "heating_up")
                elif change_type == "departed":
                    # Guest has departed - reduce heating
                    await self._set_room_cooling(room_id)

            self._last_booking_status[room_id] = booking_status

    async def _apply_heating_logic(
        self,
        room_id: str,
        new_state: str,
        old_state: str,
        booking: dict[str, Any] | None,
        schedule: dict[str, Any],
    ) -> None:
        """Apply heating based on room state with state machine logic.

        Key principle: Only set temperatures at state transitions, never during occupied state.
        This respects guest temperature adjustments.
        """
        # Check if state changed
        state_changed = new_state != old_state

        if not state_changed:
            # No state change, no action needed (respects guest adjustments)
            return

        _LOGGER.info(
            "Room %s: State transition %s → %s",
            room_id,
            old_state,
            new_state,
        )

        # State machine transitions
        if new_state in [ROOM_STATE_HEATING_UP, ROOM_STATE_OCCUPIED]:
            # Entering heating/occupied state - set to occupied temperature
            await self._set_room_heating(room_id, new_state)

        elif new_state in [ROOM_STATE_VACANT, ROOM_STATE_COOLING_DOWN, ROOM_STATE_BOOKED]:
            # Entering vacant/cooling/booked state - set to vacant temperature
            await self._set_room_cooling(room_id)

    async def _set_room_heating(self, room_id: str, state: str) -> None:
        """Set room to heating (occupied temperature)."""
        target_temp = self.get_occupied_temp(room_id)

        _LOGGER.info(
            "Room %s: Setting heating to %.1f°C (state: %s)",
            room_id,
            target_temp,
            state,
        )

        # Get ALL TRVs for this room (including bathroom)
        # Note: exclude_bathroom setting is for valve SYNC (guest adjustments), not initial heating
        trvs = self.trv_monitor.get_room_trvs(room_id)

        if not trvs:
            _LOGGER.warning("Room %s: No TRVs found", room_id)
            return

        # Set temperature with batch command (staggered)
        results = await self.trv_monitor.batch_set_room_temperature(
            room_id, trvs, target_temp
        )

        # Log results
        successful = sum(1 for success in results.values() if success)
        _LOGGER.info(
            "Room %s: Heating set - %d/%d TRVs successful",
            room_id,
            successful,
            len(trvs),
        )

    async def _set_room_cooling(self, room_id: str) -> None:
        """Set room to cooling (vacant temperature)."""
        target_temp = self.get_vacant_temp(room_id)

        _LOGGER.info(
            "Room %s: Setting cooling to %.1f°C",
            room_id,
            target_temp,
        )

        # Get TRVs for this room (include bathroom for cooling)
        trvs = self.trv_monitor.get_room_trvs(room_id)

        if not trvs:
            _LOGGER.warning("Room %s: No TRVs found", room_id)
            return

        # Set temperature with batch command (staggered)
        results = await self.trv_monitor.batch_set_room_temperature(
            room_id, trvs, target_temp
        )

        # Log results
        successful = sum(1 for success in results.values() if success)
        _LOGGER.info(
            "Room %s: Cooling set - %d/%d TRVs successful",
            room_id,
            successful,
            len(trvs),
        )

    async def async_update_all_rooms(self) -> None:
        """Update heating for all discovered rooms."""
        rooms = self.coordinator.get_all_rooms()
        _LOGGER.debug(
            "async_update_all_rooms called - updating %d rooms: %s",
            len(rooms),
            list(rooms.keys()),
        )

        for room_id in rooms:
            try:
                await self.async_update_room_heating(room_id)
            except Exception as err:
                _LOGGER.error("Error updating heating for room %s: %s", room_id, err)

    async def async_force_room_temperature(
        self,
        room_id: str,
        temperature: float,
    ) -> bool:
        """Force a specific temperature for a room (manual override).

        This disables auto mode for the room.
        """
        _LOGGER.info(
            "Room %s: Force temperature override to %.1f°C (disabling auto mode)",
            room_id,
            temperature,
        )

        # Disable auto mode
        room_settings = self.hass.data[DOMAIN].setdefault("room_settings", {})
        room_settings.setdefault(room_id, {})["auto_mode"] = False

        # Get all TRVs (include bathroom)
        trvs = self.trv_monitor.get_room_trvs(room_id)

        if not trvs:
            _LOGGER.warning("Room %s: No TRVs found", room_id)
            return False

        # Set temperature
        results = await self.trv_monitor.batch_set_room_temperature(
            room_id, trvs, temperature
        )

        # Check success
        successful = sum(1 for success in results.values() if success)
        success = successful == len(trvs)

        _LOGGER.info(
            "Room %s: Force temperature %s - %d/%d TRVs successful",
            room_id,
            "succeeded" if success else "partially failed",
            successful,
            len(trvs),
        )

        return success

    async def async_set_room_auto_mode(self, room_id: str, enabled: bool) -> None:
        """Enable or disable auto mode for a room."""
        _LOGGER.info("Room %s: Setting auto mode to %s", room_id, "enabled" if enabled else "disabled")

        room_settings = self.hass.data[DOMAIN].setdefault("room_settings", {})
        room_settings.setdefault(room_id, {})["auto_mode"] = enabled

        # If enabling auto mode, update heating immediately
        if enabled:
            await self.async_update_room_heating(room_id)

    def get_room_state(self, room_id: str) -> str:
        """Get current state for a room."""
        return self._room_states.get(room_id, ROOM_STATE_VACANT)

    def get_room_states_summary(self) -> dict[str, int]:
        """Get summary of room states."""
        summary = {
            ROOM_STATE_VACANT: 0,
            ROOM_STATE_BOOKED: 0,
            ROOM_STATE_HEATING_UP: 0,
            ROOM_STATE_OCCUPIED: 0,
            ROOM_STATE_COOLING_DOWN: 0,
        }

        for state in self._room_states.values():
            if state in summary:
                summary[state] += 1

        return summary
