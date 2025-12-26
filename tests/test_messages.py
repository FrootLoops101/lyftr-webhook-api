"""Tests for GET /messages endpoint."""

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


def insert_test_message(message_id: str, sender: str, ts: str):
    """Helper to insert test message via webhook."""
    payload = {
        "message_id": message_id,
        "from": sender,
        "to": "+14155550100",
        "ts": ts,
        "text": f"Test message {message_id}",
    }
    signature = compute_signature(payload, "test-secret-key")
    client.post("/webhook", json=payload, headers={"X-Signature": signature})


def test_messages_empty(temp_db):
    """Test messages endpoint with empty database."""
    response = client.get("/messages")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_messages_pagination(temp_db):
    """Test pagination."""
    # Insert 5 messages
    for i in range(5):
        insert_test_message(f"m{i}", "+919876543210", f"2025-01-{10+i:02d}T10:00:00Z")

    # Get first 2
    response = client.get("/messages?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0

    # Get next 2
    response = client.get("/messages?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["total"] == 5


def test_messages_filter_by_sender(temp_db):
    """Test filtering by sender."""
    insert_test_message("m1", "+919876543210", "2025-01-10T10:00:00Z")
    insert_test_message("m2", "+919876543210", "2025-01-11T10:00:00Z")
    insert_test_message("m3", "+15551234567", "2025-01-12T10:00:00Z")

    response = client.get("/messages?from=%2B919876543210")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["data"]) == 2


def test_messages_filter_by_since(temp_db):
    """Test filtering by timestamp."""
    insert_test_message("m1", "+919876543210", "2025-01-10T10:00:00Z")
    insert_test_message("m2", "+919876543210", "2025-01-15T10:00:00Z")
    insert_test_message("m3", "+919876543210", "2025-01-20T10:00:00Z")

    response = client.get("/messages?since=2025-01-15T00:00:00Z")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # m2 and m3


def test_messages_filter_by_text(temp_db):
    """Test text search."""
    payload1 = {
        "message_id": "m1",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-10T10:00:00Z",
        "text": "Hello world",
    }
    signature1 = compute_signature(payload1, "test-secret-key")
    client.post("/webhook", json=payload1, headers={"X-Signature": signature1})

    payload2 = {
        "message_id": "m2",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-11T10:00:00Z",
        "text": "Goodbye world",
    }
    signature2 = compute_signature(payload2, "test-secret-key")
    client.post("/webhook", json=payload2, headers={"X-Signature": signature2})

    response = client.get("/messages?q=Hello")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["message_id"] == "m1"


def test_messages_ordering(temp_db):
    """Test ordering by ts ASC, then message_id ASC."""
    insert_test_message("m2", "+919876543210", "2025-01-10T10:00:00Z")
    insert_test_message("m1", "+919876543210", "2025-01-10T10:00:00Z")
    insert_test_message("m3", "+919876543210", "2025-01-11T10:00:00Z")

    response = client.get("/messages")
    assert response.status_code == 200
    data = response.json()
    ids = [m["message_id"] for m in data["data"]]
    # m1 and m2 have same ts, so ordered by message_id
    assert ids == ["m1", "m2", "m3"]


def test_messages_limit_max(temp_db):
    """Test limit capping at 100."""
    for i in range(10):
        insert_test_message(f"m{i}", "+919876543210", f"2025-01-{10+i:02d}T10:00:00Z")

    response = client.get("/messages?limit=200")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 100  # Should be capped
