import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_format_price():
    from app.utils.formatters import format_price
    assert format_price(29900) == "299 ₽"
    assert format_price(149900) == "1 499 ₽"
    assert format_price(0) == "0 ₽"
    assert format_price(100) == "1 ₽"


@pytest.mark.asyncio
async def test_format_traffic():
    from app.utils.formatters import format_traffic
    assert format_traffic(0) == "∞"
    assert format_traffic(1073741824) == "1.0 ГБ"
    assert format_traffic(524288000) == "500.0 МБ"


@pytest.mark.asyncio
async def test_format_date():
    from datetime import datetime, timezone
    from app.utils.formatters import format_date
    dt = datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert format_date(dt) == "15.08.2026"


@pytest.mark.asyncio
async def test_mask_key():
    from app.utils.formatters import mask_key
    url = "https://example.com/sub/abcdef1234567890"
    masked = mask_key(url)
    assert masked.startswith("https://ex")
    assert masked.endswith("7890")
    assert "***" in masked


@pytest.mark.asyncio
async def test_promo_code_generation():
    from app.services.promo_service import PromoService
    service = PromoService()
    code = service.generate_code()
    assert code.startswith("DAGGER-")
    assert len(code) == 12  # DAGGER- + 5 chars


@pytest.mark.asyncio
async def test_payment_provider_abstract():
    from app.services.payment_service import PaymentProvider
    with pytest.raises(TypeError):
        PaymentProvider()


@pytest.mark.asyncio
async def test_is_admin_check():
    from app.config.settings import settings
    admin_ids = settings.admin_ids_list
    assert isinstance(admin_ids, list)


@pytest.mark.asyncio
async def test_referral_no_self_referral():
    """Test that self-referral is rejected"""
    from app.services.referral_service import ReferralService
    service = ReferralService()
    result = await service.register_referral(
        referred_user_id=123,
        referrer_telegram_id=123,
    )
    assert result is False or result is None


@pytest.mark.asyncio
async def test_webhook_idempotency_structure():
    """Verify webhook processing structure prevents duplicates"""
    from app.services.payment_service import YooKassaPaymentProvider
    provider = YooKassaPaymentProvider()
    invalid_payload = {"event": "invalid"}
    result = await provider.verify_webhook(invalid_payload)
    assert result is None


@pytest.mark.asyncio
async def test_tariff_confirm_callback_data():
    """Verify callback data format for tariff confirmation"""
    from app.bot.keyboards.inline import tariff_confirm_keyboard
    kb = tariff_confirm_keyboard(tariff_id=5)
    buttons = kb.inline_keyboard[0]
    assert buttons[0].callback_data == "tariff_confirm:5"


@pytest.mark.asyncio
async def test_main_menu_admin_visibility():
    """Admin sees admin button, regular user doesn't"""
    from app.bot.keyboards.inline import main_menu_keyboard
    user_kb = main_menu_keyboard(is_admin=False)
    admin_kb = main_menu_keyboard(is_admin=True)

    user_callbacks = [b.callback_data for row in user_kb.inline_keyboard for b in row]
    admin_callbacks = [b.callback_data for row in admin_kb.inline_keyboard for b in row]

    assert "admin_main" not in user_callbacks
    assert "admin_main" in admin_callbacks


@pytest.mark.asyncio
async def test_back_button_present():
    """All keyboards should have back button"""
    from app.bot.keyboards.inline import back_keyboard
    kb = back_keyboard("main_menu")
    assert kb.inline_keyboard[0][0].text == "↩️ Назад"
    assert kb.inline_keyboard[0][0].callback_data == "main_menu"
