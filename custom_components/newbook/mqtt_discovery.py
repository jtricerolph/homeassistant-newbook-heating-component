"""MQTT discovery manager for Shelly devices."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    MQTT_DISCOVERY_PREFIX,
    SHELLY_ANNOUNCE_TOPIC,
    SHELLY_ONLINE_TOPIC,
    SHELLY_STATUS_TOPIC,
    SIGNAL_TRV_DISCOVERED,
    SIGNAL_TRV_SETTINGS_UPDATED,
    SIGNAL_TRV_STATUS_UPDATED,
)
from .shelly_detector import ShellyDetector, ShellyDevice

_LOGGER = logging.getLogger(__name__)


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

            # Extract TRV device settings and store in TRV health
            await self._async_update_trv_settings(device, payload)

        except json.JSONDecodeError as err:
            _LOGGER.error("Failed to decode settings message: %s", err)
        except Exception as err:
            _LOGGER.error("Error processing settings message: %s", err)

    async def _async_update_trv_settings(
        self,
        device: ShellyDevice,
        payload: dict[str, Any]
    ) -> None:
        """Update TRV health with device settings from MQTT settings message."""
        # Only process for mapped devices
        mapping = self._mapped_devices.get(device.device_id)
        if not mapping:
            return

        site_id = mapping["site_id"]
        location = mapping["location"]
        entity_id = f"climate.room_{site_id}_{location}"

        # Get TRV monitor and health object
        trv_monitor = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("trv_monitor")
        if not trv_monitor:
            return

        health = trv_monitor.get_trv_health(entity_id)

        # Extract settings from payload
        display_brightness = payload.get("display_brightness")
        display_flipped = payload.get("display_flipped")

        # Clog prevention is in ext_power_flags bitmask (bit 0)
        ext_power_flags = payload.get("ext_power_flags", 0)
        clog_prevention = bool(ext_power_flags & 1) if ext_power_flags is not None else None

        # Also get device IP from wifi_sta
        wifi_sta = payload.get("wifi_sta", {})
        device_ip = wifi_sta.get("ip")
        if device_ip:
            health.set_device_ip(device_ip)

        # Update settings
        health.update_device_settings(
            display_brightness=display_brightness,
            display_flipped=display_flipped,
            clog_prevention=clog_prevention,
        )

        _LOGGER.debug(
            "Updated %s settings: brightness=%s, flipped=%s, clog_prevention=%s, ip=%s",
            entity_id,
            display_brightness,
            display_flipped,
            clog_prevention,
            device_ip,
        )

        # Notify entities that settings have been updated
        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_TRV_SETTINGS_UPDATED}_{self.entry_id}",
            entity_id,
        )

    def _get_room_site_name(self, site_id: str) -> str | None:
        """Get the Newbook room's site_name for area matching."""
        try:
            coordinator = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("coordinator")
            if not coordinator:
                return None

            rooms = coordinator.get_all_rooms()
            for room_id, room_info in rooms.items():
                if str(room_info.get("site_id")) == str(site_id):
                    return room_info.get("site_name", site_id)

            # Room not found in Newbook, use site_id directly (e.g., "209")
            # This ensures consistency with area naming from initial load
            return site_id
        except Exception as err:
            _LOGGER.warning("Failed to lookup room site_name for %s: %s", site_id, err)
            return site_id

    async def _async_process_device(self, device: ShellyDevice) -> None:
        """Process detected device and map to room if possible."""
        # Check if already mapped
        if device.device_id in self._mapped_devices:
            _LOGGER.debug("Device %s already mapped", device.device_id)
            return

        # Try to extract room info from device name by splitting on underscores
        # Expected format: room_{site_id}_{location}[_{other}...]
        parts = device.name.lower().split('_')

        if len(parts) >= 3 and parts[0] == 'room':
            # Extract site_id and location from 2nd and 3rd tokens
            site_id = parts[1]
            location = parts[2]

            # Check for duplicate site_id + location mapping (different device, same name)
            for existing_device_id, existing_mapping in self._mapped_devices.items():
                if (existing_mapping["site_id"] == site_id and
                    existing_mapping["location"] == location and
                    existing_mapping["mac"] != device.mac):
                    # Duplicate name detected - notify user and skip
                    _LOGGER.warning(
                        "Duplicate device name detected: %s (MAC: %s) has the same room mapping "
                        "as existing device %s (MAC: %s)",
                        device.device_id,
                        device.mac,
                        existing_device_id,
                        existing_mapping["mac"]
                    )
                    await self._async_notify_duplicate_name(
                        device, site_id, location, existing_device_id
                    )
                    return

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

            # Store mapping BEFORE publishing to prevent duplicate processing
            self._mapped_devices[device.device_id] = mapping

            # Publish discovery config
            await self._async_publish_discovery_config(device, mapping)

        else:
            # Device doesn't match pattern - add to unmapped (if not already there)
            if device.device_id not in self._unmapped_devices:
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
        """Publish Home Assistant MQTT discovery config for TRV."""
        if device.is_trv:
            await self._async_publish_climate_config(device, mapping)

    def _ensure_area_exists(self, area_name: str) -> None:
        """Ensure an area exists, create it if it doesn't."""
        area_reg = ar.async_get(self.hass)

        # Check if area already exists
        for area in area_reg.async_list_areas():
            if area.name == area_name:
                return

        # Create the area
        _LOGGER.info("Creating area %s for newly discovered device", area_name)
        area_reg.async_create(area_name)

    async def _async_publish_climate_config(
        self,
        device: ShellyDevice,
        mapping: dict[str, Any]
    ) -> None:
        """Publish climate entity discovery config for Shelly TRV."""
        site_id = mapping["site_id"]
        location = mapping["location"]
        entity_id = f"room_{site_id}_{location}"

        # Get the Newbook room's site_name for area matching
        site_name = self._get_room_site_name(site_id)

        # Ensure the area exists before publishing discovery config
        # This is necessary because suggested_area only works if the area exists
        if site_name:
            self._ensure_area_exists(site_name)

        # Discovery topic
        discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/climate/{device.device_id}/config"

        # Build config payload
        config = {
            "unique_id": f"shelly_{device.mac}_climate",
            "name": f"Room {site_id} {location.capitalize()}",
            "default_entity_id": f"climate.{entity_id}",

            # Mode - TRV only supports heat mode (no on/off)
            "modes": ["heat"],
            "mode_stat_t": f"shellies/{device.device_id}/status",
            "mode_stat_tpl": "heat",  # Always heat since TRV is heat-only

            # Temperature control
            "temp_cmd_t": f"shellies/{device.device_id}/thermostat/0/command/target_t",
            "temp_cmd_tpl": "{{ value }}",
            "temp_stat_t": f"shellies/{device.device_id}/status",
            "temp_stat_tpl": "{{ value_json.target_t.value }}",

            # Current temperature
            "curr_temp_t": f"shellies/{device.device_id}/status",
            "curr_temp_tpl": "{{ value_json.tmp.value }}",

            # HVAC action (heating/idle based on valve position)
            "action_topic": f"shellies/{device.device_id}/info",
            "action_template": "{% if value_json.thermostats[0].pos > 0 %}heating{% else %}idle{% endif %}",

            # Temperature settings
            "min_temp": 5,
            "max_temp": 30,
            "temp_step": 0.5,
            "precision": 0.1,
            "temperature_unit": "C",

            # Device info
            "device": {
                "identifiers": [f"shelly_{device.mac}"],
                "name": f"Room {site_id} {location.capitalize()} TRV",
                "model": device.model,
                "manufacturer": "Shelly",
                "sw_version": device.firmware,
                "configuration_url": f"http://{device.ip}",
                "suggested_area": site_name,
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
        await self._async_subscribe_device_status(device, mapping)

        # Subscribe to command topic to track HA commands
        await self._async_subscribe_device_commands(device, mapping)

        # Publish diagnostic sensors
        await self._async_publish_diagnostic_sensors(device, mapping)

        # Assign device to area (do this after publishing config to ensure device exists)
        if site_name:
            await self._async_assign_device_to_area(device.mac, site_name)

        # Fire signal for sensor.py to create target temp sensor
        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_TRV_DISCOVERED}_{self.entry_id}",
            {
                "entity_id": f"climate.room_{site_id}_{location}",
                "site_id": site_id,
                "location": location,
                "mac": device.mac,
                "device_id": device.device_id,
            },
        )

    async def _async_publish_diagnostic_sensors(
        self,
        device: ShellyDevice,
        mapping: dict[str, Any]
    ) -> None:
        """Publish diagnostic sensor discovery configs for Shelly TRV."""
        site_id = mapping["site_id"]
        location = mapping["location"]
        entity_id_base = f"room_{site_id}_{location}"

        # Common device info for all diagnostic sensors
        device_info = {
            "identifiers": [f"shelly_{device.mac}"],
            "name": f"Room {site_id} {location.capitalize()} TRV",
        }

        # Battery sensor
        battery_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device.device_id}_battery/config"
        battery_config = {
            "unique_id": f"shelly_{device.mac}_battery",
            "name": f"Room {site_id} {location.capitalize()} TRV Battery",
            "default_entity_id": f"sensor.{entity_id_base}_trv_battery",
            "stat_t": f"shellies/{device.device_id}/info",
            "value_template": "{{ value_json.bat.value }}",
            "unit_of_measurement": "%",
            "device_class": "battery",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "json_attributes_topic": f"shellies/{device.device_id}/info",
            "json_attributes_template": '{{ {"voltage": value_json.bat.voltage, "charging": value_json.charger} | tojson }}',
            "device": device_info,
        }

        # WiFi Signal sensor
        wifi_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device.device_id}_wifi/config"
        wifi_config = {
            "unique_id": f"shelly_{device.mac}_wifi_signal",
            "name": f"Room {site_id} {location.capitalize()} TRV WiFi Signal",
            "default_entity_id": f"sensor.{entity_id_base}_trv_wifi_signal",
            "stat_t": f"shellies/{device.device_id}/info",
            "value_template": "{{ value_json.wifi_sta.rssi }}",
            "unit_of_measurement": "dBm",
            "device_class": "signal_strength",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "json_attributes_topic": f"shellies/{device.device_id}/info",
            "json_attributes_template": '{{ {"ssid": value_json.wifi_sta.ssid, "ip": value_json.wifi_sta.ip} | tojson }}',
            "device": device_info,
        }

        # WiFi Health sensor (derived from RSSI: good >= -70, fair >= -80, poor < -80)
        wifi_health_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device.device_id}_wifi_health/config"
        wifi_health_config = {
            "unique_id": f"shelly_{device.mac}_wifi_health",
            "name": f"Room {site_id} {location.capitalize()} TRV WiFi Health",
            "default_entity_id": f"sensor.{entity_id_base}_trv_wifi_health",
            "stat_t": f"shellies/{device.device_id}/info",
            "value_template": "{% set rssi = value_json.wifi_sta.rssi | int(-100) %}{% if rssi >= -70 %}good{% elif rssi >= -80 %}fair{% else %}poor{% endif %}",
            "icon": "mdi:wifi",
            "entity_category": "diagnostic",
            "json_attributes_topic": f"shellies/{device.device_id}/info",
            "json_attributes_template": '{{ {"rssi": value_json.wifi_sta.rssi, "ssid": value_json.wifi_sta.ssid} | tojson }}',
            "device": device_info,
        }

        # Calibration status binary sensor
        calibration_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/{device.device_id}_calibrated/config"
        calibration_config = {
            "unique_id": f"shelly_{device.mac}_calibrated",
            "name": f"Room {site_id} {location.capitalize()} TRV Calibration",
            "default_entity_id": f"binary_sensor.{entity_id_base}_trv_calibration",
            "stat_t": f"shellies/{device.device_id}/info",
            "value_template": "{% if value_json.calibrated %}OFF{% else %}ON{% endif %}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "problem",
            "entity_category": "diagnostic",
            "device": device_info,
        }

        # Update available binary sensor
        update_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/{device.device_id}_update/config"
        update_config = {
            "unique_id": f"shelly_{device.mac}_update_available",
            "name": f"Room {site_id} {location.capitalize()} TRV Update Available",
            "default_entity_id": f"binary_sensor.{entity_id_base}_trv_update_available",
            "stat_t": f"shellies/{device.device_id}/info",
            "value_template": "{{ 'ON' if (value_json.get('update', {}).get('has_update', false)) else 'OFF' }}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "update",
            "entity_category": "diagnostic",
            "json_attributes_topic": f"shellies/{device.device_id}/info",
            "json_attributes_template": '{% set update = value_json.get("update", {}) %}{{ {"status": update.get("status", "unknown"), "new_version": update.get("new_version", ""), "old_version": update.get("old_version", "")} | tojson }}',
            "device": device_info,
        }

        # Valve position sensor
        valve_position_discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/sensor/{device.device_id}_valve_position/config"
        valve_position_config = {
            "unique_id": f"shelly_{device.mac}_valve_position",
            "name": f"Room {site_id} {location.capitalize()} TRV Valve Position",
            "default_entity_id": f"sensor.{entity_id_base}_trv_valve_position",
            "stat_t": f"shellies/{device.device_id}/info",
            "value_template": "{{ value_json.thermostats[0].pos }}",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "icon": "mdi:valve",
            "device": device_info,
        }

        _LOGGER.info("Publishing diagnostic sensor discovery configs for %s", device.device_id)

        # Publish all configs
        await mqtt.async_publish(
            self.hass,
            battery_discovery_topic,
            json.dumps(battery_config),
            qos=1,
            retain=True,
        )

        await mqtt.async_publish(
            self.hass,
            wifi_discovery_topic,
            json.dumps(wifi_config),
            qos=1,
            retain=True,
        )

        await mqtt.async_publish(
            self.hass,
            wifi_health_discovery_topic,
            json.dumps(wifi_health_config),
            qos=1,
            retain=True,
        )

        await mqtt.async_publish(
            self.hass,
            calibration_discovery_topic,
            json.dumps(calibration_config),
            qos=1,
            retain=True,
        )

        await mqtt.async_publish(
            self.hass,
            update_discovery_topic,
            json.dumps(update_config),
            qos=1,
            retain=True,
        )

        await mqtt.async_publish(
            self.hass,
            valve_position_discovery_topic,
            json.dumps(valve_position_config),
            qos=1,
            retain=True,
        )

        # Subscribe to info topic for diagnostic data
        await self._async_subscribe_device_info(device, mapping)

    async def _async_assign_device_to_area(self, mac: str, area_name: str) -> None:
        """Assign a device to an area using device and area registries."""
        # Small delay to ensure device is created by Home Assistant
        await asyncio.sleep(2)

        device_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)

        # Find the area
        area_id = None
        for area in area_reg.async_list_areas():
            if area.name == area_name:
                area_id = area.id
                break

        if not area_id:
            _LOGGER.warning("Area %s not found when trying to assign device", area_name)
            return

        # Find the device by identifier (shelly_{mac})
        device_identifier = f"shelly_{mac}"
        device_entry = None
        for device in device_reg.devices.values():
            for identifier_set in device.identifiers:
                if device_identifier in identifier_set:
                    device_entry = device
                    break
            if device_entry:
                break

        if not device_entry:
            _LOGGER.warning("Device with MAC %s not found in device registry", mac)
            return

        # Assign device to area
        if device_entry.area_id != area_id:
            _LOGGER.info("Assigning device %s to area %s", device_entry.name, area_name)
            device_reg.async_update_device(device_entry.id, area_id=area_id)
        else:
            _LOGGER.debug("Device %s already in area %s", device_entry.name, area_name)

    async def _async_subscribe_device_status(self, device: ShellyDevice, mapping: dict) -> None:
        """Subscribe to device status for health monitoring."""
        status_topic = f"shellies/{device.device_id}/status"
        site_id = mapping["site_id"]
        location = mapping["location"]

        @callback
        async def status_received(msg: mqtt.ReceiveMessage) -> None:
            """Handle device status update."""
            try:
                payload = json.loads(msg.payload)
                _LOGGER.debug("Device %s status: %s", device.device_id, payload)

                # Feed target temperature into TRV monitor for origin detection
                target_temp = payload.get("target_t", {}).get("value")
                if target_temp is not None:
                    trv_monitor = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("trv_monitor")
                    if trv_monitor:
                        entity_id = f"climate.room_{site_id}_{location}"
                        health = trv_monitor.get_trv_health(entity_id)
                        health.update_from_status(float(target_temp))
                        _LOGGER.debug("Updated %s target temp from status: %.1f", entity_id, target_temp)

                        # Notify sensors to update their state
                        async_dispatcher_send(
                            self.hass,
                            f"{SIGNAL_TRV_STATUS_UPDATED}_{self.entry_id}",
                            entity_id,
                        )

            except Exception as err:
                _LOGGER.error("Error processing status for %s: %s", device.device_id, err)

        await mqtt.async_subscribe(
            self.hass,
            status_topic,
            status_received,
            qos=1,
        )

    async def _async_subscribe_device_commands(self, device: ShellyDevice, mapping: dict) -> None:
        """Subscribe to command topic to track HA commands for origin detection."""
        command_topic = f"shellies/{device.device_id}/thermostat/0/command/target_t"
        site_id = mapping["site_id"]
        location = mapping["location"]

        @callback
        async def command_received(msg: mqtt.ReceiveMessage) -> None:
            """Handle command sent to TRV (track HA commands)."""
            try:
                # The payload is just a number (the target temp)
                target_temp = float(msg.payload)
                _LOGGER.debug("HA command to %s: set temp to %.1f", device.device_id, target_temp)

                # Record this as an HA command for origin detection
                trv_monitor = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("trv_monitor")
                if trv_monitor:
                    entity_id = f"climate.room_{site_id}_{location}"
                    health = trv_monitor.get_trv_health(entity_id)
                    health.record_ha_command(target_temp)
                    _LOGGER.debug("Recorded HA command for %s: %.1f", entity_id, target_temp)

                    # Notify sensors to update their state
                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_TRV_STATUS_UPDATED}_{self.entry_id}",
                        entity_id,
                    )

            except (ValueError, TypeError) as err:
                _LOGGER.debug("Could not parse command payload for %s: %s", device.device_id, err)
            except Exception as err:
                _LOGGER.error("Error processing command for %s: %s", device.device_id, err)

        await mqtt.async_subscribe(
            self.hass,
            command_topic,
            command_received,
            qos=1,
        )

    async def _async_subscribe_device_info(self, device: ShellyDevice, mapping: dict) -> None:
        """Subscribe to device info for diagnostic data."""
        info_topic = f"shellies/{device.device_id}/info"
        site_id = mapping["site_id"]
        location = mapping["location"]

        @callback
        async def info_received(msg: mqtt.ReceiveMessage) -> None:
            """Handle device info update."""
            try:
                payload = json.loads(msg.payload)
                _LOGGER.debug("Device %s info: battery=%s%%, WiFi=%sdBm",
                             device.device_id,
                             payload.get("bat", {}).get("value"),
                             payload.get("wifi_sta", {}).get("rssi"))

                # Feed valve position and calibration status into TRV health tracking
                trv_monitor = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("trv_monitor")
                if trv_monitor:
                    entity_id = f"climate.room_{site_id}_{location}"
                    health = trv_monitor.get_trv_health(entity_id)

                    # Update valve position
                    thermostats = payload.get("thermostats", [{}])
                    if thermostats:
                        valve_pos = thermostats[0].get("pos", 0)
                        health.valve_position = valve_pos

                    # Update calibration status
                    calibrated = payload.get("calibrated", True)
                    health.is_calibrated = calibrated

                    # Update device IP for HTTP wake-up
                    wifi_sta = payload.get("wifi_sta", {})
                    device_ip = wifi_sta.get("ip")
                    if device_ip:
                        health.set_device_ip(device_ip)

                    # Update last_seen
                    health.last_seen = datetime.now()

                    _LOGGER.debug(
                        "Updated %s health: valve_pos=%s%%, calibrated=%s, ip=%s",
                        entity_id, valve_pos, calibrated, device_ip
                    )

                    # Notify sensors to update their state
                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_TRV_STATUS_UPDATED}_{self.entry_id}",
                        entity_id,
                    )

            except Exception as err:
                _LOGGER.error("Error processing info for %s: %s", device.device_id, err)

        await mqtt.async_subscribe(
            self.hass,
            info_topic,
            info_received,
            qos=1,
        )

    async def _async_notify_duplicate_name(
        self,
        device: ShellyDevice,
        site_id: str,
        location: str,
        existing_device_id: str
    ) -> None:
        """Notify user when duplicate room name is detected."""
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Duplicate Shelly Device Name",
                "message": (
                    f"Device '{device.device_id}' (MAC: {device.mac}) has the same name "
                    f"as existing device '{existing_device_id}' (Room {site_id} {location.capitalize()}).\n\n"
                    f"Please rename one device in Shelly settings to avoid conflicts."
                ),
                "notification_id": f"newbook_duplicate_name_{device.mac}",
            },
        )
        _LOGGER.info(
            "Created duplicate name notification for device %s (Room %s %s)",
            device.device_id,
            site_id,
            location.capitalize()
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

        # Remove TRV climate config
        if device.is_trv:
            discovery_topic = f"{MQTT_DISCOVERY_PREFIX}/climate/{device_id}/config"
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

    async def async_fire_discovery_for_existing_devices(self) -> None:
        """Fire discovery signals for all already-mapped devices.

        This is called after platforms are set up to ensure entities
        are created for devices that were discovered before platforms
        subscribed to the discovery signal.
        """
        for device_id, mapping in self._mapped_devices.items():
            device = self.detector.get_device(device_id)
            if not device:
                continue

            site_id = mapping["site_id"]
            location = mapping["location"]

            _LOGGER.info(
                "Re-firing discovery signal for existing device %s (room %s %s)",
                device_id,
                site_id,
                location,
            )

            async_dispatcher_send(
                self.hass,
                f"{SIGNAL_TRV_DISCOVERED}_{self.entry_id}",
                {
                    "entity_id": f"climate.room_{site_id}_{location}",
                    "site_id": site_id,
                    "location": location,
                    "mac": device.mac,
                    "device_id": device_id,
                },
            )
