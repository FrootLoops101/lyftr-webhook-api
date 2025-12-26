"""Pytest configuration and shared fixtures."""

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from app.storage import init_db


@pytest.fixture(autouse=True)
def temp_db():
    """Use temporary database for each test."""
    # Create temp file
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Set env var
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    os.environ["WEBHOOK_SECRET"] = "test-secret-key"

    # Initialize
    init_db()

    yield path

    # Cleanup
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def compute_signature(payload: dict, secret: str) -> str:
    """Compute HMAC-SHA256 signature."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
