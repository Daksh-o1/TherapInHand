import sqlite3
from contextlib import closing


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_chat_db(db_path):
    with closing(get_connection(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_session_timestamp ON chats (session_id, timestamp)"
        )
        conn.commit()


def save_chat_message(db_path, session_id, user_message, bot_response, timestamp):
    with closing(get_connection(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO chats (session_id, user_message, bot_response, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, user_message, bot_response, timestamp),
        )
        conn.commit()


def fetch_chat_history(db_path, session_id, limit=80):
    with closing(get_connection(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, user_message, bot_response, timestamp
            FROM chats
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
