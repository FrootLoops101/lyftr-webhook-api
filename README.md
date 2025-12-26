# Lyftr Webhook API

A production-grade FastAPI webhook service for ingesting WhatsApp-like messages with HMAC-SHA256 signature verification, idempotent message handling, and Prometheus metrics.

## Features

- ✅ **HMAC-SHA256 Signature Verification** - Validates all incoming webhook requests
- ✅ **Idempotent Message Ingestion** - Exactly-once semantics via message_id primary key
- ✅ **SQLite Database** - Persistent message storage with structured schema
- ✅ **Pagination & Filtering** - Query messages by sender, timestamp range, or text search
- ✅ **Analytics Endpoint** - Aggregate statistics and per-sender message counts
- ✅ **Health Probes** - Liveness and readiness checks for orchestration
- ✅ **Prometheus Metrics** - HTTP request and webhook-specific metrics
- ✅ **Structured JSON Logs** - One-line-per-request logging for observability
- ✅ **Docker & Docker Compose** - Containerized deployment ready

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (async)
- **Validation**: Pydantic
- **Database**: SQLite
- **Containerization**: Docker + Docker Compose
- **Metrics**: Prometheus text exposition format
- **Logging**: Structured JSON (stdout)

## Quick Start

### Prerequisites

- Docker & Docker Compose installed
- Make installed (optional, for convenience)

### Running the Application

```bash
# Set environment variable
export WEBHOOK_SECRET=your-secret-key-here

# Start the application
make up

# Or without make:
docker-compose up -d
```

The application will be available at `http://localhost:8000`.

### Stopping the Application

```bash
make down
# or
docker-compose down
```

### Viewing Logs

```bash
make logs
# or
docker-compose logs -f webhook-api
```

### Running Tests

```bash
make test
# or
docker-compose exec webhook-api pytest -v /app/tests/
```

## API Endpoints

### 1. POST /webhook

Ingest inbound messages with HMAC-SHA256 signature verification.

**Headers**

```
Content-Type: application/json
X-Signature: hex(HMAC_SHA256(secret=WEBHOOK_SECRET, body))
```

**Request Body**

```json
{
  "message_id": "m1",
  "from": "+919876543210",
  "to": "+14155550100",
  "ts": "2025-01-15T10:00:00Z",
  "text": "Hello world"
}
```

**Field Validation**

- `message_id`: Non-empty string (primary key)
- `from`/`to`: Phone numbers starting with '+' followed by digits only
- `ts`: ISO-8601 UTC timestamp ending with 'Z'
- `text`: Optional, max 4096 characters

**Responses**

- **200 OK**: Message ingested successfully (or duplicate of existing message)
  ```json
  { "status": "ok" }
  ```

- **401 Unauthorized**: Missing or invalid signature
  ```json
  { "detail": "invalid signature" }
  ```

- **422 Unprocessable Entity**: Validation error
  ```json
  {
    "detail": [
      {
        "loc": ["body", "from"],
        "msg": "Phone number must start with '+'",
        "type": "value_error"
      }
    ]
  }
  ```

**Example**

```bash
#!/bin/bash
PAYLOAD='{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello"}'
SECRET="testsecret"
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" -hex | cut -d' ' -f2)

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD"
```

### 2. GET /messages

Retrieve paginated, filterable messages.

**Query Parameters**

- `limit` (default: 50, min: 1, max: 100) - Results per page
- `offset` (default: 0) - Pagination offset
- `from` - Filter by sender phone number (exact match)
- `since` - Filter by timestamp >= since (ISO-8601)
- `q` - Case-insensitive substring search in message text

**Response**

```json
{
  "data": [
    {
      "message_id": "m1",
      "from_msisdn": "+919876543210",
      "to_msisdn": "+14155550100",
      "ts": "2025-01-15T10:00:00Z",
      "text": "Hello world",
      "created_at": "2025-01-15T10:00:05Z"
    }
  ],
  "total": 123,
  "limit": 50,
  "offset": 0
}
```

**Examples**

