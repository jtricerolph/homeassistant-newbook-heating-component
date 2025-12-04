"""DataUpdateCoordinator for Newbook integration."""
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NewbookApiClient, NewbookApiError
from .const import (
    ACTIVE_BOOKING_STATUSES,
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
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        self._sites: dict[str, dict[str, Any]] = {}
        self._bookings: dict[str, list[dict[str, Any]]] = {}
        self._tasks: dict[str, list[dict[str, Any]]] = {}
        self._last_sites_update: datetime | None = None
        self._rooms_discovered: bool = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Newbook API."""
        try:
            # Fetch sites/rooms (only if not fetched or stale)
            if self._should_refresh_sites():
                sites = await self.client.get_sites(force_refresh=True)
                self._process_sites(sites)
                self._last_sites_update = datetime.now()
                _LOGGER.debug("Updated sites: %d rooms discovered", len(self._sites))

            # Fetch bookings for today and tomorrow
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            # Get staying bookings (active only)
            bookings = await self.client.get_bookings(
                period_from=f"{today} 00:00:00",
                period_to=f"{tomorrow} 23:59:59",
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

                self._bookings[site_id].append({
                    "booking_id": booking.get("booking_id"),
                    "booking_reference_id": booking.get("booking_reference_id"),
                    "site_id": site_id,
                    "site_name": booking.get("site_name"),
                    "booking_arrival": booking.get("booking_arrival"),
                    "booking_departure": booking.get("booking_departure"),
                    "booking_eta": booking.get("booking_eta"),
                    "booking_status": booking_status,
                    "pax": booking.get("pax", 0),
                    "guest_name": booking.get("guest_name", "Unknown"),
                    "guest_email": booking.get("guest_email"),
                    "guest_phone": booking.get("guest_phone"),
                    "rate_plan_name": booking.get("rate_plan_name"),
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

    def get_all_rooms(self) -> dict[str, dict[str, Any]]:
        """Get all discovered rooms."""
        return self._sites.copy()

    def get_room_booking(self, room_id: str) -> dict[str, Any] | None:
        """Get current booking for a room (returns first active booking)."""
        bookings = self._bookings.get(room_id, [])
        if bookings:
            # Sort by arrival date and return the first one
            sorted_bookings = sorted(
                bookings,
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
