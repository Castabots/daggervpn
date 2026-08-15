import json
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards.inline import (
    admin_main_keyboard,
    admin_promos_keyboard,
    admin_referrals_keyboard,
    admin_tariff_detail_keyboard,
    admin_tariffs_keyboard,
    admin_user_detail_keyboard,
    admin_users_list_keyboard,
    back_keyboard,
)
from app.config.settings import settings
from app.database.session import async_session_factory
from app.services.payment_service import PaymentService, YooKassaPaymentProvider
from app.services.promo_service import PromoService
from app.services.referral_service import ReferralService
from app.services.user_service import UserService
from app.utils.formatters import format_price
from sqlalchemy import func
from sqlalchemy.future import select
from app.database.models.admin_action import AdminAction
from app.database.models.payment import Payment
from app.database.models.tariff import Tariff
from app.database.models.user import User

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()
payment_service = PaymentService(YooKassaPaymentProvider())
promo_service = PromoService()
referral_service = ReferralService()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


async def log_admin_action(admin_id: int, action: str, target_user_id: int | None = None, metadata: dict | None = None):
    async with async_session_factory() as session:
        async with session.begin():
            entry = AdminAction(
                admin_id=admin_id,
                action=action,
                target_user_id=target_user_id,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            session.add(entry)


@router.callback_query(F.data == "admin_main")
async def admin_main(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    photo = FSInputFile("1.png")
    text = "⚙️ <b>Панель администратора</b>\n\nВыберите раздел:"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_main_keyboard(),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_main_keyboard(),
        )


# --- USERS ---

@router.callback_query(F.data == "admin_users")
@router.callback_query(F.data.startswith("admin_users_page:"))
async def admin_users(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    offset = 0
    if callback.data.startswith("admin_users_page:"):
        offset = int(callback.data.split(":")[1])

    users, total = await user_service.get_all_users(offset=offset, limit=10)
    photo = FSInputFile("1.png")
    text = f"👥 <b>Пользователи</b> ({total} всего)"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_users_list_keyboard(users, offset, total),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_users_list_keyboard(users, offset, total),
        )


@router.callback_query(F.data.startswith("admin_user:"))
async def admin_user_detail(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await user_service.get_by_telegram_id(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    photo = FSInputFile("1.png")
    status = "🚫 Заблокирован" if user.is_blocked else "✅ Активен"
    text = (
        f"👤 <b>Карточка пользователя</b>\n\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"👤 Имя: {user.first_name or '—'}\n"
        f"@{user.username or 'нет username'}\n"
        f"Статус: {status}\n"
        f"Скидка: {user.discount_percent}%\n"
        f"Реферер: {user.referred_by or 'нет'}\n"
        f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}"
    )
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_user_detail_keyboard(user.telegram_id, user.is_blocked),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_user_detail_keyboard(user.telegram_id, user.is_blocked),
        )


@router.callback_query(F.data.startswith("admin_user_block:"))
async def admin_block_user(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await user_service.block_user(telegram_id)
    await log_admin_action(callback.from_user.id, "block_user", telegram_id)
    await callback.answer(f"Пользователь {telegram_id} заблокирован", show_alert=True)


@router.callback_query(F.data.startswith("admin_user_unblock:"))
async def admin_unblock_user(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await user_service.unblock_user(telegram_id)
    await log_admin_action(callback.from_user.id, "unblock_user", telegram_id)
    await callback.answer(f"Пользователь {telegram_id} разблокирован", show_alert=True)


class AdminMessageState(StatesGroup):
    waiting_for_message = State()


@router.callback_query(F.data.startswith("admin_user_msg:"))
async def admin_message_user_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    telegram_id = int(callback.data.split(":")[1])
    await state.set_state(AdminMessageState.waiting_for_message)
    await state.update_data(target_telegram_id=telegram_id)
    await callback.message.answer(
        f"💬 Отправьте сообщение для пользователя {telegram_id}:",
        reply_markup=back_keyboard("admin_main"),
    )


@router.message(AdminMessageState.waiting_for_message)
async def admin_send_message(message: Message, state: FSMContext):
    fsm_data = await state.get_data()
    target_id = fsm_data.get("target_telegram_id")
    await state.clear()

    if not target_id:
        await message.answer("Ошибка: целевой пользователь не указан.")
        return

    try:
        from aiogram import Bot
        from app.config.settings import settings as s
        bot_instance = message.bot
        await bot_instance.send_message(target_id, f"📨 Сообщение от администрации:\n\n{message.text}")
        await log_admin_action(message.from_user.id, "send_message", target_id, {"text": message.text[:200]})
        await message.answer("✅ Сообщение отправлено!", reply_markup=back_keyboard("admin_main"))
    except Exception as e:
        logger.error(f"Failed to send admin message: {e}")
        await message.answer(f"❌ Не удалось отправить: {e}", reply_markup=back_keyboard("admin_main"))


# --- PAYMENTS ---

@router.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    today_stats = await payment_service.get_today_stats()
    month_stats = await payment_service.get_month_stats()

    photo = FSInputFile("1.png")
    text = (
        f"💰 <b>Статистика платежей</b>\n\n"
        f"📅 Сегодня:\n"
        f"   Платежей: {today_stats['count']}\n"
        f"   Сумма: {format_price(today_stats['total_amount_kopeks'])}\n\n"
        f"📆 Этот месяц:\n"
        f"   Платежей: {month_stats['count']}\n"
        f"   Сумма: {format_price(month_stats['total_amount_kopeks'])}"
    )
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=back_keyboard("admin_main"),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=back_keyboard("admin_main"),
        )


# --- TARIFFS ---

@router.callback_query(F.data == "admin_tariffs")
async def admin_tariffs(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Tariff).order_by(Tariff.sort_order))
        tariffs = result.scalars().all()

    photo = FSInputFile("1.png")
    text = "📋 <b>Управление тарифами</b>"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_tariffs_keyboard(tariffs),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_tariffs_keyboard(tariffs),
        )


