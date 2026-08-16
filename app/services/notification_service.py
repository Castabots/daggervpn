"""Notification service for subscription expiry reminders."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.models import NotificationLog, Subscription, User
from app.database.session import async_session_factory

logger = logging.getLogger(__name__)

# Notification thresholds in days before expiry
NOTIFICATION_THRESHOLDS = [7, 3, 1]


class NotificationService:
    """Service for sending subscription expiry notifications."""

    async def check_and_send_notifications(self, bot) -> None:
        """Check all active subscriptions and send expiry reminders.

        Sends notifications at 7 days, 3 days, 1 day before expiry,
        and when expired. Avoids duplicates via NotificationLog.
        """
        now = datetime.now(timezone.utc)

        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription, User)
                .join(User, Subscription.user_id == User.id)
                .where(
                    Subscription.status == "active",
                    User.is_blocked.is_(False),
                )
            )
            rows = result.all()

        if not rows:
            return

        logger.info("Checking %d active subscriptions for notifications", len(rows))

        for subscription, user in rows:
            try:
                expires_at = subscription.expires_at
                if expires_at is None:
                    continue

                # Ensure timezone-aware comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                days_until_expiry = (expires_at - now).days

                notification_type: str | None = None

                if days_until_expiry <= 0:
                    notification_type = "expired"
                elif days_until_expiry <= 1:
                    notification_type = "1_day"
                elif days_until_expiry <= 3:
                    notification_type = "3_days"
                elif days_until_expiry <= 7:
                    notification_type = "7_days"

                if notification_type is None:
                    continue

                # Check if already sent
                already_sent = await self._is_notification_sent(
                    user.telegram_id, subscription.id, notification_type
                )
                if already_sent:
                    continue

                # Build message
                text = self._build_message(
                    notification_type, days_until_expiry, subscription
                )

                # Send notification
                await self.send_notification(user.telegram_id, text, bot)

                # Log the notification
                await self._log_notification(
                    user.telegram_id, subscription.id, notification_type
                )

            except Exception:
                logger.exception(
                    "Error checking notification for subscription_id=%s",
                    subscription.id,
                )

    async def send_notification(
        self, user_telegram_id: int, text: str, bot
    ) -> bool:
        """Send a notification to a user. Returns True on success."""
        try:
            await bot.send_message(chat_id=user_telegram_id, text=text)
            logger.debug(
                "Sent notification to telegram_id=%s", user_telegram_id
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to send notification to telegram_id=%s: %s",
                user_telegram_id,
                exc,
            )
            return False

    async def _is_notification_sent(
        self,
        user_id: int,
        subscription_id: int,
        notification_type: str,
    ) -> bool:
        """Check if a notification of this type was already sent."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationLog.id)
                .where(
                    NotificationLog.user_id == user_id,
                    NotificationLog.subscription_id == subscription_id,
                    NotificationLog.notification_type == notification_type,
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def _log_notification(
        self,
        user_id: int,
        subscription_id: int,
        notification_type: str,
    ) -> None:
        """Record that a notification was sent."""
        async with async_session_factory() as session:
            async with session.begin():
                log_entry = NotificationLog(
                    user_id=user_id,
                    subscription_id=subscription_id,
                    notification_type=notification_type,
                )
                session.add(log_entry)

    @staticmethod
    def _build_message(
        notification_type: str,
        days_until_expiry: int,
        subscription: Subscription,
    ) -> str:
        """Build notification message text."""
        key_name = subscription.key_name or "подписка"

        if notification_type == "expired":
            return (
                f"Ваша подписка Dagger ({key_name}) истекла.\n\n"
                f"Продлите подписку, чтобы продолжить пользоваться сервисом."
            )
        elif notification_type == "1_day":
            return (
                f"Ваша подписка Dagger ({key_name}) истекает через 1 день.\n\n"
                f"Не забудьте продлить подписку, чтобы не потерять доступ."
            )
        elif notification_type == "3_days":
            return (
                f"Ваша подписка Dagger ({key_name}) истекает через {days_until_expiry} дня.\n\n"
                f"Рекомендуем продлить подписку заранее."
            )
        elif notification_type == "7_days":
            return (
                f"Ваша подписка Dagger ({key_name}) истекает через {days_until_expiry} дней.\n\n"
                f"Вы можете продлить её в любое время через бота."
            )
        else:
            return ""
