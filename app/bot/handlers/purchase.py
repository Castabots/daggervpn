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
    tariff_confirm_keyboard,
    tariff_list_keyboard,
)
from app.config.settings import settings
from app.database.session import async_session_factory
from app.utils.formatters import format_date, format_price, format_traffic
from sqlalchemy.future import select
from app.database.models.tariff import Tariff
from app.database.models.subscription import Subscription

router = Router()
logger = logging.getLogger(__name__)


class PurchaseStates(StatesGroup):
    selecting_tariff = State()
    selecting_months = State()
    confirming = State()


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
        text = "В данный момент нет доступных тарифов."
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

    lines = ["<b>Выберите тариф</b>\n"]
    for t in tariffs:
        lines.append(f"• <b>{t.name}</b> — {format_price(t.price_kopeks)} / {t.duration_days} дн.")

    text = "\n".join(lines)

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

    await state.set_state(PurchaseStates.selecting_months)
    await state.update_data(tariff_id=tariff_id)

    photo = FSInputFile("1.png")
    text = (
        f"<b>Выбор периода подписки</b>\n\n"
        f"Тариф: <b>{tariff.name}</b>\n"
        f"Стоимость за {tariff.duration_days} дн.: {format_price(tariff.price_kopeks)}\n\n"
        f"Выберите на сколько месяцев хотите оформить подписку:"
    )

    from app.bot.keyboards.inline import months_selection_keyboard
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=photo, caption=text, parse_mode="HTML",
        reply_markup=months_selection_keyboard(tariff_id),
    )


@router.callback_query(F.data.startswith("months_select:"))
async def months_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    parts = callback.data.split(":")
    tariff_id = int(parts[1])
    months = int(parts[2])

    async with async_session_factory() as session:
        result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
        tariff = result.scalar_one_or_none()

    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    await state.set_state(PurchaseStates.confirming)
    await state.update_data(tariff_id=tariff_id, months=months)

    total_price = tariff.price_kopeks * months
    total_days = tariff.duration_days * months

    photo = FSInputFile("1.png")
    text = (
        f"<b>Подтверждение покупки</b>\n\n"
        f"Тариф: <b>{tariff.name}</b>\n"
        f"Период: {months} мес.\n"
        f"Длительность: {total_days} дн.\n"
        f"Стоимость: {format_price(total_price)}\n\n"
        f"Нажмите «Оплатить» для продолжения."
    )

    from app.bot.keyboards.inline import tariff_confirm_keyboard
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=photo, caption=text, parse_mode="HTML",
        reply_markup=tariff_confirm_keyboard(tariff_id, months),
    )


@router.callback_query(F.data.startswith("tariff_confirm:"))
async def tariff_confirmed(callback: CallbackQuery, state: FSMContext, db_user=None):
    await callback.answer()

    parts = callback.data.split(":")
    tariff_id = int(parts[1])
    months = int(parts[2]) if len(parts) > 2 else 1

    await state.clear()

    if not db_user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return

    photo = FSInputFile("1.png")

    # Create payment through Platega
    try:
        from app.services.payment_service import PaymentService, get_payment_provider

        provider = get_payment_provider()
        payment_service = PaymentService(provider)

        # Get tariff to calculate total amount
        async with async_session_factory() as session:
            result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
            tariff = result.scalar_one_or_none()

        if not tariff:
            await callback.answer("Тариф не найден", show_alert=True)
            return

        total_amount = tariff.price_kopeks * months

        payment = await payment_service.create_payment(
            user_id=db_user.id,
            tariff_id=tariff_id,
            promo_code=None,
            months=months,
        )

        text = (
            "<b>💳 Оплата</b>\n\n"
            f"Тариф: {tariff.name}\n"
            f"Период: {months} мес.\n"
            f"Сумма: {format_price(total_amount)}\n\n"
            "Нажмите кнопку ниже для оплаты:"
        )

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment.payment_url)],
                [InlineKeyboardButton(text="↩️ Назад", callback_data="purchase_start")],
            ]
        )

        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=keyboard,
        )

    except NotImplementedError:
        # Payment provider not configured
        text = (
            "<b>⚠️ Оплата недоступна</b>\n\n"
            "Платежная система временно не настроена.\n"
            "Обратитесь в поддержку."
        )
        from app.bot.keyboards.inline import support_keyboard
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
    except Exception as e:
        logger.error(f"Failed to create payment: {e}", exc_info=True)
        text = (
            "<b>❌ Ошибка создания платежа</b>\n\n"
            "Произошла ошибка при создании платежа.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        from app.bot.keyboards.inline import support_keyboard
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )


