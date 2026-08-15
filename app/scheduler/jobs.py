import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


def setup_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    from app.services.notification_service import NotificationService
    from app.services.payment_service import PaymentService, get_payment_provider
    from app.services.subscription_sync_service import SubscriptionSyncService

    notification_service = NotificationService()
    try:
        payment_service = PaymentService(get_payment_provider())
    except NotImplementedError:
        payment_service = None
    sync_service = SubscriptionSyncService()

    async def job_notifications():
        try:
            await notification_service.check_and_send_notifications(bot)
        except Exception as e:
            logger.error(f"Notification job failed: {e}")

    async def job_fulfillment_retry():
        if payment_service is None:
            return
        try:
            await payment_service.retry_unfulfilled_payments()
        except Exception as e:
            logger.error(f"Fulfillment retry job failed: {e}")

    async def job_subscription_sync():
        try:
            await sync_service.sync_all_subscriptions()
        except Exception as e:
            logger.error(f"Subscription sync job failed: {e}")

    scheduler.add_job(job_notifications, "interval", minutes=15, id="notifications")
    scheduler.add_job(job_fulfillment_retry, "interval", minutes=5, id="fulfillment_retry")
    scheduler.add_job(job_subscription_sync, "interval", hours=6, id="subscription_sync")

    return scheduler
