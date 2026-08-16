"""Referral program service."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database.models import (
    Payment,
    Referral,
    ReferralCampaign,
    ReferralClick,
    User,
)
from app.database.session import async_session_factory

logger = logging.getLogger(__name__)


class ReferralService:
    """Service for the referral and blogger campaign system."""

    async def process_referral_link(
        self, start_param: str, user_telegram_id: int
    ) -> dict | None:
        """Process a referral deep link start parameter.

        Supports formats:
          - "ref_USERID"    — personal referral link
          - "bloger_CODE"   — blogger campaign link

        Records the click. Returns referral info dict or None.
        """
        try:
            if start_param.startswith("ref_"):
                referrer_id_str = start_param[4:]
                try:
                    referrer_telegram_id = int(referrer_id_str)
                except ValueError:
                    logger.warning(
                        "Invalid referral id in start_param: %s", start_param
                    )
                    return None

                async with async_session_factory() as session:
                    async with session.begin():
                        click = ReferralClick(
                            referrer_telegram_id=referrer_telegram_id,
                            user_telegram_id=user_telegram_id,
                        )
                        session.add(click)

                        # Check if user already has a referrer
                        user_result = await session.execute(
                            select(User).where(
                                User.telegram_id == user_telegram_id
                            )
                        )
                        user = user_result.scalar_one_or_none()

                        already_referred = (
                            user is not None and user.referred_by is not None
                        )

                    logger.info(
                        "Recorded referral click: referrer=%s, user=%s",
                        referrer_telegram_id,
                        user_telegram_id,
                    )

                return {
                    "type": "ref",
                    "referrer_telegram_id": referrer_telegram_id,
                    "campaign_code": None,
                    "already_referred": already_referred,
                }

            elif start_param.startswith("bloger_"):
                campaign_code = start_param[7:]

                async with async_session_factory() as session:
                    async with session.begin():
                        click = ReferralClick(
                            campaign_code=campaign_code,
                            user_telegram_id=user_telegram_id,
                        )
                        session.add(click)

                        user_result = await session.execute(
                            select(User).where(
                                User.telegram_id == user_telegram_id
                            )
                        )
                        user = user_result.scalar_one_or_none()
                        already_referred = (
                            user is not None and user.referred_by is not None
                        )

                    logger.info(
                        "Recorded blogger click: campaign=%s, user=%s",
                        campaign_code,
                        user_telegram_id,
                    )

                return {
                    "type": "bloger",
                    "referrer_telegram_id": None,
                    "campaign_code": campaign_code,
                    "already_referred": already_referred,
                }

            else:
                logger.warning("Unknown start_param format: %s", start_param)
                return None

        except Exception:
            logger.exception(
                "Error processing referral link: %s", start_param
            )
            return None

    async def register_referral(
        self,
        referred_user_id: int,
        referrer_telegram_id: int,
        campaign_code: str | None = None,
    ) -> bool:
        """Register a referral and give the referred user a 10% discount.

        Returns True if the referral was registered, False otherwise.
        """
        async with async_session_factory() as session:
            async with session.begin():
                # Fetch referred user
                user_result = await session.execute(
                    select(User).where(User.telegram_id == referred_user_id)
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    logger.warning(
                        "register_referral: user telegram_id=%s not found",
                        referred_user_id,
                    )
                    return False

                if user.referred_by is not None:
                    logger.info(
                        "User %s already has a referrer", referred_user_id
                    )
                    return False

                if referred_user_id == referrer_telegram_id:
                    logger.info(
                        "Self-referral attempt by %s", referred_user_id
                    )
                    return False

                # Verify referrer exists
                referrer_result = await session.execute(
                    select(User).where(
                        User.telegram_id == referrer_telegram_id
                    )
                )
                referrer = referrer_result.scalar_one_or_none()
                if referrer is None:
                    logger.warning(
                        "register_referral: referrer telegram_id=%s not found",
                        referrer_telegram_id,
                    )
                    return False

                # Check duplicate referral record
                existing_ref = await session.execute(
                    select(Referral).where(
                        Referral.referred_id == referred_user_id
                    )
                )
                if existing_ref.scalar_one_or_none() is not None:
                    logger.info(
                        "Referral already exists for user %s", referred_user_id
                    )
                    return False

                # Set referrer on user
                user.referred_by = referrer_telegram_id
                if campaign_code:
                    user.referral_campaign_code = campaign_code

                # Give referred user 10% discount on first purchase
                user.discount_percent = max(user.discount_percent, 10)

                # Create referral record
                referral = Referral(
                    referrer_id=referrer_telegram_id,
                    referred_id=referred_user_id,
                )
                session.add(referral)

                logger.info(
                    "Registered referral: user=%s, referrer=%s, campaign=%s",
                    referred_user_id,
                    referrer_telegram_id,
                    campaign_code,
                )
                return True

    async def process_first_purchase_reward(
        self,
        referral: Referral,
        payment_amount_kopeks: int,
        tariff_duration_days: int,
    ) -> bool:
        """Process first-purchase reward: give referrer +10% discount if conditions met.

        Conditions: payment >= 25000 kopeks (250 RUB) and tariff duration > 1 day.
        """
        if referral.is_rewarded:
            return False

        if payment_amount_kopeks < 25000 or tariff_duration_days <= 1:
            return False

        async with async_session_factory() as session:
            async with session.begin():
                ref_result = await session.execute(
                    select(Referral).where(Referral.id == referral.id)
                )
                ref = ref_result.scalar_one_or_none()
                if ref is None or ref.is_rewarded:
                    return False

                ref.is_rewarded = True

                referrer_result = await session.execute(
                    select(User).where(User.telegram_id == ref.referrer_id)
                )
                referrer = referrer_result.scalar_one_or_none()
                if referrer is not None:
                    referrer.discount_percent = min(
                        referrer.discount_percent + 10, 50
                    )
                    logger.info(
                        "Referral reward: referrer=%s now has %d%% discount",
                        ref.referrer_id,
                        referrer.discount_percent,
                    )

                return True

    async def get_referral_stats(self, referrer_telegram_id: int) -> dict:
        """Get referral statistics for a user.

        Returns {"total_referred": int, "rewarded_count": int, "total_discount_given": int}.
        """
        async with async_session_factory() as session:
            refs_result = await session.execute(
                select(Referral).where(
                    Referral.referrer_id == referrer_telegram_id
                )
            )
            referrals = list(refs_result.scalars().all())

            total_referred = len(referrals)
            rewarded_count = sum(1 for r in referrals if r.is_rewarded)
            total_discount_given = rewarded_count * 10

            return {
                "total_referred": total_referred,
                "rewarded_count": rewarded_count,
                "total_discount_given": total_discount_given,
            }

    async def create_blogger_campaign(
        self,
        code: str,
        blogger_name: str,
        discount_percent: int = 10,
    ) -> ReferralCampaign:
        """Create a new blogger campaign.

        Automatically creates a matching promo code (same `code`) so users can
        enter the campaign name as a promo at checkout.
        Raises ValueError if the campaign code already exists.
        """
        from app.services.promo_service import PromoService

        async with async_session_factory() as session:
            async with session.begin():
                existing = await session.execute(
                    select(ReferralCampaign).where(
                        ReferralCampaign.code == code
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    raise ValueError(f"Campaign code '{code}' already exists")

                # Create promo in the same transaction
                try:
                    promo = await PromoService().create_promo(
                        discount_value=discount_percent,
                        code=code,
                        max_uses=None,
                        expires_at=None,
                        min_amount_kopeks=0,
                        session=session,
                    )
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc

                campaign = ReferralCampaign(
                    code=code,
                    blogger_name=blogger_name,
                    discount_percent=discount_percent,
                    is_active=True,
                    promo_code_id=promo.id,
                )
                session.add(campaign)
                await session.flush()

                logger.info(
                    "Created blogger campaign: code=%s, blogger=%s, promo_id=%s",
                    code,
                    blogger_name,
                    promo.id,
                )
                return campaign

    async def get_campaign_stats(self, campaign_code: str) -> dict:
        """Get statistics for a blogger campaign.

        Returns {"clicks": int, "registrations": int, "payments": int,
                 "revenue": int, "conversion": float}.
        """
        async with async_session_factory() as session:
            # Count clicks
            clicks_result = await session.execute(
                select(func.count())
                .select_from(ReferralClick)
                .where(ReferralClick.campaign_code == campaign_code)
            )
            clicks = clicks_result.scalar() or 0

            # Count registrations (users with this campaign code)
            regs_result = await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.referral_campaign_code == campaign_code)
            )
            registrations = regs_result.scalar() or 0

            # Count payments and revenue from users with this campaign code
            payments_result = await session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(Payment.amount_kopeks), 0),
                )
                .select_from(Payment)
                .join(User, Payment.user_id == User.id)
                .where(
                    Payment.status == "paid",
                    User.referral_campaign_code == campaign_code,
                )
            )
            row = payments_result.one()
            payments = row[0]
            revenue = row[1]

            conversion = (
                round(registrations / clicks * 100, 1) if clicks > 0 else 0.0
            )

            return {
                "clicks": clicks,
                "registrations": registrations,
                "payments": payments,
                "revenue": revenue,
                "conversion": conversion,
            }

    async def get_all_campaigns(self) -> list[ReferralCampaign]:
        """Get all blogger campaigns."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(ReferralCampaign).order_by(
                    ReferralCampaign.created_at.desc()
                )
            )
            return list(result.scalars().all())

    async def disable_campaign(self, campaign_id: int) -> bool:
        """Disable a blogger campaign. Returns True if found and disabled."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ReferralCampaign).where(
                        ReferralCampaign.id == campaign_id
                    )
                )
                campaign = result.scalar_one_or_none()
                if campaign is None:
                    logger.warning(
                        "disable_campaign: id=%s not found", campaign_id
                    )
                    return False

                campaign.is_active = False
                logger.info(
                    "Disabled campaign: code=%s (id=%s)",
                    campaign.code,
                    campaign_id,
                )
                return True
