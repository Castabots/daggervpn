from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"), nullable=False)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    amount_kopeks: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_kopeks: Mapped[int] = mapped_column(Integer, default=0)
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    payment_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="purchase")
    is_fulfilled: Mapped[bool] = mapped_column(Boolean, default=False)
    fulfillment_attempts: Mapped[int] = mapped_column(Integer, default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="payments")
    tariff = relationship("Tariff", lazy="selectin")
    subscription = relationship("Subscription", lazy="selectin")
