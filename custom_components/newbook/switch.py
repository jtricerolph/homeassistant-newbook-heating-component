"""Switch platform for Newbook integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_EXCLUDE_BATHROOM_DEFAULT,
    CONF_SYNC_SETPOINTS_DEFAULT,
    DEFAULT_EXCLUDE_BATHROOM,
    DEFAULT_SYNC_SETPOINTS,
    DOMAIN,
)
from .coordinator import NewbookDataUpdateCoordinator
from .room_manager import RoomManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newbook switch entities from a config entry."""
    coordinator: NewbookDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    room_manager: RoomManager = hass.data[DOMAIN][entry.entry_id]["room_manager"]
    config = entry

    @callback
    def async_add_switches() -> None:
        """Add switch entities for all discovered rooms."""
        entities = []
        rooms = coordinator.get_all_rooms()

        for room_id, room_info in rooms.items():
            if not room_manager.is_room_discovered(room_id):
                # Create all switch entities for this room
                entities.extend(
                    [
                        NewbookAutoModeSwitch(coordinator, room_id, room_info, config),
                        NewbookSyncSetpointsSwitch(
                            coordinator, room_id, room_info, config
                        ),
                        NewbookExcludeBathroomSwitch(
                            coordinator, room_id, room_info, config
                        ),
                    ]
                )

        if entities:
            async_add_entities(entities)
            # Mark rooms as discovered
            for room_id in rooms:
                if not room_manager.is_room_discovered(room_id):
                    room_manager._discovered_rooms.add(room_id)

    # Add switches for initially discovered rooms
    async_add_switches()

    # Listen for coordinator updates to discover new rooms
    coordinator.async_add_listener(async_add_switches)


class NewbookRoomSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for Newbook room switch entities."""

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._room_info = room_info
        self._config = config
        self._attr_has_entity_name = True
        self._storage_key = None

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

    def _get_stored_value(self, default: bool) -> bool:
        """Get stored value from hass.data."""
        if self._storage_key is None:
            return default

        storage = self.hass.data[DOMAIN].setdefault("room_settings", {})
        room_settings = storage.setdefault(self._room_id, {})
        return room_settings.get(self._storage_key, default)

    async def _set_stored_value(self, value: bool) -> None:
        """Store value in hass.data."""
        if self._storage_key is None:
            return

        storage = self.hass.data[DOMAIN].setdefault("room_settings", {})
        room_settings = storage.setdefault(self._room_id, {})
        room_settings[self._storage_key] = value
        self.async_write_ha_state()


class NewbookAutoModeSwitch(NewbookRoomSwitchBase):
    """Switch for automatic heating mode."""

    _attr_icon = "mdi:thermostat-auto"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_auto_mode"
        self._attr_name = "Auto Mode"
        self._storage_key = "auto_mode"
        self._default_value = True  # Auto mode enabled by default

    @property
    def is_on(self) -> bool:
        """Return True if auto mode is enabled."""
        return self._get_stored_value(self._default_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on auto mode."""
        await self._set_stored_value(True)
        _LOGGER.info("Room %s: Auto mode enabled", self._room_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off auto mode."""
        await self._set_stored_value(False)
        _LOGGER.info("Room %s: Auto mode disabled (manual control)", self._room_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "description": "Enable automatic heating control based on bookings",
        }


class NewbookSyncSetpointsSwitch(NewbookRoomSwitchBase):
    """Switch for room setpoint synchronization."""

    _attr_icon = "mdi:sync"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_sync_setpoints"
        self._attr_name = "Sync Setpoints"
        self._storage_key = "sync_setpoints"

        # Get default from config
        self._default_value = config.options.get(
            CONF_SYNC_SETPOINTS_DEFAULT,
            config.data.get(CONF_SYNC_SETPOINTS_DEFAULT, DEFAULT_SYNC_SETPOINTS),
        )

    @property
    def is_on(self) -> bool:
        """Return True if sync is enabled."""
        return self._get_stored_value(self._default_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable setpoint synchronization."""
        await self._set_stored_value(True)
        _LOGGER.info("Room %s: Valve sync enabled", self._room_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable setpoint synchronization."""
        await self._set_stored_value(False)
        _LOGGER.info("Room %s: Valve sync disabled (independent control)", self._room_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "description": "Sync all TRV valves in room to same temperature",
        }


class NewbookExcludeBathroomSwitch(NewbookRoomSwitchBase):
    """Switch for excluding bathroom from sync."""

    _attr_icon = "mdi:shower"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_exclude_bathroom_from_sync"
        self._attr_name = "Exclude Bathroom from Sync"
        self._storage_key = "exclude_bathroom_from_sync"

        # Get default from config
        self._default_value = config.options.get(
            CONF_EXCLUDE_BATHROOM_DEFAULT,
            config.data.get(CONF_EXCLUDE_BATHROOM_DEFAULT, DEFAULT_EXCLUDE_BATHROOM),
        )

    @property
    def is_on(self) -> bool:
        """Return True if bathroom is excluded."""
        return self._get_stored_value(self._default_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Exclude bathroom from sync."""
        await self._set_stored_value(True)
        _LOGGER.info("Room %s: Bathroom excluded from sync", self._room_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Include bathroom in sync."""
        await self._set_stored_value(False)
        _LOGGER.info("Room %s: Bathroom included in sync", self._room_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "description": "Keep bathroom valve independent from bedroom valves",
        }
