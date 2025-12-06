"""Number platform for Newbook integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_COOLING_OFFSET_MINUTES,
    CONF_HEATING_OFFSET_MINUTES,
    CONF_OCCUPIED_TEMPERATURE,
    CONF_VACANT_TEMPERATURE,
    DEFAULT_COOLING_OFFSET,
    DEFAULT_HEATING_OFFSET,
    DEFAULT_OCCUPIED_TEMP,
    DEFAULT_VACANT_TEMP,
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
    """Set up Newbook number entities from a config entry."""
    coordinator: NewbookDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    config = entry

    # Track discovered rooms for THIS platform only
    discovered_rooms: set[str] = set()

    @callback
    def async_add_numbers() -> None:
        """Add number entities for all discovered rooms."""
        entities = []
        rooms = coordinator.get_all_rooms()

        for room_id, room_info in rooms.items():
            if room_id not in discovered_rooms:
                # Create all number entities for this room
                entities.extend(
                    [
                        NewbookHeatingOffsetNumber(
                            coordinator, room_id, room_info, config
                        ),
                        NewbookCoolingOffsetNumber(
                            coordinator, room_id, room_info, config
                        ),
                        NewbookOccupiedTempNumber(
                            coordinator, room_id, room_info, config
                        ),
                        NewbookVacantTempNumber(
                            coordinator, room_id, room_info, config
                        ),
                    ]
                )
                discovered_rooms.add(room_id)

        if entities:
            async_add_entities(entities)

    # Add numbers for initially discovered rooms
    async_add_numbers()

    # Listen for coordinator updates to discover new rooms
    coordinator.async_add_listener(async_add_numbers)


class NewbookRoomNumberBase(CoordinatorEntity, NumberEntity):
    """Base class for Newbook room number entities."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._room_info = room_info
        self._config = config
        self._attr_has_entity_name = True
        # Store values in hass.data
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

    def _get_stored_value(self, default: float) -> float:
        """Get stored value from hass.data."""
        if self._storage_key is None:
            return default

        storage = self.hass.data[DOMAIN].setdefault("room_settings", {})
        room_settings = storage.setdefault(self._room_id, {})
        return room_settings.get(self._storage_key, default)

    async def _set_stored_value(self, value: float) -> None:
        """Store value in hass.data."""
        if self._storage_key is None:
            return

        storage = self.hass.data[DOMAIN].setdefault("room_settings", {})
        room_settings = storage.setdefault(self._room_id, {})
        room_settings[self._storage_key] = value
        self.async_write_ha_state()


class NewbookHeatingOffsetNumber(NewbookRoomNumberBase):
    """Number entity for heating offset minutes."""

    _attr_icon = "mdi:timer"
    _attr_native_min_value = 0
    _attr_native_max_value = 720  # 12 hours
    _attr_native_step = 15
    _attr_native_unit_of_measurement = "min"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_heating_offset_minutes"
        self._attr_name = "Heating Offset"
        self._storage_key = "heating_offset_minutes"

        # Get default from config
        self._default_value = config.options.get(
            CONF_HEATING_OFFSET_MINUTES,
            config.data.get(CONF_HEATING_OFFSET_MINUTES, DEFAULT_HEATING_OFFSET),
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._get_stored_value(self._default_value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._set_stored_value(value)


class NewbookCoolingOffsetNumber(NewbookRoomNumberBase):
    """Number entity for cooling offset minutes."""

    _attr_icon = "mdi:timer-off"
    _attr_native_min_value = -180  # Can be negative (before checkout)
    _attr_native_max_value = 180  # 3 hours
    _attr_native_step = 15
    _attr_native_unit_of_measurement = "min"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_cooling_offset_minutes"
        self._attr_name = "Cooling Offset"
        self._storage_key = "cooling_offset_minutes"

        # Get default from config
        self._default_value = config.options.get(
            CONF_COOLING_OFFSET_MINUTES,
            config.data.get(CONF_COOLING_OFFSET_MINUTES, DEFAULT_COOLING_OFFSET),
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._get_stored_value(self._default_value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._set_stored_value(value)


class NewbookOccupiedTempNumber(NewbookRoomNumberBase):
    """Number entity for occupied temperature."""

    _attr_icon = "mdi:thermometer-chevron-up"
    _attr_native_min_value = 10.0
    _attr_native_max_value = 30.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_occupied_temperature"
        self._attr_name = "Occupied Temperature"
        self._storage_key = "occupied_temperature"

        # Get default from config
        self._default_value = config.options.get(
            CONF_OCCUPIED_TEMPERATURE,
            config.data.get(CONF_OCCUPIED_TEMPERATURE, DEFAULT_OCCUPIED_TEMP),
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._get_stored_value(self._default_value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._set_stored_value(value)


class NewbookVacantTempNumber(NewbookRoomNumberBase):
    """Number entity for vacant temperature."""

    _attr_icon = "mdi:thermometer-chevron-down"
    _attr_native_min_value = 5.0
    _attr_native_max_value = 25.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        coordinator: NewbookDataUpdateCoordinator,
        room_id: str,
        room_info: dict[str, Any],
        config: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, room_id, room_info, config)
        self._attr_unique_id = f"{DOMAIN}_{room_id}_vacant_temperature"
        self._attr_name = "Vacant Temperature"
        self._storage_key = "vacant_temperature"

        # Get default from config
        self._default_value = config.options.get(
            CONF_VACANT_TEMPERATURE,
            config.data.get(CONF_VACANT_TEMPERATURE, DEFAULT_VACANT_TEMP),
        )

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._get_stored_value(self._default_value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._set_stored_value(value)
