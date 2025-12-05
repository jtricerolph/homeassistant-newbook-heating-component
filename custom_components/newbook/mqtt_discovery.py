"""MQTT discovery manager for Shelly devices."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    MQTT_DISCOVERY_PREFIX,
    SHELLY_ANNOUNCE_TOPIC,
    SHELLY_ONLINE_TOPIC,
    SHELLY_STATUS_TOPIC,
)
from .shelly_detector import ShellyDetector, ShellyDevice

_LOGGER = logging.getLogger(__name__)

# Room pattern: room_{site_id}_{location}
# Match anywhere in the device ID (handles custom MQTT prefixes like "shellytrv_room_101_bedroom")
ROOM_PATTERN = re.compile(r"room_(\w+)_(\w+)", re.IGNORECASE)


class MQTTDiscoveryManager:
    """Manage MQTT autodiscovery for Shelly devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
    ) -> None:
        """Initialize the discovery manager."""
        self.hass = hass
        self.entry_id = entry_id
        self.detector = ShellyDetector()

        # Track mapped and unmapped devices
        self._mapped_devices: dict[str, dict[str, Any]] = {}  # device_id -> mapping info
        self._unmapped_devices: dict[str, ShellyDevice] = {}  # device_id -> device

        # MQTT subscriptions
        self._subscriptions: list[Any] = []

    async def async_setup(self) -> bool:
        """Set up MQTT discovery."""
        try:
            # Subscribe to Shelly settings messages
            # Gen1 Shelly devices publish settings but don't reliably publish announce messages
            # Topic format: shellies/{device_id}/settings
            _LOGGER.info("Setting up Shelly MQTT autodiscovery")

            await mqtt.async_subscribe(
                self.hass,
                "shellies/+/settings",
                self._async_settings_received,
                qos=1,
            )

            _LOGGER.info("Subscribed to Shelly settings topic: shellies/+/settings")
            return True

        except Exception as err:
            _LOGGER.error("Failed to setup MQTT discovery: %s", err)
            return False

    async def async_unload(self) -> None:
        """Unload MQTT discovery."""
        _LOGGER.info("Unloading Shelly MQTT autodiscovery")

        # Remove all published discovery configs
        for device_id in list(self._mapped_devices.keys()):
            await self._async_remove_discovery_config(device_id)

    @callback
    async def _async_settings_received(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle Shelly settings message."""
        try:
            # Extract device_id from topic: shellies/{device_id}/settings
            topic_parts = msg.topic.split("/")
            if len(topic_parts) != 3 or topic_parts[0] != "shellies" or topic_parts[2] != "settings":
                _LOGGER.debug("Invalid settings topic format: %s", msg.topic)
                return

            device_id = topic_parts[1]

            payload = json.loads(msg.payload)
            _LOGGER.debug("Received Shelly settings for %s: name=%s", device_id, payload.get("name"))

            # Parse device from settings
            device = self.detector.parse_settings(device_id, payload)
            if not device:
                return

            # Check if device name matches room pattern
            await self._async_process_device(device)

        except json.JSONDecodeError as err:
            _LOGGER.error("Failed to decode settings message: %s", err)
        except Exception as err:
            _LOGGER.error("Error processing settings message: %s", err)

    async def _async_process_device(self, device: ShellyDevice) -> None:
        """Process detected device and map to room if possible."""
        # Check if already mapped
        if device.device_id in self._mapped_devices:
            _LOGGER.debug("Device %s already mapped", device.device_id)
            return

        # Try to extract room info from device name
        match = ROOM_PATTERN.search(device.name)

        if match:
            # Auto-map device
            site_id = match.group(1)
            location = match.group(2)

            _LOGGER.info(
                "Auto-mapping Shelly device %s to room %s, location %s",
                device.device_id,
                site_id,
                location
            )

            mapping = {
                "device_id": device.device_id,
                "site_id": site_id,
                "location": location,
                "model": device.model,
                "mac": device.mac,
            }

            # Publish discovery config
            await self._async_publish_discovery_config(device, mapping)

            # Store mapping
            self._mapped_devices[device.device_id] = mapping

        else:
            # Device doesn't match pattern - add to unmapped
            _LOGGER.warning(
                "Shelly device %s (model: %s, MAC: %s) does not match room naming pattern 'room_{site_id}_{location}'. "
                "Please rename the device or manually map it in the Newbook integration options.",
                device.device_id,
                device.model,
                device.mac
            )
            self._unmapped_devices[device.device_id] = device

            # Dispatch event for UI notification
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.entry_id}_unmapped_device",
                device
            )

    async def _async_publish_discovery_config(
        self,
        device: ShellyDevice,
        mapping: dict[str, Any]
    ) -> None:
        """Publish Home Assistant MQTT discovery config."""
        if device.is_trv:
            await self._async_publish_climate_config(device, mapping)
        elif device.is_ht_sensor:
            await self._async_publish_sensor_config(device, mapping)

    async def _async_publish_climate_config(
        self,
        device: ShellyDevice,
        mapping: dict[str, Any]
    ) -> None:
        """Publish climate entity discovery config for Shelly TRV."""
        site_id = mapping["site_id"]
        location = mapping["location"]
        entity_id = f"room_{site_id}_{location}"

        # Discovery topic
        discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/climate/{device.device_id}/config"

        # Build config payload
        config = {
            "unique_id": f"shelly_{device.mac}_climate",
            "name": f"Room {site_id} {location}".title(),
            "default_entity_id": f"climate.{entity_id}",

            # Mode control
            "mode_cmd_t": f"{device.device_id}/thermostat/0/command/target_t",
            "mode_cmd_tpl": "{% if value == 'heat' %}{{'{\"enabled\": true}'}}{% else %}{{'{\"enabled\": false}'}}{% endif %}",
            "mode_stat_t": f"{device.device_id}/status",
            "mode_stat_tpl": "{% if value_json.target_t.enabled %}heat{% else %}off{% endif %}",
            "modes": ["off", "heat"],

            # Temperature control
            "temp_cmd_t": f"{device.device_id}/thermostat/0/command/target_t",
            "temp_cmd_tpl": "{{'{\"value\": ' ~ value ~ '}'}}",
            "temp_stat_t": f"{device.device_id}/status",
            "temp_stat_tpl": "{{ value_json.target_t.value }}",

            # Current temperature
            "curr_temp_t": f"{device.device_id}/status",
            "curr_temp_tpl": "{{ value_json.tmp.value }}",

            # Temperature settings
            "min_temp": 5,
            "max_temp": 30,
            "temp_step": 0.5,
            "precision": 0.1,
            "temperature_unit": "C",

            # Device info
            "device": {
                "identifiers": [f"shelly_{device.mac}"],
                "name": f"Shelly TRV {device.short_mac}",
                "model": device.model,
                "manufacturer": "Shelly",
                "sw_version": device.firmware,
            },
        }

        # Publish config
        _LOGGER.info(
            "Publishing climate discovery config for %s to %s",
            entity_id,
            discovery_topic
        )

        await mqtt.async_publish(
            self.hass,
            discovery_topic,
            json.dumps(config),
            qos=1,
            retain=True,
        )

        # Subscribe to status for health monitoring
        await self._async_subscribe_device_status(device)

    async def _async_publish_sensor_config(
        self,
        device: ShellyDevice,
        mapping: dict[str, Any]
    ) -> None:
        """Publish sensor entity discovery config for Shelly H&T."""
        site_id = mapping["site_id"]
        location = mapping["location"]

        # Temperature sensor
        temp_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device.device_id}_temp/config"
        temp_config = {
            "unique_id": f"shelly_{device.mac}_temperature",
            "name": f"Room {site_id} {location} Temperature".title(),
            "default_entity_id": f"sensor.room_{site_id}_{location}_temperature",
            "stat_t": f"{device.device_id}/sensor/temperature",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "device": {
                "identifiers": [f"shelly_{device.mac}"],
                "name": f"Shelly H&T {device.short_mac}",
                "model": device.model,
                "manufacturer": "Shelly",
                "sw_version": device.firmware,
            },
        }

        # Humidity sensor
        humidity_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device.device_id}_humidity/config"
        humidity_config = {
            "unique_id": f"shelly_{device.mac}_humidity",
            "name": f"Room {site_id} {location} Humidity".title(),
            "default_entity_id": f"sensor.room_{site_id}_{location}_humidity",
            "stat_t": f"{device.device_id}/sensor/humidity",
            "unit_of_measurement": "%",
            "device_class": "humidity",
            "state_class": "measurement",
            "device": {
                "identifiers": [f"shelly_{device.mac}"],
                "name": f"Shelly H&T {device.short_mac}",
                "model": device.model,
                "manufacturer": "Shelly",
                "sw_version": device.firmware,
            },
        }

        _LOGGER.info("Publishing sensor discovery configs for %s", device.device_id)

        await mqtt.async_publish(
            self.hass,
            temp_discovery_topic,
            json.dumps(temp_config),
            qos=1,
            retain=True,
        )

        await mqtt.async_publish(
            self.hass,
            humidity_discovery_topic,
            json.dumps(humidity_config),
            qos=1,
            retain=True,
        )

    async def _async_subscribe_device_status(self, device: ShellyDevice) -> None:
        """Subscribe to device status for health monitoring."""
        status_topic = f"{device.device_id}/status"

        @callback
        async def status_received(msg: mqtt.ReceiveMessage) -> None:
            """Handle device status update."""
            try:
                payload = json.loads(msg.payload)
                # TODO: Feed into TRV monitor health tracking
                _LOGGER.debug("Device %s status: %s", device.device_id, payload)
            except Exception as err:
                _LOGGER.error("Error processing status for %s: %s", device.device_id, err)

        await mqtt.async_subscribe(
            self.hass,
            status_topic,
            status_received,
            qos=1,
        )

    async def _async_remove_discovery_config(self, device_id: str) -> None:
        """Remove discovery config for a device."""
        mapping = self._mapped_devices.get(device_id)
        if not mapping:
            return

        device = self.detector.get_device(device_id)
        if not device:
            return

        _LOGGER.info("Removing discovery config for %s", device_id)

        # Remove climate config
        if device.is_trv:
            discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/climate/{device_id}/config"
            await mqtt.async_publish(
                self.hass,
                discovery_topic,
                "",
                qos=1,
                retain=True,
            )

        # Remove sensor configs
        elif device.is_ht_sensor:
            for sensor_type in ["temp", "humidity"]:
                discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device_id}_{sensor_type}/config"
                await mqtt.async_publish(
                    self.hass,
                    discovery_topic,
                    "",
                    qos=1,
                    retain=True,
                )

        # Remove from mapped devices
        del self._mapped_devices[device_id]

    async def async_manual_map_device(
        self,
        device_id: str,
        site_id: str,
        location: str
    ) -> bool:
        """Manually map an unmapped device to a room."""
        device = self._unmapped_devices.get(device_id)
        if not device:
            _LOGGER.error("Device %s not found in unmapped devices", device_id)
            return False

        _LOGGER.info(
            "Manually mapping device %s to room %s, location %s",
            device_id,
            site_id,
            location
        )

        mapping = {
            "device_id": device_id,
            "site_id": site_id,
            "location": location,
            "model": device.model,
            "mac": device.mac,
        }

        # Publish discovery config
        await self._async_publish_discovery_config(device, mapping)

        # Move from unmapped to mapped
        self._mapped_devices[device_id] = mapping
        del self._unmapped_devices[device_id]

        return True

    def get_unmapped_devices(self) -> list[ShellyDevice]:
        """Get list of unmapped devices."""
        return list(self._unmapped_devices.values())

    def get_mapped_devices(self) -> dict[str, dict[str, Any]]:
        """Get dictionary of mapped devices."""
        return self._mapped_devices.copy()
