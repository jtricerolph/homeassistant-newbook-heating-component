"""Dashboard generator for Newbook integration."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant

from .const import CONF_CATEGORY_SORT_ORDER, DOMAIN
from .room_manager import normalize_room_id

_LOGGER = logging.getLogger(__name__)

DASHBOARDS_DIR = "dashboards/newbook"


class DashboardGenerator:
    """Generate Lovelace dashboards for Newbook integration."""

    def __init__(self, hass: HomeAssistant, entry_id: str | None = None) -> None:
        """Initialize dashboard generator."""
        self.hass = hass
        self.entry_id = entry_id
        self.dashboards_path = Path(hass.config.path(DASHBOARDS_DIR))

    def _get_current_config(self) -> dict[str, Any]:
        """Get the current configuration from the config entry."""
        if not self.entry_id:
            return {}

        try:
            entry = self.hass.data[DOMAIN][self.entry_id]["config"]
            # Merge data and options to get complete config
            return {**entry.data, **entry.options}
        except (KeyError, AttributeError):
            return {}

    def _get_category_sort_key(self, category_name: str) -> tuple[int, str]:
        """Get sort key for a category based on custom sort order.

        Returns a tuple where:
        - First element: position in custom order (or 999 if not in custom order)
        - Second element: category name (for alphabetical sorting of unlisted categories)
        """
        config = self._get_current_config()
        sort_order_str = config.get(CONF_CATEGORY_SORT_ORDER, "")
        if not sort_order_str:
            # No custom order, sort alphabetically
            return (0, category_name)

        # Parse custom sort order
        custom_order = [cat.strip() for cat in sort_order_str.split(",") if cat.strip()]

        try:
            # Category is in custom order list
            position = custom_order.index(category_name)
            return (position, category_name)
        except ValueError:
            # Category not in custom order, put it after all custom ordered ones
            return (999, category_name)

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
        section_cards = []

        # Title card
        section_cards.append({
            "type": "markdown",
            "content": "# 🏨 Hotel Heating Overview\nManage heating for all rooms based on Newbook bookings.",
        })

        # Group rooms by category
        from collections import defaultdict
        categories = defaultdict(list)

        for room_id, room_info in rooms.items():
            category_name = room_info.get("category_name", "Uncategorized")
            categories[category_name].append((room_id, room_info))

        # Sort categories by custom sort order (if configured) or alphabetically
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: self._get_category_sort_key(x[0])
        )

        # Generate room cards grouped by category
        for category_name, category_rooms in sorted_categories:
            # Add category header
            section_cards.append({
                "type": "markdown",
                "content": f"## {category_name}",
            })

            # Sort rooms within category by site_name
            sorted_rooms = sorted(
                category_rooms,
                key=lambda x: str(x[1].get("site_name", x[0]))
            )

            # Add room cards for this category
            for room_id, room_info in sorted_rooms:
                site_name = room_info.get("site_name", room_id)
                normalized_id = normalize_room_id(site_name)
                room_name = site_name

                # Build secondary text template based on room state
                secondary_template = (
                    "{% set state = states('sensor." + site_name + "_room_state') %}"
                    "{% if state == 'vacant' %}Vacant"
                    "{% elif state == 'booked' %}"
                    "{% set heating_start = states('sensor." + site_name + "_heating_start') %}"
                    "{% if heating_start not in ['unknown', 'unavailable'] %}"
                    "Booked - Preheating {{ relative_time(strptime(heating_start, '%Y-%m-%d %H:%M:%S')) }}"
                    "{% else %}Booked{% endif %}"
                    "{% elif state == 'heating_up' %}Preheating"
                    "{% elif state == 'occupied' %}{{ states('sensor." + site_name + "_guest_name') }}"
                    "{% elif state == 'cooling_down' %}Cooling Down"
                    "{% else %}{{ states('sensor." + site_name + "_guest_name') }}{% endif %}"
                )

                card = {
                    "type": "custom:mushroom-template-card",
                    "primary": room_name,
                    "secondary": secondary_template,
                    "icon": "mdi:radiator",
                    "icon_color": "{% if is_state('binary_sensor." + site_name + "_should_heat', 'on') %}red{% else %}blue{% endif %}",
                    "badge_icon": "{% if is_state('switch." + site_name + "_auto_mode', 'on') %}mdi:auto-fix{% else %}mdi:hand{% endif %}",
                    "badge_color": "{% if is_state('switch." + site_name + "_auto_mode', 'on') %}green{% else %}orange{% endif %}",
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": f"/dashboard-newbook/room-{normalized_id}",
                    },
                    "entity": f"binary_sensor.{site_name}_should_heat",
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
                {"entity": f"sensor.{site_name}_guest_name"},
                {"entity": f"sensor.{site_name}_arrival"},
                {"entity": f"sensor.{site_name}_departure"},
                {"entity": f"sensor.{site_name}_current_night"},
                {"entity": f"sensor.{site_name}_total_nights"},
                {"entity": f"sensor.{site_name}_number_of_guests"},
                {"entity": f"sensor.{site_name}_booking_reference"},
            ],
        }
        section_cards.append(booking_card)

        # Heating schedule card
        heating_card = {
            "type": "entities",
            "title": "🔥 Heating Schedule",
            "entities": [
                f"binary_sensor.{site_name}_should_heat",
                f"sensor.{site_name}_heating_start_time",
                f"sensor.{site_name}_cooling_start_time",
                f"sensor.{site_name}_room_state",
            ],
        }
        section_cards.append(heating_card)

        # Auto mode control
        control_card = {
            "type": "entities",
            "title": "⚙️ Heating Control",
            "show_header_toggle": False,
            "entities": [
                {
                    "entity": f"switch.{site_name}_auto_mode",
                    "name": "Auto Mode",
                },
                {
                    "entity": f"switch.{site_name}_sync_setpoints",
                    "name": "Sync All Valves",
                },
                {
                    "entity": f"switch.{site_name}_exclude_bathroom_from_sync",
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
                    "entity": f"number.{site_name}_occupied_temperature",
                    "name": "Occupied Temperature",
                },
                {
                    "entity": f"number.{site_name}_vacant_temperature",
                    "name": "Vacant Temperature",
                },
                {
                    "entity": f"number.{site_name}_heating_offset",
                    "name": "Pre-heat Offset (min)",
                },
                {
                    "entity": f"number.{site_name}_cooling_offset",
                    "name": "Cooling Offset (min)",
                },
            ],
        }
        section_cards.append(settings_card)

        # TRV devices card - uses auto-entities with mushroom climate cards
        # Mushroom cards support Jinja2 templates for dynamic names
        # New TRVs will automatically appear when connected to MQTT
        trvs_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "grid",
                "columns": 1,
            },
            "card_param": "cards",
            "filter": {
                "include": [
                    {
                        "entity_id": f"climate.room_{site_name}_*",
                        "options": {
                            "type": "custom:mushroom-climate-card",
                            "name": "{{ state_attr(entity, 'friendly_name').split(' ')[2] | default(state_attr(entity, 'friendly_name')) | title }}",
                            "show_temperature_control": True,
                            "collapsible_controls": False,
                            "tap_action": {
                                "action": "more-info",
                            },
                        },
                    }
                ],
            },
            "sort": {
                "method": "entity_id",
            },
            "show_empty": False,
        }
        section_cards.append(trvs_card)

        # TRV battery sensors - auto-discovers batteries for this room's TRVs
        battery_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "🔋 TRV Batteries",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": f"sensor.room_{site_name}_*_trv_battery",
                    }
                ],
            },
            "sort": {
                "method": "entity_id",
            },
            "show_empty": False,
        }
        section_cards.append(battery_card)

        # Manual override service card
        # Sync all valves to the temperature shown above (doesn't affect auto mode)
        override_card = {
            "type": "entities",
            "title": "🔧 Manual Sync",
            "entities": [
                {
                    "entity": f"number.{site_name}_occupied_temperature",
                    "name": "Target Temperature",
                },
                {
                    "type": "button",
                    "name": "Sync All Valves to Target",
                    "icon": "mdi:sync",
                    "tap_action": {
                        "action": "call-service",
                        "service": "newbook.sync_room_valves",
                        "data": {
                            "room_id": room_id,
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
            "subview": True,  # Makes this a subview with proper back navigation
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
## Battery Level Guidelines (Rechargeable)
- **80-100%**: Excellent ✓
- **50-80%**: Good ✓
- **20-50%**: Low ⚠ Plan recharge
- **Below 20%**: Critical ❌ Recharge immediately
""",
        })

        # Collect all battery sensors
        battery_entities = []
        for state in self.hass.states.async_all():
            if "_trv_battery" in state.entity_id and state.entity_id.startswith("sensor.room_"):
                battery_entities.append(state.entity_id)

        if battery_entities:
            # Critical battery card (< 20%)
            critical_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "❌ Critical Batteries (< 20%)",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 20",
                            "options": {
                                "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "show_empty": True,
                "sort": {
                    "method": "state",
                    "numeric": True,
                },
            }
            section_cards.append(critical_battery_card)

            # Low battery warning card (20% to 50%)
            low_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "⚠️ Low Battery (20-50%)",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 50",
                            "options": {
                                "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                    "exclude": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 20",
                        }
                    ],
                },
                "show_empty": True,
                "sort": {
                    "method": "state",
                    "numeric": True,
                },
            }
            section_cards.append(low_battery_card)

            # Good batteries card (>= 50%)
            good_batteries_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "✅ Good Batteries (≥ 50%)",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "options": {
                                "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                    "exclude": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 50",
                        }
                    ],
                },
                "sort": {
                    "method": "state",
                    "numeric": True,
                    "reverse": True,
                },
            }
            section_cards.append(good_batteries_card)

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
- **Calibration Error**: Device reporting but not calibrated (valve pos = -1%)
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
                "sensor.newbook_trv_health_calibration_error",
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
                        "domain": "climate",
                        "entity_id": "climate.room_*",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                        },
                    }
                ],
            },
            "sort": {
                "method": "entity_id",
            },
        }
        section_cards.append(all_trvs_card)

        # Calibration Error card - TRVs needing calibration
        calibration_error_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "🔧 Calibration Required",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "binary_sensor.room_*_trv_calibration",
                        "state": "on",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
        }
        section_cards.append(calibration_error_card)

        # Unresponsive TRVs card (uses responsiveness sensor)
        unresponsive_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "❌ Unresponsive TRVs",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_responsiveness",
                        "state": "unresponsive",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_responsiveness$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
        }
        section_cards.append(unresponsive_card)

        # Poor Health TRVs card (uses responsiveness sensor)
        poor_health_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "⚠️ Poor Health TRVs",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_responsiveness",
                        "state": "poor",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_responsiveness$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
        }
        section_cards.append(poor_health_card)

        # Degraded TRVs card (uses responsiveness sensor)
        degraded_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "🟡 Degraded TRVs",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_responsiveness",
                        "state": "degraded",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_responsiveness$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
        }
        section_cards.append(degraded_card)

        # Poor WiFi Health card (uses wifi_health sensor with state "poor")
        poor_wifi_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "❌ Poor WiFi (< -80 dBm)",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_health",
                        "state": "poor",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
        }
        section_cards.append(poor_wifi_card)

        # Fair WiFi Health card (uses wifi_health sensor with state "fair")
        fair_wifi_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "⚠️ Fair WiFi (-70 to -80 dBm)",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_health",
                        "state": "fair",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
        }
        section_cards.append(fair_wifi_card)

        # All WiFi signals card (shows actual RSSI values)
        wifi_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "📶 All WiFi Signal Strength",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_signal",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
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
        section_cards.append(wifi_card)

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

        cards = []

        # Title card
        cards.append({
            "type": "markdown",
            "content": "# 🏨 Hotel Heating Overview\nManage heating for all rooms based on Newbook bookings.",
        })

        # Group rooms by category
        from collections import defaultdict
        categories = defaultdict(list)

        for room_id, room_info in rooms.items():
            category_name = room_info.get("category_name", "Uncategorized")
            categories[category_name].append((room_id, room_info))

        # Sort categories by custom sort order (if configured) or alphabetically
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: self._get_category_sort_key(x[0])
        )

        # Generate room cards grouped by category
        for category_name, category_rooms in sorted_categories:
            # Add category header
            cards.append({
                "type": "markdown",
                "content": f"## {category_name}",
            })

            # Sort rooms within category by site_name
            sorted_rooms = sorted(
                category_rooms,
                key=lambda x: str(x[1].get("site_name", x[0]))
            )

            # Add room cards for this category
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
                cards.append(card)

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
        cards.append(services_card)

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
## Battery Level Guidelines (Rechargeable)
- **80-100%**: Excellent ✓
- **50-80%**: Good ✓
- **20-50%**: Low ⚠ Plan recharge
- **Below 20%**: Critical ❌ Recharge immediately
""",
        })

        # Collect all battery sensors
        battery_entities = []
        for state in self.hass.states.async_all():
            if "_trv_battery" in state.entity_id and state.entity_id.startswith("sensor.room_"):
                battery_entities.append(state.entity_id)

        if battery_entities:
            # Critical battery card (< 20%)
            critical_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "❌ Critical Batteries (< 20%)",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 20",
                            "options": {
                                "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                },
                "show_empty": True,
                "sort": {
                    "method": "state",
                    "numeric": True,
                },
            }
            section_cards.append(critical_battery_card)

            # Low battery warning card (20% to 50%)
            low_battery_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "⚠️ Low Battery (20-50%)",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 50",
                            "options": {
                                "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                    "exclude": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 20",
                        }
                    ],
                },
                "show_empty": True,
                "sort": {
                    "method": "state",
                    "numeric": True,
                },
            }
            section_cards.append(low_battery_card)

            # Good batteries card (>= 50%)
            good_batteries_card = {
                "type": "custom:auto-entities",
                "card": {
                    "type": "entities",
                    "title": "✅ Good Batteries (≥ 50%)",
                },
                "filter": {
                    "include": [
                        {
                            "entity_id": "*_trv_battery",
                            "options": {
                                "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                                "secondary_info": "last-changed",
                            },
                        }
                    ],
                    "exclude": [
                        {
                            "entity_id": "*_trv_battery",
                            "state": "< 50",
                        }
                    ],
                },
                "sort": {
                    "method": "state",
                    "numeric": True,
                    "reverse": True,
                },
            }
            section_cards.append(good_batteries_card)

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
                        "domain": "climate",
                        "entity_id": "climate.room_*",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                        },
                    }
                ],
            },
            "sort": {
                "method": "entity_id",
            },
        }
        section_cards.append(all_trvs_card)

        # Poor WiFi signal card (< -80 dBm)
        poor_wifi_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "❌ Poor WiFi Signal (< -80 dBm)",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_signal",
                        "state": "< -80",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
            },
            "show_empty": True,
            "sort": {
                "method": "state",
                "numeric": True,
            },
        }
        section_cards.append(poor_wifi_card)

        # Fair WiFi signal card (-70 to -80 dBm)
        fair_wifi_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "⚠️ Fair WiFi Signal (-70 to -80 dBm)",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_signal",
                        "state": "< -70",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
                            "secondary_info": "last-changed",
                        },
                    }
                ],
                "exclude": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_signal",
                        "state": "< -80",
                    }
                ],
            },
            "show_empty": True,
            "sort": {
                "method": "state",
                "numeric": True,
            },
        }
        section_cards.append(fair_wifi_card)

        # All WiFi signals card
        wifi_card = {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": "📶 All WiFi Signal Strength",
            },
            "filter": {
                "include": [
                    {
                        "entity_id": "sensor.room_*_trv_wifi_signal",
                        "options": {
                            "name": "{{ config.entity.split('.')[1] | replace('room_', '') | regex_replace('_trv.*$', '') | replace('_', ' ') | title }}",
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
        section_cards.append(wifi_card)

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
