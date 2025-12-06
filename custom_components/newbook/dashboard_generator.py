"""Dashboard generator for Newbook integration."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .room_manager import normalize_room_id

_LOGGER = logging.getLogger(__name__)

DASHBOARDS_DIR = "dashboards/newbook"


class DashboardGenerator:
    """Generate Lovelace dashboards for Newbook integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize dashboard generator."""
        self.hass = hass
        self.dashboards_path = Path(hass.config.path(DASHBOARDS_DIR))

    async def async_generate_all_dashboards(self, rooms: dict[str, dict[str, Any]]) -> None:
        """Generate single unified dashboard with multiple views."""
        _LOGGER.info("Generating unified Newbook dashboard for %d rooms", len(rooms))

        # Ensure dashboards directory exists
        await self.hass.async_add_executor_job(self._ensure_directory)

        # Generate single dashboard with all views
        try:
            await self._async_generate_unified_dashboard(rooms)
            _LOGGER.info("Successfully generated unified Newbook dashboard")
        except Exception as err:
            _LOGGER.error("Error generating dashboard: %s", err, exc_info=True)

    def _ensure_directory(self) -> None:
        """Ensure dashboards directory exists."""
        self.dashboards_path.mkdir(parents=True, exist_ok=True)

    async def _async_generate_unified_dashboard(self, rooms: dict[str, dict[str, Any]]) -> None:
        """Generate single dashboard with all views (home, rooms, battery, health)."""
        _LOGGER.debug("Generating unified dashboard with %d rooms", len(rooms))

        views = []

        # View 1: Home overview (visible tab)
        views.append(self._generate_home_view(rooms))

        # Views 2-N: Individual room views (hidden, navigation only)
        for room_id, room_info in rooms.items():
            views.append(self._generate_room_view(room_id, room_info))

        # View N+1: Battery monitoring (visible tab)
        views.append(self._generate_battery_view())

        # View N+2: Health monitoring (visible tab)
        views.append(self._generate_health_view())

        # Create unified dashboard
        dashboard = {
            "title": "Hotel Heating",
            "icon": "mdi:hotel",
            "views": views,
        }

        await self._async_write_dashboard("newbook.yaml", dashboard)

    def _generate_home_view(self, rooms: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Generate home overview view."""
        # Sort rooms by room ID
        sorted_rooms = sorted(rooms.items(), key=lambda x: str(x[0]))

        section_cards = []

        # Title card
        section_cards.append({
            "type": "markdown",
            "content": "# 🏨 Hotel Heating Overview\nManage heating for all rooms based on Newbook bookings.",
        })

        # Room cards in grid
        for room_id, room_info in sorted_rooms:
            site_name = room_info.get("site_name", room_id)
            normalized_id = normalize_room_id(site_name)
            room_name = site_name

            card = {
                "type": "custom:mushroom-template-card",
                "primary": room_name,
                "secondary": "{{ states('sensor.room_" + site_name + "_guest_name') }}",
                "icon": "mdi:radiator",
                "icon_color": "{% if is_state('binary_sensor.room_" + site_name + "_should_heat', 'on') %}red{% else %}blue{% endif %}",
                "badge_icon": "{% if is_state('switch.room_" + site_name + "_auto_mode', 'on') %}mdi:auto-fix{% else %}mdi:hand{% endif %}",
                "badge_color": "{% if is_state('switch.room_" + site_name + "_auto_mode', 'on') %}green{% else %}orange{% endif %}",
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": f"/dashboard-newbook/room-{normalized_id}",
                },
                "entity": f"binary_sensor.room_{site_name}_should_heat",
            }
            section_cards.append(card)

        # Services card
        services_card = {
            "type": "entities",
            "title": "🔧 Quick Actions",
            "entities": [
                {
                    "type": "button",
                    "name": "Refresh Bookings",
                    "icon": "mdi:refresh",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.refresh_bookings",
                    },
                },
                {
                    "type": "button",
                    "name": "Retry Unresponsive TRVs",
                    "icon": "mdi:reload-alert",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.retry_unresponsive_trvs",
                    },
                },
            ],
        }
        section_cards.append(services_card)

        # System status card
        system_card = {
            "type": "entities",
            "title": "📊 System Status",
            "entities": [
                "sensor.newbook_system_status",
                "sensor.newbook_last_update",
                "sensor.newbook_rooms_discovered",
                "sensor.newbook_active_bookings",
            ],
        }
        section_cards.append(system_card)

        return {
            "title": "Home",
            "path": "home",
            "icon": "mdi:home",
            "type": "sections",
            "cards": [],
            "sections": [
                {
                    "type": "grid",
                    "cards": section_cards
                }
            ]
        }

    def _generate_room_view(self, room_id: str, room_info: dict[str, Any]) -> dict[str, Any]:
        """Generate individual room view (hidden from tabs)."""
        site_name = room_info.get("site_name", room_id)
        normalized_id = normalize_room_id(site_name)
        room_name = site_name

        # Section cards list
        section_cards = []

        # Room header with back button
        section_cards.append({
            "type": "markdown",
            "content": f"# {room_name}\n[← Back to Overview](/dashboard-newbook/home)",
        })

        # Booking information card (uses site_name for entity IDs)
        booking_card = {
            "type": "entities",
            "title": "📅 Booking Information",
            "entities": [
                {"entity": f"sensor.{site_name}_booking_status"},
                {"entity": f"sensor.room_{site_name}_guest_name"},
                {"entity": f"sensor.room_{site_name}_arrival_time"},
                {"entity": f"sensor.room_{site_name}_departure_time"},
                {"entity": f"sensor.room_{site_name}_current_night"},
                {"entity": f"sensor.room_{site_name}_total_nights"},
                {"entity": f"sensor.room_{site_name}_pax"},
                {"entity": f"sensor.room_{site_name}_booking_reference"},
            ],
        }
        section_cards.append(booking_card)

        # Heating schedule card
        heating_card = {
            "type": "entities",
            "title": "🔥 Heating Schedule",
            "entities": [
                f"binary_sensor.room_{site_name}_should_heat",
                f"sensor.room_{site_name}_heating_start_time",
                f"sensor.room_{site_name}_cooling_start_time",
                f"sensor.room_{site_name}_room_state",
            ],
        }
        section_cards.append(heating_card)

        # Auto mode control
        control_card = {
            "type": "entities",
            "title": "⚙️ Heating Control",
            "entities": [
                {
                    "entity": f"switch.room_{site_name}_auto_mode",
                    "name": "Auto Mode",
                },
                {
                    "entity": f"switch.room_{site_name}_sync_setpoints",
                    "name": "Sync All Valves",
                },
                {
                    "entity": f"switch.room_{site_name}_exclude_bathroom_from_sync",
                    "name": "Exclude Bathroom",
                },
            ],
        }
        section_cards.append(control_card)

        # Settings card
        settings_card = {
            "type": "entities",
            "title": "🌡️ Temperature Settings",
            "entities": [
                {
                    "entity": f"number.room_{site_name}_occupied_temperature",
                    "name": "Occupied Temperature",
                },
                {
                    "entity": f"number.room_{site_name}_vacant_temperature",
                    "name": "Vacant Temperature",
                },
                {
                    "entity": f"number.room_{site_name}_heating_offset_minutes",
                    "name": "Pre-heat Offset (min)",
                },
                {
                    "entity": f"number.room_{site_name}_cooling_offset_minutes",
                    "name": "Cooling Offset (min)",
                },
            ],
        }
        section_cards.append(settings_card)

        # TRV devices card
        trv_entities = []
        for state in self.hass.states.async_all():
            if (
                state.entity_id.startswith("climate.room_")
                and state.entity_id.endswith("_trv")
                and f"room_{site_name}_" in state.entity_id
            ):
                trv_entities.append(state.entity_id)

        if trv_entities:
            trvs_card = {
                "type": "entities",
                "title": "🎚️ TRV Devices",
                "entities": [],
            }

            for trv_entity in sorted(trv_entities):
                trvs_card["entities"].append({
                    "type": "custom:mushroom-climate-card",
                    "entity": trv_entity,
                    "show_temperature_control": True,
                    "hvac_modes": ["heat", "off"],
                    "collapsible_controls": True,
                })

                # Battery sensor if exists
                battery_entity = trv_entity.replace("climate.", "sensor.") + "_battery"
                if self.hass.states.get(battery_entity):
                    trvs_card["entities"].append({
                        "entity": battery_entity,
                        "name": f"{trv_entity.split('_')[-2].title()} Battery",
                    })

            section_cards.append(trvs_card)

        # Manual override service card
        override_card = {
            "type": "entities",
            "title": "🔧 Manual Override",
            "entities": [
                {
                    "type": "button",
                    "name": "Force Temperature",
                    "icon": "mdi:thermometer-alert",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.force_room_temperature",
                        "service_data": {
                            "room_id": room_id,
                            "temperature": 22,
                        },
                    },
                },
                {
                    "type": "button",
                    "name": "Sync All Valves",
                    "icon": "mdi:sync",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.sync_room_valves",
                        "service_data": {
                            "room_id": room_id,
                            "temperature": 22,
                        },
                    },
                },
            ],
        }
        section_cards.append(override_card)

        return {
            "title": room_name,
            "path": f"room-{normalized_id}",
            "icon": "mdi:bed",
            "visible": False,  # Hidden from tabs, navigation only
            "type": "sections",
            "cards": [],
            "sections": [
                {
                    "type": "grid",
                    "cards": section_cards
                }
            ]
        }

    def _generate_battery_view(self) -> dict[str, Any]:
        """Generate battery monitoring view."""
        section_cards = []

        # Title
        section_cards.append({
            "type": "markdown",
            "content": "# 🔋 TRV Battery Monitoring\nMonitor battery levels across all Shelly TRV devices.",
        })

        # Battery level thresholds info
        section_cards.append({
            "type": "markdown",
            "content": """
## Battery Level Guidelines
- **80-100%**: Excellent ✓
- **50-80%**: Good ✓
- **20-50%**: Low ⚠ Plan replacement
- **Below 20%**: Critical ❌ Replace immediately
""",
        })

        # Collect all battery sensors
        battery_entities = []
        for state in self.hass.states.async_all():
            if "_trv_battery" in state.entity_id and state.entity_id.startswith("sensor.room_"):
                battery_entities.append(state.entity_id)

        if battery_entities:
            # Critical battery card
            critical_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "❌ Critical Batteries",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 20",
                            "options": {
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "show_empty": True,
            }
            section_cards.append(critical_battery_card)

            # Low battery warning card
            low_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "⚠️ Low Battery Warnings",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 50",
                            "options": {
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "show_empty": True,
            }
            section_cards.append(low_battery_card)

            # All batteries card
            all_batteries_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "📊 All TRV Batteries",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "options": {
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "sort": {
                    "method": "state",
                    "numeric": True,
                },
            }
            section_cards.append(all_batteries_card)

        else:
            section_cards.append({
                "type": "markdown",
                "content": "No TRV battery sensors found. Ensure your Shelly TRVs are configured correctly.",
            })

        return {
            "title": "Battery",
            "path": "battery",
            "icon": "mdi:battery",
            "type": "sections",
            "cards": [],
            "sections": [
                {
                    "type": "grid",
                    "cards": section_cards
                }
            ]
        }

    def _generate_health_view(self) -> dict[str, Any]:
        """Generate TRV health monitoring view."""
        section_cards = []

        # Title
        section_cards.append({
            "type": "markdown",
            "content": "# 🏥 TRV Health Monitoring\nMonitor responsiveness and health of all Shelly TRV devices.",
        })

        # Health status guide
        section_cards.append({
            "type": "markdown",
            "content": """
## Health Status Guide
- **Healthy**: Responding normally (< 3 attempts)
- **Degraded**: Slow but working (3-4 attempts)
- **Poor**: Unreliable (5-9 attempts)
- **Unresponsive**: Not responding (10+ attempts)
""",
        })

        # Health status summary card
        summary_card = {
            "type": "entities",
            "title": "📊 Health Summary",
            "entities": [
                "sensor.newbook_trv_health_healthy",
                "sensor.newbook_trv_health_degraded",
                "sensor.newbook_trv_health_poor",
                "sensor.newbook_trv_health_unresponsive",
            ],
        }
        section_cards.append(summary_card)

        # All TRVs health card
        all_trvs_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "🎚️ All TRV Devices",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "climate.room_*_trv",
                        "options": {
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "sort": {
                "method": "name",
            },
        }
        section_cards.append(all_trvs_card)

        # Degraded/Poor TRVs card
        warning_card = {
            "type": "markdown",
            "content": """
### ⚠️ TRVs Requiring Attention
Check the logs for TRVs with degraded or poor health status.
Common issues:
- Weak WiFi signal (< -70 dBm)
- Low battery (< 50%)
- Incorrect MQTT configuration
""",
        }
        section_cards.append(warning_card)

        # Quick actions
        actions_card = {
            "type": "entities",
            "title": "🔧 Quick Actions",
            "entities": [
                {
                    "type": "button",
                    "name": "Retry Unresponsive TRVs",
                    "icon": "mdi:reload-alert",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.retry_unresponsive_trvs",
                    },
                },
                {
                    "type": "button",
                    "name": "Refresh Bookings",
                    "icon": "mdi:refresh",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.refresh_bookings",
                    },
                },
            ],
        }
        section_cards.append(actions_card)

        # WiFi signal strength guide
        wifi_guide = {
            "type": "markdown",
            "content": """
## WiFi Signal Strength Guidelines
- **-50 to -60 dBm**: Excellent ✓
- **-60 to -70 dBm**: Good ✓
- **-70 to -80 dBm**: Fair ⚠
- **-80 to -90 dBm**: Poor ❌
- **Below -90 dBm**: Very Poor ❌

Check signal strength in Shelly web interface → Device Info
""",
        }
        section_cards.append(wifi_guide)

        return {
            "title": "Health",
            "path": "health",
            "icon": "mdi:heart-pulse",
            "type": "sections",
            "cards": [],
            "sections": [
                {
                    "type": "grid",
                    "cards": section_cards
                }
            ]
        }

    async def _async_generate_home_overview(self, rooms: dict[str, dict[str, Any]]) -> None:
        """Generate home overview dashboard with all rooms."""
        _LOGGER.debug("Generating home overview dashboard")

        # Sort rooms by room ID
        sorted_rooms = sorted(rooms.items(), key=lambda x: str(x[0]))

        cards = []

        # Title card
        cards.append({
            "type": "markdown",
            "content": "# 🏨 Hotel Heating Overview\nManage heating for all rooms based on Newbook bookings.",
        })

        # Room cards in grid
        for room_id, room_info in sorted_rooms:
            normalized_id = normalize_room_id(room_id)
            room_name = room_info.get("site_name", f"Room {room_id}")

            card = {
                "type": "custom:mushroom-template-card",
                "primary": room_name,
                "secondary": "{{ states('sensor.room_" + room_id + "_guest_name') }}",
                "icon": "mdi:radiator",
                "icon_color": "{% if is_state('binary_sensor.room_" + room_id + "_should_heat', 'on') %}red{% else %}blue{% endif %}",
                "badge_icon": "{% if is_state('switch.room_" + room_id + "_auto_mode', 'on') %}mdi:auto-fix{% else %}mdi:hand{% endif %}",
                "badge_color": "{% if is_state('switch.room_" + room_id + "_auto_mode', 'on') %}green{% else %}orange{% endif %}",
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": f"/dashboard-newbook/room-{normalized_id}",
                },
                "entity": f"binary_sensor.room_{room_id}_should_heat",
            }
            section_cards.append(card)

        # Services card
        services_card = {
            "type": "entities",
            "title": "🔧 Quick Actions",
            "entities": [
                {
                    "type": "button",
                    "name": "Refresh Bookings",
                    "icon": "mdi:refresh",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.refresh_bookings",
                    },
                },
                {
                    "type": "button",
                    "name": "Retry Unresponsive TRVs",
                    "icon": "mdi:reload-alert",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.retry_unresponsive_trvs",
                    },
                },
            ],
        }
        section_cards.append(services_card)

        # System status card
        system_card = {
            "type": "entities",
            "title": "📊 System Status",
            "entities": [
                "sensor.newbook_system_status",
                "sensor.newbook_last_update",
                "sensor.newbook_rooms_discovered",
                "sensor.newbook_active_bookings",
            ],
        }
        cards.append(system_card)

        dashboard = {
            "title": "Hotel Heating",
            "icon": "mdi:radiator",
            "path": "newbook-home",
            "views": [
                {
                    "title": "Overview",
                    "path": "overview",
                    "type": "sections",
                    "cards": cards,
                }
            ],
        }

        await self._async_write_dashboard("home_overview.yaml", dashboard)

    async def _async_generate_room_dashboards(self, rooms: dict[str, dict[str, Any]]) -> None:
        """Generate individual dashboard for each room."""
        _LOGGER.debug("Generating per-room dashboards")

        for room_id, room_info in rooms.items():
            normalized_id = normalize_room_id(room_id)
            room_name = room_info.get("site_name", f"Room {room_id}")

            cards = []

            # Room header
            cards.append({
                "type": "markdown",
                "content": f"# {room_name}\nDetailed heating control and booking information.",
            })

            # Booking information card
            booking_card = {
                "type": "entities",
                "title": "📅 Booking Information",
                "entities": [
                    f"sensor.room_{normalized_id}_booking_status",
                    f"sensor.room_{normalized_id}_guest_name",
                    f"sensor.room_{normalized_id}_arrival_time",
                    f"sensor.room_{normalized_id}_departure_time",
                    f"sensor.room_{normalized_id}_current_night",
                    f"sensor.room_{normalized_id}_total_nights",
                    f"sensor.room_{normalized_id}_pax",
                    f"sensor.room_{normalized_id}_booking_reference",
                ],
            }
            cards.append(booking_card)

            # Heating schedule card
            heating_card = {
                "type": "entities",
                "title": "🔥 Heating Schedule",
                "entities": [
                    f"binary_sensor.room_{room_id}_should_heat",
                    f"sensor.room_{room_id}_heating_start_time",
                    f"sensor.room_{room_id}_cooling_start_time",
                    f"sensor.room_{room_id}_room_state",
                ],
            }
            cards.append(heating_card)

            # Auto mode control
            control_card = {
                "type": "entities",
                "title": "⚙️ Heating Control",
                "entities": [
                    {
                        "entity": f"switch.room_{room_id}_auto_mode",
                        "name": "Auto Mode",
                    },
                    {
                        "entity": f"switch.room_{room_id}_sync_setpoints",
                        "name": "Sync All Valves",
                    },
                    {
                        "entity": f"switch.room_{room_id}_exclude_bathroom_from_sync",
                        "name": "Exclude Bathroom",
                    },
                ],
            }
            cards.append(control_card)

            # Settings card
            settings_card = {
                "type": "entities",
                "title": "🌡️ Temperature Settings",
                "entities": [
                    {
                        "entity": f"number.room_{room_id}_occupied_temperature",
                        "name": "Occupied Temperature",
                    },
                    {
                        "entity": f"number.room_{room_id}_vacant_temperature",
                        "name": "Vacant Temperature",
                    },
                    {
                        "entity": f"number.room_{room_id}_heating_offset_minutes",
                        "name": "Pre-heat Offset (min)",
                    },
                    {
                        "entity": f"number.room_{room_id}_cooling_offset_minutes",
                        "name": "Cooling Offset (min)",
                    },
                ],
            }
            cards.append(settings_card)

            # TRV devices card
            # Get TRVs for this room from state machine
            trv_entities = []
            for state in self.hass.states.async_all():
                if (
                    state.entity_id.startswith("climate.room_")
                    and state.entity_id.endswith("_trv")
                    and f"room_{normalized_id}_" in state.entity_id
                ):
                    trv_entities.append(state.entity_id)

            if trv_entities:
                trvs_card = {
                    "type": "entities",
                    "title": "🎚️ TRV Devices",
                    "entities": [],
                }

                for trv_entity in sorted(trv_entities):
                    trvs_card["entities"].append({
                        "type": "custom:mushroom-climate-card",
                        "entity": trv_entity,
                        "show_temperature_control": True,
                        "hvac_modes": ["heat", "off"],
                        "collapsible_controls": True,
                    })

                    # Battery sensor if exists
                    battery_entity = trv_entity.replace("climate.", "sensor.") + "_battery"
                    if self.hass.states.get(battery_entity):
                        trvs_card["entities"].append({
                            "entity": battery_entity,
                            "name": f"{trv_entity.split('_')[-2].title()} Battery",
                        })

                cards.append(trvs_card)

            # Manual override service card
            override_card = {
                "type": "entities",
                "title": "🔧 Manual Override",
                "entities": [
                    {
                        "type": "button",
                        "name": "Force Temperature",
                        "icon": "mdi:thermometer-alert",
                        "tap_action": {
                            "action": "call-service",
                            "service": "newbook.force_room_temperature",
                            "service_data": {
                                "room_id": room_id,
                                "temperature": 22,
                            },
                        },
                    },
                    {
                        "type": "button",
                        "name": "Sync All Valves",
                        "icon": "mdi:sync",
                        "tap_action": {
                            "action": "call-service",
                            "service": "newbook.sync_room_valves",
                            "service_data": {
                                "room_id": room_id,
                                "temperature": 22,
                            },
                        },
                    },
                ],
            }
            cards.append(override_card)

            dashboard = {
                "title": room_name,
                "icon": "mdi:bed",
                "path": f"room-{normalized_id}",
                "views": [
                    {
                        "title": room_name,
                        "path": "details",
                        "type": "sections",
                        "cards": cards,
                    }
                ],
            }

            await self._async_write_dashboard(f"room_{normalized_id}.yaml", dashboard)

    async def _async_generate_battery_dashboard(self, rooms: dict[str, dict[str, Any]]) -> None:
        """Generate battery monitoring dashboard."""
        _LOGGER.debug("Generating battery monitoring dashboard")

        cards = []

        # Title
        cards.append({
            "type": "markdown",
            "content": "# 🔋 TRV Battery Monitoring\nMonitor battery levels across all Shelly TRV devices.",
        })

        # Battery level thresholds info
        section_cards.append({
            "type": "markdown",
            "content": """
## Battery Level Guidelines
- **80-100%**: Excellent ✓
- **50-80%**: Good ✓
- **20-50%**: Low ⚠ Plan replacement
- **Below 20%**: Critical ❌ Replace immediately
""",
        })

        # Collect all battery sensors
        battery_entities = []
        for state in self.hass.states.async_all():
            if "_trv_battery" in state.entity_id and state.entity_id.startswith("sensor.room_"):
                battery_entities.append(state.entity_id)

        if battery_entities:
            # All batteries card
            all_batteries_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "📊 All TRV Batteries",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "options": {
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "sort": {
                    "method": "state",
                    "numeric": True,
                },
            }
            section_cards.append(all_batteries_card)

            # Low battery warning card
            low_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "⚠️ Low Battery Warnings",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 50",
                            "options": {
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "show_empty": True,
            }
            section_cards.append(low_battery_card)

            # Critical battery card
            critical_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "❌ Critical Batteries",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 20",
                            "options": {
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "show_empty": True,
            }
            section_cards.append(critical_battery_card)

        else:
            cards.append({
                "type": "markdown",
                "content": "No TRV battery sensors found. Ensure your Shelly TRVs are configured correctly.",
            })

        dashboard = {
            "title": "TRV Batteries",
            "icon": "mdi:battery",
            "path": "newbook-batteries",
            "views": [
                {
                    "title": "Battery Status",
                    "path": "batteries",
                    "type": "sections",
                    "cards": cards,
                }
            ],
        }

        await self._async_write_dashboard("battery_monitoring.yaml", dashboard)

    async def _async_generate_health_dashboard(self, rooms: dict[str, dict[str, Any]]) -> None:
        """Generate TRV health monitoring dashboard."""
        _LOGGER.debug("Generating TRV health monitoring dashboard")

        cards = []

        # Title
        cards.append({
            "type": "markdown",
            "content": "# 🏥 TRV Health Monitoring\nMonitor responsiveness and health of all Shelly TRV devices.",
        })

        # Health status guide
        section_cards.append({
            "type": "markdown",
            "content": """
## Health Status Guide
- **Healthy**: Responding normally (< 3 attempts)
- **Degraded**: Slow but working (3-4 attempts)
- **Poor**: Unreliable (5-9 attempts)
- **Unresponsive**: Not responding (10+ attempts)
""",
        })

        # Health status summary card
        summary_card = {
            "type": "entities",
            "title": "📊 Health Summary",
            "entities": [
                "sensor.newbook_trv_health_healthy",
                "sensor.newbook_trv_health_degraded",
                "sensor.newbook_trv_health_poor",
                "sensor.newbook_trv_health_unresponsive",
            ],
        }
        section_cards.append(summary_card)

        # All TRVs health card
        all_trvs_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "🎚️ All TRV Devices",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "climate.room_*_trv",
                        "options": {
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "sort": {
                "method": "name",
            },
        }
        section_cards.append(all_trvs_card)

        # Degraded/Poor TRVs card
        warning_card = {
            "type": "markdown",
            "content": """
### ⚠️ TRVs Requiring Attention
Check the logs for TRVs with degraded or poor health status.
Common issues:
- Weak WiFi signal (< -70 dBm)
- Low battery (< 50%)
- Incorrect MQTT configuration
""",
        }
        section_cards.append(warning_card)

        # Quick actions
        actions_card = {
            "type": "entities",
            "title": "🔧 Quick Actions",
            "entities": [
                {
                    "type": "button",
                    "name": "Retry Unresponsive TRVs",
                    "icon": "mdi:reload-alert",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.retry_unresponsive_trvs",
                    },
                },
                {
                    "type": "button",
                    "name": "Refresh Bookings",
                    "icon": "mdi:refresh",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.refresh_bookings",
                    },
                },
            ],
        }
        section_cards.append(actions_card)

        # WiFi signal strength guide
        wifi_guide = {
            "type": "markdown",
            "content": """
## WiFi Signal Strength Guidelines
- **-50 to -60 dBm**: Excellent ✓
- **-60 to -70 dBm**: Good ✓
- **-70 to -80 dBm**: Fair ⚠
- **-80 to -90 dBm**: Poor ❌
- **Below -90 dBm**: Very Poor ❌

Check signal strength in Shelly web interface → Device Info
""",
        }
        cards.append(wifi_guide)

        dashboard = {
            "title": "TRV Health",
            "icon": "mdi:heart-pulse",
            "path": "newbook-health",
            "views": [
                {
                    "title": "Health Status",
                    "path": "health",
                    "type": "sections",
                    "cards": cards,
                }
            ],
        }

        await self._async_write_dashboard("trv_health.yaml", dashboard)

    async def _async_write_dashboard(self, filename: str, dashboard: dict[str, Any]) -> None:
        """Write dashboard YAML file."""
        filepath = self.dashboards_path / filename

        def _write():
            with open(filepath, "w", encoding="utf-8") as file:
                yaml.dump(dashboard, file, default_flow_style=False, allow_unicode=True, sort_keys=False)

        await self.hass.async_add_executor_job(_write)
        _LOGGER.debug("Generated dashboard: %s", filename)

    async def async_delete_all_dashboards(self) -> None:
        """Delete all generated dashboards."""
        if not self.dashboards_path.exists():
            return

        def _delete():
            for file in self.dashboards_path.glob("*.yaml"):
                file.unlink()
            # Only remove directory if empty
            if not any(self.dashboards_path.iterdir()):
                self.dashboards_path.rmdir()

        await self.hass.async_add_executor_job(_delete)
        _LOGGER.info("Deleted all Newbook dashboards")
