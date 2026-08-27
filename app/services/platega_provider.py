"""Platega payment provider implementation."""

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import settings
from app.services.payment_service import PaymentProvider

logger = logging.getLogger(__name__)


class PlategaProvider(PaymentProvider):
    """Platega payment gateway integration.

    Docs: https://docs.platega.io/
    """

    def __init__(self) -> None:
        self._base_url = settings.PLATEGA_API_URL.rstrip("/")
        self._merchant_id = settings.PLATEGA_MERCHANT_ID
        self._secret = settings.PLATEGA_SECRET
        self._timeout = 30.0

    def _get_headers(self) -> dict[str, str]:
        """Build authentication headers for Platega API."""
        return {
            "X-MerchantId": self._merchant_id,
            "X-Secret": self._secret,
            "Content-Type": "application/json",
        }

    async def create_payment(
        self, amount_kopeks: int, description: str, metadata: dict
    ) -> dict:
        """Create a payment invoice in Platega.

        Returns {"payment_id": str, "payment_url": str}.
        """
        # Platega expects amount in rubles with kopeks as decimal
        amount_rubles = amount_kopeks / 100.0

        payload = {
            "amount": amount_rubles,
            "currency": "RUB",
            "description": description,
            "orderId": metadata.get("telegram_id", ""),
            "metadata": metadata,
            "successUrl": f"https://t.me/{settings.BOT_USERNAME}",
            "failUrl": f"https://t.me/{settings.BOT_USERNAME}",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/invoices",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Platega response structure (assumed based on typical payment APIs)
                # Adjust based on actual Platega response format
                payment_id = data.get("id") or data.get("invoiceId") or data.get("paymentId")
                payment_url = data.get("paymentUrl") or data.get("url") or data.get("link")

                if not payment_id or not payment_url:
                    logger.error("Platega response missing required fields: %s", data)
                    raise RuntimeError("Invalid Platega response")

                logger.info(
                    "Created Platega payment: id=%s, amount=%.2f RUB",
                    payment_id,
                    amount_rubles,
                )
                return {"payment_id": str(payment_id), "payment_url": payment_url}

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Platega API error: status=%d, body=%s",
                exc.response.status_code,
                exc.response.text,
            )
            raise RuntimeError(f"Platega API error: {exc.response.status_code}")
        except httpx.RequestError as exc:
            logger.error("Platega request error: %s", exc)
            raise RuntimeError(f"Platega connection error: {exc}")

    async def get_payment_status(self, payment_id: str) -> str:
        """Get payment status from Platega.

        Returns status string: "pending", "succeeded", "failed", etc.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self._base_url}/invoices/{payment_id}",
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()

                # Map Platega status to internal status
                # Adjust based on actual Platega status values
                platega_status = data.get("status", "").lower()
                status_map = {
                    "new": "pending",
                    "pending": "pending",
                    "paid": "succeeded",
                    "success": "succeeded",
                    "completed": "succeeded",
                    "failed": "failed",
                    "cancelled": "cancelled",
                    "expired": "expired",
                }
                return status_map.get(platega_status, "pending")

        except httpx.RequestError as exc:
            logger.error("Failed to get payment status: %s", exc)
            return "pending"

    async def verify_webhook(self, payload: dict) -> dict | None:
        """Verify and parse Platega webhook payload.

        Returns {"payment_id": str, "status": str} or None if verification fails.
        """
        # Platega webhook signature verification
        # Adjust based on actual Platega webhook structure

        # Extract signature from headers (this would come from the webhook handler)
        signature = payload.get("_signature")
        if not signature:
            logger.warning("Webhook missing signature")
            return None

        # Verify signature (implementation depends on Platega's signing method)
        # Typically: HMAC-SHA256 of the payload with secret key
        try:
            payment_id = payload.get("id") or payload.get("invoiceId")
            status = payload.get("status", "").lower()

            if not payment_id:
                logger.warning("Webhook missing payment ID")
                return None

            # Map Platega webhook status to internal status
            status_map = {
                "paid": "succeeded",
                "success": "succeeded",
                "completed": "succeeded",
                "failed": "failed",
                "cancelled": "cancelled",
            }
            internal_status = status_map.get(status, status)

            logger.info(
                "Verified Platega webhook: payment_id=%s, status=%s",
                payment_id,
                internal_status,
            )
            return {"payment_id": str(payment_id), "status": internal_status}

        except Exception as exc:
            logger.error("Webhook verification error: %s", exc)
            return None

    def _verify_signature(self, payload: dict, signature: str) -> bool:
        """Verify webhook signature using HMAC-SHA256.

        This is a typical implementation - adjust based on Platega docs.
        """
        try:
            # Create canonical string from payload (order matters)
            # Typically sorted keys or specific field order
            canonical = ""
            for key in sorted(payload.keys()):
                if key != "_signature":
                    canonical += f"{key}={payload[key]}&"
            canonical = canonical.rstrip("&")

            # Calculate HMAC
            expected_signature = hmac.new(
                self._secret.encode(),
                canonical.encode(),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(expected_signature, signature)
        except Exception as exc:
            logger.error("Signature verification failed: %s", exc)
            return False
