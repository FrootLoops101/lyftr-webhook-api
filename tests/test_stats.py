"""Tests for GET /stats endpoint."""

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


def test_stats_empty(temp_db):
    """Test stats with empty database."""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_messages"] == 0
    assert data["senders_count"] == 0
    assert data["messages_per_sender"] == []
    assert data["first_message_ts"] is None
    assert data["last_message_ts"] is None


def test_stats_single_message(temp_db):
    """Test stats with single message."""
    insert_test_message("m1", "+919876543210", "2025-01-10T10:00:00Z")

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_messages"] == 1
    assert data["senders_count"] == 1
    assert len(data["messages_per_sender"]) == 1
    assert data["messages_per_sender"][0]["from"] == "+919876543210"
    assert data["messages_per_sender"][0]["count"] == 1
    assert data["first_message_ts"] == "2025-01-10T10:00:00Z"
    assert data["last_message_ts"] == "2025-01-10T10:00:00Z"


def test_stats_multiple_senders(temp_db):
    """Test stats with multiple senders."""
    insert_test_message("m1", "+919876543210", "2025-01-10T10:00:00Z")
    insert_test_message("m2", "+919876543210", "2025-01-11T10:00:00Z")
    insert_test_message("m3", "+15551234567", "2025-01-12T10:00:00Z")
    insert_test_message("m4", "+447911000000", "2025-01-13T10:00:00Z")

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_messages"] == 4
    assert data["senders_count"] == 3

    # Check sorting by count DESC
    senders = data["messages_per_sender"]
    assert senders[0]["count"] >= senders[1]["count"]

    # Verify timestamps
    assert data["first_message_ts"] == "2025-01-10T10:00:00Z"
    assert data["last_message_ts"] == "2025-01-13T10:00:00Z"


def test_stats_top_10_senders(temp_db):
    """Test that only top 10 senders are returned."""
    # Insert 15 messages from 15 different senders
    for i in range(15):
        sender = f"+9198765432{i:02d}"
        insert_test_message(f"m{i}", sender, f"2025-01-{10+i:02d}T10:00:00Z")

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["senders_count"] == 15
    assert len(data["messages_per_sender"]) == 10  # Only top 10
