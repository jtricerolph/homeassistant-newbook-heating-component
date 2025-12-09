"""Config flow for Newbook Hotel Management integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import NewbookApiClient, NewbookApiError, NewbookAuthError
from .const import (
    CONF_API_KEY,
    CONF_BATTERY_CRITICAL_THRESHOLD,
    CONF_BATTERY_WARNING_THRESHOLD,
    CONF_CATEGORY_SORT_ORDER,
    CONF_COMMAND_TIMEOUT,
    CONF_COOLING_OFFSET_MINUTES,
    CONF_DEFAULT_ARRIVAL_TIME,
    CONF_DEFAULT_DEPARTURE_TIME,
    CONF_EXCLUDE_BATHROOM_DEFAULT,
    CONF_EXCLUDED_CATEGORIES,
    CONF_EXCLUDED_ROOMS,
    CONF_HEATING_OFFSET_MINUTES,
    CONF_MAX_RETRY_ATTEMPTS,
    CONF_OCCUPIED_TEMPERATURE,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SYNC_SETPOINTS_DEFAULT,
    CONF_VACANT_TEMPERATURE,
    DEFAULT_ARRIVAL_TIME,
    DEFAULT_BATTERY_CRITICAL,
    DEFAULT_BATTERY_WARNING,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_COOLING_OFFSET,
    DEFAULT_DEPARTURE_TIME,
    DEFAULT_EXCLUDE_BATHROOM,
    DEFAULT_HEATING_OFFSET,
    DEFAULT_MAX_RETRY_ATTEMPTS,
    DEFAULT_OCCUPIED_TEMP,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SYNC_SETPOINTS,
    DEFAULT_VACANT_TEMP,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_auth(
    hass: HomeAssistant,
    username: str,
    password: str,
    api_key: str,
    region: str,
) -> dict[str, Any]:
    """Validate the API credentials."""
    session = async_get_clientsession(hass)
    client = NewbookApiClient(username, password, api_key, region, session)

    try:
        # Test connection
        if not await client.test_connection():
            return {"error": "cannot_connect"}

        return {"title": f"Newbook ({username})"}

    except NewbookAuthError:
        return {"error": "invalid_auth"}
    except NewbookApiError:
        return {"error": "cannot_connect"}
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected exception")
        return {"error": "unknown"}


class NewbookConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Newbook Hotel Management."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate credentials
            result = await validate_auth(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_API_KEY],
                user_input[CONF_REGION],
            )

            if "error" in result:
                errors["base"] = result["error"]
            else:
                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                # Store data and move to next step
                self._data.update(user_input)
                return await self.async_step_polling()

        # Show form
        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(
                    ["au", "eu", "us", "nz"]
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_polling(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle polling configuration step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_defaults()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL.total_seconds() // 60,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            }
        )

        return self.async_show_form(
            step_id="polling",
            data_schema=data_schema,
        )

    async def async_step_defaults(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle default room settings step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_trv_monitoring()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEFAULT_ARRIVAL_TIME,
                    default=DEFAULT_ARRIVAL_TIME,
                ): str,
                vol.Required(
                    CONF_DEFAULT_DEPARTURE_TIME,
                    default=DEFAULT_DEPARTURE_TIME,
                ): str,
                vol.Required(
                    CONF_HEATING_OFFSET_MINUTES,
                    default=DEFAULT_HEATING_OFFSET,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=720)),
                vol.Required(
                    CONF_COOLING_OFFSET_MINUTES,
                    default=DEFAULT_COOLING_OFFSET,
                ): vol.All(vol.Coerce(int), vol.Range(min=-180, max=180)),
                vol.Required(
                    CONF_OCCUPIED_TEMPERATURE,
                    default=DEFAULT_OCCUPIED_TEMP,
                ): vol.All(vol.Coerce(float), vol.Range(min=10.0, max=30.0)),
                vol.Required(
                    CONF_VACANT_TEMPERATURE,
                    default=DEFAULT_VACANT_TEMP,
                ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=25.0)),
            }
        )

        return self.async_show_form(
            step_id="defaults",
            data_schema=data_schema,
        )

    async def async_step_trv_monitoring(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle TRV monitoring settings step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_valve_sync()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAX_RETRY_ATTEMPTS,
                    default=DEFAULT_MAX_RETRY_ATTEMPTS,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                vol.Required(
                    CONF_COMMAND_TIMEOUT,
                    default=DEFAULT_COMMAND_TIMEOUT,
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Required(
                    CONF_BATTERY_WARNING_THRESHOLD,
                    default=DEFAULT_BATTERY_WARNING,
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=50)),
                vol.Required(
                    CONF_BATTERY_CRITICAL_THRESHOLD,
                    default=DEFAULT_BATTERY_CRITICAL,
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=30)),
            }
        )

        return self.async_show_form(
            step_id="trv_monitoring",
            data_schema=data_schema,
        )

    async def async_step_valve_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle valve sync defaults step."""
        if user_input is not None:
            self._data.update(user_input)
            # All data collected, create entry
            return self.async_create_entry(
                title=f"Newbook ({self._data[CONF_USERNAME]})",
                data=self._data,
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SYNC_SETPOINTS_DEFAULT,
                    default=DEFAULT_SYNC_SETPOINTS,
                ): bool,
                vol.Required(
                    CONF_EXCLUDE_BATHROOM_DEFAULT,
                    default=DEFAULT_EXCLUDE_BATHROOM,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="valve_sync",
            data_schema=data_schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Newbook integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - show menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["general_settings", "room_exclusions", "map_shelly_devices"],
        )

    async def async_step_general_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage general settings."""
        if user_input is not None:
            # Merge with existing options to preserve other settings (like room exclusions)
            new_options = {**self._config_entry.options, **user_input}
            return self.async_create_entry(title="", data=new_options)

        # Get current config
        current_config = {**self._config_entry.data, **self._config_entry.options}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current_config.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds() // 60
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Required(
                    CONF_DEFAULT_ARRIVAL_TIME,
                    default=current_config.get(
                        CONF_DEFAULT_ARRIVAL_TIME, DEFAULT_ARRIVAL_TIME
                    ),
                ): str,
                vol.Required(
                    CONF_DEFAULT_DEPARTURE_TIME,
                    default=current_config.get(
                        CONF_DEFAULT_DEPARTURE_TIME, DEFAULT_DEPARTURE_TIME
                    ),
                ): str,
                vol.Required(
                    CONF_HEATING_OFFSET_MINUTES,
                    default=current_config.get(
                        CONF_HEATING_OFFSET_MINUTES, DEFAULT_HEATING_OFFSET
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=720)),
                vol.Required(
                    CONF_COOLING_OFFSET_MINUTES,
                    default=current_config.get(
                        CONF_COOLING_OFFSET_MINUTES, DEFAULT_COOLING_OFFSET
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=-180, max=180)),
                vol.Required(
                    CONF_OCCUPIED_TEMPERATURE,
                    default=current_config.get(
                        CONF_OCCUPIED_TEMPERATURE, DEFAULT_OCCUPIED_TEMP
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=10.0, max=30.0)),
                vol.Required(
                    CONF_VACANT_TEMPERATURE,
                    default=current_config.get(
                        CONF_VACANT_TEMPERATURE, DEFAULT_VACANT_TEMP
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=25.0)),
                vol.Required(
                    CONF_MAX_RETRY_ATTEMPTS,
                    default=current_config.get(
                        CONF_MAX_RETRY_ATTEMPTS, DEFAULT_MAX_RETRY_ATTEMPTS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                vol.Required(
                    CONF_COMMAND_TIMEOUT,
                    default=current_config.get(
                        CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Required(
                    CONF_BATTERY_WARNING_THRESHOLD,
                    default=current_config.get(
                        CONF_BATTERY_WARNING_THRESHOLD, DEFAULT_BATTERY_WARNING
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=50)),
                vol.Required(
                    CONF_BATTERY_CRITICAL_THRESHOLD,
                    default=current_config.get(
                        CONF_BATTERY_CRITICAL_THRESHOLD, DEFAULT_BATTERY_CRITICAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=30)),
                vol.Required(
                    CONF_SYNC_SETPOINTS_DEFAULT,
                    default=current_config.get(
                        CONF_SYNC_SETPOINTS_DEFAULT, DEFAULT_SYNC_SETPOINTS
                    ),
                ): bool,
                vol.Required(
                    CONF_EXCLUDE_BATHROOM_DEFAULT,
                    default=current_config.get(
                        CONF_EXCLUDE_BATHROOM_DEFAULT, DEFAULT_EXCLUDE_BATHROOM
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="general_settings",
            data_schema=data_schema,
        )

    async def async_step_map_shelly_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Map unmapped Shelly devices to rooms."""
        # Get MQTT discovery manager
        mqtt_discovery = self.hass.data[DOMAIN][self._config_entry.entry_id].get("mqtt_discovery")
        if not mqtt_discovery:
            return self.async_abort(reason="mqtt_discovery_not_available")

        # Get unmapped devices
        unmapped_devices = mqtt_discovery.get_unmapped_devices()

        if not unmapped_devices:
            return self.async_abort(reason="no_unmapped_devices")

        if user_input is not None:
            # Process mapping
            device_id = user_input.get("device_id")
            site_id = user_input.get("site_id")
            location = user_input.get("location")

            if device_id and site_id and location:
                success = await mqtt_discovery.async_manual_map_device(
                    device_id, site_id, location
                )
                if success:
                    # Preserve existing options (mapping is stored separately by MQTT discovery)
                    return self.async_create_entry(title="", data=self._config_entry.options)

            return self.async_abort(reason="mapping_failed")

        # Get coordinator to get available rooms
        coordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]["coordinator"]
        rooms = coordinator.get_all_rooms()

        # Create device selection schema
        device_options = {
            device.device_id: f"{device.model} - {device.mac} ({device.ip})"
            for device in unmapped_devices
        }

        if not device_options:
            return self.async_abort(reason="no_unmapped_devices")

        # For simplicity, just show a text input for site_id and location
        # In a more advanced UI, these could be dropdowns
        data_schema = vol.Schema(
            {
                vol.Required("device_id"): vol.In(device_options),
                vol.Required("site_id"): str,
                vol.Required("location"): str,
            }
        )

        return self.async_show_form(
            step_id="map_shelly_devices",
            data_schema=data_schema,
            description_placeholders={
                "unmapped_count": str(len(unmapped_devices)),
            },
        )

    async def async_step_room_exclusions(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure room and category exclusions."""
        if user_input is not None:
            # Merge with existing options to preserve other settings (like general settings)
            new_options = {**self._config_entry.options, **user_input}
            return self.async_create_entry(title="", data=new_options)

        # Get coordinator to get available rooms and categories
        # Use unfiltered version to show ALL rooms including already excluded ones
        try:
            coordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]["coordinator"]
            rooms = coordinator.get_all_rooms_unfiltered()
        except (KeyError, AttributeError):
            _LOGGER.error("Failed to get coordinator or rooms for exclusions config")
            return self.async_abort(reason="coordinator_not_available")

        # Get current config
        current_config = {**self._config_entry.data, **self._config_entry.options}

        # Build lists of available rooms and categories
        room_options = {}
        categories = set()

        for room_id, room_info in rooms.items():
            site_name = room_info.get("site_name", room_id)
            room_options[site_name] = site_name

            category_name = room_info.get("category_name")
            if category_name:
                categories.add(category_name)

        # If no rooms found, show error
        if not room_options:
            _LOGGER.warning("No rooms available for exclusion configuration")
            return self.async_abort(reason="no_rooms_available")

        # Create schema with multi-select
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_EXCLUDED_ROOMS,
                    default=current_config.get(CONF_EXCLUDED_ROOMS, []),
                ): cv.multi_select(room_options),
                vol.Optional(
                    CONF_EXCLUDED_CATEGORIES,
                    default=current_config.get(CONF_EXCLUDED_CATEGORIES, []),
                ): cv.multi_select({cat: cat for cat in sorted(categories)}),
                vol.Optional(
                    CONF_CATEGORY_SORT_ORDER,
                    default=current_config.get(CONF_CATEGORY_SORT_ORDER, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="room_exclusions",
            data_schema=data_schema,
            description_placeholders={
                "room_count": str(len(room_options)),
                "category_count": str(len(categories)),
            },
        )
