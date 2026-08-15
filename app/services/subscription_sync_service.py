"""Subscription synchronization service."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import Subscription
from app.database.session import async_session_factory
from app.services.remnawave_service import RemnawaveService

logger = logging.getLogger(__name__)


class SubscriptionSyncService:
    """Synchronizes local subscription data with the VPN panel API."""

    def __init__(self) -> None:
        self._remnawave = RemnawaveService()

    async def sync_all_subscriptions(self) -> dict:
        """Sync all active subscriptions from the VPN panel API.

        Returns {"synced": int, "failed": int} summary.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.status == "active",
                    Subscription.subscription_url.isnot(None),
                )
            )
            subscriptions = list(result.scalars().all())

        if not subscriptions:
            logger.info("No active subscriptions to sync")
            return {"synced": 0, "failed": 0}

        logger.info("Syncing %d active subscriptions", len(subscriptions))

        synced = 0
        failed = 0

        for sub in subscriptions:
            try:
                info = await self._remnawave.get_subscription_info(sub.subscription_url)
                if info is None:
                    logger.warning(
                        "Failed to get info for subscription_id=%s", sub.id
                    )
                    failed += 1
                    continue

                # Extract fields from API response (handle nested response format)
                data = info.get("response", info)

                await self._update_subscription(sub.id, data)
                synced += 1

            except Exception:
                logger.exception(
                    "Error syncing subscription_id=%s", sub.id
                )
                failed += 1

        logger.info(
            "Subscription sync complete: synced=%d, failed=%d", synced, failed
        )
        return {"synced": synced, "failed": failed}

    async def _update_subscription(
        self, subscription_id: int, api_data: dict
    ) -> None:
        """Update a single subscription record from API data."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.id == subscription_id
                    )
                )
                sub = result.scalar_one_or_none()
                if sub is None:
                    logger.warning(
                        "Subscription id=%s disappeared during sync",
                        subscription_id,
                    )
                    return

                updated = False

                # Update expires_at
                expire_str = api_data.get("expireAt") or api_data.get("expires_at")
                if expire_str:
                    try:
                        if isinstance(expire_str, str):
                            parsed = datetime.fromisoformat(
                                expire_str.replace("Z", "+00:00")
                            )
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            sub.expires_at = parsed
                            updated = True
                    except ValueError:
                        logger.warning(
                            "Invalid expireAt for subscription_id=%s: %s",
                            subscription_id,
                            expire_str,
                        )

                # Update traffic_used_bytes
                traffic_used = api_data.get("usedTrafficBytes") or api_data.get(
                    "traffic_used_bytes"
                )
                if traffic_used is not None:
                    try:
                        sub.traffic_used_bytes = int(traffic_used)
                        updated = True
                    except (ValueError, TypeError):
                        pass

                # Update devices_connected
                devices = api_data.get("hwidDeviceCount") or api_data.get(
                    "devices_connected"
                )
                if devices is not None:
                    try:
                        sub.devices_connected = int(devices)
                        updated = True
                    except (ValueError, TypeError):
                        pass

                # Update status
                status = api_data.get("status")
                if status and isinstance(status, str):
                    status_lower = status.lower()
                    if status_lower in ("active", "expired", "disabled", "limited"):
                        sub.status = status_lower
                        updated = True

                if updated:
                    logger.debug(
                        "Updated subscription_id=%s from API", subscription_id
                    )
