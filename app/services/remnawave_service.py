"""Remnawave VPN panel API service."""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class RemnawaveService:
    """HTTP client for the Remnawave VPN management panel API."""

    def __init__(self) -> None:
        self._base_url = settings.REMNAWAVE_API_URL.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.REMNAWAVE_API_TOKEN}",
            "Content-Type": "application/json",
        }
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

    async def create_user(
        self, username: str, email: str | None = None
    ) -> dict | None:
        """Create a new user on the VPN panel. Returns dict with uuid or None."""
        body: dict[str, Any] = {"username": username}
        if email:
            body["email"] = email

        response = await self._request("POST", "/user", json=body)
        if response is None:
            return None

        try:
            data = response.json()
            logger.info("Created VPN user: username=%s", username)
            return data
        except ValueError:
            logger.error("Failed to parse create_user response")
            return None

    async def get_user(self, uuid: str) -> dict | None:
        """Get user info by UUID. Returns dict or None."""
        response = await self._request("GET", f"/user/{uuid}")
        if response is None:
            return None

        try:
            return response.json()
        except ValueError:
            logger.error("Failed to parse get_user response for uuid=%s", uuid)
            return None

    async def create_subscription(
        self,
        user_uuid: str,
        traffic_limit_bytes: int,
        expire_at: str,
        hwid_device_limit: int = 5,
    ) -> dict | None:
        """Create a subscription for a VPN user. Returns dict or None."""
        body: dict[str, Any] = {
            "userId": user_uuid,
            "trafficLimitBytes": traffic_limit_bytes,
            "expireAt": expire_at,
            "hwidDeviceLimit": hwid_device_limit,
        }

        response = await self._request("POST", "/subscription", json=body)
        if response is None:
            return None

        try:
            data = response.json()
            logger.info("Created subscription for user_uuid=%s", user_uuid)
            return data
        except ValueError:
            logger.error("Failed to parse create_subscription response")
            return None

    async def extend_subscription(
        self, subscription_uuid: str, additional_days: int
    ) -> dict | None:
        """Extend an existing subscription by N days. Returns dict or None."""
        body = {"additionalDays": additional_days}

        response = await self._request(
            "PATCH", f"/subscription/{subscription_uuid}/extend", json=body
        )
        if response is None:
            return None

        try:
            data = response.json()
            logger.info(
                "Extended subscription %s by %d days",
                subscription_uuid,
                additional_days,
            )
            return data
        except ValueError:
            logger.error(
                "Failed to parse extend_subscription response for %s",
                subscription_uuid,
            )
            return None

    async def get_subscription_info(self, subscription_url: str) -> dict | None:
        """Get subscription info. The subscription_url may be a full URL or a relative path."""
        if subscription_url.startswith("http"):
            path = subscription_url.replace(self._base_url, "")
        else:
            path = subscription_url

        response = await self._request("GET", path)
        if response is None:
            return None

        try:
            return response.json()
        except ValueError:
            logger.error(
                "Failed to parse get_subscription_info response for %s",
                subscription_url,
            )
            return None

    async def disable_user(self, uuid: str) -> bool:
        """Disable a VPN user. Returns True on success."""
        response = await self._request("POST", f"/user/{uuid}/disable")
        if response is None:
            return False

        logger.info("Disabled VPN user uuid=%s", uuid)
        return True

    async def delete_user(self, uuid: str) -> bool:
        """Delete a VPN user. Returns True on success."""
        response = await self._request("DELETE", f"/user/{uuid}")
        if response is None:
            return False

        logger.info("Deleted VPN user uuid=%s", uuid)
        return True

    async def get_user_subscriptions(self, user_uuid: str) -> list[dict]:
        """Get all subscriptions for a user. Returns empty list on failure."""
        response = await self._request(
            "GET", "/subscription", params={"userId": user_uuid}
        )
        if response is None:
            return []

        try:
            data = response.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "data" in data:
                items = data["data"]
                return items if isinstance(items, list) else [items]
            return [data]
        except ValueError:
            logger.error(
                "Failed to parse get_user_subscriptions response for %s",
                user_uuid,
            )
            return []
