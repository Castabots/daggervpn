from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.user_service import UserService


class UserMiddleware(BaseMiddleware):
    def __init__(self):
        self.user_service = UserService()

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = None
        if isinstance(event, Message) and event.from_user:
            user = await self.user_service.get_or_create(
                telegram_id=event.from_user.id,
                username=event.from_user.username,
                first_name=event.from_user.first_name or "",
            )
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = await self.user_service.get_or_create(
                telegram_id=event.from_user.id,
                username=event.from_user.username,
                first_name=event.from_user.first_name or "",
            )

        if user and user.is_blocked:
            if isinstance(event, Message):
                await event.answer("⛔ Ваш аккаунт заблокирован. Обратитесь в поддержку.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Ваш аккаунт заблокирован.", show_alert=True)
            return

        data["db_user"] = user
        return await handler(event, data)
