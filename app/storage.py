"""Database storage operations."""

import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

from app.config import config


def init_db() -> None:
    """Initialize database schema."""
    db_path = config.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            from_msisdn TEXT NOT NULL,
            to_msisdn TEXT NOT NULL,
            ts TEXT NOT NULL,
            text TEXT,
            created_at TEXT NOT NULL
        )
    """
    )

    conn.commit()
    conn.close()


def get_db_connection() -> sqlite3.Connection:
    """Get database connection."""
    db_path = config.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def is_db_ready() -> bool:
    """Check if database is initialized and accessible."""
    try:
        db_path = config.DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path, timeout=2)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception:
        return False


def insert_message(
    message_id: str,
    from_msisdn: str,
    to_msisdn: str,
    ts: str,
    text: Optional[str],
) -> Tuple[bool, bool]:
    """
    Insert message into database.

    Returns:
        (success: bool, is_duplicate: bool)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        created_at = datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            """
            INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (message_id, from_msisdn, to_msisdn, ts, text, created_at),
        )
        conn.commit()
        conn.close()
        return (True, False)  # success, not duplicate
    except sqlite3.IntegrityError:
        # message_id already exists
        conn.close()
        return (True, True)  # success (idempotent), is duplicate
    except Exception:
        conn.close()
        return (False, False)  # failure


def get_messages(
    limit: int = 50,
    offset: int = 0,
    from_msisdn: Optional[str] = None,
    since: Optional[str] = None,
    q: Optional[str] = None,
) -> Tuple[List[dict], int]:
    """
    Retrieve messages with filtering and pagination.

    Returns:
        (messages: List[dict], total_count: int)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build WHERE clause
    where_clauses = []
    params = []

    if from_msisdn:
        where_clauses.append("from_msisdn = ?")
        params.append(from_msisdn)

    if since:
        where_clauses.append("ts >= ?")
        params.append(since)

    if q:
        where_clauses.append("text LIKE ?")
        params.append(f"%{q}%")

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Get total count
    cursor.execute(f"SELECT COUNT(*) FROM messages WHERE {where_clause}", params)
    total_count = cursor.fetchone()[0]

    # Get paginated results
    query = f"""
        SELECT message_id, from_msisdn, to_msisdn, ts, text, created_at
        FROM messages
        WHERE {where_clause}
        ORDER BY ts ASC, message_id ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    messages = [dict(row) for row in rows]
    return (messages, total_count)


def get_stats() -> dict:
    """
    Get analytics statistics.

    Returns:
        {"total_messages": int, "senders_count": int, "messages_per_sender": [...],
         "first_message_ts": str or None, "last_message_ts": str or None}
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total messages
    cursor.execute("SELECT COUNT(*) FROM messages")
    total_messages = cursor.fetchone()[0]

    # Unique senders
    cursor.execute("SELECT COUNT(DISTINCT from_msisdn) FROM messages")
    senders_count = cursor.fetchone()[0]

    # Messages per sender (top 10)
    cursor.execute(
        """
        SELECT from_msisdn, COUNT(*) as count
        FROM messages
        GROUP BY from_msisdn
        ORDER BY count DESC
        LIMIT 10
    """
    )
    messages_per_sender = [
        {"from": row[0], "count": row[1]} for row in cursor.fetchall()
    ]

    # First and last message timestamps
    cursor.execute(
        "SELECT MIN(ts), MAX(ts) FROM messages WHERE ts IS NOT NULL"
    )
    result = cursor.fetchone()
    first_message_ts = result[0] if result[0] else None
    last_message_ts = result[1] if result[1] else None

    conn.close()

    return {
        "total_messages": total_messages,
        "senders_count": senders_count,
        "messages_per_sender": messages_per_sender,
        "first_message_ts": first_message_ts,
        "last_message_ts": last_message_ts,
    }
