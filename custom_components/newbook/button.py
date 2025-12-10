"""Button platform for Newbook integration - TRV calibration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_TRV_DISCOVERED,
)
from .trv_monitor import TRVMonitor

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newbook button entities from a config entry."""
    trv_monitor: TRVMonitor = hass.data[DOMAIN][entry.entry_id]["trv_monitor"]

    # Track discovered TRVs for THIS platform only
    discovered_trvs: set[str] = set()

    @callback
    def async_trv_discovered(discovery_info: dict[str, Any]) -> None:
        """Handle TRV discovery."""
        entity_id = discovery_info["entity_id"]
        if entity_id in discovered_trvs:
            return

        site_id = discovery_info["site_id"]
        location = discovery_info["location"]
        mac = discovery_info["mac"]
        device_id = discovery_info["device_id"]

        _LOGGER.info(
            "Creating button entity for TRV %s (mac=%s, device_id=%s)",
            entity_id, mac, device_id
        )

        entities = [
            TRVCalibrateButton(
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


class TRVCalibrateButton(ButtonEntity):
    """Button entity for TRV calibration."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:tune"

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
        """Initialize the button entity."""
        self.hass = hass
        self._entry_id = entry_id
        self._trv_monitor = trv_monitor
        self._climate_entity_id = climate_entity_id
        self._site_id = site_id
        self._location = location
        self._mac = mac
        self._device_id = device_id

        self._attr_unique_id = f"shelly_{mac}_calibrate"
        self._attr_name = "Setting - Calibrate"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping with TRV."""
        # MQTT discovery creates devices with identifiers as ("mqtt", "shelly_{mac}")
        return {
            "identifiers": {("mqtt", f"shelly_{self._mac}")},
        }

    async def async_press(self) -> None:
        """Run calibration on the TRV."""
        health = self._trv_monitor.get_trv_health(self._climate_entity_id)
        if not health.device_ip:
            _LOGGER.error("No device IP available for %s", self._climate_entity_id)
            return

        url = f"http://{health.device_ip}/calibrate"
        try:
            _LOGGER.info("Starting calibration for %s (url=%s)", self._climate_entity_id, url)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    _LOGGER.info("Calibration started for %s", self._climate_entity_id)
                    # Mark as not calibrated until process completes
                    health.is_calibrated = False
                else:
                    _LOGGER.error(
                        "Failed to start calibration for %s: HTTP %d",
                        self._climate_entity_id,
                        response.status,
                    )
        except asyncio.TimeoutError:
            _LOGGER.error("Failed to start calibration for %s: Timeout connecting to %s", self._climate_entity_id, health.device_ip)
        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to start calibration for %s: %s (%s)", self._climate_entity_id, type(err).__name__, err)