```bash
# Get first 10 messages
curl http://localhost:8000/messages?limit=10

# Filter by sender
curl "http://localhost:8000/messages?from=%2B919876543210"

# Filter by timestamp
curl "http://localhost:8000/messages?since=2025-01-15T00:00:00Z"

# Search by text
curl "http://localhost:8000/messages?q=hello"

# Combine filters with pagination
curl "http://localhost:8000/messages?from=%2B919876543210&since=2025-01-15T00:00:00Z&limit=20&offset=10"
```

### 3. GET /stats

Retrieve analytics and statistics.

**Response**

```json
{
  "total_messages": 1523,
  "senders_count": 45,
  "messages_per_sender": [
    { "from": "+919876543210", "count": 342 },
    { "from": "+15551234567", "count": 287 },
    { "from": "+447911000000", "count": 156 }
  ],
  "first_message_ts": "2025-01-10T09:00:00Z",
  "last_message_ts": "2025-01-20T18:30:00Z"
}
```

**Rules**

- Returns top 10 senders by message count (descending)
- Timestamps are null if no messages exist
- Total count includes all senders, not just top 10

**Example**

```bash
curl http://localhost:8000/stats
```

### 4. GET /health/live

Liveness probe. Always returns 200 when the app is running.

**Response**

```json
{ "status": "alive" }
```

```bash
curl http://localhost:8000/health/live
```

### 5. GET /health/ready

Readiness probe. Returns 200 only when:
- Database is initialized and accessible
- WEBHOOK_SECRET is configured

Returns 503 Service Unavailable if any requirement fails.

**Response (Ready)**

```json
{ "status": "ready" }
```

**Response (Not Ready)**

```json
{ "detail": "database not ready" }
```

```bash
curl http://localhost:8000/health/ready
```

### 6. GET /metrics

Prometheus metrics exposition format.

**Response**

```
# HELP http_requests_total Total HTTP requests by method, path, and status
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/webhook",status="200"} 42
http_requests_total{method="POST",path="/webhook",status="401"} 2
http_requests_total{method="GET",path="/messages",status="200"} 15

# HELP webhook_requests_total Total webhook requests by result
# TYPE webhook_requests_total counter
webhook_requests_total{result="created"} 40
webhook_requests_total{result="duplicate"} 2
webhook_requests_total{result="invalid_signature"} 2
```

```bash
curl http://localhost:8000/metrics
```

## Design Decisions

### HMAC Signature Verification

- Uses `HMAC-SHA256` with the raw request body for signature computation
- Verifies signature before any request processing to prevent unauthorized message ingestion
- Invalid signatures result in HTTP 401 with no database mutations
- Reduces risk of unauthorized access and replay attacks

### Idempotent Message Ingestion

- Message table uses `message_id` as PRIMARY KEY
- First valid insertion succeeds → message is stored
- Duplicate valid requests return 200 "ok" without re-inserting
- Prevents duplicate messages from retries or network failures
- Ensures exactly-once semantics at the application level

### Pagination Logic

- `limit` parameter: Capped at 100 to prevent large result sets
- `offset` parameter: Allows efficient pagination without cursor state
- `total` field: Reflects the full count ignoring pagination (for UI pagination)
- Ordering: By `ts ASC, message_id ASC` for deterministic results

### /stats Computation

- Aggregates across all messages in the database
- Returns top 10 senders by message count (descending order)
- Timestamps use database MIN/MAX on the `ts` column
- Efficient SQL aggregation without in-memory processing

### Metrics Approach

- Prometheus text exposition format (simple, human-readable)
- In-memory counter storage (no persistence required)
- Tracks HTTP requests by method, path, and status code
- Tracks webhook outcomes: "created", "duplicate", "invalid_signature", "error"
- Suitable for Prometheus scraping and observability tools

### Structured Logging

- JSON format with one line per request (streaming to stdout)
- Mandatory fields: `ts`, `level`, `request_id`, `method`, `path`, `status`, `latency_ms`
- Additional fields for /webhook: `message_id`, `dup`, `result`
- Enables easy parsing, searching, and aggregation in logging systems (ELK, Datadog, etc.)

