"""User management service."""

import logging
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Referral, User
from app.database.session import async_session_factory

logger = logging.getLogger(__name__)


class UserService:
    """Service for user CRUD and referral operations."""

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> User:
        """Find user by telegram_id or create a new one."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()

                if user is None:
                    user = User(
                        telegram_id=telegram_id,
                        username=username,
                        first_name=first_name,
                    )
                    session.add(user)
                    logger.info("Created new user: telegram_id=%s", telegram_id)
                else:
                    updated = False
                    if username is not None and user.username != username:
                        user.username = username
                        updated = True
                    if first_name is not None and user.first_name != first_name:
                        user.first_name = first_name
                        updated = True
                    if updated:
                        logger.debug("Updated user info: telegram_id=%s", telegram_id)

                return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Get user by telegram_id."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def set_referrer(
        self,
        user_id: int,
        referrer_telegram_id: int,
        campaign_code: str | None = None,
    ) -> bool:
        """Set referrer for a user. Returns False if self-referral or already has referrer."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    logger.warning("set_referrer: user_id=%s not found", user_id)
                    return False

                if user.telegram_id == referrer_telegram_id:
                    logger.info("Self-referral attempt by telegram_id=%s", user.telegram_id)
                    return False

                if user.referred_by is not None:
                    logger.info(
                        "User %s already has referrer %s",
                        user.telegram_id,
                        user.referred_by,
                    )
                    return False

                user.referred_by = referrer_telegram_id
                if campaign_code:
                    user.referral_campaign_code = campaign_code

                referral = Referral(
                    referrer_id=referrer_telegram_id,
                    referred_id=user.telegram_id,
                )
                session.add(referral)

                logger.info(
                    "Set referrer: user_id=%s, referrer=%s, campaign=%s",
                    user_id,
                    referrer_telegram_id,
                    campaign_code,
                )
                return True

    async def update_discount(self, user_id: int, discount_percent: int) -> User:
        """Update user's discount percentage (capped at 50%)."""
        capped = min(discount_percent, 50)
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    raise ValueError(f"User with id={user_id} not found")
                user.discount_percent = capped
                logger.info(
                    "Updated discount for user_id=%s to %d%%", user_id, capped
                )
                return user

    async def block_user(self, user_id: int) -> User:
        """Block a user."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    raise ValueError(f"User with id={user_id} not found")
                user.is_blocked = True
                logger.info("Blocked user_id=%s", user_id)
                return user

    async def unblock_user(self, user_id: int) -> User:
        """Unblock a user."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    raise ValueError(f"User with id={user_id} not found")
                user.is_blocked = False
                logger.info("Unblocked user_id=%s", user_id)
                return user

    async def get_all_active_telegram_ids(self) -> list[int]:
        """Telegram IDs of all non-blocked users (for broadcasts)."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(User.telegram_id).where(User.is_blocked.is_(False))
            )
            return [row[0] for row in result.all()]

    async def search_users(
        self, query: str, offset: int, limit: int
    ) -> tuple[list[User], int]:
        """Search users by telegram_id or username. Returns (users, total_count)."""
        async with async_session_factory() as session:
            numeric_query = None
            try:
                numeric_query = int(query)
            except ValueError:
                pass

            if numeric_query is not None:
                condition = or_(
                    User.telegram_id == numeric_query,
                    User.username.ilike(f"%{query}%"),
                )
            else:
                condition = User.username.ilike(f"%{query}%")

            count_result = await session.execute(
                select(func.count()).select_from(User).where(condition)
            )
            total = count_result.scalar() or 0

            rows_result = await session.execute(
                select(User)
                .where(condition)
                .order_by(User.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            users = list(rows_result.scalars().all())

            return users, total

    async def get_all_users(
        self, offset: int, limit: int
    ) -> tuple[list[User], int]:
        """Get all users with pagination. Returns (users, total_count)."""
        async with async_session_factory() as session:
            count_result = await session.execute(
                select(func.count()).select_from(User)
            )
            total = count_result.scalar() or 0

            rows_result = await session.execute(
                select(User)
                .order_by(User.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            users = list(rows_result.scalars().all())

            return users, total
