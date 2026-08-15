import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards.inline import (
    back_keyboard,
    extend_tariff_keyboard,
    key_detail_keyboard,
    keys_list_keyboard,
    payment_success_keyboard,
    tariff_confirm_keyboard,
    tariff_list_keyboard,
)
from app.database.session import async_session_factory
from app.services.payment_service import PaymentService, get_payment_provider
from app.services.subscription_sync_service import SubscriptionSyncService
from app.utils.formatters import format_date, format_price, format_traffic
from sqlalchemy.future import select
from app.database.models.tariff import Tariff
from app.database.models.subscription import Subscription
from app.database.models.payment import Payment

router = Router()
logger = logging.getLogger(__name__)


def _get_payment_service() -> PaymentService | None:
    try:
        return PaymentService(get_payment_provider())
    except NotImplementedError:
        return None


class PurchaseStates(StatesGroup):
    selecting_tariff = State()
    confirming = State()
    entering_promo = State()


@router.callback_query(F.data == "purchase_start")
async def purchase_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PurchaseStates.selecting_tariff)

    async with async_session_factory() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.is_active == True).order_by(Tariff.sort_order)
        )
        tariffs = result.scalars().all()

    photo = FSInputFile("1.png")
    if not tariffs:
        text = "😔 В данный момент нет доступных тарифов."
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=back_keyboard("main_menu"),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=back_keyboard("main_menu"),
            )
        return

    lines = ["💳 <b>Выберите тариф</b>\n"]
    for t in tariffs:
        lines.append(f"• <b>{t.name}</b> — {format_price(t.price_kopeks)} / {t.duration_days} дн.")

    text = "\n".join(lines)
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=tariff_list_keyboard(tariffs),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=tariff_list_keyboard(tariffs),
        )


@router.callback_query(F.data.startswith("tariff_select:"))
async def tariff_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tariff_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
        tariff = result.scalar_one_or_none()

    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    await state.set_state(PurchaseStates.confirming)
    await state.update_data(tariff_id=tariff_id)

    user_discount = 0
    db_user = callback.message.chat.__dict__.get("db_user") if hasattr(callback.message.chat, "__dict__") else None

    photo = FSInputFile("1.png")
    discount_text = ""
    if user_discount > 0:
        discount_text = f"\n🎁 Ваша скидка: {user_discount}%"

    text = (
        f"💳 <b>Подтверждение покупки</b>\n\n"
        f"📋 Тариф: <b>{tariff.name}</b>\n"
        f"⏳ Длительность: {tariff.duration_days} дн.\n"
        f"💰 Стоимость: {format_price(tariff.price_kopeks)}{discount_text}\n\n"
        f"Нажмите «Оплатить» для продолжения."
    )
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=tariff_confirm_keyboard(tariff_id),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=tariff_confirm_keyboard(tariff_id),
        )


@router.callback_query(F.data.startswith("tariff_confirm:"))
async def tariff_confirmed(callback: CallbackQuery, state: FSMContext, db_user=None):
    await callback.answer()
    tariff_id = int(callback.data.split(":")[1])

    payment_service = _get_payment_service()
    if payment_service is None:
        await callback.answer(
            "Платежи временно недоступны. Пожалуйста, обратитесь в поддержку.",
            show_alert=True,
        )
        return

    promo_code = None
    fsm_data = await state.get_data()
    if "promo_code" in fsm_data:
        promo_code = fsm_data["promo_code"]

    try:
        payment = await payment_service.create_payment(
            user_id=db_user.id if db_user else 0,
            tariff_id=tariff_id,
            promo_code=promo_code,
        )
        await state.clear()

        photo = FSInputFile("1.png")
        text = (
            f"💳 <b>Оплата создана</b>\n\n"
            f"Сумма: {format_price(payment.amount_kopeks)}\n\n"
            f"Нажмите кнопку ниже для оплаты:"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment.payment_url)],
                [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")],
                [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
            ]
        )
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception as e:
        logger.error(f"Payment creation failed: {e}")
        await callback.answer("Ошибка создания платежа. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data == "my_keys")
async def my_keys(callback: CallbackQuery, db_user=None):
    await callback.answer()
    photo = FSInputFile("1.png")

    if not db_user:
        text = "❌ Ошибка получения данных пользователя."
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=back_keyboard("main_menu"),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=back_keyboard("main_menu"),
            )
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.user_id == db_user.id,
                Subscription.status == "active",
            )
        )
        subscriptions = result.scalars().all()

    if not subscriptions:
        text = (
            "🔑 <b>Мои ключи</b>\n\n"
            "У вас пока нет активных подписок.\n"
            "Приобретите тариф в разделе «Купить VPN»."
        )
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=back_keyboard("main_menu"),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=back_keyboard("main_menu"),
            )
        return

    lines = ["🔑 <b>Ваши активные ключи:</b>\n"]
    for sub in subscriptions:
        status_icon = "🟢" if sub.status == "active" else "🔴"
        lines.append(f"{status_icon} <b>{sub.key_name}</b>")
        if sub.expires_at:
            lines.append(f"   ⏳ до {format_date(sub.expires_at)}")
        lines.append("")

    text = "\n".join(lines)
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=keys_list_keyboard(subscriptions),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=keys_list_keyboard(subscriptions),
        )


