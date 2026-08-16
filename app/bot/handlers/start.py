import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards.inline import main_menu_keyboard, back_keyboard
from app.config.settings import settings
from app.services.user_service import UserService
from app.services.referral_service import ReferralService

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()
referral_service = ReferralService()


@router.message(CommandStart())
async def cmd_start(message: Message, db_user=None):
    photo = FSInputFile("1.png")
    text = (
        "🗡️ <b>Dagger</b>\n\n"
        "Добро пожаловать! Здесь вы можете приобрести надёжный сервис.\n\n"
        "Выберите действие:"
    )
    is_admin = message.from_user.id in settings.admin_ids_list

    if message.text and len(message.text.split()) > 1:
        start_param = message.text.split()[1]
        await referral_service.process_referral_link(start_param, message.from_user.id)

    await message.answer_photo(
        photo=photo,
        caption=text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, db_user=None):
    await callback.answer()
    photo = FSInputFile("1.png")
    text = (
        "🗡️ <b>Dagger</b>\n\n"
        "Главное меню. Выберите действие:"
    )
    is_admin = callback.from_user.id in settings.admin_ids_list
    try:
        await callback.message.edit_media(
            media=FSInputFile("1.png"),
            caption=text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery):
    await callback.answer()
    from app.bot.keyboards.inline import support_keyboard
    photo = FSInputFile("1.png")
    text = (
        "🎓 <b>Поддержка Dagger</b>\n\n"
        "Если у вас возникли вопросы или проблемы, наша поддержка поможет!"
    )
    try:
        await callback.message.edit_media(
            media=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=support_keyboard(),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=support_keyboard(),
        )


@router.callback_query(F.data == "info")
async def info_handler(callback: CallbackQuery):
    await callback.answer()
    from app.bot.keyboards.inline import info_keyboard
    photo = FSInputFile("1.png")
    text = (
        "📖 <b>Информация о Dagger</b>\n\n"
        "Dagger использует протокол <b>VLESS</b> — современный и безопасный "
        "протокол для защищённого соединения.\n\n"
        "✅ Высокая скорость\n"
        "✅ Надёжное шифрование\n"
        "✅ Работа на всех устройствах\n"
        "✅ До 5 устройств одновременно"
    )
    try:
        await callback.message.edit_media(
            media=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=info_keyboard(),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=info_keyboard(),
        )


@router.callback_query(F.data == "referral")
async def referral_handler(callback: CallbackQuery, db_user=None):
    await callback.answer()
    from app.bot.keyboards.inline import referral_keyboard
    photo = FSInputFile("1.png")
    stats = await referral_service.get_referral_stats(callback.from_user.id)
    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Ваша ссылка:\nhttps://t.me/{settings.BOT_USERNAME}?start=ref_{callback.from_user.id}\n\n"
        f"📊 Приглашено друзей: {stats['total_referred']}\n"
        f"💰 Ваша скидка: {db_user.discount_percent if db_user else 0}%"
    )
    try:
        await callback.message.edit_media(
            media=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=referral_keyboard(callback.from_user.id),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=referral_keyboard(callback.from_user.id),
        )
