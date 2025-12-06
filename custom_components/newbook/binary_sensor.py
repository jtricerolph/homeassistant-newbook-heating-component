"""Binary sensor platform for Newbook integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NewbookDataUpdateCoordinator
from .room_manager import RoomManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newbook binary sensors from a config entry."""
    coordinator: NewbookDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    room_manager: RoomManager = hass.data[DOMAIN][entry.entry_id]["room_manager"]

    @callback
    def async_add_binary_sensors() -> None:
        """Add binary sensors for all discovered rooms."""
        entities = []
        rooms = coordinator.get_all_rooms()

        for room_id, room_info in rooms.items():
            if not room_manager.is_room_discovered(room_id):
                # Create binary sensor for heating state
                entities.append(
                    NewbookShouldHeatBinarySensor(coordinator, room_id, room_info)
                )

        if entities:
            async_add_entities(entities)
            # Mark rooms as discovered
            for room_id in rooms:
                if not room_manager.is_room_discovered(room_id):
                    room_manager._discovered_rooms.add(room_id)

    # Add binary sensors for initially discovered rooms
    async_add_binary_sensors()

    # Listen for coordinator updates to discover new rooms
    coordinator.async_add_listener(async_add_binary_sensors)


class NewbookRoomBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Newbook room binary sensors."""

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._room_info = room_info
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping entities."""
        return {
            "identifiers": {(DOMAIN, self._room_id)},
            "name": self._room_info.get("site_name", f"Room {self._room_id}"),
            "manufacturer": "Newbook",
            "model": self._room_info.get("site_category_name", "Hotel Room"),
            "suggested_area": f"Room {self._room_id}",
        }

    def _get_booking_data(self) -> dict[str, Any] | None:
        """Get current booking data for the room."""
        return self.coordinator.get_room_booking(self._room_id)


class NewbookShouldHeatBinarySensor(NewbookRoomBinarySensorBase):
    """Binary sensor indicating if room should be heated."""

    _attr_icon = "mdi:radiator"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, room_id, room_info)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_should_heat"
        self._attr_name = "Should Heat"

    @property
    def is_on(self) -> bool:
        """Return True if room should be heated."""
        # TODO: Implement proper heating logic in Phase 5
        # For now, return True if room has an active booking
        booking = self._get_booking_data()
        if not booking:
            return False

        # Simple logic: if there's a booking, should heat
        # This will be replaced with proper state machine logic
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        booking = self._get_booking_data()
        if not booking:
            return {"reason": "no_booking"}

        return {
            "reason": "has_booking",
            "booking_status": booking.get("booking_status"),
            "booking_id": booking.get("booking_id"),
        }
