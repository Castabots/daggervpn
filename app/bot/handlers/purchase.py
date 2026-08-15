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

    photo = FSInputFile("1.png")
    text = (
        f"<b>Подтверждение покупки</b>\n\n"
        f"Тариф: <b>{tariff.name}</b>\n"
        f"Длительность: {tariff.duration_days} дн.\n"
        f"Стоимость: {format_price(tariff.price_kopeks)}\n\n"
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
    await state.clear()

    photo = FSInputFile("1.png")
    text = (
        "<b>Оплата временно недоступна</b>\n\n"
        "Мы скоро подключим платёжную систему.\n"
        "По вопросам оплаты обращайтесь в поддержку."
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
    photo = FSInputFile("1.png")

    text = (
        "<b>Продление подписки</b>\n\n"
        "Оплата временно недоступна.\n"
        "По вопросам продления обращайтесь в поддержку."
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
