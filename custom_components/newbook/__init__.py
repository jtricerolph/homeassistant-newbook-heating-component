"""The Newbook Hotel Management integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
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
from .heating_controller import HeatingController
from .services import async_register_services
from .trv_monitor import TRVMonitor

_LOGGER = logging.getLogger(__name__)


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

    # Store everything in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "config": entry,
        "trv_monitor": trv_monitor,
        "heating_controller": heating_controller,
    }

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_register_services(hass, entry.entry_id)

    # Setup coordinator listener to update heating when bookings change
    async def _async_coordinator_updated():
        """Handle coordinator updates."""
        await heating_controller.async_update_all_rooms()

    coordinator.async_add_listener(_async_coordinator_updated)

    # Setup update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info("Newbook integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Newbook integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    _LOGGER.info("Updating Newbook integration options")
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    # TODO: Implement services in future phases
    # - refresh_bookings
    # - set_room_auto_mode
    # - force_room_temperature
    # - sync_room_valves
    # - retry_unresponsive_trvs
    pass
