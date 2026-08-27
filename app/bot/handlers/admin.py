import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards.inline import (
    admin_main_keyboard,
    admin_promos_keyboard,
    admin_referrals_keyboard,
    admin_user_detail_keyboard,
    admin_users_list_keyboard,
    admin_keys_list_keyboard,
    admin_key_detail_keyboard,
    back_keyboard,
)
from app.config.settings import settings
from app.database.session import async_session_factory
from app.services.payment_service import PaymentService
from app.services.promo_service import PromoService
from app.services.referral_service import ReferralService
from app.services.subscription_service import SubscriptionService
from app.services.user_service import UserService
from app.utils.formatters import format_price
from sqlalchemy import func
from sqlalchemy.future import select
from app.database.models.admin_action import AdminAction
from app.database.models.payment import Payment
from app.database.models.user import User
from app.database.models.subscription import Subscription

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()
payment_service = PaymentService()
promo_service = PromoService()
referral_service = ReferralService()
subscription_service = SubscriptionService()


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
    code = State()
    discount_value = State()
    max_uses = State()
    min_amount = State()


@router.callback_query(F.data == "admin_promo_create")
async def admin_promo_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(PromoCreateState.code)
    await callback.message.answer(
        "Введите название промокода (латиница/цифры/_/- до 100 символов):",
        reply_markup=back_keyboard("admin_promos"),
    )


@router.message(PromoCreateState.code)
async def promo_code_text(message: Message, state: FSMContext):
    code = message.text.strip() if message.text else ""
    if not code or len(code) > 100 or not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        await message.answer(
            "Некорректное имя. Допустимы только буквы A-Z/a-z, цифры, _ и - (до 100 символов)."
        )
        return
    existing = await promo_service.get_all_active()
    if any(p.code == code for p in existing):
        await message.answer(f"Промокод «{code}» уже существует. Введите другое имя.")
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreateState.discount_value)
    await message.answer("Размер скидки в %:")


@router.message(PromoCreateState.discount_value)
async def promo_discount_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.strip())
        if value <= 0 or value > 100:
            await message.answer("Скидка должна быть от 1 до 100%.")
            return
    except ValueError:
        await message.answer("Введите целое число.")
        return
    await state.update_data(discount_value=value)
    await state.set_state(PromoCreateState.max_uses)
    await message.answer("Максимум использований (пусто = безлимит):")


@router.message(PromoCreateState.max_uses)
async def promo_max_uses(message: Message, state: FSMContext):
    max_uses = None
    if message.text and message.text.strip():
        try:
            max_uses = int(message.text.strip())
            if max_uses <= 0:
                await message.answer("Значение должно быть положительным.")
                return
        except ValueError:
            await message.answer("Введите число или оставьте пустым.")
            return

    await state.update_data(max_uses=max_uses)
    await state.set_state(PromoCreateState.min_amount)
    await message.answer("Минимальная сумма заказа в рублях (пусто = 0):")


