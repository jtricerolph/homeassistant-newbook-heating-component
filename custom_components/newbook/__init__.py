"""The Newbook Hotel Management integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

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
    SIGNAL_TRV_STATUS_UPDATED,
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
    """Create Home Assistant areas for each discovered room and assign devices."""
    area_reg = ar.async_get(hass)
    device_reg = dr.async_get(hass)

    for room_id, room_info in rooms.items():
        # Use site_name directly from Newbook (e.g., "101", "102")
        # This ensures consistency with MQTT-discovered devices
        area_name = room_info.get("site_name", room_id)

        # Check if area already exists, create if not
        area = None
        for existing_area in area_reg.async_list_areas():
            if existing_area.name == area_name:
                area = existing_area
                break

        if not area:
            # Create new area
            _LOGGER.info("Creating area for %s", area_name)
            area = area_reg.async_create(area_name)

        # Assign Newbook room device to area
        # Room devices have identifiers {(DOMAIN, room_id)}
        device = device_reg.async_get_device(identifiers={(DOMAIN, room_id)})
        if device and device.area_id != area.id:
            _LOGGER.debug("Assigning device %s to area %s", device.name, area_name)
            device_reg.async_update_device(device.id, area_id=area.id)


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

    # Listen for climate.set_temperature service calls to track HA commands
    @callback
    def _handle_service_call(event: Event) -> None:
        """Track climate.set_temperature calls for origin detection."""
        if event.data.get("domain") != "climate":
            return
        if event.data.get("service") != "set_temperature":
            return

        service_data = event.data.get("service_data", {})
        entity_ids = service_data.get(ATTR_ENTITY_ID, [])
        target_temp = service_data.get(ATTR_TEMPERATURE)

        if not target_temp:
            return

        # Handle single entity_id or list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        # Record HA command for any TRV entities
        for entity_id in entity_ids:
            if entity_id.startswith("climate.room_"):
                health = trv_monitor.get_trv_health(entity_id)
                health.record_ha_command(float(target_temp))
                _LOGGER.info("Tracked HA command for %s: %.1f°C", entity_id, target_temp)

                # Notify sensors to update
                async_dispatcher_send(
                    hass,
                    f"{SIGNAL_TRV_STATUS_UPDATED}_{entry.entry_id}",
                    entity_id,
                )

    # Subscribe to service call events
    entry.async_on_unload(
        hass.bus.async_listen("call_service", _handle_service_call)
    )

    # Listen for TRV state changes to detect guest adjustments
    @callback
    def _handle_trv_state_change(event: Event) -> None:
        """Handle TRV state changes to detect guest temperature adjustments."""
        entity_id = event.data.get("entity_id")
        if not entity_id or not entity_id.startswith("climate.room_"):
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not old_state or not new_state:
            return

        # Get the temperature attribute
        old_temp = old_state.attributes.get(ATTR_TEMPERATURE)
        new_temp = new_state.attributes.get(ATTR_TEMPERATURE)

        if old_temp is None or new_temp is None:
            return

        # Check if temperature actually changed
        if abs(float(old_temp) - float(new_temp)) < 0.1:
            return

        # Check if this was an HA command or a guest change
        health = trv_monitor.get_trv_health(entity_id)

        # Check both pending and acknowledged HA commands
        ha_commanded_temp = health.ha_pending_command_temp or health.ha_last_acked_temp

        # If the new temp matches what HA commanded, it's not a guest change
        if ha_commanded_temp is not None and abs(float(new_temp) - ha_commanded_temp) < 0.1:
            _LOGGER.debug(
                "%s temp changed to %.1f°C (matches HA command, not a guest change)",
                entity_id,
                new_temp,
            )
            return

        # This is likely a guest change - sync to other TRVs
        _LOGGER.info(
            "%s temp changed from %.1f°C to %.1f°C (guest change detected, HA last commanded: %s)",
            entity_id,
            old_temp,
            new_temp,
            f"{ha_commanded_temp:.1f}°C" if ha_commanded_temp else "None",
        )

        # Trigger valve sync
        hass.async_create_task(
            heating_controller.async_handle_guest_temperature_change(entity_id, float(new_temp))
        )

    # Subscribe to state change events for all climate entities
    # We filter for room_* TRVs in the callback
    entry.async_on_unload(
        hass.bus.async_listen("state_changed", _handle_trv_state_change)
    )

    # Schedule initial room state calculation in background (don't block setup)
    # This prevents slow/unresponsive TRVs from blocking integration initialization
    _LOGGER.info("Scheduling initial room states for %d rooms (background)", len(coordinator.get_all_rooms()))
    hass.async_create_task(heating_controller.async_update_all_rooms())

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_register_services(hass, entry.entry_id)

    # Setup coordinator listener to update heating when bookings change
    @callback
    def _coordinator_updated():
        """Handle coordinator updates."""
        _LOGGER.debug("Coordinator update triggered, refreshing all room states")
        hass.async_create_task(heating_controller.async_update_all_rooms())

    coordinator.async_add_listener(_coordinator_updated)

    # Setup time-based tracker to update room states every minute
    # This ensures states transition at the correct times (heating_start, arrival, etc.)
    # independent of the coordinator polling schedule
    async def _async_time_based_update(_now=None):
        """Handle time-based room state updates."""
        _LOGGER.debug("Time-based update triggered (every 1 minute)")
        # Use async_create_task to avoid blocking the time tracker
        # TRV commands can have long timeouts due to retry logic
        hass.async_create_task(heating_controller.async_update_all_rooms())

    # Track time every 1 minute
    remove_time_tracker = async_track_time_interval(
        hass,
        _async_time_based_update,
        timedelta(minutes=1)
    )
    entry.async_on_unload(remove_time_tracker)

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

    # After a delay, re-fire discovery signals for any devices that were
    # discovered before platforms finished subscribing to the signal.
    # Shelly TRVs are battery-powered and may take time to wake up and publish settings.
    async def _async_fire_delayed_discovery():
        """Fire discovery signals for existing devices after delay."""
        import asyncio
        _LOGGER.info("Waiting 15 seconds for Shelly devices to publish settings...")
        await asyncio.sleep(15)  # Wait for devices to wake up and publish settings
        await mqtt_discovery.async_fire_discovery_for_existing_devices()

    hass.async_create_task(_async_fire_delayed_discovery())

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


