import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import admin, profile, purchase, start
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.middlewares.user_middleware import UserMiddleware
from app.config.settings import settings
from app.database.session import engine
from app.scheduler.jobs import setup_scheduler

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(start.router)
    dp.include_router(purchase.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Bot started (polling mode)")
    await dp.start_polling(bot)

    scheduler.shutdown(wait=False)
    await bot.session.close()
    await engine.dispose()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
