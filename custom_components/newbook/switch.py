"""Switch platform for Newbook integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_EXCLUDE_BATHROOM_DEFAULT,
    CONF_SYNC_SETPOINTS_DEFAULT,
    DEFAULT_EXCLUDE_BATHROOM,
    DEFAULT_SYNC_SETPOINTS,
    DOMAIN,
    SIGNAL_TRV_DISCOVERED,
    SIGNAL_TRV_SETTINGS_UPDATED,
)
from .coordinator import NewbookDataUpdateCoordinator
from .room_manager import RoomManager
from .trv_monitor import TRVMonitor

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
    trv_monitor: TRVMonitor = hass.data[DOMAIN][entry.entry_id]["trv_monitor"]
    config = entry

    # Track discovered rooms for THIS platform only
    discovered_rooms: set[str] = set()

    @callback
    def async_add_switches() -> None:
        """Add switch entities for all discovered rooms."""
        entities = []
        rooms = coordinator.get_all_rooms()

        for room_id, room_info in rooms.items():
            if room_id not in discovered_rooms:
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
                discovered_rooms.add(room_id)

        if entities:
            async_add_entities(entities)

    # Add switches for initially discovered rooms
    async_add_switches()

    # Listen for coordinator updates to discover new rooms
    coordinator.async_add_listener(async_add_switches)

    # Track discovered TRVs for TRV settings switches
    discovered_trvs: set[str] = set()

    @callback
    def async_trv_discovered(discovery_info: dict[str, Any]) -> None:
        """Handle TRV discovery for settings switches."""
        entity_id = discovery_info["entity_id"]
        if entity_id in discovered_trvs:
            return

        site_id = discovery_info["site_id"]
        location = discovery_info["location"]
        mac = discovery_info["mac"]
        device_id = discovery_info["device_id"]

        _LOGGER.info("Creating TRV settings switches for %s", entity_id)

        entities = [
            TRVScreenRotationSwitch(
                hass,
                entry.entry_id,
                trv_monitor,
                entity_id,
                site_id,
                location,
                mac,
                device_id,
            ),
            TRVClogPreventionSwitch(
                hass,
                entry.entry_id,
                trv_monitor,
                entity_id,
                site_id,
                location,
                mac,
                device_id,
            ),
        ]

        async_add_entities(entities)
        discovered_trvs.add(entity_id)

    # Subscribe to TRV discovery events
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{SIGNAL_TRV_DISCOVERED}_{entry.entry_id}",
            async_trv_discovered,
        )
    )


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


# TRV Settings Switches


class TRVSettingsSwitchBase(SwitchEntity):
    """Base class for TRV settings switch entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        trv_monitor: TRVMonitor,
        climate_entity_id: str,
        site_id: str,
        location: str,
        mac: str,
        device_id: str,
    ) -> None:
        """Initialize the switch entity."""
        self.hass = hass
        self._entry_id = entry_id
        self._trv_monitor = trv_monitor
        self._climate_entity_id = climate_entity_id
        self._site_id = site_id
        self._location = location
        self._mac = mac
        self._device_id = device_id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping with TRV."""
        return {
            "identifiers": {(f"shelly_{self._mac}",)},
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()

        @callback
        def _async_settings_updated(entity_id: str) -> None:
            """Handle settings update."""
            if entity_id == self._climate_entity_id:
                self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_TRV_SETTINGS_UPDATED}_{self._entry_id}",
                _async_settings_updated,
            )
        )


class TRVScreenRotationSwitch(TRVSettingsSwitchBase):
    """Switch entity for TRV screen rotation (180°)."""

    _attr_icon = "mdi:screen-rotation"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        trv_monitor: TRVMonitor,
        climate_entity_id: str,
        site_id: str,
        location: str,
        mac: str,
        device_id: str,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(
            hass, entry_id, trv_monitor, climate_entity_id,
            site_id, location, mac, device_id
        )
        self._attr_unique_id = f"shelly_{mac}_screen_rotation"
        self._attr_name = "Screen Rotation"

    @property
    def is_on(self) -> bool | None:
        """Return True if screen is rotated (flipped)."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        return health.display_flipped

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable screen rotation (flip display)."""
        await self._set_display_flipped(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable screen rotation (normal display)."""
        await self._set_display_flipped(False)

    async def _set_display_flipped(self, flipped: bool) -> None:
        """Set the display flipped setting."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        if not health.device_ip:
            _LOGGER.error("No device IP available for %s", self._climate_entity_id)
            return

        value = 1 if flipped else 0
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{health.device_ip}/settings/?display_flipped={value}"
                _LOGGER.info("Setting %s screen rotation to %s", self._climate_entity_id, flipped)
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Successfully set screen rotation for %s", self._climate_entity_id)
                        health.display_flipped = flipped
                        self.async_write_ha_state()
                    else:
                        _LOGGER.error(
                            "Failed to set screen rotation for %s: HTTP %d",
                            self._climate_entity_id,
                            response.status,
                        )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to set screen rotation for %s: %s", self._climate_entity_id, err)


class TRVClogPreventionSwitch(TRVSettingsSwitchBase):
    """Switch entity for TRV clog prevention (anti-seize)."""

    _attr_icon = "mdi:pipe-valve"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        trv_monitor: TRVMonitor,
        climate_entity_id: str,
        site_id: str,
        location: str,
        mac: str,
        device_id: str,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(
            hass, entry_id, trv_monitor, climate_entity_id,
            site_id, location, mac, device_id
        )
        self._attr_unique_id = f"shelly_{mac}_clog_prevention"
        self._attr_name = "Clog Prevention"

    @property
    def is_on(self) -> bool | None:
        """Return True if clog prevention is enabled."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        return health.clog_prevention

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable clog prevention."""
        await self._set_clog_prevention(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable clog prevention."""
        await self._set_clog_prevention(False)

    async def _set_clog_prevention(self, enabled: bool) -> None:
        """Set the clog prevention setting."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        if not health.device_ip:
            _LOGGER.error("No device IP available for %s", self._climate_entity_id)
            return

        value = 1 if enabled else 0
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{health.device_ip}/settings/?clog_prevention={value}"
                _LOGGER.info("Setting %s clog prevention to %s", self._climate_entity_id, enabled)
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Successfully set clog prevention for %s", self._climate_entity_id)
                        health.clog_prevention = enabled
                        self.async_write_ha_state()
                    else:
                        _LOGGER.error(
                            "Failed to set clog prevention for %s: HTTP %d",
                            self._climate_entity_id,
                            response.status,
                        )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to set clog prevention for %s: %s", self._climate_entity_id, err)
