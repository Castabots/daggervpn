"""Promo code management service."""

import logging
import random
import string
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PromoCode, PromoCodeUsage, User
from app.database.session import async_session_factory

logger = logging.getLogger(__name__)


class PromoService:
    """Service for promo code CRUD and validation."""

    @staticmethod
    def generate_code() -> str:
        """Generate a unique promo code in DAGGER-XXXXX format."""
        chars = string.ascii_uppercase + string.digits
        suffix = "".join(random.choices(chars, k=5))
        return f"DAGGER-{suffix}"

    async def create_promo(
        self,
        discount_type: str,
        discount_value: int,
        max_uses: int | None = None,
        expires_at: datetime | None = None,
        min_amount_kopeks: int = 0,
        one_per_user: bool = True,
        tariff_id: int | None = None,
    ) -> PromoCode:
        """Create a new promo code."""
        async with async_session_factory() as session:
            async with session.begin():
                # Ensure unique code
                while True:
                    code = self.generate_code()
                    existing = await session.execute(
                        select(PromoCode).where(PromoCode.code == code)
                    )
                    if existing.scalar_one_or_none() is None:
                        break

                promo = PromoCode(
                    code=code,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    max_uses=max_uses,
                    expires_at=expires_at,
                    min_amount_kopeks=min_amount_kopeks,
                    one_per_user=one_per_user,
                    is_active=True,
                )
                session.add(promo)

                logger.info(
                    "Created promo code: %s (%s %s)",
                    code,
                    discount_type,
                    discount_value,
                )
                return promo

    async def validate_promo(
        self, code: str, user_id: int, amount_kopeks: int
    ) -> tuple[bool, str, PromoCode | None]:
        """Validate a promo code for a specific user and amount.

        Returns (is_valid, message, promo_code_or_none).
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(PromoCode).where(PromoCode.code == code)
            )
            promo = result.scalar_one_or_none()

            if promo is None:
                return False, "Promo code not found", None

            if not promo.is_active:
                return False, "Promo code is no longer active", None

            now = datetime.now(timezone.utc)
            if promo.expires_at and promo.expires_at < now:
                return False, "Promo code has expired", None

            if promo.max_uses is not None and promo.uses_count >= promo.max_uses:
                return False, "Promo code usage limit reached", None

            if amount_kopeks < promo.min_amount_kopeks:
                min_rub = promo.min_amount_kopeks // 100
                return (
                    False,
                    f"Minimum order amount is {min_rub} RUB",
                    None,
                )

            if promo.one_per_user:
                usage_result = await session.execute(
                    select(func.count())
                    .select_from(PromoCodeUsage)
                    .where(
                        PromoCodeUsage.promo_code_id == promo.id,
                        PromoCodeUsage.user_id == user_id,
                    )
                )
                if (usage_result.scalar() or 0) > 0:
                    return False, "You have already used this promo code", None

            return True, "OK", promo

    async def get_all_active(self) -> list[PromoCode]:
        """Get all active promo codes."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(PromoCode)
                .where(PromoCode.is_active.is_(True))
                .order_by(PromoCode.created_at.desc())
            )
            return list(result.scalars().all())

    async def disable_promo(self, promo_id: int) -> bool:
        """Disable a promo code. Returns True if found and disabled."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(PromoCode).where(PromoCode.id == promo_id)
                )
                promo = result.scalar_one_or_none()
                if promo is None:
                    logger.warning("disable_promo: id=%s not found", promo_id)
                    return False

                promo.is_active = False
                logger.info("Disabled promo code: %s (id=%s)", promo.code, promo_id)
                return True

    async def get_usage_stats(self, promo_id: int) -> dict:
        """Get usage statistics for a promo code.

        Returns {"uses_count": int, "users": [{"user_id": int, "payment_id": int | None}, ...]}.
        """
        async with async_session_factory() as session:
            pc_result = await session.execute(
                select(PromoCode).where(PromoCode.id == promo_id)
            )
            promo = pc_result.scalar_one_or_none()
            if promo is None:
                return {"uses_count": 0, "users": []}

            usage_result = await session.execute(
                select(PromoCodeUsage)
                .where(PromoCodeUsage.promo_code_id == promo_id)
                .order_by(PromoCodeUsage.id.desc())
            )
            usages = usage_result.scalars().all()

            users_list = [
                {"user_id": u.user_id, "payment_id": u.payment_id}
                for u in usages
            ]

            return {
                "uses_count": promo.uses_count,
                "users": users_list,
            }
