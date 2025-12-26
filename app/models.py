"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class WebhookMessage(BaseModel):
    """Inbound webhook message."""

    message_id: str = Field(..., min_length=1, description="Unique message identifier")
    from_msisdn: str = Field(..., alias="from", description="Sender phone number")
    to_msisdn: str = Field(..., alias="to", description="Recipient phone number")
    ts: str = Field(..., description="ISO-8601 UTC timestamp with Z suffix")
    text: Optional[str] = Field(None, max_length=4096, description="Message body")

    class Config:
        populate_by_name = True

    @field_validator("from_msisdn", "to_msisdn")
    @classmethod
    def validate_msisdn(cls, v: str) -> str:
        """Validate phone numbers: must start with + and contain only digits after."""
        if not v.startswith("+"):
            raise ValueError("Phone number must start with '+'")
        if not v[1:].isdigit():
            raise ValueError("Phone number must contain only digits after '+'")
        return v

    @field_validator("ts")
    @classmethod
    def validate_ts(cls, v: str) -> str:
        """Validate ISO-8601 UTC timestamp with Z suffix."""
        if not v.endswith("Z"):
            raise ValueError("Timestamp must end with 'Z' (UTC)")
        try:
            # Parse and re-format to ensure valid ISO-8601
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid ISO-8601 timestamp format")
        return v


class WebhookResponse(BaseModel):
    """Webhook endpoint response."""

    status: str = Field(default="ok", description="Status of ingestion")


class Message(BaseModel):
    """Message record from database."""

    message_id: str
    from_msisdn: str
    to_msisdn: str
    ts: str
    text: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class MessagesResponse(BaseModel):
    """Paginated messages listing."""

    data: List[Message] = Field(default_factory=list)
    total: int = Field(description="Total count ignoring limit/offset")
    limit: int
    offset: int


class SenderStats(BaseModel):
    """Per-sender statistics."""

    from_msisdn: str = Field(..., alias="from")
    count: int

    class Config:
        populate_by_name = True


class StatsResponse(BaseModel):
    """Analytics response."""

    total_messages: int
    senders_count: int
    messages_per_sender: List[SenderStats]
    first_message_ts: Optional[str] = None
    last_message_ts: Optional[str] = None
