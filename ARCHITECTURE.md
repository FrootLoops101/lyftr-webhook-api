# Architecture & Design Documentation

## System Overview

The Lyftr Webhook API is a production-grade service for ingesting WhatsApp-like messages with cryptographic signature verification, idempotent storage, and comprehensive observability.

```
┌─────────────────┐
│  Client         │
│  (External API) │
└────────┬────────┘
         │ HTTP POST /webhook
         │ with X-Signature header
         ▼
┌──────────────────────────────────────┐
│   FastAPI Application (Async)        │
│  ┌────────────────────────────────┐  │
│  │  Request Middleware            │  │
│  │  - Logging (JSON structured)   │  │
│  │  - Metrics collection          │  │
│  │  - Timing                      │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Webhook Endpoint              │  │
│  │  - HMAC-SHA256 verification    │  │
│  │  - Pydantic validation         │  │
│  │  - Signature-first architecture│  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Storage Layer (SQLite)        │  │
│  │  - Idempotent insert (PK)      │  │
│  │  - Query with filtering        │  │
│  │  - Aggregation for stats       │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Metrics & Monitoring          │  │
│  │  - Prometheus counters         │  │
│  │  - /metrics endpoint           │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
         │
         │ SQLite operations
         ▼
┌─────────────────┐
│  SQLite DB      │
│  /data/app.db   │
└─────────────────┘
```

## Module Architecture

### app/config.py

**Purpose**: Centralized configuration management via environment variables.

**Key Responsibilities**:
- Load and validate environment variables
- Provide config singleton to all modules
- Early validation of critical config (WEBHOOK_SECRET)

**Export**: `config` instance

```python
config.WEBHOOK_SECRET       # Required, non-empty
config.DATABASE_URL         # SQLite connection string
config.LOG_LEVEL           # INFO, DEBUG, etc.
```

### app/models.py

**Purpose**: Pydantic models for request/response validation.

**Key Classes**:

- `WebhookMessage`: Inbound message validation
  - Field validators for MSISDN format and timestamp format
  - Alias mapping (`from` → `from_msisdn`)
  
- `WebhookResponse`: Webhook response model
- `Message`: Database record representation
- `MessagesResponse`: Paginated listing response
- `SenderStats`: Per-sender statistics
- `StatsResponse`: Analytics aggregation response

**Validation Rules**:
- Phone numbers: Must start with '+', digits only after
- Timestamps: ISO-8601 UTC with 'Z' suffix
- Text: Optional, max 4096 characters

### app/storage.py

**Purpose**: Direct SQLite database operations.

**Key Functions**:

```python
init_db()                               # Initialize schema
get_db_connection() → Connection        # Get new connection
is_db_ready() → bool                    # Health check

insert_message(...) → (bool, bool)      # Returns (success, is_duplicate)
get_messages(...) → (List[dict], int)   # Returns (rows, total_count)
get_stats() → dict                      # Returns stats aggregation
```

**Database Schema**:

```sql
CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,          -- Idempotency key
  from_msisdn TEXT NOT NULL,            -- Sender phone
  to_msisdn TEXT NOT NULL,              -- Recipient phone
  ts TEXT NOT NULL,                     -- ISO-8601 timestamp
  text TEXT,                            -- Message body (optional)
  created_at TEXT NOT NULL              -- Server insertion time
);
```

**Design Notes**:
- Uses `sqlite3` module directly (not ORM) for simplicity and control
- PRIMARY KEY on `message_id` prevents duplicates at DB level
- All timestamps stored as TEXT (ISO-8601) for consistency

### app/logging_utils.py

**Purpose**: Structured JSON logging infrastructure.

**Key Components**:

- `StructuredJsonFormatter`: Converts log records to JSON
- `setup_logging()`: Initializes logger with JSON formatter
- `log_request()`: Log HTTP request with all context
- `log_error()`: Log error events

**Log Format**:

```json
{
  "ts": "2025-01-15T10:00:05.123Z",
  "level": "INFO",
  "request_id": "uuid",
  "method": "POST",
  "path": "/webhook",
  "status": 200,
  "latency_ms": 12,
  "message_id": "m1",              // Webhook-specific
  "dup": false,                    // Webhook-specific
  "result": "created"              // Webhook-specific
}
```

**Design Notes**:
- One JSON object per line (streaming logs)
- Every request gets a unique `request_id`
- Additional fields added dynamically with `setattr()`

### app/metrics.py

**Purpose**: Prometheus metrics collection and exposition.

**Key Class**: `MetricsCollector`

**Counters**:

```python
metrics.increment_http_request(method, path, status)
metrics.increment_webhook_request(result)  # created|duplicate|invalid_signature|error
```

**Exposition**:

```python
metrics.render_prometheus() → str  # Returns Prometheus text format
```

**Design Notes**:
- In-memory counters (reset on app restart)
- Exposed as `MetricsCollector` singleton instance
- Prometheus format includes HELP and TYPE lines

