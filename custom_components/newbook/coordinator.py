"""DataUpdateCoordinator for Newbook integration."""
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NewbookApiClient, NewbookApiError
from .booking_processor import BookingProcessor
from .const import (
    ACTIVE_BOOKING_STATUSES,
    BOOKING_STATUS_ARRIVED,
    BOOKING_STATUS_CONFIRMED,
    BOOKING_STATUS_UNCONFIRMED,
    CONF_EXCLUDED_CATEGORIES,
    CONF_EXCLUDED_ROOMS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class NewbookDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Newbook data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NewbookApiClient,
        update_interval: timedelta,
        config: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        self.config = config
        self._sites: dict[str, dict[str, Any]] = {}
        self._bookings: dict[str, list[dict[str, Any]]] = {}
        self._tasks: dict[str, list[dict[str, Any]]] = {}
        self._last_sites_update: datetime | None = None
        self._rooms_discovered: bool = False
        self._booking_processor: BookingProcessor | None = None

    @property
    def booking_processor(self) -> BookingProcessor:
        """Get booking processor instance."""
        if self._booking_processor is None:
            # Get room settings from hass.data
            room_settings = self.hass.data[DOMAIN].get("room_settings", {})
            self._booking_processor = BookingProcessor(self.config, room_settings)
        return self._booking_processor

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Newbook API."""
        try:
            # Fetch sites/rooms (only if not fetched or stale)
            if self._should_refresh_sites():
                sites = await self.client.get_sites(force_refresh=True)
                self._process_sites(sites)
                self._last_sites_update = datetime.now()
                _LOGGER.debug("Updated sites: %d rooms discovered", len(self._sites))

            # Fetch bookings from yesterday to +7 days
            # Include yesterday to capture guests departing today
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            future = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

            # Get staying bookings (active only)
            bookings = await self.client.get_bookings(
                period_from=f"{yesterday} 00:00:00",
                period_to=f"{future} 23:59:59",
                list_type="staying",
                force_refresh=True,
            )
            self._process_bookings(bookings)
            _LOGGER.debug("Updated bookings: %d active bookings", len(bookings))

            # Fetch tasks for today (optional - for future enhancement)
            # tasks = await self.client.get_tasks(
            #     period_from=today,
            #     period_to=today,
            #     task_type=[-1, -2],  # Housekeeping and maintenance
            #     show_uncomplete=True,
            #     force_refresh=True,
            # )
            # self._process_tasks(tasks)

            return {
                "sites": self._sites,
                "bookings": self._bookings,
                "tasks": self._tasks,
                "last_update": datetime.now().isoformat(),
            }

        except NewbookApiError as err:
            raise UpdateFailed(f"Error fetching Newbook data: {err}") from err

    def _should_refresh_sites(self) -> bool:
        """Check if sites should be refreshed."""
        # Refresh if never fetched or if older than 24 hours
        if self._last_sites_update is None:
            return True

        age = datetime.now() - self._last_sites_update
        return age > timedelta(hours=24)

    def _process_sites(self, sites: list[dict[str, Any]]) -> None:
        """Process and store sites data."""
        self._sites.clear()

        for site in sites:
            site_id = site.get("site_id")
            if site_id:
                self._sites[site_id] = {
                    "site_id": site_id,
                    "site_name": site.get("site_name", f"Room {site_id}"),
                    "site_category_name": site.get("site_category_name", "Unknown"),
                    "site_status": site.get("site_status", "Unknown"),
                    "site_category_id": site.get("site_category_id"),
                }

        # Mark rooms as discovered
        if not self._rooms_discovered and self._sites:
            self._rooms_discovered = True
            _LOGGER.info("Room discovery complete: %d rooms found", len(self._sites))

    def _process_bookings(self, bookings: list[dict[str, Any]]) -> None:
        """Process and organize bookings by room."""
        self._bookings.clear()

        for booking in bookings:
            site_id = booking.get("site_id")
            booking_status = booking.get("booking_status", "").lower()

            # Only process active bookings
            if site_id and booking_status in ACTIVE_BOOKING_STATUSES:
                if site_id not in self._bookings:
                    self._bookings[site_id] = []

                # Extract guest information from guests array
                guest_name = "Unknown"
                guest_email = None
                guest_phone = None

                guests = booking.get("guests", [])
                if guests:
                    # Find primary guest
                    primary_guest = None
                    for guest in guests:
                        if guest.get("primary_client") == "1":
                            primary_guest = guest
                            break
                    if not primary_guest and guests:
                        primary_guest = guests[0]

                    if primary_guest:
                        firstname = primary_guest.get("firstname", "")
                        lastname = primary_guest.get("lastname", "")
                        guest_name = f"{firstname} {lastname}".strip() or "Unknown"

                        # Extract contact details
                        contact_details = primary_guest.get("contact_details", [])
                        for contact in contact_details:
                            if contact.get("type") == "email" and not guest_email:
                                guest_email = contact.get("content")
                            elif contact.get("type") in ["mobile", "phone"] and not guest_phone:
                                guest_phone = contact.get("content")

                # Calculate pax from booking_adults, booking_children, booking_infants
                pax = int(booking.get("booking_adults", 0) or 0) + \
                      int(booking.get("booking_children", 0) or 0) + \
                      int(booking.get("booking_infants", 0) or 0)

                self._bookings[site_id].append({
                    "booking_id": booking.get("booking_id"),
                    "booking_reference_id": booking.get("booking_reference_id"),
                    "site_id": site_id,
                    "site_name": booking.get("site_name"),
                    "booking_arrival": booking.get("booking_arrival"),
                    "booking_departure": booking.get("booking_departure"),
                    "booking_eta": booking.get("booking_eta"),
                    "booking_status": booking_status,
                    "pax": pax,
                    "guest_name": guest_name,
                    "guest_email": guest_email,
                    "guest_phone": guest_phone,
                    "rate_plan_name": booking.get("tariff_name"),
                    "notes": booking.get("notes", []),
                    "custom_fields": booking.get("custom_fields", []),
                })

    def _process_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Process and organize tasks by room."""
        self._tasks.clear()

        for task in tasks:
            # Determine room ID from task location
            site_id = None
            if task.get("task_location_type") == "sites":
                site_id = task.get("task_location_id")
            elif task.get("task_location_type") == "bookings":
                site_id = task.get("booking_site_id")

            if site_id:
                if site_id not in self._tasks:
                    self._tasks[site_id] = []

                self._tasks[site_id].append({
                    "task_id": task.get("task_id"),
                    "task_description": task.get("task_description"),
                    "task_type_id": task.get("task_type_id"),
                    "task_location_occupy": task.get("task_location_occupy", 0),
                    "task_completed_on": task.get("task_completed_on"),
                    "task_when_date": task.get("task_when_date"),
                })

    def get_room_data(self, room_id: str) -> dict[str, Any]:
        """Get all data for a specific room."""
        site_data = self._sites.get(room_id, {})
        bookings = self._bookings.get(room_id, [])
        tasks = self._tasks.get(room_id, [])

        return {
            "site": site_data,
            "bookings": bookings,
            "tasks": tasks,
        }

    def get_all_rooms_unfiltered(self) -> dict[str, dict[str, Any]]:
        """Get all discovered rooms without any filtering.

        Used by config flow to show all available rooms for exclusion configuration.
        """
        return self._sites.copy()

    def get_all_rooms(self) -> dict[str, dict[str, Any]]:
        """Get all discovered rooms, excluding configured exclusions."""
        excluded_rooms = self.config.get(CONF_EXCLUDED_ROOMS, [])
        excluded_categories = self.config.get(CONF_EXCLUDED_CATEGORIES, [])

        # If no exclusions configured, return all rooms
        if not excluded_rooms and not excluded_categories:
            return self._sites.copy()

        # Filter out excluded rooms and categories
        filtered_rooms = {}
        for room_id, room_info in self._sites.items():
            site_name = room_info.get("site_name", room_id)
            category_name = room_info.get("category_name", "")

            # Skip if room is explicitly excluded
            if site_name in excluded_rooms:
                _LOGGER.debug("Excluding room %s (site_name: %s)", room_id, site_name)
                continue

            # Skip if room's category is excluded
            if category_name and category_name in excluded_categories:
                _LOGGER.debug(
                    "Excluding room %s (category: %s)", room_id, category_name
                )
                continue

            filtered_rooms[room_id] = room_info

        return filtered_rooms

    def get_room_booking(self, room_id: str) -> dict[str, Any] | None:
        """Get current/next booking for a room using priority logic.

        Priority:
        1. Return "arrived" booking (current guest in room)
        2. If no "arrived", return next "confirmed" or "unconfirmed" booking by arrival date
        """
        bookings = self._bookings.get(room_id, [])
        if not bookings:
            return None

        # Priority 1: Find "arrived" booking (current guest)
        for booking in bookings:
            if booking.get("booking_status") == BOOKING_STATUS_ARRIVED:
                return booking

        # Priority 2: Find next "confirmed" or "unconfirmed" booking
        # Sort by arrival date to get the next upcoming booking
        upcoming_bookings = [
            b for b in bookings
            if b.get("booking_status") in [BOOKING_STATUS_CONFIRMED, BOOKING_STATUS_UNCONFIRMED]
        ]

        if upcoming_bookings:
            sorted_bookings = sorted(
                upcoming_bookings,
                key=lambda x: x.get("booking_arrival", ""),
            )
            return sorted_bookings[0] if sorted_bookings else None

        return None

    def has_active_booking(self, room_id: str) -> bool:
        """Check if room has an active booking."""
        return room_id in self._bookings and len(self._bookings[room_id]) > 0

    @property
    def rooms_discovered(self) -> bool:
        """Return True if rooms have been discovered."""
        return self._rooms_discovered

    async def async_refresh_bookings(self) -> None:
        """Manually refresh booking data."""
        _LOGGER.info("Manual booking refresh requested")
        await self.async_request_refresh()
