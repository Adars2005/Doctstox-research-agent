import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from config import DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tools TEXT,
                citations TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER,
                local_path TEXT,
                gemini_document_name TEXT,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def parse_json_field(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def serialize_conversation(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["message_count"] = item.get("message_count", 0)
    return item


def serialize_message(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["tools"] = parse_json_field(item.get("tools"), [])
    item["citations"] = parse_json_field(item.get("citations"), [])
    return item


def serialize_file(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("local_path", None)
    return item


def list_conversations() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   COALESCE((
                       SELECT content FROM messages
                       WHERE conversation_id = c.id AND role = 'user'
                       ORDER BY created_at ASC LIMIT 1
                   ), '') AS preview,
                   COALESCE((
                       SELECT COUNT(*) FROM messages WHERE conversation_id = c.id
                   ), 0) AS message_count
            FROM conversations c
            ORDER BY c.updated_at DESC
            """
        ).fetchall()
    return [serialize_conversation(row) for row in rows]


def create_conversation(title: str = "New research") -> dict[str, Any]:
    conversation_id = new_id()
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation_id, title, now, now),
        )
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return serialize_conversation(row)


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return serialize_conversation(row) if row else None


def touch_conversation(conversation_id: str, title: str | None = None) -> None:
    with connect() as conn:
        if title:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, utc_now(), conversation_id),
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (utc_now(), conversation_id),
            )


def delete_conversation(conversation_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
    return cursor.rowcount > 0


def list_messages(conversation_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
    return [serialize_message(row) for row in rows]


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    tools: list[str] | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    message_id = new_id()
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, tools, citations, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                content,
                json.dumps(tools or []),
                json.dumps(citations or []),
                now,
            ),
        )
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    touch_conversation(conversation_id)
    return serialize_message(row)


def add_file(
    conversation_id: str,
    filename: str,
    mime_type: str | None,
    size_bytes: int,
    local_path: str,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    file_id = new_id()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO files (
                id, conversation_id, filename, mime_type, size_bytes,
                local_path, gemini_document_name, status, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                conversation_id,
                filename,
                mime_type,
                size_bytes,
                local_path,
                None,
                status,
                error,
                utc_now(),
            ),
        )
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return serialize_file(row)


def update_file(file_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_file(file_id)
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [file_id]
    with connect() as conn:
        conn.execute(f"UPDATE files SET {assignments} WHERE id = ?", values)
    return get_file(file_id)


def get_file(file_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return serialize_file(row) if row else None


def get_file_raw(file_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return dict(row) if row else None


def list_files(conversation_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM files
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            """,
            (conversation_id,),
        ).fetchall()
    return [serialize_file(row) for row in rows]


def ready_files(conversation_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM files
            WHERE conversation_id = ? AND status = 'ready'
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
    return [serialize_file(row) for row in rows]


def get_setting(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