@router.callback_query(F.data.startswith("admin_tariff_disable:"))
async def admin_disable_tariff(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    tariff_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
            tariff = result.scalar_one_or_none()
            if tariff:
                tariff.is_active = False
    await log_admin_action(callback.from_user.id, "disable_tariff", metadata={"tariff_id": tariff_id})
    await callback.answer("Тариф деактивирован", show_alert=True)


@router.callback_query(F.data.startswith("admin_tariff_enable:"))
async def admin_enable_tariff(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    tariff_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
            tariff = result.scalar_one_or_none()
            if tariff:
                tariff.is_active = True
    await log_admin_action(callback.from_user.id, "enable_tariff", metadata={"tariff_id": tariff_id})
    await callback.answer("Тариф активирован", show_alert=True)


class TariffCreateState(StatesGroup):
    name = State()
    price = State()
    duration = State()


@router.callback_query(F.data == "admin_tariff_add")
async def admin_tariff_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(TariffCreateState.name)
    await callback.message.answer(
        "Введите название тарифа:",
        reply_markup=back_keyboard("admin_tariffs"),
    )


@router.message(TariffCreateState.name)
async def admin_tariff_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(TariffCreateState.price)
    await message.answer("Введите цену в рублях:")


@router.message(TariffCreateState.price)
async def admin_tariff_price(message: Message, state: FSMContext):
    try:
        price_rub = float(message.text.strip())
        if price_rub < 0:
            await message.answer("Цена не может быть отрицательной.")
            return
        price_kopeks = int(price_rub * 100)
        await state.update_data(price_kopeks=price_kopeks)
        await state.set_state(TariffCreateState.duration)
        await message.answer("Введите длительность в днях:")
    except ValueError:
        await message.answer("Введите корректное число.")


@router.message(TariffCreateState.duration)
async def admin_tariff_duration(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            await message.answer("Длительность должна быть больше 0.")
            return

        data = await state.get_data()
        await state.clear()

        async with async_session_factory() as session:
            async with session.begin():
                count_result = await session.execute(select(func.count()).select_from(Tariff))
                count = count_result.scalar() or 0
                tariff = Tariff(
                    name=data["name"],
                    price_kopeks=data["price_kopeks"],
                    duration_days=days,
                    sort_order=count + 1,
                )
                session.add(tariff)

        await log_admin_action(
            message.from_user.id, "create_tariff",
            metadata={"name": data["name"], "price": data["price_kopeks"], "days": days},
        )
        await message.answer(
            f"✅ Тариф «{data['name']}» создан!",
            reply_markup=back_keyboard("admin_tariffs"),
        )
    except ValueError:
        await message.answer("Введите целое число дней.")


# --- PROMO CODES ---

@router.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    promos = await promo_service.get_all_active()
    photo = FSInputFile("1.png")
    text = "🎁 <b>Управление промокодами</b>"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_promos_keyboard(promos),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_promos_keyboard(promos),
        )


class PromoCreateState(StatesGroup):
    discount_type = State()
    discount_value = State()
    max_uses = State()
    min_amount = State()


@router.callback_query(F.data == "admin_promo_create")
async def admin_promo_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(PromoCreateState.discount_type)
    await callback.message.answer(
        "Тип скидки: percent или fixed?",
        reply_markup=back_keyboard("admin_promos"),
    )


@router.message(PromoCreateState.discount_type)
async def promo_discount_type(message: Message, state: FSMContext):
    dtype = message.text.strip().lower()
    if dtype not in ("percent", "fixed"):
        await message.answer("Введите 'percent' или 'fixed'.")
        return
    await state.update_data(discount_type=dtype)
    await state.set_state(PromoCreateState.discount_value)
    unit = "%" if dtype == "percent" else "₽"
    await message.answer(f"Введите значение скидки ({unit}):")


@router.message(PromoCreateState.discount_value)
async def promo_discount_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.strip())
        if value <= 0:
            await message.answer("Значение должно быть положительным.")
            return
        await state.update_data(discount_value=value)
        await state.set_state(PromoCreateState.max_uses)
        await message.answer("Максимум использований (пусто = безлимит):")
    except ValueError:
        await message.answer("Введите целое число.")


@router.message(PromoCreateState.max_uses)
async def promo_max_uses(message: Message, state: FSMContext):
    max_uses = None
    if message.text.strip():
        try:
            max_uses = int(message.text.strip())
        except ValueError:
            await message.answer("Введите число или оставьте пустым.")
            return

    await state.update_data(max_uses=max_uses)
    await state.set_state(PromoCreateState.min_amount)
    await message.answer("Минимальная сумма заказа в рублях (пусто = 0):")


@router.message(PromoCreateState.min_amount)
async def promo_min_amount(message: Message, state: FSMContext):
    min_amount_kopeks = 0
    if message.text.strip():
        try:
            min_amount_kopeks = int(float(message.text.strip()) * 100)
        except ValueError:
            await message.answer("Введите число или оставьте пустым.")
            return

    data = await state.get_data()
    await state.clear()

    promo = await promo_service.create_promo(
        discount_type=data["discount_type"],
        discount_value=data["discount_value"],
        max_uses=data.get("max_uses"),
        min_amount_kopeks=min_amount_kopeks,
    )

    await log_admin_action(
        message.from_user.id, "create_promo",
        metadata={"code": promo.code, "type": data["discount_type"], "value": data["discount_value"]},
    )
    await message.answer(
        f"✅ Промокод <b>{promo.code}</b> создан!",
        parse_mode="HTML",
        reply_markup=back_keyboard("admin_promos"),
    )


@router.callback_query(F.data.startswith("admin_promo:"))
async def admin_promo_detail(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    promo_id = int(callback.data.split(":")[1])
    stats = await promo_service.get_usage_stats(promo_id)

    photo = FSInputFile("1.png")
    text = (
        f"🎁 <b>Промокод #{promo_id}</b>\n\n"
        f"Использований: {stats['uses_count']}"
    )
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=back_keyboard("admin_promos"),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=back_keyboard("admin_promos"),
        )


# --- REFERRALS ---

@router.callback_query(F.data == "admin_referrals")
async def admin_referrals(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    campaigns = await referral_service.get_all_campaigns()
    photo = FSInputFile("1.png")
    text = "👥 <b>Управление реферальными кампаниями</b>"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_referrals_keyboard(campaigns),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_referrals_keyboard(campaigns),
        )


class CampaignCreateState(StatesGroup):
    code = State()
    blogger_name = State()
    discount = State()


@router.callback_query(F.data == "admin_campaign_create")
async def campaign_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(CampaignCreateState.code)
    await callback.message.answer(
        "Введите код кампании (латиница):",
        reply_markup=back_keyboard("admin_referrals"),
    )


@router.message(CampaignCreateState.code)
async def campaign_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if not code.replace("_", "").replace("-", "").isalnum():
        await message.answer("Код должен содержать только буквы, цифры, _ и -.")
        return
    await state.update_data(code=code)
    await state.set_state(CampaignCreateState.blogger_name)
    await message.answer("Имя блогера:")


@router.message(CampaignCreateState.blogger_name)
async def campaign_blogger_name(message: Message, state: FSMContext):
    await state.update_data(blogger_name=message.text.strip())
    await state.set_state(CampaignCreateState.discount)
    await message.answer("Размер скидки в % (по умолчанию 10):")


@router.message(CampaignCreateState.discount)
async def campaign_discount(message: Message, state: FSMContext):
    try:
        discount = int(message.text.strip()) if message.text.strip() else 10
    except ValueError:
        discount = 10

    data = await state.get_data()
    await state.clear()

    campaign = await referral_service.create_blogger_campaign(
        code=data["code"],
        blogger_name=data["blogger_name"],
        discount_percent=discount,
    )

    await log_admin_action(
        message.from_user.id, "create_campaign",
        metadata={"code": data["code"], "blogger": data["blogger_name"]},
    )
    await message.answer(
        f"✅ Кампания <b>{campaign.blogger_name}</b> ({campaign.code}) создана!",
        parse_mode="HTML",
        reply_markup=back_keyboard("admin_referrals"),
    )


# --- STATISTICS ---

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    async with async_session_factory() as session:
        users_count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        payments_count = (await session.execute(
            select(func.count()).select_from(Payment).where(Payment.status == "paid")
        )).scalar() or 0
        revenue_result = await session.execute(
            select(func.coalesce(func.sum(Payment.amount_kopeks), 0)).where(Payment.status == "paid")
        )
        revenue = revenue_result.scalar() or 0

    photo = FSInputFile("1.png")
    text = (
        f"📊 <b>Общая статистика</b>\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"💰 Оплаченных платежей: {payments_count}\n"
        f"💵 Общая выручка: {format_price(revenue)}"
    )
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=back_keyboard("admin_main"),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=back_keyboard("admin_main"),
        )
