"""Subscription provisioning service: key names and admin-issued keys."""

import logging
import random
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Subscription, User
from app.database.session import async_session_factory
from app.services.remnawave_service import RemnawaveService

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Key issuance logic shared by payments and admin flows."""

    def __init__(self) -> None:
        self._remnawave = RemnawaveService()

    async def generate_unique_key_name(
        self, session: AsyncSession, max_attempts: int = 10
    ) -> str:
        """Generate 'dagger<random digits>' name not present in the DB."""
        for _ in range(max_attempts):
            name = f"dagger{random.randint(100_000_000, 999_999_999)}"
            result = await session.execute(
                select(Subscription.id).where(Subscription.key_name == name).limit(1)
            )
            if result.first() is None:
                return name
        raise RuntimeError("Failed to generate a unique key name")

    async def issue_key_by_admin(
        self,
        bot: Bot,
        user_telegram_id: int,
        duration_days: int,
    ) -> Subscription:
        """Provision a key via Remnawave and notify the user.

        Raises ValueError if the user is unknown, RuntimeError on panel errors.
        """
        async with async_session_factory() as session:
            async with session.begin():
                user_result = await session.execute(
                    select(User).where(User.telegram_id == user_telegram_id)
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    raise ValueError(f"Пользователь с Telegram ID {user_telegram_id} не найден")

                # Reuse an existing panel user if we have one
                uuid_result = await session.execute(
                    select(Subscription.remnawave_user_uuid)
                    .where(
                        Subscription.user_id == user.id,
                        Subscription.remnawave_user_uuid.is_not(None),
                    )
                    .order_by(Subscription.created_at.desc())
                    .limit(1)
                )
                user_uuid = uuid_result.scalar_one_or_none()

                if user_uuid is None:
                    remnawave_user = await self._remnawave.create_user(
                        username=f"dagger_{user.telegram_id}",
                        email=f"{user.telegram_id}@dagger.local",
                    )
                    if remnawave_user is None:
                        raise RuntimeError("Не удалось создать пользователя в панели")
                    user_uuid = (
                        remnawave_user.get("uuid")
                        or remnawave_user.get("response", {}).get("uuid")
                    )
                    if not user_uuid:
                        raise RuntimeError("Панель не вернула UUID пользователя")

                expire_at = (
                    datetime.now(timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    + timedelta(days=duration_days)
                )

                subscription_result = await self._remnawave.create_subscription(
                    user_uuid=user_uuid,
                    traffic_limit_bytes=0,
                    expire_at=expire_at.isoformat(),
                    hwid_device_limit=5,
                )
                if subscription_result is None:
                    raise RuntimeError("Не удалось создать подписку в панели")

                sub_url = (
                    subscription_result.get("subscriptionUrl")
                    or subscription_result.get("response", {}).get("subscriptionUrl")
                    or ""
                )

                key_name = await self.generate_unique_key_name(session)

                subscription = Subscription(
                    user_id=user.id,
                    remnawave_user_uuid=user_uuid,
                    key_name=key_name,
                    subscription_url=sub_url,
                    tariff_id=None,
                    expires_at=expire_at,
                    traffic_limit_bytes=0,
                    device_limit=5,
                    status="active",
                )
                session.add(subscription)
                await session.flush()
                session.refresh(subscription)

                logger.info(
                    "Admin issued key %s to telegram_id=%s for %d days",
                    key_name,
                    user_telegram_id,
                    duration_days,
                )

        await bot.send_message(
            user_telegram_id,
            (
                "Администратор вам выдал ключ\n"
                f"<code>{sub_url}</code>\n"
                f"Длительность: {duration_days} дн."
            ),
        )

        return subscription