@router.message(PromoCreateState.min_amount)
async def promo_min_amount(message: Message, state: FSMContext):
    min_amount_kopeks = 0
    if message.text and message.text.strip():
        try:
            min_amount_kopeks = int(float(message.text.strip()) * 100)
        except ValueError:
            await message.answer("Введите число или оставьте пустым.")
            return

    data = await state.get_data()
    await state.clear()

    try:
        promo = await promo_service.create_promo(
            discount_value=data["discount_value"],
            code=data["code"],
            max_uses=data.get("max_uses"),
            min_amount_kopeks=min_amount_kopeks,
        )
    except ValueError as exc:
        await message.answer(
            str(exc),
            reply_markup=back_keyboard("admin_promos"),
        )
        return

    await log_admin_action(
        message.from_user.id, "create_promo",
        metadata={"code": promo.code, "value": data["discount_value"]},
    )
    await message.answer(
        f"✅ Промокод <b>{promo.code}</b> создан (скидка {data['discount_value']}%)!",
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

    try:
        campaign = await referral_service.create_blogger_campaign(
            code=data["code"],
            blogger_name=data["blogger_name"],
            discount_percent=discount,
        )
    except ValueError as exc:
        await message.answer(
            str(exc),
            reply_markup=back_keyboard("admin_referrals"),
        )
        return

    await log_admin_action(
        message.from_user.id, "create_campaign",
        metadata={"code": data["code"], "blogger": data["blogger_name"]},
    )
    link = f"https://t.me/{settings.BOT_USERNAME}?start=bloger_{campaign.code}"
    await message.answer(
        (
            f"✅ Кампания <b>{campaign.blogger_name}</b> создана!\n\n"
            f"🔗 Ссылка: {link}\n"
            f"🎁 Промокод: <code>{campaign.code}</code> (скидка {discount}%)"
        ),
        parse_mode="HTML",
        reply_markup=back_keyboard("admin_referrals"),
    )


# --- BROADCAST ---

class BroadcastState(StatesGroup):
    waiting_for_message = State()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.answer(
        "Отправьте сообщение для рассылки всем пользователям (/cancel — отмена):",
        reply_markup=back_keyboard("admin_main"),
    )


@router.message(BroadcastState.waiting_for_message)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text and message.text.strip().lower() in ("/cancel", "/stop"):
        await state.clear()
        await message.answer("Рассылка отменена.", reply_markup=back_keyboard("admin_main"))
        return

    await state.clear()
    telegram_ids = await user_service.get_all_active_telegram_ids()
    total = len(telegram_ids)
    delivered = 0
    blocked = 0
    failed = 0

    for tg_id in telegram_ids:
        try:
            await message.bot.copy_message(
                chat_id=tg_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            delivered += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(min(exc.retry_after + 1, 60))
            try:
                await message.bot.copy_message(
                    chat_id=tg_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                delivered += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await log_admin_action(
        message.from_user.id, "broadcast",
        metadata={"delivered": delivered, "blocked": blocked, "failed": failed, "total": total},
    )
    await message.answer(
        (
            f"📣 Рассылка завершена\n\n"
            f"Всего получателей: {total}\n"
            f"Доставлено: {delivered}\n"
            f"Заблокировали бота: {blocked}\n"
            f"Ошибок: {failed}"
        ),
        reply_markup=back_keyboard("admin_main"),
    )


# --- ISSUE KEY ---

class IssueKeyState(StatesGroup):
    waiting_for_user = State()
    waiting_for_duration = State()


@router.callback_query(F.data == "admin_issue_key")
async def admin_issue_key_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(IssueKeyState.waiting_for_user)
    await callback.message.answer(
        "Введите Telegram ID пользователя, которому выдать ключ:",
        reply_markup=back_keyboard("admin_main"),
    )


@router.callback_query(F.data.startswith("admin_issue_key_for:"))
async def admin_issue_key_for_user(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    try:
        tg_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID", show_alert=True)
        return
    await state.update_data(target_telegram_id=tg_id)
    await state.set_state(IssueKeyState.waiting_for_duration)
    await callback.message.answer(
        f"Выдаём ключ пользователю {tg_id}.\nВведите длительность в днях:",
        reply_markup=back_keyboard("admin_main"),
    )


@router.message(IssueKeyState.waiting_for_user)
async def issue_key_user(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("Введите числовой Telegram ID.")
        return
    await state.update_data(target_telegram_id=tg_id)
    await state.set_state(IssueKeyState.waiting_for_duration)
    await message.answer(f"Пользователь: {tg_id}. Введите длительность в днях:")


@router.message(IssueKeyState.waiting_for_duration)
async def issue_key_duration(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_telegram_id")
    await state.clear()

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Введите положительное целое число дней.", reply_markup=back_keyboard("admin_main"))
        return

    try:
        subscription = await subscription_service.issue_key_by_admin(
            bot=message.bot,
            user_telegram_id=target_id,
            duration_days=days,
        )
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=back_keyboard("admin_main"))
        return
    except RuntimeError as exc:
        logger.error("Admin issue key failed: %s", exc)
        await message.answer(f"❌ Ошибка панели: {exc}", reply_markup=back_keyboard("admin_main"))
        return

    await log_admin_action(
        message.from_user.id, "issue_key",
        target_user_id=target_id,
        metadata={"key_name": subscription.key_name, "days": days},
    )
    await message.answer(
        (
            f"✅ Ключ <b>{subscription.key_name}</b> выдан пользователю {target_id} на {days} дн."
        ),
        parse_mode="HTML",
        reply_markup=back_keyboard("admin_main"),
    )


# --- KEYS MANAGEMENT ---

@router.callback_query(F.data == "admin_keys")
@router.callback_query(F.data.startswith("admin_keys_page:"))
async def admin_keys(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    offset = 0
    if callback.data.startswith("admin_keys_page:"):
        offset = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        total_result = await session.execute(select(func.count()).select_from(Subscription))
        total = total_result.scalar() or 0

        result = await session.execute(
            select(Subscription)
            .join(User, Subscription.user_id == User.id)
            .order_by(Subscription.created_at.desc())
            .offset(offset)
            .limit(10)
        )
        subscriptions = result.scalars().all()

    photo = FSInputFile("1.png")
    text = f"🔑 <b>Все ключи</b> ({total} всего)"
    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_keys_list_keyboard(subscriptions, offset, total),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_keys_list_keyboard(subscriptions, offset, total),
        )


@router.callback_query(F.data.startswith("admin_key:"))
async def admin_key_detail(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    try:
        sub_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription, User)
            .join(User, Subscription.user_id == User.id)
            .where(Subscription.id == sub_id)
        )
        row = result.first()

    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    subscription, user = row
    expires_str = subscription.expires_at.strftime('%d.%m.%Y %H:%M') if subscription.expires_at else "—"

    days_left = "—"
    if subscription.expires_at:
        now = datetime.now(timezone.utc)
        expires_at = subscription.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        days_left = (expires_at - now).days

    photo = FSInputFile("1.png")
    text = (
        f"🔑 <b>Ключ #{subscription.id}</b>\n\n"
        f"Имя: <code>{subscription.key_name}</code>\n"
        f"Пользователь: {user.first_name or '—'} (ID: <code>{user.telegram_id}</code>)\n"
        f"Статус: {'🟢 Активен' if subscription.status == 'active' else '🔴 Неактивен'}\n"
        f"Истекает: {expires_str}\n"
        f"Осталось дней: {days_left}\n"
        f"Устройств: {subscription.devices_connected}/{subscription.device_limit}\n"
        f"Трафик: {subscription.traffic_used_bytes // (1024**3)} ГБ"
    )

    if subscription.subscription_url:
        text += f"\n\n🔗 Ссылка: <code>{subscription.subscription_url}</code>"

    try:
        await callback.message.edit_media(
            media=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_key_detail_keyboard(subscription.id, subscription.subscription_url),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo, caption=text, parse_mode="HTML",
            reply_markup=admin_key_detail_keyboard(subscription.id, subscription.subscription_url),
        )


class AddDaysState(StatesGroup):
    waiting_for_days = State()


@router.callback_query(F.data.startswith("admin_key_add_days:"))
async def admin_key_add_days_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    try:
        sub_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID", show_alert=True)
        return

    await state.update_data(subscription_id=sub_id)
    await state.set_state(AddDaysState.waiting_for_days)
    await callback.message.answer(
        "➕ Введите количество дней для добавления к подписке:",
        reply_markup=back_keyboard("admin_keys"),
    )


@router.message(AddDaysState.waiting_for_days)
async def admin_key_add_days_process(message: Message, state: FSMContext):
    data = await state.get_data()
    sub_id = data.get("subscription_id")
    await state.clear()

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Введите положительное целое число дней.", reply_markup=back_keyboard("admin_keys"))
        return

    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(Subscription).where(Subscription.id == sub_id)
            )
            subscription = result.scalar_one_or_none()

            if not subscription:
                await message.answer("❌ Ключ не найден.", reply_markup=back_keyboard("admin_keys"))
                return

            # Add days to expiration date
            if subscription.expires_at:
                subscription.expires_at = subscription.expires_at + timedelta(days=days)
            else:
                subscription.expires_at = datetime.now(timezone.utc) + timedelta(days=days)

            # Update in Remnawave panel
            try:
                from app.services.remnawave_service import RemnawaveService
                remnawave = RemnawaveService()

                if subscription.remnawave_user_uuid:
                    await remnawave.update_user_expiry(
                        user_uuid=subscription.remnawave_user_uuid,
                        expire_at=subscription.expires_at.isoformat()
                    )
            except Exception as e:
                logger.error(f"Failed to update Remnawave expiry: {e}")
                await message.answer(
                    f"⚠️ Дни добавлены в базе, но не удалось обновить панель: {e}",
                    reply_markup=back_keyboard("admin_keys")
                )
                return

    await log_admin_action(
        message.from_user.id, "add_days",
        metadata={"subscription_id": sub_id, "days": days, "key_name": subscription.key_name}
    )

    await message.answer(
        f"✅ К ключу <b>{subscription.key_name}</b> добавлено {days} дн.\n"
        f"Новая дата истечения: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}",
        parse_mode="HTML",
        reply_markup=back_keyboard("admin_keys"),
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
