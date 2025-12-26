# Testing & Validation Guide

This document provides comprehensive testing instructions for validating the Lyftr Webhook API implementation against the specification.

## Quick Start

```bash
# Set the webhook secret
export WEBHOOK_SECRET=testsecret
export DATABASE_URL=sqlite:////data/app.db

# Start the application
make up

# Run tests
make test

# View logs
make logs
```

## Manual Testing with curl + jq

### 1. Health Checks

#### Liveness Probe

```bash
curl -s http://localhost:8000/health/live | jq .
```

Expected: `{"status": "alive"}`

#### Readiness Probe

```bash
curl -s http://localhost:8000/health/ready | jq .
```

Expected: `{"status": "ready"}`

### 2. Webhook Ingestion

#### Valid Message with Signature

```bash
#!/bin/bash
WEBHOOK_SECRET="testsecret"
PAYLOAD='{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello world"}'

# Compute HMAC-SHA256 signature
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | cut -d' ' -f2)

# Send request
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD" | jq .
```

Expected Response (200 OK):
```json
{"status": "ok"}
```

#### Invalid Signature

```bash
PAYLOAD='{"message_id":"m2","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Test"}'

curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: invalid_signature_here" \
  -d "$PAYLOAD" | jq .
```

Expected Response (401 Unauthorized):
```json
{"detail": "invalid signature"}
```

#### Missing Signature

```bash
PAYLOAD='{"message_id":"m3","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Test"}'

curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | jq .
```

Expected Response (401 Unauthorized):
```json
{"detail": "invalid signature"}
```

#### Idempotency Test

```bash
#!/bin/bash
WEBHOOK_SECRET="testsecret"
PAYLOAD='{"message_id":"m4","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Duplicate test"}'
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | cut -d' ' -f2)

# First request
echo "First request:"
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD" | jq .

# Second request (duplicate)
echo "Second request (duplicate):"
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD" | jq .
```

Expected: Both return 200 OK with `{"status": "ok"}`

#### Invalid Phone Number

```bash
WEBHOOK_SECRET="testsecret"
PAYLOAD='{"message_id":"m5","from":"919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Invalid phone"}'
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | cut -d' ' -f2)

curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD" | jq .
```

Expected Response (422 Unprocessable Entity): Validation error about phone number format

#### Invalid Timestamp

```bash
WEBHOOK_SECRET="testsecret"
PAYLOAD='{"message_id":"m6","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00","text":"Invalid timestamp"}'
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | cut -d' ' -f2)

curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD" | jq .
```

Expected Response (422 Unprocessable Entity): Validation error about timestamp format

### 3. Message Retrieval

#### Get All Messages

```bash
curl -s "http://localhost:8000/messages" | jq .
```

Expected Response:
```json
{
  "data": [...],
  "total": <count>,
  "limit": 50,
  "offset": 0
}
```

#### Pagination

```bash
# First page (10 results)
curl -s "http://localhost:8000/messages?limit=10&offset=0" | jq '.data | length'

# Second page
curl -s "http://localhost:8000/messages?limit=10&offset=10" | jq '.data | length'
```

#### Filter by Sender

```bash
curl -s "http://localhost:8000/messages?from=%2B919876543210" | jq '.total'
```

#### Filter by Timestamp

```bash
curl -s "http://localhost:8000/messages?since=2025-01-15T00:00:00Z" | jq '.total'
```

#### Text Search

```bash
curl -s "http://localhost:8000/messages?q=hello" | jq '.data | length'
```

#### Combined Filters

```bash
curl -s "http://localhost:8000/messages?from=%2B919876543210&since=2025-01-15T00:00:00Z&q=test&limit=20&offset=0" | jq .
```

#### Limit Validation

```bash
# Limit > 100 should be capped at 100
curl -s "http://localhost:8000/messages?limit=200" | jq '.limit'
# Expected: 100

# Limit < 1 should be set to 1
curl -s "http://localhost:8000/messages?limit=0" | jq '.limit'
# Expected: 1
```

#### Ordering

```bash
curl -s "http://localhost:8000/messages" | jq '.data | map(.message_id)'
# Should be ordered by ts ASC, then message_id ASC
```

### 4. Analytics

#### Get Statistics

```bash
curl -s http://localhost:8000/stats | jq .
```

Expected Response:
```json
{
  "total_messages": <int>,
  "senders_count": <int>,
  "messages_per_sender": [
    {"from": "+919876543210", "count": 5},
    {"from": "+15551234567", "count": 3}
  ],
  "first_message_ts": "2025-01-10T10:00:00Z",
  "last_message_ts": "2025-01-20T10:00:00Z"
}
```

