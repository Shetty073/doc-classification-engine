"""
Signed Webhook Notification Utility for Document Lifecycle Events.
Sends authenticated HTTP POST events to the banking client callback URL
with HMAC-SHA256 signature verification headers.
"""
import hashlib
import hmac
import json
import logging
from typing import Any, Dict
import httpx
from app.config import settings

logger = logging.getLogger("webhook_service")


async def dispatch_webhook(callback_url: str, payload: Dict[str, Any]) -> bool:
    """
    Delivers document event payload to the client's callback URL.
    Includes X-Signature-SHA256 header computed with application SECRET_KEY.
    """
    if not callback_url:
        return False

    try:
        body_json = json.dumps(payload, default=str)
        signature = hmac.new(
            key=settings.SECRET_KEY.encode("utf-8"),
            msg=body_json.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "IndianBankDocClassifier-Webhook/2.0",
            "X-Signature-SHA256": signature,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(callback_url, content=body_json, headers=headers)
            logger.info(
                "Webhook delivered to %s for document %s (Status: %d)",
                callback_url,
                payload.get("document_id"),
                response.status_code,
            )
            return response.status_code in [200, 201, 202, 204]

    except Exception as exc:
        logger.warning(
            "Webhook delivery failed for URL %s (Doc: %s): %s",
            callback_url,
            payload.get("document_id"),
            exc,
        )
        return False
