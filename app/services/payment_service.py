"""Payment processing service."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func, select

from app.config import settings
from app.database.models import (
    Payment,
    PromoCode,
    PromoCodeUsage,
    Referral,
    Subscription,
    Tariff,
    User,
)
from app.database.session import async_session_factory
from app.services.remnawave_service import RemnawaveService
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class PaymentProvider(ABC):
    """Abstract payment provider interface."""

    @abstractmethod
    async def create_payment(
        self, amount_kopeks: int, description: str, metadata: dict
    ) -> dict:
        """Create a payment. Returns {"payment_id": str, "payment_url": str}."""
        ...

    @abstractmethod
    async def get_payment_status(self, payment_id: str) -> str:
        """Get payment status string."""
        ...

    @abstractmethod
    async def verify_webhook(self, payload: dict) -> dict | None:
        """Parse and verify webhook payload. Returns {"payment_id": str, "status": str} or None."""
        ...


def get_payment_provider() -> PaymentProvider:
    """Factory for the configured payment provider.

    Add your provider here when ready, e.g.:
        if settings.PAYMENT_PROVIDER == "myprovider":
            return MyPaymentProvider()
    """
    if settings.PAYMENT_PROVIDER == "platega":
        from app.services.platega_provider import PlategaProvider
        return PlategaProvider()

    raise NotImplementedError(
        f"Payment provider '{settings.PAYMENT_PROVIDER}' is not configured. "
        f"Add it in get_payment_provider() in app/services/payment_service.py"
    )


class PaymentService:
    """High-level payment business logic."""

    def __init__(self, provider: PaymentProvider | None = None) -> None:
        self._provider = provider
        self._remnawave = RemnawaveService()
        self._subscription_service = SubscriptionService()

    def _require_provider(self) -> PaymentProvider:
        if self._provider is None:
            raise NotImplementedError(
                "Payment provider is not configured. "
                "Add your provider in get_payment_provider() in app/services/payment_service.py"
            )
        return self._provider

    async def create_payment(
        self,
        user_id: int,
        tariff_id: int,
        promo_code: str | None = None,
        months: int = 1,
    ) -> Payment:
        """Create a new payment for a tariff, applying discounts and promo codes."""
        provider = self._require_provider()
        async with async_session_factory() as session:
            async with session.begin():
                # Fetch tariff
                tariff_result = await session.execute(
                    select(Tariff).where(
                        Tariff.id == tariff_id, Tariff.is_active.is_(True)
                    )
                )
                tariff = tariff_result.scalar_one_or_none()
                if tariff is None:
                    raise ValueError(f"Active tariff with id={tariff_id} not found")

                # Fetch user
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    raise ValueError(f"User with id={user_id} not found")

                base_amount = tariff.price_kopeks * months
                discount_total = 0
                promo_code_obj: PromoCode | None = None

                # Promo code and personal discount are mutually exclusive:
                # a promo replaces the user's referral discount.
                if promo_code:
                    pc_result = await session.execute(
                        select(PromoCode).where(
                            PromoCode.code == promo_code,
                            PromoCode.is_active.is_(True),
                        )
                    )
                    promo_code_obj = pc_result.scalar_one_or_none()

                    if promo_code_obj is not None:
                        valid, message, _ = await self._validate_promo_internal(
                            session, promo_code_obj, user_id, base_amount
                        )
                        if valid:
                            discount_total = int(
                                base_amount * promo_code_obj.discount_value / 100
                            )
                        else:
                            logger.info("Promo code rejected: %s - %s", promo_code, message)
                            promo_code_obj = None

                if promo_code_obj is None and user.discount_percent > 0:
                    discount_total = int(base_amount * user.discount_percent / 100)

                final_amount = max(0, base_amount - discount_total)

                # Create payment via provider
                metadata = {
                    "user_id": str(user_id),
                    "tariff_id": str(tariff_id),
                    "telegram_id": str(user.telegram_id),
                    "months": str(months),
                }
                if promo_code_obj:
                    metadata["promo_code_id"] = str(promo_code_obj.id)

                provider_result = await provider.create_payment(
                    amount_kopeks=final_amount,
                    description=f"Dagger - {tariff.name} ({months} мес.)",
                    metadata=metadata,
                )

                # Create DB record
                payment = Payment(
                    user_id=user_id,
                    tariff_id=tariff_id,
                    amount_kopeks=final_amount,
                    discount_kopeks=discount_total,
                    promo_code_id=promo_code_obj.id if promo_code_obj else None,
                    status="pending",
                    provider_payment_id=provider_result["payment_id"],
                    payment_url=provider_result["payment_url"],
                    type="purchase",
                )
                session.add(payment)

                logger.info(
                    "Created payment: user_id=%s, tariff=%s, months=%d, amount=%d kopeks",
                    user_id,
                    tariff.name,
                    months,
                    final_amount,
                )
                return payment

    async def process_webhook(self, payload: dict) -> bool:
        """Process an incoming payment webhook. Idempotent."""
        provider = self._require_provider()
        verified = await provider.verify_webhook(payload)
        if verified is None:
            logger.warning("Webhook verification failed")
            return False

        provider_payment_id = verified["payment_id"]
        status = verified["status"]

        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(Payment).where(
                        Payment.provider_payment_id == provider_payment_id
                    )
                )
                payment = result.scalar_one_or_none()

                if payment is None:
                    logger.warning(
                        "Payment not found for provider_id=%s", provider_payment_id
                    )
                    return False

                # Idempotent: already processed
                if payment.status == "paid" and payment.is_fulfilled:
                    logger.info(
                        "Payment %s already fulfilled, skipping",
                        provider_payment_id,
                    )
                    return True

                if status != "succeeded":
                    payment.status = status
                    logger.info(
                        "Payment %s status updated to %s",
                        provider_payment_id,
                        status,
                    )
                    return True

                # Mark as paid
                payment.status = "paid"
                payment.paid_at = datetime.now(timezone.utc)
                payment.is_fulfilled = False

                logger.info("Payment %s marked as paid", provider_payment_id)

        # Attempt fulfillment outside the transaction to avoid long-held locks
        try:
            await self.fulfill_payment(payment.id)
        except Exception:
            logger.exception(
                "Fulfillment failed for payment %s after webhook", payment.id
            )

        return True

    async def fulfill_payment(self, payment_id: int) -> bool:
        """Fulfill a paid payment: provision VPN access, handle referrals, promo codes."""
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(Payment).where(Payment.id == payment_id)
                )
                payment = result.scalar_one_or_none()

                if payment is None:
                    logger.error("fulfill_payment: payment_id=%s not found", payment_id)
                    return False

                if payment.status != "paid":
                    logger.warning(
                        "fulfill_payment: payment_id=%s status is %s, expected 'paid'",
                        payment_id,
                        payment.status,
                    )
                    return False

                if payment.is_fulfilled:
                    logger.info("fulfill_payment: payment_id=%s already fulfilled", payment_id)
                    return True

                # Fetch tariff
                tariff_result = await session.execute(
                    select(Tariff).where(Tariff.id == payment.tariff_id)
                )
                tariff = tariff_result.scalar_one_or_none()
                if tariff is None:
                    logger.error(
                        "fulfill_payment: tariff_id=%s not found", payment.tariff_id
                    )
                    payment.fulfillment_attempts += 1
                    return False

                # Fetch user
                user_result = await session.execute(
                    select(User).where(User.id == payment.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    logger.error(
                        "fulfill_payment: user_id=%s not found", payment.user_id
                    )
                    payment.fulfillment_attempts += 1
                    return False

                try:
                    if payment.type == "purchase":
                        await self._fulfill_purchase(session, payment, user, tariff)
                    elif payment.type == "renewal":
                        await self._fulfill_renewal(session, payment, user, tariff)
                    else:
                        logger.warning(
                            "Unknown payment type '%s' for payment_id=%s",
                            payment.type,
                            payment_id,
                        )
                        payment.fulfillment_attempts += 1
                        return False

                    # Process referral reward
                    await self._process_referral_reward(session, user, payment, tariff)

                    # Increment promo code usage
                    if payment.promo_code_id:
                        await self._increment_promo_usage(
                            session, payment.promo_code_id, payment.user_id, payment.id
                        )

                    payment.is_fulfilled = True
                    logger.info("Successfully fulfilled payment_id=%s", payment_id)
                    return True

                except Exception:
                    logger.exception(
                        "Fulfillment error for payment_id=%s", payment_id
                    )
                    payment.fulfillment_attempts += 1
                    return False

    async def _fulfill_purchase(
        self, session: Any, payment: Payment, user: User, tariff: Tariff
    ) -> None:
        """Provision new VPN access for a purchase."""
        key_name = await self._subscription_service.generate_unique_key_name(session)

        # Extract months from payment metadata
        months = 1
        if payment.provider_payment_id:
            # Try to get months from Payment model if we add a field, or from metadata
            # For now, we'll calculate from amount
            if payment.amount_kopeks > 0 and tariff.price_kopeks > 0:
                months = max(1, round(payment.amount_kopeks / tariff.price_kopeks))

        expire_at = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        total_days = tariff.duration_days * months
        expire_at = expire_at + timedelta(days=total_days)

        rw_user = await self._remnawave.create_user(
            username=key_name,
            expire_at=expire_at.isoformat(),
            traffic_limit_bytes=0,
            hwid_device_limit=5,
            email=f"{user.telegram_id}@dagger.local",
            telegram_id=user.telegram_id,
        )
        if rw_user is None:
            raise RuntimeError("Failed to create panel user")

        fields = RemnawaveService.extract_user_fields(rw_user)
        sub_url = fields["subscription_url"]
        identifier = fields["identifier"]

        db_subscription = Subscription(
            user_id=user.id,
            remnawave_user_uuid=identifier or None,
            key_name=key_name,
            subscription_url=sub_url,
            tariff_id=tariff.id,
            expires_at=expire_at,
            traffic_limit_bytes=0,
            device_limit=5,
            status="active",
        )
        session.add(db_subscription)
        await session.flush()

        payment.subscription_id = db_subscription.id
        logger.info(
            "Purchase fulfilled: user_id=%s, panel_id=%s, subscription_id=%s, months=%d, days=%d",
            user.id,
            identifier,
            db_subscription.id,
            months,
            total_days,
        )

    async def _fulfill_renewal(
        self, session: Any, payment: Payment, user: User, tariff: Tariff
    ) -> None:
        """Extend existing VPN subscription for a renewal."""
        if payment.subscription_id is None:
            # Find active subscription for this user
            sub_result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.status == "active",
                ).order_by(Subscription.expires_at.desc()).limit(1)
            )
            subscription = sub_result.scalar_one_or_none()
            if subscription is None:
                raise RuntimeError("No active subscription found for renewal")
            payment.subscription_id = subscription.id
        else:
            sub_result = await session.execute(
                select(Subscription).where(Subscription.id == payment.subscription_id)
            )
            subscription = sub_result.scalar_one_or_none()
            if subscription is None:
                raise RuntimeError(
                    f"Subscription id={payment.subscription_id} not found"
                )

        if not subscription.remnawave_user_uuid:
            raise RuntimeError("Subscription has no panel user identifier")

        # Remnawave extend endpoint requires the numeric panel user id, which we
        # store in remnawave_user_uuid (see extract_user_fields). Old records that
        # hold a uuid instead will 400 here; those predate this integration.
        extend_result = await self._remnawave.extend_user(
            user_id=subscription.remnawave_user_uuid,
            days=tariff.duration_days,
        )
        if extend_result is None:
            raise RuntimeError("Failed to extend panel user")

        from datetime import timedelta
        subscription.expires_at = subscription.expires_at + timedelta(
            days=tariff.duration_days
        )

        logger.info(
            "Renewal fulfilled: user_id=%s, subscription_id=%s, +%d days",
            user.id,
            subscription.id,
            tariff.duration_days,
        )

    async def _process_referral_reward(
        self, session: Any, user: User, payment: Payment, tariff: Tariff
    ) -> None:
        """Give referrer a discount bonus if conditions are met."""
        if user.referred_by is None:
            return

        # Conditions: >= 250 rubles (25000 kopeks) and duration > 1 day
        if payment.amount_kopeks < 25000 or tariff.duration_days <= 1:
            return

        ref_result = await session.execute(
            select(Referral).where(
                Referral.referred_id == user.telegram_id,
                Referral.referrer_id == user.referred_by,
            )
        )
        referral = ref_result.scalar_one_or_none()
        if referral is None or referral.is_rewarded:
            return

        referral.is_rewarded = True

        # Give referrer +10% discount (cap at 50%)
        referrer_result = await session.execute(
            select(User).where(User.telegram_id == user.referred_by)
        )
        referrer = referrer_result.scalar_one_or_none()
        if referrer is not None:
            new_discount = min(referrer.discount_percent + 10, 50)
            referrer.discount_percent = new_discount
            logger.info(
                "Referral reward: referrer telegram_id=%s got +10%% discount (now %d%%)",
                user.referred_by,
                new_discount,
            )

    async def _increment_promo_usage(
        self, session: Any, promo_code_id: int, user_id: int, payment_id: int
    ) -> None:
        """Increment promo code uses_count and record usage."""
        pc_result = await session.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id)
        )
        promo = pc_result.scalar_one_or_none()
        if promo is None:
            return

        promo.uses_count += 1

        usage = PromoCodeUsage(
            promo_code_id=promo_code_id,
            user_id=user_id,
            payment_id=payment_id,
        )
        session.add(usage)
        logger.info(
            "Promo code %s usage incremented to %d", promo.code, promo.uses_count
        )

    async def retry_unfulfilled_payments(self) -> None:
        """Retry fulfillment for all unfulfilled paid payments."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Payment.id).where(
                    Payment.status == "paid",
                    Payment.is_fulfilled.is_(False),
                    Payment.fulfillment_attempts < 5,
                )
            )
            payment_ids = [row[0] for row in result.all()]

        if not payment_ids:
            return

        logger.info("Retrying %d unfulfilled payments", len(payment_ids))
        for pid in payment_ids:
            try:
                success = await self.fulfill_payment(pid)
                if not success:
                    logger.warning("Retry failed for payment_id=%s", pid)
            except Exception:
                logger.exception("Exception retrying payment_id=%s", pid)

    async def get_today_stats(self) -> dict:
        """Get today's payment statistics."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async with async_session_factory() as session:
            count_result = await session.execute(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.status == "paid",
                    Payment.paid_at >= today_start,
                )
            )
            count = count_result.scalar() or 0

            sum_result = await session.execute(
                select(func.coalesce(func.sum(Payment.amount_kopeks), 0))
                .where(
                    Payment.status == "paid",
                    Payment.paid_at >= today_start,
                )
            )
            total = sum_result.scalar() or 0

        return {"count": count, "total_amount_kopeks": total}

    async def get_month_stats(self) -> dict:
        """Get current month's payment statistics."""
        now = datetime.now(timezone.utc)

        async with async_session_factory() as session:
            count_result = await session.execute(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.status == "paid",
                    extract("year", Payment.paid_at) == now.year,
                    extract("month", Payment.paid_at) == now.month,
                )
            )
            count = count_result.scalar() or 0

            sum_result = await session.execute(
                select(func.coalesce(func.sum(Payment.amount_kopeks), 0))
                .where(
                    Payment.status == "paid",
                    extract("year", Payment.paid_at) == now.year,
                    extract("month", Payment.paid_at) == now.month,
                )
            )
            total = sum_result.scalar() or 0

        return {"count": count, "total_amount_kopeks": total}

    async def get_recent_payments(
        self, limit: int, offset: int
    ) -> list[Payment]:
        """Get recent payments ordered by creation time descending."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Payment)
                .order_by(Payment.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def _validate_promo_internal(
        self,
        session: Any,
        promo: PromoCode,
        user_id: int,
        amount_kopeks: int,
    ) -> tuple[bool, str, PromoCode | None]:
        """Validate promo code within an existing session."""
        if not promo.is_active:
            return False, "Promo code is inactive", None

        if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
            return False, "Promo code has expired", None

        if promo.max_uses is not None and promo.uses_count >= promo.max_uses:
            return False, "Promo code usage limit reached", None

        if amount_kopeks < promo.min_amount_kopeks:
            return (
                False,
                f"Minimum order amount is {promo.min_amount_kopeks // 100} RUB",
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
