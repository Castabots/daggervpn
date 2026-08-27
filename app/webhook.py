"""Webhook server for payment callbacks."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status

from app.config.settings import settings
from app.services.payment_service import PaymentService, get_payment_provider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for FastAPI."""
    logger.info("Webhook server starting")
    yield
    logger.info("Webhook server shutting down")


app = FastAPI(title="DaggerVPN Webhook Server", lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook/platega")
async def platega_webhook(request: Request):
    """Handle Platega payment webhooks.

    This endpoint receives payment status updates from Platega.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        headers = dict(request.headers)

        # Parse JSON payload
        payload = await request.json()

        # Add signature from headers if present
        if "x-signature" in headers:
            payload["_signature"] = headers["x-signature"]
        elif "signature" in headers:
            payload["_signature"] = headers["signature"]

        logger.info("Received Platega webhook: %s", payload.get("id"))

        # Process webhook
        try:
            provider = get_payment_provider()
            payment_service = PaymentService(provider)
            success = await payment_service.process_webhook(payload)

            if success:
                logger.info("Webhook processed successfully")
                return {"status": "ok"}
            else:
                logger.warning("Webhook processing failed")
                return Response(
                    content='{"status": "error"}',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            logger.error("Webhook processing error: %s", e, exc_info=True)
            return Response(
                content='{"status": "error"}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except Exception as e:
        logger.error("Webhook parsing error: %s", e, exc_info=True)
        return Response(
            content='{"status": "error"}',
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@app.post("/webhook/payment")
async def generic_payment_webhook(request: Request):
    """Generic payment webhook handler.

    Can be used for other payment providers in the future.
    """
    try:
        payload = await request.json()
        provider_name = payload.get("provider", settings.PAYMENT_PROVIDER)

        logger.info("Received payment webhook from provider: %s", provider_name)

        # Route to appropriate handler based on provider
        if provider_name == "platega":
            return await platega_webhook(request)
        else:
            logger.warning("Unknown payment provider: %s", provider_name)
            return Response(
                content='{"status": "unknown_provider"}',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.error("Generic webhook error: %s", e, exc_info=True)
        return Response(
            content='{"status": "error"}',
            status_code=status.HTTP_400_BAD_REQUEST,
        )


if __name__ == "__main__":
    import uvicorn

    # Run webhook server on port 8000
    uvicorn.run(
        "app.webhook:app",
        host="0.0.0.0",
        port=8000,
        log_level=settings.LOG_LEVEL.lower(),
    )
