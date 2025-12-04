"""Room manager for dynamic room discovery and entity tracking."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def normalize_room_id(room_id: str) -> str:
    """Normalize room ID to valid entity ID format."""
    # Remove any non-alphanumeric characters except underscores
    normalized = "".join(c if c.isalnum() or c == "_" else "_" for c in str(room_id))
    # Remove leading/trailing underscores
    normalized = normalized.strip("_")
    # Convert to lowercase
    return normalized.lower()


class RoomManager:
    """Manage room discovery and entity tracking."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the room manager."""
        self.hass = hass
        self.entry_id = entry_id
        self._discovered_rooms: set[str] = set()
        self._entity_platforms: dict[str, Any] = {}

    @callback
    def register_platform(self, platform: str, add_entities_callback: Any) -> None:
        """Register a platform's add_entities callback."""
        self._entity_platforms[platform] = add_entities_callback
        _LOGGER.debug("Registered platform: %s", platform)

    async def async_discover_rooms(self, rooms_data: dict[str, dict[str, Any]]) -> None:
        """Discover and create entities for new rooms."""
        new_rooms = set()

        for room_id, room_info in rooms_data.items():
            if room_id not in self._discovered_rooms:
                new_rooms.add(room_id)
                self._discovered_rooms.add(room_id)
                _LOGGER.info(
                    "Discovered new room: %s (%s)",
                    room_id,
                    room_info.get("site_name", f"Room {room_id}"),
                )

        if new_rooms:
            _LOGGER.info("Discovered %d new rooms, creating entities", len(new_rooms))
            # Entities will be created by the entity platforms during their setup
        else:
            _LOGGER.debug("No new rooms discovered")

    def get_discovered_rooms(self) -> set[str]:
        """Get set of discovered room IDs."""
        return self._discovered_rooms.copy()

    def is_room_discovered(self, room_id: str) -> bool:
        """Check if a room has been discovered."""
        return room_id in self._discovered_rooms

    async def async_cleanup_removed_rooms(
        self, current_rooms: dict[str, dict[str, Any]]
    ) -> None:
        """Clean up entities for rooms that no longer exist."""
        current_room_ids = set(current_rooms.keys())
        removed_rooms = self._discovered_rooms - current_room_ids

        if not removed_rooms:
            return

        _LOGGER.info("Removing entities for %d removed rooms", len(removed_rooms))

        entity_reg = er.async_get(self.hass)

        for room_id in removed_rooms:
            # Find and remove all entities for this room
            entities_to_remove = [
                entity_id
                for entity_id, entity in entity_reg.entities.items()
                if entity.config_entry_id == self.entry_id
                and entity.unique_id
                and entity.unique_id.startswith(f"{DOMAIN}_{room_id}_")
            ]

            for entity_id in entities_to_remove:
                _LOGGER.debug("Removing entity: %s", entity_id)
                entity_reg.async_remove(entity_id)

            self._discovered_rooms.discard(room_id)

    @staticmethod
    def get_room_name(room_info: dict[str, Any]) -> str:
        """Get display name for a room."""
        return room_info.get("site_name", f"Room {room_info.get('site_id', 'Unknown')}")

    @staticmethod
    def create_entity_unique_id(room_id: str, entity_type: str) -> str:
        """Create a unique ID for an entity."""
        return f"{DOMAIN}_{room_id}_{entity_type}"