#### Top 10 Senders

```bash
curl -s http://localhost:8000/stats | jq '.messages_per_sender | length'
# Should be <= 10
```

#### Sorted by Count

```bash
curl -s http://localhost:8000/stats | jq '.messages_per_sender | map(.count)'
# Should be in descending order
```

### 5. Metrics

#### Prometheus Format

```bash
curl -s http://localhost:8000/metrics | head -20
```

Expected Output:
```
# HELP http_requests_total Total HTTP requests by method, path, and status
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/webhook",status="200"} 5
http_requests_total{method="GET",path="/messages",status="200"} 3

# HELP webhook_requests_total Total webhook requests by result
# TYPE webhook_requests_total counter
webhook_requests_total{result="created"} 4
webhook_requests_total{result="duplicate"} 1
webhook_requests_total{result="invalid_signature"} 1
```

### 6. Structured Logging

View logs with JSON formatting:

```bash
make logs
```

Expected format (one JSON object per line):
```json
{"ts":"2025-01-15T10:00:05.123Z","level":"INFO","request_id":"abc-123","method":"POST","path":"/webhook","status":200,"latency_ms":12,"message_id":"m1","dup":false,"result":"created"}
```

## Automated Test Suite

Run the complete test suite:

```bash
make test
```

Tests are organized as follows:

- **test_webhook.py**: Webhook signature validation and idempotency
- **test_messages.py**: Message retrieval, pagination, filtering
- **test_stats.py**: Analytics aggregation

## Specification Checklist

Use this checklist to validate compliance:

### Endpoints
- [ ] `POST /webhook` - 200 on valid signature
- [ ] `POST /webhook` - 401 on invalid/missing signature
- [ ] `POST /webhook` - Idempotent (duplicate returns 200)
- [ ] `GET /messages` - Paginated results with total count
- [ ] `GET /messages?from=X` - Filters by sender
- [ ] `GET /messages?since=X` - Filters by timestamp
- [ ] `GET /messages?q=X` - Text search (case-insensitive)
- [ ] `GET /stats` - Returns aggregate statistics
- [ ] `GET /stats` - Top 10 senders by count
- [ ] `GET /health/live` - Always 200
- [ ] `GET /health/ready` - 200 when ready, 503 when not
- [ ] `GET /metrics` - Prometheus format with required metrics

### Validation
- [ ] Phone numbers must start with '+'
- [ ] Phone numbers must contain only digits after '+'
- [ ] Timestamps must be ISO-8601 with 'Z' suffix
- [ ] Text field max 4096 characters
- [ ] Message_id is non-empty string

### Database
- [ ] Schema created on startup
- [ ] Data persists in `/data/app.db`
- [ ] Message_id is primary key (prevents duplicates)

### Configuration
- [ ] WEBHOOK_SECRET required
- [ ] DATABASE_URL configurable
- [ ] LOG_LEVEL configurable
- [ ] HOST/PORT configurable

### Docker
- [ ] Multi-stage Dockerfile
- [ ] docker-compose.yml works
- [ ] make up/down/logs/test work
- [ ] Health check passes

### Logging
- [ ] JSON format, one per line
- [ ] Includes request_id, method, path, status, latency_ms
- [ ] /webhook logs include message_id, dup, result

### Metrics
- [ ] http_requests_total by method, path, status
- [ ] webhook_requests_total by result
- [ ] Prometheus text exposition format

## Troubleshooting

### Application won't start

```bash
# Check if WEBHOOK_SECRET is set
echo $WEBHOOK_SECRET

# View container logs
docker-compose logs webhook-api

# Check if port 8000 is already in use
lsof -i :8000
```

### Database issues

```bash
# Check if data directory exists
ls -la /data/

# Check database file
sqlite3 /data/app.db "SELECT COUNT(*) FROM messages;"

# Reset database
rm /data/app.db && make up
```

### Tests failing

```bash
# Run with verbose output
docker-compose exec webhook-api pytest -vv tests/

# Run specific test
docker-compose exec webhook-api pytest -vv tests/test_webhook.py::test_webhook_valid_message
```

## Performance Notes

- The application uses SQLite for simplicity
- For high-volume production use, migrate to PostgreSQL
- Metrics are stored in memory (reset on restart)
- Logs are streamed to stdout (use log aggregation in production)
