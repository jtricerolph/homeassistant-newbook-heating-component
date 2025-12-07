"""The Newbook Hotel Management integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NewbookApiClient
from .const import (
    CONF_API_KEY,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_FORCE_ROOM_TEMPERATURE,
    SERVICE_REFRESH_BOOKINGS,
    SERVICE_RETRY_UNRESPONSIVE_TRVS,
    SERVICE_SET_ROOM_AUTO_MODE,
    SERVICE_SYNC_ROOM_VALVES,
)
from .coordinator import NewbookDataUpdateCoordinator
from .dashboard_generator import DashboardGenerator
from .heating_controller import HeatingController
from .mqtt_discovery import MQTTDiscoveryManager
from .room_manager import RoomManager
from .services import async_register_services
from .trv_monitor import TRVMonitor

_LOGGER = logging.getLogger(__name__)


async def async_create_room_areas(hass: HomeAssistant, rooms: dict[str, Any]) -> None:
    """Create Home Assistant areas for each discovered room."""
    area_reg = ar.async_get(hass)

    for room_id, room_info in rooms.items():
        area_name = room_info.get("site_name", f"Room {room_id}")

        # Check if area already exists
        existing_area = None
        for area in area_reg.async_list_areas():
            if area.name == area_name:
                existing_area = area
                break

        if not existing_area:
            # Create new area
            _LOGGER.info("Creating area for %s", area_name)
            area_reg.async_create(area_name)
        else:
            _LOGGER.debug("Area %s already exists", area_name)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Newbook Hotel Management from a config entry."""
    _LOGGER.info("Setting up Newbook integration")

    # Get configuration
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    api_key = entry.data[CONF_API_KEY]
    region = entry.data.get(CONF_REGION, "au")

    # Get scan interval from options or config
    scan_interval_minutes = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds() // 60),
    )
    scan_interval = timedelta(minutes=float(scan_interval_minutes))

    # Create API client
    session = async_get_clientsession(hass)
    client = NewbookApiClient(username, password, api_key, region, session)

    # Prepare config dict for coordinator and booking processor
    config_dict = {**entry.data, **entry.options}

    # Create data update coordinator
    coordinator = NewbookDataUpdateCoordinator(
        hass,
        client,
        scan_interval,
        config_dict,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Create TRV monitor
    trv_monitor = TRVMonitor(hass, config_dict)

    # Create heating controller
    heating_controller = HeatingController(hass, coordinator, trv_monitor, config_dict)

    # Create dashboard generator
    dashboard_generator = DashboardGenerator(hass, entry.entry_id)

    # Create MQTT discovery manager for Shelly devices
    mqtt_discovery = MQTTDiscoveryManager(hass, entry.entry_id)

    # Create room manager for tracking discovered rooms
    room_manager = RoomManager(hass, entry.entry_id)

    # Store everything in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "config": entry,
        "trv_monitor": trv_monitor,
        "heating_controller": heating_controller,
        "dashboard_generator": dashboard_generator,
        "mqtt_discovery": mqtt_discovery,
        "room_manager": room_manager,
    }

    # Perform initial room state calculation before sensors are created
    _LOGGER.info("Calculating initial room states for %d rooms", len(coordinator.get_all_rooms()))
    await heating_controller.async_update_all_rooms()

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_register_services(hass, entry.entry_id)

    # Setup coordinator listener to update heating when bookings change
    async def _async_coordinator_updated():
        """Handle coordinator updates."""
        await heating_controller.async_update_all_rooms()

    coordinator.async_add_listener(_async_coordinator_updated)

    # Generate dashboards after platforms are set up
    rooms = coordinator.get_all_rooms()
    if rooms:
        _LOGGER.info("Generating dashboards for %d discovered rooms", len(rooms))
        await dashboard_generator.async_generate_all_dashboards(rooms)

        # Create areas for all discovered rooms
        await async_create_room_areas(hass, rooms)
    else:
        _LOGGER.warning("No rooms discovered yet, dashboards will be generated on next update")

    # Setup MQTT discovery for Shelly devices
    await mqtt_discovery.async_setup()

    # Setup update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info("Newbook integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Newbook integration")

    # Delete generated dashboards
    dashboard_generator = hass.data[DOMAIN][entry.entry_id].get("dashboard_generator")
    if dashboard_generator:
        await dashboard_generator.async_delete_all_dashboards()

    # Unload MQTT discovery
    mqtt_discovery = hass.data[DOMAIN][entry.entry_id].get("mqtt_discovery")
    if mqtt_discovery:
        await mqtt_discovery.async_unload()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    _LOGGER.info("Updating Newbook integration options")
    await hass.config_entries.async_reload(entry.entry_id)


