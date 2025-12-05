"""Shelly device detector for MQTT autodiscovery."""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Supported Shelly device models
SHELLY_TRV_MODELS = ["SHTRV-01"]
SHELLY_HT_MODELS = ["SHHT-1"]
SHELLY_CLIMATE_MODELS = SHELLY_TRV_MODELS + SHELLY_HT_MODELS


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
    def is_ht_sensor(self) -> bool:
        """Check if device is H&T sensor."""
        return self.model in SHELLY_HT_MODELS

    @property
    def is_climate_device(self) -> bool:
        """Check if device is any climate-related device."""
        return self.model in SHELLY_CLIMATE_MODELS

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

            # Only process climate-related devices
            if not device.is_climate_device:
                _LOGGER.debug(
                    "Detected non-climate Shelly device %s (model: %s), skipping",
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

    def get_device(self, device_id: str) -> ShellyDevice | None:
        """Get device by ID."""
        return self._devices.get(device_id)

    def get_all_devices(self) -> list[ShellyDevice]:
        """Get all detected devices."""
        return list(self._devices.values())

    def get_climate_devices(self) -> list[ShellyDevice]:
        """Get all climate devices (TRVs, H&T)."""
        return [d for d in self._devices.values() if d.is_climate_device]

    def remove_device(self, device_id: str) -> None:
        """Remove device from tracking."""
        if device_id in self._devices:
            _LOGGER.info("Removing Shelly device: %s", device_id)
            del self._devices[device_id]
