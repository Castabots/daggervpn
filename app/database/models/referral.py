from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Referral(TimestampMixin, Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    is_rewarded: Mapped[bool] = mapped_column(Boolean, default=False)


class ReferralCampaign(TimestampMixin, Base):
    __tablename__ = "referral_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    blogger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    discount_percent: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    promo_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="SET NULL"), nullable=True
    )

    promo_code = relationship("PromoCode", lazy="selectin")


class ReferralClick(TimestampMixin, Base):
    __tablename__ = "referral_clicks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    referrer_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
