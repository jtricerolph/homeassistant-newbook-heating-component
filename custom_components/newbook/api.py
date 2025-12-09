"""Newbook API client."""
import asyncio
import base64
from datetime import datetime
import json
import logging
import time
from typing import Any

import aiohttp
import async_timeout

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class NewbookApiError(Exception):
    """Exception to indicate a general API error."""


class NewbookAuthError(Exception):
    """Exception to indicate an authentication error."""


class NewbookApiClient:
    """Newbook API client."""

    def __init__(
        self,
        username: str,
        password: str,
        api_key: str,
        region: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.api_key = api_key
        self.region = region
        self.session = session
        self.api_base_url = API_BASE_URL

    def _get_auth_header(self) -> str:
        """Generate HTTP Basic Auth header."""
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _api_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Make a request to the Newbook API."""
        url = f"{self.api_base_url}{endpoint}"

        if params is None:
            params = {}

        # Add API key and region to all requests
        params["api_key"] = self.api_key
        params["region"] = self.region
        # Add timestamp for cache busting
        params["_t"] = int(time.time() * 1000)

        headers = {
            "Content-Type": "application/json",
            "Authorization": self._get_auth_header(),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }

        try:
            async with async_timeout.timeout(timeout):
                async with self.session.post(
                    url,
                    headers=headers,
                    json=params,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Check for API-level errors
                    if isinstance(data, dict) and data.get("error"):
                        error_msg = data.get("error_message", "Unknown error")
                        _LOGGER.error("Newbook API error: %s", error_msg)
                        raise NewbookApiError(error_msg)

                    # Unwrap Newbook API response format: {"success": "true", "data": [...]}
                    if isinstance(data, dict) and "data" in data:
                        if data.get("success") not in ["true", True]:
                            error_msg = data.get("message", "API request failed")
                            _LOGGER.error("Newbook API error: %s", error_msg)
                            raise NewbookApiError(error_msg)
                        return data["data"]

                    return data

        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.error("Authentication failed")
                raise NewbookAuthError("Invalid credentials") from err
            _LOGGER.error("HTTP error: %s", err)
            raise NewbookApiError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError as err:
            _LOGGER.error("Request timeout")
            raise NewbookApiError("Request timeout") from err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            raise NewbookApiError(f"Unexpected error: {err}") from err

    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            # Try to get sites list as a connection test
            await self.get_sites()
            return True
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    async def get_sites(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Get list of all sites/rooms.

        Returns list of sites with structure:
        [
            {
                'site_id': '101',
                'site_name': 'Room 101',
                'site_category_name': 'Deluxe Queen',
                'site_status': 'Clean',  # Clean/Dirty/Inspected/Unknown
                'site_category_id': 5
            },
            ...
        ]
        """
        _LOGGER.debug("Fetching sites list (force_refresh=%s)", force_refresh)

        params = {"force_refresh": force_refresh}

        try:
            response = await self._api_request("sites_list", params)

            if isinstance(response, list):
                _LOGGER.debug("Retrieved %d sites", len(response))
                return response

            _LOGGER.warning("Unexpected response format for sites_list")
            return []

        except Exception as err:
            _LOGGER.error("Failed to fetch sites: %s", err)
            raise

    async def get_bookings(
        self,
        period_from: str,
        period_to: str,
        list_type: str = "staying",
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Get bookings within a date range.

        Args:
            period_from: Start date/time (YYYY-MM-DD HH:MM:SS)
            period_to: End date/time (YYYY-MM-DD HH:MM:SS)
            list_type: 'staying', 'placed', 'cancelled', 'all'
            force_refresh: Force fresh data from API

        Returns list of bookings with structure:
        [
            {
                'booking_id': 12345,
                'booking_reference_id': 'BK-2024-001',
                'site_id': '101',
                'site_name': 'Room 101',
                'booking_arrival': '2025-12-04 15:00:00',
                'booking_departure': '2025-12-06 10:00:00',
                'booking_eta': '2025-12-04 14:30:00',
                'booking_status': 'arrived',  # confirmed/unconfirmed/arrived/departed/cancelled/no_show
                'pax': 2,
                'guest_name': 'John Smith',
                'guest_email': 'john@example.com',
                'guests': [...],
                'notes': [...],
                'custom_fields': [...]
            },
            ...
        ]
        """
        _LOGGER.debug(
            "Fetching bookings from %s to %s (type=%s, force_refresh=%s)",
            period_from,
            period_to,
            list_type,
            force_refresh,
        )

        params = {
            "period_from": period_from,
            "period_to": period_to,
            "list_type": list_type,
            "force_refresh": force_refresh,
        }

        try:
            response = await self._api_request("bookings_list", params)

            if isinstance(response, list):
                _LOGGER.debug("Retrieved %d bookings", len(response))
                return response

            _LOGGER.warning("Unexpected response format for bookings_list")
            return []

        except Exception as err:
            _LOGGER.error("Failed to fetch bookings: %s", err)
            raise

    async def get_booking(
        self,
        booking_id: int,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        """Get detailed information for a single booking.

        Args:
            booking_id: The booking ID
            force_refresh: Force fresh data from API

        Returns booking details or None if not found
        """
        _LOGGER.debug("Fetching booking %d (force_refresh=%s)", booking_id, force_refresh)

        params = {
            "booking_id": booking_id,
            "force_refresh": force_refresh,
        }

        try:
            response = await self._api_request("bookings_get", params)
            return response if isinstance(response, dict) else None

        except Exception as err:
            _LOGGER.error("Failed to fetch booking %d: %s", booking_id, err)
            raise

    async def get_tasks(
        self,
        period_from: str,
        period_to: str,
        task_type: list[int] | None = None,
        show_uncomplete: bool = True,
        created_when: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Get housekeeping/maintenance tasks.

        Args:
            period_from: Start date (YYYY-MM-DD)
            period_to: End date (YYYY-MM-DD)
            task_type: Array of task type IDs (e.g., [-1, -2] for housekeeping and maintenance)
            show_uncomplete: Show only uncompleted tasks
            created_when: Filter by creation date (YYYY-MM-DD)
            force_refresh: Force fresh data from API

        Returns list of tasks with structure:
        [
            {
                'task_id': 789,
                'task_description': 'Full Clean',
                'task_type_id': -1,  # -1 = housekeeping, -2 = maintenance
                'task_location_type': 'bookings',  # or 'sites'
                'booking_site_id': '101',  # For booking tasks
                'task_location_id': '101',  # For site tasks
                'task_location_occupy': 0,  # 1 = marks room occupied
                'task_completed_on': None,  # or timestamp
                'task_when_date': '2025-12-04',
            },
            ...
        ]
        """
        _LOGGER.debug(
            "Fetching tasks from %s to %s (types=%s, force_refresh=%s)",
            period_from,
            period_to,
            task_type,
            force_refresh,
        )

        params = {
            "period_from": period_from,
            "period_to": period_to,
            "show_uncomplete": show_uncomplete,
            "force_refresh": force_refresh,
        }

        if task_type is not None:
            params["task_type"] = task_type

        if created_when is not None:
            params["created_when"] = created_when

        try:
            response = await self._api_request("tasks_list", params)

            if isinstance(response, list):
                _LOGGER.debug("Retrieved %d tasks", len(response))
                return response

            _LOGGER.warning("Unexpected response format for tasks_list")
            return []

        except Exception as err:
            _LOGGER.error("Failed to fetch tasks: %s", err)
            raise

    async def update_task(
        self,
        task_id: int,
        completed_on: str,
    ) -> dict[str, Any] | None:
        """Mark a task as completed.

        Args:
            task_id: Task ID
            completed_on: Completion timestamp (YYYY-MM-DD HH:MM:SS)

        Returns response with updated site_status
        """
        _LOGGER.debug("Updating task %d as completed", task_id)

        params = {
            "task_id": task_id,
            "completed_on": completed_on,
        }

        try:
            response = await self._api_request("tasks_update", params)
            return response if isinstance(response, dict) else None

        except Exception as err:
            _LOGGER.error("Failed to update task %d: %s", task_id, err)
            raise

    async def update_site_status(
        self,
        site_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        """Update site/room status.

        Args:
            site_id: Site/room ID
            status: New status ('Clean', 'Dirty', 'Inspected')

        Returns response
        """
        _LOGGER.debug("Updating site %s status to %s", site_id, status)

        params = {
            "site_id": site_id,
            "status": status,
        }

        try:
            response = await self._api_request("sites_update", params)
            return response if isinstance(response, dict) else None

        except Exception as err:
            _LOGGER.error("Failed to update site %s: %s", site_id, err)
            raise
