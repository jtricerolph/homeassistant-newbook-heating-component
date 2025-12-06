"""TRV monitoring and reliability system."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    AUTOMATION_SOURCES,
    CONF_COMMAND_TIMEOUT,
    CONF_MAX_RETRY_ATTEMPTS,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_MAX_RETRY_ATTEMPTS,
    DOMAIN,
    EVENT_TRV_DEGRADED,
    EVENT_TRV_FAILED,
    EVENT_TRV_UNRESPONSIVE,
    GUEST_SOURCES,
    RETRY_DELAYS,
    TRV_HEALTH_DEGRADED,
    TRV_HEALTH_HEALTHY,
    TRV_HEALTH_POOR,
    TRV_HEALTH_UNRESPONSIVE,
)

_LOGGER = logging.getLogger(__name__)


class TRVCommand:
    """Represents a command sent to a TRV."""

    def __init__(
        self,
        entity_id: str,
        target_temp: float,
        sent_at: datetime,
        attempt: int = 1,
    ) -> None:
        """Initialize the command."""
        self.entity_id = entity_id
        self.target_temp = target_temp
        self.sent_at = sent_at
        self.attempt = attempt
        self.acknowledged = False
        self.acknowledged_at: datetime | None = None


class TRVHealth:
    """Tracks health metrics for a TRV."""

    def __init__(self, entity_id: str) -> None:
        """Initialize TRV health tracking."""
        self.entity_id = entity_id
        self.last_seen: datetime | None = None
        self.last_command_sent: datetime | None = None
        self.last_command_ack: datetime | None = None
        self.response_times: list[float] = []  # Last 10 response times in seconds
        self.retry_count_24h: int = 0
        self.current_attempts: int = 0
        self.total_commands: int = 0
        self.failed_commands: int = 0
        self.battery_level: int | None = None

    @property
    def health_state(self) -> str:
        """Determine current health state."""
        if not self.last_seen:
            return TRV_HEALTH_UNRESPONSIVE

        # Check if unresponsive (no response in last 30 minutes)
        age = datetime.now() - self.last_seen
        if age > timedelta(minutes=30):
            return TRV_HEALTH_UNRESPONSIVE

        # Check retry counts
        if self.current_attempts >= 10:
            return TRV_HEALTH_UNRESPONSIVE
        elif self.current_attempts >= 5 or self.retry_count_24h >= 10:
            return TRV_HEALTH_POOR
        elif self.current_attempts >= 3 or self.retry_count_24h >= 5:
            return TRV_HEALTH_DEGRADED

        return TRV_HEALTH_HEALTHY

    @property
    def avg_response_time(self) -> float | None:
        """Get average response time in seconds."""
        if not self.response_times:
            return None
        return sum(self.response_times) / len(self.response_times)

    @property
    def is_responsive(self) -> bool:
        """Check if TRV is currently responsive."""
        return self.health_state != TRV_HEALTH_UNRESPONSIVE

    def record_command_sent(self) -> None:
        """Record that a command was sent."""
        self.last_command_sent = datetime.now()
        self.current_attempts += 1
        self.total_commands += 1

    def record_command_ack(self, response_time: float) -> None:
        """Record successful command acknowledgment."""
        self.last_command_ack = datetime.now()
        self.last_seen = datetime.now()
        self.current_attempts = 0  # Reset attempts on success

        # Track response time (keep last 10)
        self.response_times.append(response_time)
        if len(self.response_times) > 10:
            self.response_times.pop(0)

    def record_command_failed(self) -> None:
        """Record failed command."""
        self.failed_commands += 1
        self.retry_count_24h += 1

    def reset_retry_count(self) -> None:
        """Reset 24-hour retry count (called daily)."""
        self.retry_count_24h = 0

    def update_battery(self, level: int) -> None:
        """Update battery level."""
        self.battery_level = level
        self.last_seen = datetime.now()


class TRVMonitor:
    """Monitor TRV health and handle command retries."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the TRV monitor."""
        self.hass = hass
        self.config = config
        self._commands: dict[str, TRVCommand] = {}
        self._health: dict[str, TRVHealth] = {}
        self._guest_adjustments: dict[str, datetime] = {}  # Track guest changes

        # Get settings
        self._max_retry_attempts = config.get(
            CONF_MAX_RETRY_ATTEMPTS, DEFAULT_MAX_RETRY_ATTEMPTS
        )
        self._command_timeout = config.get(
            CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT
        )

    def get_trv_health(self, entity_id: str) -> TRVHealth:
        """Get or create health tracking for a TRV."""
        if entity_id not in self._health:
            self._health[entity_id] = TRVHealth(entity_id)
        return self._health[entity_id]

    async def set_temperature_with_retry(
        self,
        entity_id: str,
        target_temp: float,
    ) -> bool:
        """Set TRV temperature with retry logic.

        Returns:
            True if command was acknowledged, False if all retries failed
        """
        health = self.get_trv_health(entity_id)
        retry_delays = RETRY_DELAYS[: self._max_retry_attempts]

        _LOGGER.info(
            "Setting %s to %.1f°C (max %d attempts)",
            entity_id,
            target_temp,
            len(retry_delays),
        )

        for attempt in range(1, len(retry_delays) + 1):
            # Send command
            command = TRVCommand(
                entity_id=entity_id,
                target_temp=target_temp,
                sent_at=datetime.now(),
                attempt=attempt,
            )
            self._commands[entity_id] = command
            health.record_command_sent()

            # Actually send the command to Home Assistant
            try:
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_SET_TEMPERATURE,
                    {
                        ATTR_ENTITY_ID: entity_id,
                        ATTR_TEMPERATURE: target_temp,
                    },
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.error("Failed to send command to %s: %s", entity_id, err)
                continue

            # Wait for acknowledgment
            timeout = retry_delays[attempt - 1]
            acknowledged = await self._wait_for_acknowledgment(
                entity_id, target_temp, timeout
            )

            if acknowledged:
                response_time = (datetime.now() - command.sent_at).total_seconds()
                health.record_command_ack(response_time)
                _LOGGER.info(
                    "%s acknowledged temp change to %.1f°C (attempt %d, %.1fs)",
                    entity_id,
                    target_temp,
                    attempt,
                    response_time,
                )

                # Fire health event if degraded
                if health.health_state in [TRV_HEALTH_DEGRADED, TRV_HEALTH_POOR]:
                    self.hass.bus.fire(
                        EVENT_TRV_DEGRADED,
                        {
                            "entity_id": entity_id,
                            "health_state": health.health_state,
                            "attempts": attempt,
                        },
                    )

                return True

            # Not acknowledged, log and retry
            _LOGGER.warning(
                "%s did not acknowledge temp change (attempt %d/%d), retrying in %ds...",
                entity_id,
                attempt,
                len(retry_delays),
                retry_delays[attempt - 1] if attempt < len(retry_delays) else 0,
            )

            # Wait before retry (unless it's the last attempt)
            if attempt < len(retry_delays):
                await asyncio.sleep(retry_delays[attempt - 1])

        # All retries failed
        health.record_command_failed()
        _LOGGER.error(
            "%s failed to acknowledge temp change after %d attempts",
            entity_id,
            len(retry_delays),
        )

        # Fire unresponsive event
        self.hass.bus.fire(
            EVENT_TRV_UNRESPONSIVE,
            {
                "entity_id": entity_id,
                "target_temp": target_temp,
                "attempts": len(retry_delays),
            },
        )

        return False

    async def _wait_for_acknowledgment(
        self,
        entity_id: str,
        target_temp: float,
        timeout: int,
    ) -> bool:
        """Wait for TRV to acknowledge temperature change.

        Checks if the TRV's temperature attribute has changed to the target.
        """
        start_time = datetime.now()
        check_interval = 5  # Check every 5 seconds

        while (datetime.now() - start_time).total_seconds() < timeout:
            # Get current state
            state = self.hass.states.get(entity_id)
            if state:
                current_temp = state.attributes.get(ATTR_TEMPERATURE)
                if current_temp is not None and abs(current_temp - target_temp) < 0.1:
                    # Temperature matches target (within 0.1°C)
                    command = self._commands.get(entity_id)
                    if command:
                        command.acknowledged = True
                        command.acknowledged_at = datetime.now()
                    return True

            await asyncio.sleep(check_interval)

        return False

    async def batch_set_room_temperature(
        self,
        room_id: str,
        entity_ids: list[str],
        target_temp: float,
        stagger_delay: int = 10,
    ) -> dict[str, bool]:
        """Set temperature for multiple TRVs in a room with staggered timing.

        Args:
            room_id: Room identifier
            entity_ids: List of TRV entity IDs
            target_temp: Target temperature
            stagger_delay: Delay between commands in seconds

        Returns:
            Dict mapping entity_id to success boolean
        """
        _LOGGER.info(
            "Setting %d TRVs in room %s to %.1f°C (staggered)",
            len(entity_ids),
            room_id,
            target_temp,
        )

        results = {}

        for i, entity_id in enumerate(entity_ids):
            # Stagger commands to avoid WiFi congestion
            if i > 0:
                await asyncio.sleep(stagger_delay)

            success = await self.set_temperature_with_retry(entity_id, target_temp)
            results[entity_id] = success

        # Log summary
        successful = sum(1 for s in results.values() if s)
        _LOGGER.info(
            "Room %s: %d/%d TRVs successfully set to %.1f°C",
            room_id,
            successful,
            len(entity_ids),
            target_temp,
        )

        return results

    def record_guest_adjustment(
        self,
        entity_id: str,
        new_temp: float,
        source: str,
    ) -> bool:
        """Record a temperature adjustment and determine if it was from a guest.

        Args:
            entity_id: TRV entity ID
            new_temp: New temperature setting
            source: Source of the change (from MQTT payload)

        Returns:
            True if this was a guest adjustment, False if automation
        """
        is_guest_adjustment = source in GUEST_SOURCES

        if is_guest_adjustment:
            self._guest_adjustments[entity_id] = datetime.now()
            _LOGGER.info(
                "Guest adjusted %s to %.1f°C (source: %s)",
                entity_id,
                new_temp,
                source,
            )
        else:
            _LOGGER.debug(
                "Automation adjusted %s to %.1f°C (source: %s)",
                entity_id,
                new_temp,
                source,
            )

        # Update last seen
        health = self.get_trv_health(entity_id)
        health.last_seen = datetime.now()

        return is_guest_adjustment

    def was_recently_adjusted_by_guest(
        self,
        entity_id: str,
        within_minutes: int = 60,
    ) -> bool:
        """Check if TRV was recently adjusted by a guest.

        Args:
            entity_id: TRV entity ID
            within_minutes: Time window to check

        Returns:
            True if guest adjusted within the time window
        """
        last_adjustment = self._guest_adjustments.get(entity_id)
        if not last_adjustment:
            return False

        age = datetime.now() - last_adjustment
        return age < timedelta(minutes=within_minutes)

    def get_room_trvs(self, room_id: str) -> list[str]:
        """Get all TRV entity IDs for a room.

        Looks for climate entities with the room ID in their entity_id.
        """
        # Get site_name from coordinator
        from .const import DOMAIN

        coordinator = None
        for entry_id, data in self.hass.data[DOMAIN].items():
            if isinstance(data, dict) and "coordinator" in data:
                coordinator = data["coordinator"]
                break

        if not coordinator:
            return []

        rooms = coordinator.get_all_rooms()
        room_info = rooms.get(room_id)
        if not room_info:
            return []

        site_name = room_info.get("site_name", room_id)

        entity_registry = er.async_get(self.hass)
        trvs = []

        for entity in entity_registry.entities.values():
            if entity.domain == "climate" and f"room_{site_name}_" in entity.entity_id:
                trvs.append(entity.entity_id)

        return trvs

    def filter_room_trvs(
        self,
        room_id: str,
        exclude_bathroom: bool = False,
    ) -> list[str]:
        """Get TRVs for a room, optionally excluding bathroom.

        Args:
            room_id: Room identifier
            exclude_bathroom: If True, exclude TRVs with 'bathroom' in entity_id

        Returns:
            List of TRV entity IDs
        """
        trvs = self.get_room_trvs(room_id)

        if exclude_bathroom:
            trvs = [trv for trv in trvs if "bathroom" not in trv.lower()]

        return trvs

    async def retry_unresponsive_trvs(self) -> dict[str, bool]:
        """Retry sending commands to all unresponsive TRVs.

        Returns:
            Dict mapping entity_id to success boolean
        """
        unresponsive = [
            entity_id
            for entity_id, health in self._health.items()
            if not health.is_responsive
        ]

        if not unresponsive:
            _LOGGER.info("No unresponsive TRVs to retry")
            return {}

        _LOGGER.info("Retrying %d unresponsive TRVs", len(unresponsive))
        results = {}

        for entity_id in unresponsive:
            # Get last commanded temperature
            command = self._commands.get(entity_id)
            if command:
                target_temp = command.target_temp
            else:
                # Try to get current target from state
                state = self.hass.states.get(entity_id)
                if state:
                    target_temp = state.attributes.get(ATTR_TEMPERATURE)
                    if target_temp is None:
                        _LOGGER.warning("Cannot determine target temp for %s", entity_id)
                        continue
                else:
                    continue

            success = await self.set_temperature_with_retry(entity_id, target_temp)
            results[entity_id] = success

        return results

    def get_health_summary(self) -> dict[str, Any]:
        """Get summary of all TRV health states.

        Returns:
            Dict with health statistics
        """
        summary = {
            "total": len(self._health),
            "healthy": 0,
            "degraded": 0,
            "poor": 0,
            "unresponsive": 0,
            "details": [],
        }

        for entity_id, health in self._health.items():
            state = health.health_state
            summary[state] += 1

            summary["details"].append(
                {
                    "entity_id": entity_id,
                    "health_state": state,
                    "last_seen": health.last_seen.isoformat() if health.last_seen else None,
                    "current_attempts": health.current_attempts,
                    "retry_count_24h": health.retry_count_24h,
                    "avg_response_time": health.avg_response_time,
                    "battery_level": health.battery_level,
                }
            )

        return summary

    async def update_battery_levels(self) -> None:
        """Update battery levels for all tracked TRVs."""
        entity_registry = er.async_get(self.hass)

        for entity_id, health in self._health.items():
            # Try to find battery sensor for this TRV
            # Battery sensors typically follow pattern: sensor.{device}_battery
            device_name = entity_id.replace("climate.", "").replace("_trv", "")
            battery_sensor = f"sensor.{device_name}_battery"

            state = self.hass.states.get(battery_sensor)
            if state and state.state not in ["unknown", "unavailable"]:
                try:
                    battery_level = int(float(state.state))
                    health.update_battery(battery_level)
                except (ValueError, TypeError):
                    pass

    @callback
    def async_reset_daily_counts(self) -> None:
        """Reset daily retry counts for all TRVs."""
        _LOGGER.info("Resetting daily retry counts for all TRVs")
        for health in self._health.values():
            health.reset_retry_count()
