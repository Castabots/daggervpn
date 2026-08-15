import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards.inline import back_keyboard
from app.database.session import async_session_factory
from app.services.promo_service import PromoService
from app.utils.formatters import format_price
from sqlalchemy.future import select
from app.database.models.subscription import Subscription

router = Router()
logger = logging.getLogger(__name__)
promo_service = PromoService()


class PromoStates(StatesGroup):
    entering_code = State()


@router.callback_query(F.data == "profile")
async def profile_handler(callback: CallbackQuery, db_user=None):
    await callback.answer()
    photo = FSInputFile("1.png")

    if not db_user:
        text = "❌ Ошибка получения профиля."
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
        active_subs = result.scalars().all()

    from app.services.referral_service import ReferralService
    ref_service = ReferralService()
    ref_stats = await ref_service.get_referral_stats(callback.from_user.id)

    text = (
        f"📦 <b>Мой профиль</b>\n\n"
        f"🆔 Telegram ID: <code>{callback.from_user.id}</code>\n"
        f"👤 Имя: {callback.from_user.first_name or '—'}\n"
        f"🔑 Активных ключей: {len(active_subs)}\n"
        f"👥 Приглашено друзей: {ref_stats['total_referred']}\n"
        f"🎁 Скидка: {db_user.discount_percent}%"
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


@router.callback_query(F.data == "promo_enter")
async def promo_enter(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PromoStates.entering_code)

    photo = FSInputFile("1.png")
    text = (
        "🎁 <b>Активация промокода</b>\n\n"
        "Отправьте промокод сообщением.\n"
        "Формат: DAGGER-XXXXX"
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


@router.message(PromoStates.entering_code)
async def promo_code_received(message: Message, state: FSMContext, db_user=None):
    code = message.text.strip().upper()
    await state.update_data(promo_code=code)

    valid, msg, promo = await promo_service.validate_promo(
        code=code,
        user_id=db_user.id if db_user else 0,
        amount_kopeks=0,
    )

    if valid:
        discount_text = ""
        if promo.discount_type == "percent":
            discount_text = f"{promo.discount_value}%"
        else:
            discount_text = format_price(promo.discount_value)

        text = f"✅ Промокод <b>{code}</b> активирован!\nСкидка: {discount_text}"
    else:
        text = f"❌ {msg}"

    await state.set_state(None)
    await message.answer(text, parse_mode="HTML", reply_markup=back_keyboard("main_menu"))