@router.callback_query(F.data.startswith("key_detail:"))
async def key_detail(callback: CallbackQuery):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])
    photo = FSInputFile("1.png")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        sub = result.scalar_one_or_none()

    if not sub:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    traffic = format_traffic(sub.traffic_limit_bytes) if sub.traffic_limit_bytes else "∞"
    expiry = format_date(sub.expires_at) if sub.expires_at else "—"

    text = (
        f"🔑 <b>{sub.key_name}</b>\n\n"
        f"📋 Статус: {'🟢 Активна' if sub.status == 'active' else '🔴 Неактивна'}\n"
        f"⏳ Действует до: {expiry}\n"
        f"📊 Трафик: {traffic}\n"
        f"📱 Устройства: {sub.devices_connected}/{sub.device_limit}\n\n"
        f"<code>{sub.subscription_url or 'Ссылка недоступна'}</code>"
    )
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=key_detail_keyboard(sub.id, sub.subscription_url or ""),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=key_detail_keyboard(sub.id, sub.subscription_url or ""),
        )


@router.callback_query(F.data.startswith("key_copy:"))
async def key_copy(callback: CallbackQuery):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        sub = result.scalar_one_or_none()

    if sub and sub.subscription_url:
        await callback.answer("Ключ скопирован!", show_alert=False)
        await callback.message.answer(f"<code>{sub.subscription_url}</code>", parse_mode="HTML")
    else:
        await callback.answer("Ключ недоступен", show_alert=True)


@router.callback_query(F.data.startswith("key_extend:"))
async def key_extend(callback: CallbackQuery):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])
    photo = FSInputFile("1.png")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.is_active == True).order_by(Tariff.sort_order)
        )
        tariffs = result.scalars().all()

    text = "⏳ <b>Продление подписки</b>\n\nВыберите тариф для продления:"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=extend_tariff_keyboard(sub_id, tariffs),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=extend_tariff_keyboard(sub_id, tariffs),
        )


@router.callback_query(F.data.startswith("extend_confirm:"))
async def extend_confirmed(callback: CallbackQuery, db_user=None):
    await callback.answer()
    parts = callback.data.split(":")
    sub_id = int(parts[1])
    tariff_id = int(parts[2])

    payment_service = _get_payment_service()
    if payment_service is None:
        await callback.answer(
            "Платежи временно недоступны. Пожалуйста, обратитесь в поддержку.",
            show_alert=True,
        )
        return

    try:
        payment = await payment_service.create_payment(
            user_id=db_user.id if db_user else 0,
            tariff_id=tariff_id,
        )
        # Mark as renewal type
        async with async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(Payment).where(Payment.id == payment.id)
                )
                p = result.scalar_one_or_none()
                if p:
                    p.type = "renewal"
                    p.subscription_id = sub_id

        photo = FSInputFile("1.png")
        text = (
            f"💳 <b>Оплата продления</b>\n\n"
            f"Сумма: {format_price(payment.amount_kopeks)}\n\n"
            f"Нажмите кнопку ниже для оплаты:"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment.payment_url)],
                [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")],
                [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
            ]
        )
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception as e:
        logger.error(f"Extend payment creation failed: {e}")
        await callback.answer("Ошибка создания платежа.", show_alert=True)
