"""Select platform for Newbook integration - TRV device settings."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_TRV_DISCOVERED,
    SIGNAL_TRV_SETTINGS_UPDATED,
)
from .trv_monitor import TRVMonitor

_LOGGER = logging.getLogger(__name__)

# Brightness options mapping: display name -> API value
BRIGHTNESS_OPTIONS = {
    "Low": 1,
    "Normal": 4,
    "High": 7,
}
BRIGHTNESS_VALUES_TO_OPTIONS = {v: k for k, v in BRIGHTNESS_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newbook select entities from a config entry."""
    trv_monitor: TRVMonitor = hass.data[DOMAIN][entry.entry_id]["trv_monitor"]

    # Track discovered TRVs for THIS platform only
    discovered_trvs: set[str] = set()

    @callback
    def async_trv_discovered(discovery_info: dict[str, Any]) -> None:
        """Handle TRV discovery."""
        entity_id = discovery_info["entity_id"]
        if entity_id in discovered_trvs:
            _LOGGER.debug("TRV %s already has select entity, skipping", entity_id)
            return

        site_id = discovery_info["site_id"]
        location = discovery_info["location"]
        mac = discovery_info["mac"]
        device_id = discovery_info["device_id"]

        _LOGGER.info(
            "Creating select entity for TRV %s (mac=%s, device_id=%s)",
            entity_id, mac, device_id
        )

        entities = [
            TRVBrightnessSelect(
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


class TRVBrightnessSelect(SelectEntity):
    """Select entity for TRV screen brightness."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:brightness-6"
    _attr_options = list(BRIGHTNESS_OPTIONS.keys())

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
        """Initialize the select entity."""
        self.hass = hass
        self._entry_id = entry_id
        self._trv_monitor = trv_monitor
        self._climate_entity_id = climate_entity_id
        self._site_id = site_id
        self._location = location
        self._mac = mac
        self._device_id = device_id

        self._attr_unique_id = f"shelly_{mac}_brightness"
        self._attr_name = "Screen Brightness"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping with TRV."""
        # MQTT discovery creates devices with identifiers as ("mqtt", "shelly_{mac}")
        return {
            "identifiers": {("mqtt", f"shelly_{self._mac}")},
        }

    @property
    def current_option(self) -> str | None:
        """Return the current brightness option."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        if health.display_brightness is None:
            return None
        return BRIGHTNESS_VALUES_TO_OPTIONS.get(health.display_brightness, "Normal")

    async def async_select_option(self, option: str) -> None:
        """Set the brightness option."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        if not health.device_ip:
            _LOGGER.error("No device IP available for %s", self._climate_entity_id)
            return

        brightness_value = BRIGHTNESS_OPTIONS.get(option)
        if brightness_value is None:
            _LOGGER.error("Invalid brightness option: %s", option)
            return

        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{health.device_ip}/settings/?display_brightness={brightness_value}"
                _LOGGER.info("Setting %s brightness to %s (%d)", self._climate_entity_id, option, brightness_value)
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        _LOGGER.info("Successfully set brightness for %s", self._climate_entity_id)
                        # Update local state
                        health.display_brightness = brightness_value
                        self.async_write_ha_state()
                    else:
                        _LOGGER.error(
                            "Failed to set brightness for %s: HTTP %d",
                            self._climate_entity_id,
                            response.status,
                        )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to set brightness for %s: %s", self._climate_entity_id, err)

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
