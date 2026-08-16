from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    remnawave_user_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    key_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    traffic_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    device_limit: Mapped[int] = mapped_column(Integer, default=5)
    devices_connected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")

    user = relationship("User", back_populates="subscriptions")
    tariff = relationship("Tariff", lazy="selectin")
