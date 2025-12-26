"""FastAPI webhook service application."""

import hashlib
import hmac
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from app.config import config
from app.logging_utils import log_error, log_request
from app.metrics import metrics
from app.models import (
    Message,
    MessagesResponse,
    SenderStats,
    StatsResponse,
    WebhookMessage,
    WebhookResponse,
)
from app.storage import get_messages, get_stats, init_db, insert_message, is_db_ready

# Initialize app
app = FastAPI(title="Lyftr Webhook API", version="1.0.0")


@app.on_event("startup")
async def startup() -> None:
    """Initialize database on startup."""
    if not config.validate():
        raise RuntimeError("WEBHOOK_SECRET must be set and non-empty")
    init_db()


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all HTTP requests."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.time()

    response = await call_next(request)

    latency_ms = (time.time() - start_time) * 1000

    # Record metrics
    path = request.url.path
    method = request.method
    status = response.status_code

    metrics.increment_http_request(method, path, status)

    # Log request
    log_request(
        method=method,
        path=path,
        status=status,
        latency_ms=latency_ms,
        request_id=request_id,
    )

    return response


@app.post("/webhook", response_model=WebhookResponse, status_code=200)
async def webhook(
    payload: WebhookMessage,
    request: Request,
    x_signature: Optional[str] = Header(None),
) -> WebhookResponse:
    """
    Ingest WhatsApp-like messages with HMAC-SHA256 signature verification.

    - Validates X-Signature header
    - Prevents duplicate messages via message_id primary key
    - Returns { "status": "ok" } for both new and duplicate valid messages
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Read raw body
    body = await request.body()

    # Verify signature
    if not x_signature:
        metrics.increment_webhook_request("invalid_signature")
        log_error(
            "Missing X-Signature header",
            request_id=request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signature",
        )

    # Compute HMAC
    expected_signature = hmac.new(
        config.WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, x_signature):
        metrics.increment_webhook_request("invalid_signature")
        log_error(
            "Invalid X-Signature",
            request_id=request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signature",
        )

    # Signature valid, attempt insert
    success, is_duplicate = insert_message(
        message_id=payload.message_id,
        from_msisdn=payload.from_msisdn,
        to_msisdn=payload.to_msisdn,
        ts=payload.ts,
        text=payload.text,
    )

    if not success:
        metrics.increment_webhook_request("error")
        log_error(
            "Failed to insert message",
            request_id=request_id,
            message_id=payload.message_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="internal server error",
        )

    # Log success
    result = "duplicate" if is_duplicate else "created"
    metrics.increment_webhook_request(result)

    return WebhookResponse(status="ok")


@app.get("/messages", response_model=MessagesResponse)
async def messages(
    limit: int = 50,
    offset: int = 0,
    from_msisdn: Optional[str] = None,
    since: Optional[str] = None,
    q: Optional[str] = None,
) -> MessagesResponse:
    """
    Retrieve paginated, filterable messages.

    Query Parameters:
    - limit: Number of results (default 50, min 1, max 100)
    - offset: Pagination offset (default 0)
    - from: Filter by sender phone number
    - since: Filter by timestamp >= since (ISO-8601)
    - q: Case-insensitive substring search in text

    Results ordered by ts ASC, message_id ASC.
    """
    # Validate limit
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    # Validate offset
    if offset < 0:
        offset = 0

    # Retrieve from storage
    rows, total = get_messages(
        limit=limit,
        offset=offset,
        from_msisdn=from_msisdn,
        since=since,
        q=q,
    )

    messages_list = [
        Message(
            message_id=row["message_id"],
            from_msisdn=row["from_msisdn"],
            to_msisdn=row["to_msisdn"],
            ts=row["ts"],
            text=row["text"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return MessagesResponse(
        data=messages_list,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """
    Retrieve analytics and statistics.

    Returns:
    - total_messages: Total message count
    - senders_count: Unique sender count
    - messages_per_sender: Top 10 senders by message count
    - first_message_ts: Earliest message timestamp
    - last_message_ts: Latest message timestamp
    """
    stats_data = get_stats()

    senders = [
        SenderStats(from_msisdn=s["from"], count=s["count"])
        for s in stats_data["messages_per_sender"]
    ]

    return StatsResponse(
        total_messages=stats_data["total_messages"],
        senders_count=stats_data["senders_count"],
        messages_per_sender=senders,
        first_message_ts=stats_data["first_message_ts"],
        last_message_ts=stats_data["last_message_ts"],
    )


@app.get("/health/live", status_code=200)
async def health_live() -> dict:
    """
    Liveness probe. Always returns 200 when app is running.
    """
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready() -> dict:
    """
    Readiness probe. Returns 200 only if:
    - Database is initialized
    - Schema is applied
    - WEBHOOK_SECRET is set
    
    Returns 503 otherwise.
    """
    if not config.validate():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WEBHOOK_SECRET not configured",
        )

    if not is_db_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database not ready",
        )

    return {"status": "ready"}


@app.get("/metrics")
async def metrics_endpoint() -> PlainTextResponse:
    """
    Prometheus metrics exposition format.

    Includes:
    - http_requests_total{method, path, status}
    - webhook_requests_total{result}
    """
    return PlainTextResponse(metrics.render_prometheus())