### Database Schema

```sql
CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  from_msisdn TEXT NOT NULL,
  to_msisdn TEXT NOT NULL,
  ts TEXT NOT NULL,
  text TEXT,
  created_at TEXT NOT NULL
);
```

- `message_id`: Primary key for idempotency
- `from_msisdn`/`to_msisdn`: Phone numbers for filtering
- `ts`: ISO-8601 timestamp for range queries
- `text`: Optional message body (max 4096 chars)
- `created_at`: Server-side insertion timestamp

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WEBHOOK_SECRET` | Yes | — | Secret key for HMAC-SHA256 signature verification |
| `DATABASE_URL` | No | `sqlite:////data/app.db` | SQLite database URL |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `HOST` | No | `0.0.0.0` | Server host |
| `PORT` | No | `8000` | Server port |

## Docker Deployment

### Building the Image

```bash
docker build -t lyftr-webhook-api:latest .
```

### Running with Docker Compose

```bash
export WEBHOOK_SECRET=your-secret-key
docker-compose up -d
```

### Data Persistence

- SQLite database is stored in a named volume: `webhook-data:/data`
- Persists across container restarts
- Clean up with: `docker-compose down -v`

## Testing

The project includes comprehensive pytest test suite:

```bash
# Run all tests
make test

# Run specific test file
docker-compose exec webhook-api pytest -v tests/test_webhook.py

# Run with coverage
docker-compose exec webhook-api pytest --cov=app tests/
```

**Test Coverage**

- `test_webhook.py`: Signature validation, idempotency, validation errors
- `test_messages.py`: Pagination, filtering, ordering
- `test_stats.py`: Aggregation, sender rankings, timestamps

## Error Handling

### Signature Errors

- Missing `X-Signature` header → 401 with "invalid signature"
- Invalid signature value → 401 with "invalid signature"
- No database mutations occur

### Validation Errors

- Malformed phone numbers → 422 Unprocessable Entity
- Invalid timestamp format → 422 Unprocessable Entity
- Empty message_id → 422 Unprocessable Entity
- Text exceeds 4096 chars → 422 Unprocessable Entity

### Database Errors

- DB connection failure → Returns 503 on /health/ready
- Insert failure → 500 Internal Server Error

## Logging Examples

**Successful webhook ingestion**

```json
{"ts":"2025-01-15T10:00:05.123Z","level":"INFO","request_id":"abc-123","method":"POST","path":"/webhook","status":200,"latency_ms":12,"message_id":"m1","dup":false,"result":"created"}
```

**Invalid signature**

```json
{"ts":"2025-01-15T10:00:06.456Z","level":"ERROR","request_id":"def-456","method":"POST","path":"/webhook","status":401,"latency_ms":5}
```

**Message retrieval**

```json
{"ts":"2025-01-15T10:00:07.789Z","level":"INFO","request_id":"ghi-789","method":"GET","path":"/messages","status":200,"latency_ms":8}
```

## Production Considerations

1. **Scaling**: Use multiple app instances behind a load balancer. Ensure database is network-accessible or use shared volume.
2. **Security**: Generate strong `WEBHOOK_SECRET`, rotate regularly, use HTTPS in production.
3. **Monitoring**: Scrape `/metrics` with Prometheus, visualize in Grafana.
4. **Logs**: Aggregate JSON logs with ELK, Datadog, or CloudWatch.
5. **Database**: For high volumes, consider migrating to PostgreSQL.

## AI Usage Disclosure

This project was generated with assistance from Claude AI. The implementation follows best practices for production-grade API design, including:

- Type-safe request/response models with Pydantic
- Structured error handling and HTTP status codes
- Comprehensive test coverage
- Security-focused signature verification
- Observability through metrics and structured logging
- Containerization for reproducible deployments

## License

MIT

## Repository

[github.com/FrootLoops101/lyftr-webhook-api](https://github.com/FrootLoops101/lyftr-webhook-api)
