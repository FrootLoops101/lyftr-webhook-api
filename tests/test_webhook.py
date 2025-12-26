"""Tests for POST /webhook endpoint."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def compute_signature(payload: dict, secret: str) -> str:
    """Compute HMAC-SHA256 signature."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_valid_message(temp_db):
    """Test webhook with valid signature."""
    payload = {
        "message_id": "m1",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello",
    }

    signature = compute_signature(payload, "test-secret-key")

    response = client.post(
        "/webhook",
        json=payload,
        headers={"X-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_missing_signature(temp_db):
    """Test webhook without signature."""
    payload = {
        "message_id": "m2",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello",
    }

    response = client.post("/webhook", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid signature"


def test_webhook_invalid_signature(temp_db):
    """Test webhook with wrong signature."""
    payload = {
        "message_id": "m3",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello",
    }

    response = client.post(
        "/webhook",
        json=payload,
        headers={"X-Signature": "invalid_signature_here"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid signature"


def test_webhook_duplicate_message(temp_db):
    """Test duplicate message is idempotent."""
    payload = {
        "message_id": "m4",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello",
    }

    signature = compute_signature(payload, "test-secret-key")

    # First request
    response1 = client.post(
        "/webhook",
        json=payload,
        headers={"X-Signature": signature},
    )
    assert response1.status_code == 200

    # Second request (duplicate)
    response2 = client.post(
        "/webhook",
        json=payload,
        headers={"X-Signature": signature},
    )
    assert response2.status_code == 200
    assert response2.json() == {"status": "ok"}


def test_webhook_invalid_msisdn(temp_db):
    """Test validation of phone numbers."""
    payload = {
        "message_id": "m5",
        "from": "919876543210",  # Missing +
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello",
    }

    signature = compute_signature(payload, "test-secret-key")

    response = client.post(
        "/webhook",
        json=payload,
        headers={"X-Signature": signature},
    )

    # Pydantic validation should fail (422)
    assert response.status_code == 422


def test_webhook_invalid_timestamp(temp_db):
    """Test validation of timestamp."""
    payload = {
        "message_id": "m6",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00",  # Missing Z
        "text": "Hello",
    }

    signature = compute_signature(payload, "test-secret-key")

    response = client.post(
        "/webhook",
        json=payload,
        headers={"X-Signature": signature},
    )

    assert response.status_code == 422
