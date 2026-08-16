"""Remnawave panel API client.

Endpoints follow the real Remnawave contract (libs/contract in remnawave/backend):
- Users:   POST/PATCH/DELETE /api/users, POST /api/users/{id}/actions/*
- Squads:  GET /api/internal-squads

The panel's nginx requires a secret cookie (settings.REMNAWAVE_PANEL_COOKIE).
Without it every request is closed with no response (444), which httpx reports as
"Server disconnected without sending a response".
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class RemnawaveService:
    """HTTP client for the Remnawave VPN management panel API."""

    def __init__(self) -> None:
        self._base_url = settings.REMNAWAVE_API_URL.rstrip("/")
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {settings.REMNAWAVE_API_TOKEN}",
            "Content-Type": "application/json",
        }
        if settings.REMNAWAVE_PANEL_COOKIE:
            self._headers["Cookie"] = settings.REMNAWAVE_PANEL_COOKIE
        self._timeout = 30.0
        self._max_retries = 3

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response | None:
        """Execute an HTTP request with retries. Returns None on failure."""
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=self._headers,
                        json=json,
                        params=params,
                    )
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Remnawave API %s %s returned %d (attempt %d/%d): %s",
                    method,
                    path,
                    exc.response.status_code,
                    attempt,
                    self._max_retries,
                    exc.response.text[:500],
                )
                last_exc = exc
                if exc.response.status_code < 500:
                    break
            except httpx.RequestError as exc:
                logger.warning(
                    "Remnawave API %s %s request error (attempt %d/%d): %s",
                    method,
                    path,
                    attempt,
                    self._max_retries,
                    exc,
                )
                last_exc = exc

        logger.error(
            "Remnawave API %s %s failed after %d attempts: %s",
            method,
            path,
            self._max_retries,
            last_exc,
        )
        return None

    @staticmethod
    def _unwrap(data: Any) -> Any:
        """Unwrap Remnawave responses of the form {"response": ...}."""
        if isinstance(data, dict) and "response" in data:
            return data["response"]
        return data

    @staticmethod
    def extract_user_fields(user: dict) -> dict[str, str]:
        """Normalize user response into fields the bot needs.

        Remnawave mutations (extend/disable/delete) require the numeric `id`.
        Older panel versions may not expose `id`, so we fall back to uuid/shortUuid.
        """
        identifier = ""
        if user.get("id") is not None:
            identifier = str(user["id"])
        else:
            identifier = user.get("uuid") or user.get("shortUuid") or ""
        return {
            "identifier": identifier,
            "subscription_url": user.get("subscriptionUrl") or "",
        }

    # ------------------------------------------------------------------
    # Internal squads
    # ------------------------------------------------------------------

    async def get_internal_squads(self) -> list[dict]:
        """List all internal squads. Each item has at least `uuid` and `name`."""
        response = await self._request("GET", "/internal-squads")
        if response is None:
            return []
        try:
            data = self._unwrap(response.json())
            squads = (
                data.get("internalSquads") if isinstance(data, dict) else data
            )
            return list(squads or [])
        except ValueError:
            logger.error("Failed to parse internal-squads response")
            return []

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def create_user(
        self,
        username: str,
        expire_at: str,
        traffic_limit_bytes: int = 0,
        hwid_device_limit: int = 5,
        active_internal_squads: list[str] | None = None,
        email: str | None = None,
        telegram_id: int | None = None,
    ) -> dict | None:
        """Create a panel user.

        Args:
            username: unique panel username (3-36 chars, [a-zA-Z0-9_-]).
            expire_at: ISO-8601 datetime string (required by Remnawave).
            traffic_limit_bytes: 0 means unlimited.
            hwid_device_limit: max concurrent devices.
            active_internal_squads: squad UUIDs granting node access. If None,
                ALL available internal squads are assigned automatically.
            email: optional panel user email.
            telegram_id: optional Telegram user id for panel notifications.

        Returns the unwrapped user dict (with subscriptionUrl) or None on failure.
        """
        if active_internal_squads is None:
            squads = await self.get_internal_squads()
            active_internal_squads = [
                s["uuid"] for s in squads if isinstance(s, dict) and s.get("uuid")
            ]
            if not active_internal_squads:
                logger.warning(
                    "No internal squads found; created user will have no node access"
                )

        body: dict[str, Any] = {
            "username": username,
            "expireAt": expire_at,
            "trafficLimitBytes": traffic_limit_bytes,
            "hwidDeviceLimit": hwid_device_limit,
        }
        if active_internal_squads:
            body["activeInternalSquads"] = active_internal_squads
        if email:
            body["email"] = email
        if telegram_id is not None:
            body["telegramId"] = telegram_id

        response = await self._request("POST", "/users", json=body)
        if response is None:
            return None
        try:
            data = self._unwrap(response.json())
            if not isinstance(data, dict):
                logger.error("Unexpected create_user response type: %s", type(data))
                return None
            logger.info(
                "Created panel user username=%s id=%s",
                data.get("username"),
                data.get("id"),
            )
            return data
        except ValueError:
            logger.error("Failed to parse create_user response")
            return None

    async def get_user(self, user_id: str) -> dict | None:
        """Get panel user by numeric id. Returns unwrapped dict or None."""
        response = await self._request("GET", f"/users/{user_id}")
        if response is None:
            return None
        try:
            return self._unwrap(response.json())
        except ValueError:
            logger.error("Failed to parse get_user response for user_id=%s", user_id)
            return None

    async def extend_user(self, user_id: str, days: int) -> dict | None:
        """Extend a panel user's expiration date by N days.

        Requires the numeric panel user id (stored in Subscription.remnawave_user_uuid).
        """
        response = await self._request(
            "POST",
            f"/users/{user_id}/actions/extend",
            json={"days": days},
        )
        if response is None:
            return None
        try:
            data = self._unwrap(response.json())
            logger.info("Extended panel user %s by %d days", user_id, days)
            return data if isinstance(data, dict) else None
        except ValueError:
            logger.error(
                "Failed to parse extend_user response for user_id=%s", user_id
            )
            return None

    async def disable_user(self, user_id: str) -> bool:
        """Disable a panel user. Requires numeric panel user id."""
        response = await self._request(
            "POST", f"/users/{user_id}/actions/disable"
        )
        if response is None:
            return False
        logger.info("Disabled panel user %s", user_id)
        return True

    async def enable_user(self, user_id: str) -> bool:
        """Enable a previously disabled panel user."""
        response = await self._request(
            "POST", f"/users/{user_id}/actions/enable"
        )
        if response is None:
            return False
        logger.info("Enabled panel user %s", user_id)
        return True

    async def delete_user(self, user_id: str) -> bool:
        """Delete a panel user. Requires numeric panel user id."""
        response = await self._request("DELETE", f"/users/{user_id}")
        if response is None:
            return False
        logger.info("Deleted panel user %s", user_id)
        return True

    # ------------------------------------------------------------------
    # Legacy helpers kept for sync service compatibility
    # ------------------------------------------------------------------

    async def get_subscription_info(self, subscription_url: str) -> dict | None:
        """Fetch subscription info by URL. Used by SubscriptionSyncService.

        Note: this fetches from sub.daggervpn.ru when given a full URL,
        NOT from the panel API. Kept for backwards compatibility only.
        """
        if subscription_url.startswith("http"):
            url = subscription_url
        else:
            url = f"{self._base_url}{subscription_url}"

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, headers=self._headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "get_subscription_info %s request error (attempt %d/%d): %s",
                    url,
                    attempt,
                    self._max_retries,
                    exc,
                )
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code < 500:
                    break
        logger.error(
            "get_subscription_info %s failed: %s", url, last_exc
        )
        return None
