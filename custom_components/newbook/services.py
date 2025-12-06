"""Services for Newbook integration."""
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_CREATE_DASHBOARDS,
    SERVICE_FORCE_ROOM_TEMPERATURE,
    SERVICE_REFRESH_BOOKINGS,
    SERVICE_RETRY_UNRESPONSIVE_TRVS,
    SERVICE_SET_ROOM_AUTO_MODE,
    SERVICE_SYNC_ROOM_VALVES,
)

_LOGGER = logging.getLogger(__name__)

# Service schemas
REFRESH_BOOKINGS_SCHEMA = vol.Schema({})

SET_ROOM_AUTO_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("room_id"): cv.string,
        vol.Required("enabled"): cv.boolean,
    }
)

FORCE_ROOM_TEMPERATURE_SCHEMA = vol.Schema(
    {
        vol.Required("room_id"): cv.string,
        vol.Required("temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=5.0, max=30.0)
        ),
    }
)

SYNC_ROOM_VALVES_SCHEMA = vol.Schema(
    {
        vol.Required("room_id"): cv.string,
        vol.Required("temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=5.0, max=30.0)
        ),
    }
)

RETRY_UNRESPONSIVE_TRVS_SCHEMA = vol.Schema({})

CREATE_DASHBOARDS_SCHEMA = vol.Schema({})


async def async_register_services(hass: HomeAssistant, entry_id: str) -> None:
    """Register integration services."""
    heating_controller = hass.data[DOMAIN][entry_id]["heating_controller"]
    trv_monitor = hass.data[DOMAIN][entry_id]["trv_monitor"]
    coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
    dashboard_generator = hass.data[DOMAIN][entry_id]["dashboard_generator"]

    async def async_refresh_bookings(call: ServiceCall) -> None:
        """Refresh booking data from Newbook API."""
        _LOGGER.info("Service called: refresh_bookings")
        await coordinator.async_refresh_bookings()

    async def async_set_room_auto_mode(call: ServiceCall) -> None:
        """Enable or disable auto mode for a room."""
        room_id = call.data["room_id"]
        enabled = call.data["enabled"]
        _LOGGER.info("Service called: set_room_auto_mode for room %s to %s", room_id, enabled)
        await heating_controller.async_set_room_auto_mode(room_id, enabled)

    async def async_force_room_temperature(call: ServiceCall) -> None:
        """Force a specific temperature for a room."""
        room_id = call.data["room_id"]
        temperature = call.data["temperature"]
        _LOGGER.info(
            "Service called: force_room_temperature for room %s to %.1f°C",
            room_id,
            temperature,
        )
        await heating_controller.async_force_room_temperature(room_id, temperature)

    async def async_sync_room_valves(call: ServiceCall) -> None:
        """Manually sync all valves in a room."""
        room_id = call.data["room_id"]
        temperature = call.data["temperature"]
        _LOGGER.info(
            "Service called: sync_room_valves for room %s to %.1f°C",
            room_id,
            temperature,
        )
        trvs = trv_monitor.get_room_trvs(room_id)
        await trv_monitor.batch_set_room_temperature(room_id, trvs, temperature)

    async def async_retry_unresponsive_trvs(call: ServiceCall) -> None:
        """Retry sending commands to unresponsive TRVs."""
        _LOGGER.info("Service called: retry_unresponsive_trvs")
        result = await trv_monitor.retry_unresponsive_trvs()
        successful = sum(1 for success in result.values() if success)
        _LOGGER.info(
            "Retry unresponsive TRVs complete: %d/%d successful",
            successful,
            len(result),
        )

    async def async_create_dashboards(call: ServiceCall) -> None:
        """Create or update all Newbook dashboards."""
        _LOGGER.info("Service called: create_dashboards")

        # Get all rooms
        rooms = coordinator.get_all_rooms()
        if not rooms:
            _LOGGER.warning("No rooms discovered, cannot create dashboards")
            hass.components.persistent_notification.async_create(
                "No rooms discovered. Please wait for booking data to be fetched.",
                title="Newbook Dashboards",
                notification_id="newbook_dashboards_no_rooms",
            )
            return

        # Generate dashboard YAML files
        _LOGGER.info("Generating dashboard YAML files for %d rooms", len(rooms))
        await dashboard_generator.async_generate_all_dashboards(rooms)

        # Notify user that dashboards have been generated
        hass.components.persistent_notification.async_create(
            f"Dashboard templates generated for {len(rooms)} rooms at `/config/dashboards/newbook/`.\n\n"
            f"To use them:\n"
            f"1. Go to Settings → Dashboards\n"
            f"2. Click 'Add Dashboard'\n"
            f"3. Give it a name (e.g., 'Newbook Home')\n"
            f"4. Edit the new dashboard in YAML mode\n"
            f"5. Copy/paste content from the generated YAML files\n\n"
            f"Generated files:\n"
            f"- home_overview.yaml (main dashboard)\n"
            f"- room_*.yaml ({len(rooms)} room dashboards)\n"
            f"- battery_monitoring.yaml\n"
            f"- trv_health.yaml",
            title="Newbook Dashboards Created",
            notification_id="newbook_dashboards_created",
        )

        _LOGGER.info("Dashboard generation complete")

    # Register services only once
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_BOOKINGS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_BOOKINGS,
            async_refresh_bookings,
            schema=REFRESH_BOOKINGS_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_ROOM_AUTO_MODE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_ROOM_AUTO_MODE,
            async_set_room_auto_mode,
            schema=SET_ROOM_AUTO_MODE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_FORCE_ROOM_TEMPERATURE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORCE_ROOM_TEMPERATURE,
            async_force_room_temperature,
            schema=FORCE_ROOM_TEMPERATURE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SYNC_ROOM_VALVES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SYNC_ROOM_VALVES,
            async_sync_room_valves,
            schema=SYNC_ROOM_VALVES_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RETRY_UNRESPONSIVE_TRVS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RETRY_UNRESPONSIVE_TRVS,
            async_retry_unresponsive_trvs,
            schema=RETRY_UNRESPONSIVE_TRVS_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_DASHBOARDS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CREATE_DASHBOARDS,
            async_create_dashboards,
            schema=CREATE_DASHBOARDS_SCHEMA,
        )

    _LOGGER.info("Newbook services registered")
