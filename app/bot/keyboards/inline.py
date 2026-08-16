from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config.settings import settings


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Купить доступ", callback_data="purchase_start")],
        [InlineKeyboardButton(text="📦 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_enter")],
        [InlineKeyboardButton(text="👥 Реферальная программа", callback_data="referral")],
        [InlineKeyboardButton(text="🎓 Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="info")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_keyboard(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data=callback_data)]]
    )


def tariff_list_keyboard(tariffs: list) -> InlineKeyboardMarkup:
    buttons = []
    for tariff in tariffs:
        price = f"{tariff.price_kopeks // 100} ₽"
        if tariff.price_kopeks % 100:
            price = f"{tariff.price_kopeks / 100:.0f} ₽"
        buttons.append(
            [InlineKeyboardButton(
                text=f"{tariff.name} — {price}",
                callback_data=f"tariff_select:{tariff.id}"
            )]
        )
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def tariff_confirm_keyboard(tariff_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Оплатить", callback_data=f"tariff_confirm:{tariff_id}")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="purchase_start")],
        ]
    )


def payment_success_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def keys_list_keyboard(subscriptions: list) -> InlineKeyboardMarkup:
    buttons = []
    for sub in subscriptions:
        status_icon = "🟢" if sub.status == "active" else "🔴"
        buttons.append(
            [InlineKeyboardButton(
                text=f"{status_icon} {sub.key_name}",
                callback_data=f"key_detail:{sub.id}"
            )]
        )
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def key_detail_keyboard(subscription_id: int, subscription_url: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 Скопировать ключ", callback_data=f"key_copy:{subscription_id}")],
        [InlineKeyboardButton(text="⏳ Продлить", callback_data=f"key_extend:{subscription_id}")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="my_keys")],
    ]
    if subscription_url:
        buttons.insert(0, [InlineKeyboardButton(text="🔗 Открыть подписку", url=subscription_url)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def extend_tariff_keyboard(subscription_id: int, tariffs: list) -> InlineKeyboardMarkup:
    buttons = []
    for tariff in tariffs:
        price = f"{tariff.price_kopeks // 100} ₽"
        buttons.append(
            [InlineKeyboardButton(
                text=f"{tariff.name} — {price}",
                callback_data=f"extend_confirm:{subscription_id}:{tariff.id}"
            )]
        )
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"key_detail:{subscription_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать в поддержку", url=settings.SUPPORT_URL)],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
        ]
    )


def info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Политика конфиденциальности", url="https://telegra.ph/Politika-konfidencialnosti-08-15-60")],
            [InlineKeyboardButton(text="📜 Пользовательское соглашение", url="https://telegra.ph/Polzovatelskoe-soglashenie-08-15-20")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
        ]
    )


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
            [InlineKeyboardButton(text="💰 Платежи", callback_data="admin_payments")],
            [InlineKeyboardButton(text="🎁 Промокоды", callback_data="admin_promos")],
            [InlineKeyboardButton(text="👥 Рефералы", callback_data="admin_referrals")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔑 Выдать ключ", callback_data="admin_issue_key")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
        ]
    )


def admin_users_list_keyboard(users: list, offset: int, total: int, limit: int = 10) -> InlineKeyboardMarkup:
    buttons = []
    for user in users:
        status = "🚫" if user.is_blocked else "✅"
        buttons.append(
            [InlineKeyboardButton(
                text=f"{status} {user.username or user.telegram_id}",
                callback_data=f"admin_user:{user.telegram_id}"
            )]
        )
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_page:{offset - limit}"))
    if offset + limit < total:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_page:{offset + limit}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_user_detail_keyboard(telegram_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📊 Подписки", callback_data=f"admin_user_subs:{telegram_id}")],
        [InlineKeyboardButton(text="💬 Написать", callback_data=f"admin_user_msg:{telegram_id}")],
        [InlineKeyboardButton(text="🔑 Выдать ключ", callback_data=f"admin_issue_key_for:{telegram_id}")],
    ]
    if is_blocked:
        buttons.append([InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin_user_unblock:{telegram_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin_user_block:{telegram_id}")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_users")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_promos_keyboard(promos: list) -> InlineKeyboardMarkup:
    buttons = []
    for promo in promos:
        status = "✅" if promo.is_active else "❌"
        buttons.append(
            [InlineKeyboardButton(
                text=f"{status} {promo.code} ({promo.uses_count} исп.)",
                callback_data=f"admin_promo:{promo.id}"
            )]
        )
    buttons.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_promo_create")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_referrals_keyboard(campaigns: list) -> InlineKeyboardMarkup:
    buttons = []
    for campaign in campaigns:
        status = "✅" if campaign.is_active else "❌"
        buttons.append(
            [InlineKeyboardButton(
                text=f"{status} {campaign.blogger_name} ({campaign.code})",
                callback_data=f"admin_campaign:{campaign.id}"
            )]
        )
    buttons.append([InlineKeyboardButton(text="➕ Создать кампанию", callback_data="admin_campaign_create")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def referral_keyboard(user_telegram_id: int) -> InlineKeyboardMarkup:
    bot_username = settings.BOT_USERNAME
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Поделиться ссылкой",
                url=f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{user_telegram_id}"
            )],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
        ]
    )
