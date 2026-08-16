"""features: campaigns link promo, nullable tariff_id, unique promo usage, seed tariffs

Revision ID: 002_features
Revises: 001_initial
Create Date: 2026-08-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_features"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. referral_campaigns.promo_code_id FK → promo_codes.id
    op.add_column(
        "referral_campaigns",
        sa.Column("promo_code_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_referral_campaigns_promo_code_id",
        "referral_campaigns",
        "promo_codes",
        ["promo_code_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_referral_campaigns_promo_code_id",
        "referral_campaigns",
        ["promo_code_id"],
    )

    # 2. subscriptions.tariff_id → nullable (issued keys have no tariff)
    op.alter_column(
        "subscriptions",
        "tariff_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 3. one_per_user DB guard
    op.create_unique_constraint(
        "uq_promo_usage_user_promo",
        "promo_code_usages",
        ["promo_code_id", "user_id"],
    )

    # 4. promo_codes.code VARCHAR(50) → VARCHAR(100) to match campaign codes
    op.alter_column(
        "promo_codes",
        "code",
        existing_type=sa.String(50),
        type_=sa.String(100),
    )

    # 5. Seed fixed tariffs (idempotent by name)
    tariffs_table = sa.table(
        "tariffs",
        sa.column("name", sa.String()),
        sa.column("duration_days", sa.Integer()),
        sa.column("price_kopeks", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    conn = op.get_bind()
    seeds = [
        {"name": "\U0001f680Light", "duration_days": 30, "price_kopeks": 20000, "is_active": True, "sort_order": 1},
        {"name": "\U0001f680Medium", "duration_days": 90, "price_kopeks": 50000, "is_active": True, "sort_order": 2},
        {"name": "\U0001f680Hard", "duration_days": 180, "price_kopeks": 90000, "is_active": True, "sort_order": 3},
        {"name": "\U0001f680Full", "duration_days": 360, "price_kopeks": 170000, "is_active": True, "sort_order": 4},
    ]
    for s in seeds:
        exists = conn.execute(
            sa.select(sa.func.count()).select_from(tariffs_table).where(tariffs_table.c.name == s["name"])
        ).scalar() or 0
        if exists == 0:
            conn.execute(tariffs_table.insert().values(**s))

    # Deactivate any tariffs not among the fixed four
    fixed_names = [s["name"] for s in seeds]
    conn.execute(
        tariffs_table.update()
        .where(~tariffs_table.c.name.in_(fixed_names))
        .values(is_active=False)
    )

    # 6. Legacy fixed-type promos → deactivate
    op.execute("UPDATE promo_codes SET is_active = false WHERE discount_type = 'fixed' AND is_active = true")


def downgrade() -> None:
    op.drop_constraint("uq_promo_usage_user_promo", "promo_code_usages", type_="unique")
    op.alter_column(
        "promo_codes",
        "code",
        existing_type=sa.String(100),
        type_=sa.String(50),
    )
    op.alter_column(
        "subscriptions",
        "tariff_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_index("ix_referral_campaigns_promo_code_id", table_name="referral_campaigns")
    op.drop_constraint("fk_referral_campaigns_promo_code_id", "referral_campaigns", type_="foreignkey")
    op.drop_column("referral_campaigns", "promo_code_id")
    # Note: seeded tariffs are NOT removed in downgrade to avoid data loss.