### app/main.py

**Purpose**: FastAPI application and endpoint implementations.

**Key Endpoints**:

1. `POST /webhook`
   - Signature verification (HMAC-SHA256)
   - Pydantic validation
   - Idempotent insert
   - Returns 200 or 401

2. `GET /messages`
   - Pagination (limit, offset)
   - Filtering (from, since, q)
   - Ordering (ts ASC, message_id ASC)
   - Returns MessagesResponse

3. `GET /stats`
   - Aggregate statistics
   - Top 10 senders
   - First/last message timestamps

4. `GET /health/live`
   - Always 200 (liveness)

5. `GET /health/ready`
   - 200 if ready, 503 if not
   - Checks: DB connectivity, WEBHOOK_SECRET presence

6. `GET /metrics`
   - Prometheus text exposition format

**Middleware**:

```python
@app.middleware("http")
async def logging_middleware(...)
```

- Captures timing information
- Increments metrics
- Logs request/response

**Startup Event**:

```python
@app.on_event("startup")
async def startup()
```

- Validates configuration
- Initializes database schema

**Design Notes**:
- Signature verification happens BEFORE validation
- Invalid signatures return 401 with NO database side effects
- Pydantic automatically handles request validation (422 errors)
- All endpoints are async

## Request Flow: Webhook Ingestion

```
1. Client sends POST /webhook
   ├─ Body: JSON message
   └─ Header: X-Signature (HMAC-SHA256)

2. Logging middleware starts
   └─ Record start time, assign request_id

3. Webhook endpoint receives request
   ├─ Check: X-Signature header present?
   │  └─ NO → 401 (invalid signature)
   ├─ Compute HMAC-SHA256(WEBHOOK_SECRET, body)
   ├─ Check: Signature matches?
   │  └─ NO → 401 (invalid signature)
   ├─ Pydantic validates request body
   │  └─ FAIL → 422 (validation error)
   ├─ insert_message(...)
   │  ├─ Try INSERT into messages
   │  ├─ Duplicate? → (True, True)
   │  └─ Success → (True, False)
   ├─ Record metric (webhook_requests_total)
   └─ Return 200 {"status": "ok"}

4. Logging middleware completes
   ├─ Compute latency
   ├─ Record HTTP metric
   └─ Emit JSON log
```

## Request Flow: Message Retrieval

```
1. Client sends GET /messages?limit=50&offset=0&from=...

2. Logging middleware starts

3. Messages endpoint receives request
   ├─ Parse & validate query parameters
   ├─ get_messages(limit, offset, filters)
   │  ├─ Build WHERE clause from filters
   │  ├─ SELECT COUNT(*) for total
   │  ├─ SELECT * with LIMIT/OFFSET
   │  └─ Return (rows, total_count)
   ├─ Convert rows to Message objects
   └─ Return MessagesResponse

4. Logging middleware completes
   ├─ Record metric
   └─ Emit JSON log
```

## Idempotency Implementation

**Problem**: Network retries or client bugs could cause duplicate message ingestion.

**Solution**: Database-level idempotency via PRIMARY KEY.

```python
def insert_message(...) -> (bool, bool):
    try:
        cursor.execute(
            "INSERT INTO messages (message_id, ...) VALUES (?, ...)",
            (message_id, ...)
        )
        conn.commit()
        return (True, False)  # success, not duplicate
    except sqlite3.IntegrityError:
        # message_id already exists
        return (True, True)   # success (idempotent), is duplicate
```

**Behavior**:
- First valid request → INSERT succeeds → 200 OK
- Duplicate valid request → PRIMARY KEY conflict → 200 OK (no re-insert)
- Invalid signature → NO database access (immediate 401)

## Signature Verification

**Algorithm**: HMAC-SHA256

**Key**: WEBHOOK_SECRET (environment variable)

**Message**: Raw HTTP request body (byte-for-byte)

**Computation**:

```python
import hashlib, hmac

expected = hmac.new(
    WEBHOOK_SECRET.encode(),
    body,  # Raw bytes
    hashlib.sha256
).hexdigest()

valid = hmac.compare_digest(expected, provided)
```

**Design Notes**:
- Uses `hmac.compare_digest()` to prevent timing attacks
- Raw body (not parsed JSON) ensures client/server compute same hash
- Verified BEFORE any other processing

## Filtering & Pagination

**Filtering**:

- `from=+919876543210`: Exact match on `from_msisdn`
- `since=2025-01-15T00:00:00Z`: Range query `ts >= since`
- `q=hello`: LIKE query (case-insensitive) on `text`

**SQL Construction**:

```python
where_clauses = []
if from_msisdn:
    where_clauses.append("from_msisdn = ?")
if since:
    where_clauses.append("ts >= ?")
if q:
    where_clauses.append("text LIKE ?")

where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
```

**Pagination**:

```python
LIMIT ?
 OFFSET ?
```

