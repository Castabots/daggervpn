import asyncio
import json
import logging

from aiohttp import web
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


async def webhook_handler(request: web.Request):
    bot: Bot = request.app["bot"]
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400)

    from app.services.payment_service import PaymentService, get_payment_provider

    try:
        payment_service = PaymentService(get_payment_provider())
    except NotImplementedError:
        # No payment provider configured yet; skip payment webhooks
        pass
    else:
        if payload.get("event") == "notification":
            result = await payment_service.process_webhook(payload)
            if result:
                return web.Response(status=200)
            return web.Response(status=400)

    # Forward to aiogram update processing
    from aiogram.types import Update
    update = Update.model_validate(payload, context={"bot": bot})
    await bot.dispatcher.feed_update(bot, update)
    return web.Response(status=200)


async def health_handler(request: web.Request):
    return web.Response(text="OK", status=200)


async def on_startup(app: web.Application):
    bot: Bot = app["bot"]
    dp: Dispatcher = app["dp"]

    webhook_url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook/bot"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")


async def on_shutdown(app: web.Application):
    bot: Bot = app["bot"]
    await bot.session.close()
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> web.Application:
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

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp

    app.router.add_post("/webhook/bot", webhook_handler)
    app.router.add_get("/health", health_handler)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8080)