@router.callback_query(F.data == "my_keys")
async def my_keys(callback: CallbackQuery, db_user=None):
    await callback.answer()
    photo = FSInputFile("1.png")

    if not db_user:
        text = "Ошибка получения данных пользователя."
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
            "<b>Мои ключи</b>\n\n"
            "У вас пока нет активных подписок.\n"
            "Приобретите тариф в разделе «Купить доступ»."
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

    lines = ["<b>Ваши активные ключи:</b>\n"]
    for sub in subscriptions:
        lines.append(f"<b>{sub.key_name}</b>")
        if sub.expires_at:
            lines.append(f"   до {format_date(sub.expires_at)}")
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
        f"<b>{sub.key_name}</b>\n\n"
        f"Статус: {'Активна' if sub.status == 'active' else 'Неактивна'}\n"
        f"Действует до: {expiry}\n"
        f"Трафик: {traffic}\n"
        f"Устройства: {sub.devices_connected}/{sub.device_limit}\n\n"
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

    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        sub = result.scalar_one_or_none()

    if not sub:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    # Get available tariffs
    async with async_session_factory() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.is_active == True).order_by(Tariff.sort_order)
        )
        tariffs = result.scalars().all()

    photo = FSInputFile("1.png")

    if not tariffs:
        text = (
            "<b>Продление подписки</b>\n\n"
            "В данный момент нет доступных тарифов для продления.\n"
            "Обратитесь в поддержку."
        )
        from app.bot.keyboards.inline import support_keyboard
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        return

    text = (
        f"<b>Продление подписки</b>\n\n"
        f"Ключ: <code>{sub.key_name}</code>\n\n"
        f"Выберите период продления:"
    )

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
async def extend_confirm(callback: CallbackQuery, db_user=None):
    await callback.answer()

    parts = callback.data.split(":")
    sub_id = int(parts[1])
    tariff_id = int(parts[2])

    if not db_user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return

    photo = FSInputFile("1.png")

    # Create renewal payment
    try:
        from app.services.payment_service import PaymentService, get_payment_provider

        provider = get_payment_provider()
        payment_service = PaymentService(provider)

        # Create renewal payment
        async with async_session_factory() as session:
            result = await session.execute(
                select(Tariff).where(Tariff.id == tariff_id)
            )
            tariff = result.scalar_one_or_none()

        if not tariff:
            await callback.answer("Тариф не найден", show_alert=True)
            return

        payment = await payment_service.create_payment(
            user_id=db_user.id,
            tariff_id=tariff_id,
            promo_code=None,
        )

        # Link payment to subscription for renewal
        async with async_session_factory() as session:
            async with session.begin():
                from app.database.models import Payment
                result = await session.execute(
                    select(Payment).where(Payment.id == payment.id)
                )
                payment_obj = result.scalar_one()
                payment_obj.subscription_id = sub_id
                payment_obj.type = "renewal"

        text = (
            "<b>💳 Продление подписки</b>\n\n"
            f"Период: {tariff.name}\n"
            f"Сумма: {format_price(payment.amount_kopeks)}\n\n"
            "Нажмите кнопку для оплаты:"
        )

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment.payment_url)],
                [InlineKeyboardButton(text="↩️ Назад", callback_data=f"key_detail:{sub_id}")],
            ]
        )

        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=keyboard,
        )

    except NotImplementedError:
        text = (
            "<b>⚠️ Оплата недоступна</b>\n\n"
            "Платежная система временно не настроена.\n"
            "Обратитесь в поддержку."
        )
        from app.bot.keyboards.inline import support_keyboard
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
    except Exception as e:
        logger.error(f"Failed to create renewal payment: {e}", exc_info=True)
        text = (
            "<b>❌ Ошибка создания платежа</b>\n\n"
            "Произошла ошибка при создании платежа.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        from app.bot.keyboards.inline import support_keyboard
        try:
            await callback.message.edit_media(
                media=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo, caption=text, parse_mode="HTML",
                reply_markup=support_keyboard(),
            )