- `limit`: Capped at 100 (prevent resource exhaustion)
- `offset`: Zero-based, no minimum

**Total Count**:

```python
# Count BEFORE LIMIT/OFFSET
SELECT COUNT(*) FROM messages WHERE {where_clause}
```

**Ordering**:

```python
ORDER BY ts ASC, message_id ASC
```

- Deterministic even for messages with same timestamp
- ASC order supports pagination without cursor state

## Statistics Aggregation

**Queries**:

```sql
-- Total messages
SELECT COUNT(*) FROM messages

-- Unique senders
SELECT COUNT(DISTINCT from_msisdn) FROM messages

-- Top 10 senders
SELECT from_msisdn, COUNT(*) as count
FROM messages
GROUP BY from_msisdn
ORDER BY count DESC
LIMIT 10

-- First and last timestamps
SELECT MIN(ts), MAX(ts) FROM messages WHERE ts IS NOT NULL
```

**Design Notes**:
- All computed server-side (no client aggregation)
- Efficient SQL grouping and aggregation
- NULL handling for empty database

## Health Checks

### Liveness (/health/live)

**Purpose**: K8s liveness probe (Is the container alive?)

**Implementation**: Always returns 200

```python
@app.get("/health/live")
async def health_live():
    return {"status": "alive"}
```

### Readiness (/health/ready)

**Purpose**: K8s readiness probe (Is the app ready to serve requests?)

**Checks**:
1. WEBHOOK_SECRET is set and non-empty
2. Database is accessible and schema is initialized

**Implementation**:

```python
if not config.validate():                    # Check WEBHOOK_SECRET
    raise HTTPException(503, "...")

if not is_db_ready():                       # Check DB
    raise HTTPException(503, "...")
```

## Containerization

### Dockerfile (Multi-stage)

**Stage 1: Builder**
- Uses `python:3.11-slim`
- Installs dependencies from `requirements.txt`
- Creates `/usr/local/lib/python3.11/site-packages`

**Stage 2: Runtime**
- Uses `python:3.11-slim` (small base image)
- Copies dependencies from builder
- Copies application code
- Sets environment variables
- Exposes port 8000
- Runs `uvicorn app.main:app`

**Benefits**:
- Smaller final image (no build tools)
- Faster deployment
- Better security posture

### Docker Compose

**Service**: `webhook-api`
- Builds from `Dockerfile`
- Exposes `8000:8000`
- Mounts volume at `/data` (SQLite persistence)
- Health check: `/health/live` every 30s
- Restart policy: `unless-stopped`

**Volume**: `webhook-data`
- Named volume for database persistence
- Survives container restart

## Error Handling Strategy

### Signature Errors

- **Missing header**: 401 with `"invalid signature"`
- **Invalid signature**: 401 with `"invalid signature"`
- **No DB mutations**: Return immediately

### Validation Errors

- **Pydantic validation**: Automatic 422 response
- **Field errors**: Detailed error messages in response

### Database Errors

- **Connection failure**: 503 on `/health/ready`
- **Insert failure**: 500 on `/webhook`

## Performance Considerations

### Query Optimization

- `message_id` PRIMARY KEY: O(1) duplicate detection
- `from_msisdn`, `ts` indexed (would add in production)
- `ts ASC, message_id ASC` ordering for efficient pagination

### Resource Management

- SQLite suitable for <100k messages
- For production: PostgreSQL with connection pooling
- Metrics stored in memory (acceptable for small deployments)

### Async Design

- All endpoints are `async`
- Uvicorn runs multiple worker threads
- Non-blocking I/O ready

## Security Considerations

### Authentication

- HMAC-SHA256 signature verification
- No username/password needed
- Shared secret in environment variable

### Validation

- Pydantic enforces field types and formats
- Phone number format validation
- Timestamp format validation
- Max length on text field

### Injection Prevention

- Parameterized SQL queries
- No string interpolation
- `LIKE` escaping handled by SQLite

### Timing Attacks

- `hmac.compare_digest()` for constant-time comparison

## Testing Strategy

### Unit Tests

- Isolated test database (temp file)
- Test fixtures for common setup
- Hypothesis: Generate test cases

### Integration Tests

- Full request/response cycle
- TestClient from FastAPI
- Tests all endpoints

### Test Coverage

- Webhook: Signature validation, idempotency, validation
- Messages: Filtering, pagination, ordering
- Stats: Aggregation, rankings, timestamps

## Future Enhancements

1. **Database**: Migrate to PostgreSQL for scale
2. **Indexing**: Add indexes on `from_msisdn`, `ts`
3. **Caching**: Redis for frequent queries
4. **Auth**: API key rotation mechanism
5. **Rate Limiting**: Per-sender or per-IP limits
6. **Message Retention**: TTL policy on old messages
7. **Webhook Retries**: Implement client retry logic
8. **Alerting**: PagerDuty integration for metrics
