"""Shelly device detector for MQTT autodiscovery."""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Supported Shelly device models (TRVs only)
SHELLY_TRV_MODELS = ["SHTRV-01"]


class ShellyDevice:
    """Represents a detected Shelly device."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize from announce message."""
        self.device_id: str = data.get("id", "")
        self.mac: str = data.get("mac", "")
        self.model: str = data.get("model", "")
        self.ip: str = data.get("ip", "")
        self.firmware: str = data.get("fw_ver", "")
        self.has_update: bool = data.get("new_fw", False)

        # Extract device name from ID (e.g., "shellytrv-84FD270DD7CC" -> "shellytrv-84FD270DD7CC")
        self.name: str = self.device_id

    @property
    def is_gen1(self) -> bool:
        """Check if device is Gen1 (no 'gen' field means Gen1)."""
        return True  # Gen1 devices don't have 'gen' field in announce

    @property
    def is_trv(self) -> bool:
        """Check if device is a TRV."""
        return self.model in SHELLY_TRV_MODELS

    @property
    def short_mac(self) -> str:
        """Get short MAC address (last 6 chars)."""
        return self.mac[-6:] if len(self.mac) >= 6 else self.mac

    def __repr__(self) -> str:
        """String representation."""
        return f"ShellyDevice(id={self.device_id}, model={self.model}, mac={self.mac})"


class ShellyDetector:
    """Detector for Shelly devices via MQTT."""

    def __init__(self) -> None:
        """Initialize the detector."""
        self._devices: dict[str, ShellyDevice] = {}

    def parse_announce(self, payload: dict[str, Any]) -> ShellyDevice | None:
        """Parse Shelly announce message.

        Example payload:
        {
            "id": "shellytrv-84FD270DD7CC",
            "model": "SHTRV-01",
            "mac": "84FD270DD7CC",
            "ip": "10.4.2.5",
            "new_fw": true,
            "fw_ver": "20220811-152343/v2.1.8@5afc928c"
        }
        """
        try:
            # Validate required fields
            if not payload.get("id") or not payload.get("model"):
                _LOGGER.debug("Invalid announce payload: missing id or model")
                return None

            # Check if Gen2+ (has 'gen' field) - we only support Gen1
            if "gen" in payload:
                _LOGGER.debug(
                    "Detected Gen2+ Shelly device %s, skipping (only Gen1 supported)",
                    payload.get("id")
                )
                return None

            device = ShellyDevice(payload)

            # Only process TRV devices
            if not device.is_trv:
                _LOGGER.debug(
                    "Detected non-TRV Shelly device %s (model: %s), skipping",
                    device.device_id,
                    device.model
                )
                return None

            # Store device
            self._devices[device.device_id] = device

            _LOGGER.info(
                "Detected Shelly %s: %s (MAC: %s, IP: %s, FW: %s)",
                device.model,
                device.device_id,
                device.mac,
                device.ip,
                device.firmware
            )

            return device

        except Exception as err:
            _LOGGER.error("Error parsing Shelly announce message: %s", err)
            return None

    def parse_settings(self, device_id: str, payload: dict[str, Any]) -> ShellyDevice | None:
        """Parse Shelly settings message.

        Example payload:
        {
            "name": "room_101_bedroom",
            "device": {
                "type": "SHTRV-01",
                "mac": "84FD270DD7CC",
                "hostname": "shellytrv-84FD270DD7CC"
            },
            "wifi_ap": {...},
            "wifi_sta": {...},
            "mqtt": {...},
            "sntp": {...},
            "login": {...},
            "pin_code": "000000",
            "coiot": {...},
            "time": "15:30",
            "timezone": "UTC",
            "lat": 50.4501,
            "lng": 30.5234,
            "tzautodetect": false,
            "tz_utc_offset": 0,
            "tz_dst": false,
            "tz_dst_auto": true,
            "discoverable": true
        }

        device_id is extracted from the MQTT topic: shellies/{device_id}/settings
        """
        try:
            # Validate required fields
            device_info = payload.get("device", {})
            device_type = device_info.get("type", "")
            device_mac = device_info.get("mac", "")
            device_name = payload.get("name", device_id)  # Use name from settings, fallback to device_id

            if not device_type or not device_mac:
                _LOGGER.debug("Invalid settings payload: missing device.type or device.mac")
                return None

            # Check if Gen2+ (settings structure is different for Gen2)
            # Gen1 has device.type, Gen2 has different structure
            # For now we assume Gen1 if we got this far

            # Build announce-like structure for ShellyDevice
            announce_data = {
                "id": device_id,
                "model": device_type,
                "mac": device_mac,
                "ip": payload.get("wifi_sta", {}).get("ip", ""),
                "fw_ver": "",  # Not available in settings
            }

            device = ShellyDevice(announce_data)

            # Override the name with the settings name field
            device.name = device_name

            # Only process TRV devices
            if not device.is_trv:
                _LOGGER.debug(
                    "Detected non-TRV Shelly device %s (model: %s), skipping",
                    device.device_id,
                    device.model
                )
                return None

            # Store device
            self._devices[device.device_id] = device

            _LOGGER.info(
                "Detected Shelly %s from settings: %s (name: %s, MAC: %s, IP: %s)",
                device.model,
                device.device_id,
                device.name,
                device.mac,
                device.ip
            )

            return device

        except Exception as err:
            _LOGGER.error("Error parsing Shelly settings message: %s", err)
            return None

    def get_device(self, device_id: str) -> ShellyDevice | None:
        """Get device by ID."""
        return self._devices.get(device_id)

    def get_all_devices(self) -> list[ShellyDevice]:
        """Get all detected devices."""
        return list(self._devices.values())

    def get_trv_devices(self) -> list[ShellyDevice]:
        """Get all TRV devices."""
        return [d for d in self._devices.values() if d.is_trv]

    def remove_device(self, device_id: str) -> None:
        """Remove device from tracking."""
        if device_id in self._devices:
            _LOGGER.info("Removing Shelly device: %s", device_id)
            del self._devices[device_id]
