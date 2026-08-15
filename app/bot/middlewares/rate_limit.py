import time
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, list[float]] = defaultdict(list)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        self._requests[user_id] = [
            t for t in self._requests[user_id] if now - t < self.window_seconds
        ]

        if len(self._requests[user_id]) >= self.max_requests:
            if isinstance(event, Message):
                await event.answer("⚠️ Слишком много запросов. Подождите немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ Слишком много запросов.", show_alert=True)
            return

        self._requests[user_id].append(now)
        return await handler(event, data)
