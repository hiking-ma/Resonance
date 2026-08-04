from store.database import get_connection


def was_notified(event_key: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM notification_log WHERE event_key = ?",
            (event_key,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_notified(event_key: str, channel: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO notification_log (event_key, channel) VALUES (?, ?)",
            (event_key, channel),
        )
        conn.commit()
    finally:
        conn.close()
