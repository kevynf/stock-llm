from __future__ import annotations

from .base import SQLiteRepository


class ChatRepository(SQLiteRepository):
    def create_chat(self, chat_id: str, created_at: str, run_id: str | None, stock_code: str | None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO chats(id, created_at, run_id, stock_code) VALUES (?, ?, ?, ?)",
                (chat_id, created_at, run_id, stock_code),
            )

    def get_chat(self, chat_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def list_chat_messages(self, chat_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chat_messages WHERE chat_id=? ORDER BY created_at", (chat_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def add_chat_messages(self, messages: list[tuple[str, str, str, str, str, str]]) -> None:
        with self.connect() as connection:
            connection.executemany(
                "INSERT INTO chat_messages(id, chat_id, role, content, created_at, tool_traces) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                messages,
            )

    def find_latest_chat(self, run_id: str | None = None, stock_code: str | None = None) -> dict | None:
        conditions: list[str] = []
        parameters: list[str] = []
        if run_id is not None:
            conditions.append("run_id=?")
            parameters.append(run_id)
        if stock_code is not None:
            conditions.append("stock_code=?")
            parameters.append(stock_code)
        if not conditions:
            return None
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, created_at, run_id, stock_code FROM chats "
                f"WHERE {' AND '.join(conditions)} ORDER BY created_at DESC, id DESC LIMIT 1",
                parameters,
            ).fetchone()
        return dict(row) if row else None

    def list_chats(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.id, c.created_at, c.run_id, c.stock_code, "
                "COALESCE(MAX(m.created_at), c.created_at) AS updated_at, "
                "COUNT(m.id) AS message_count, "
                "COALESCE((SELECT content FROM chat_messages preview "
                "WHERE preview.chat_id=c.id AND preview.role='user' "
                "ORDER BY preview.created_at, preview.id LIMIT 1), '') AS preview "
                "FROM chats c LEFT JOIN chat_messages m ON m.chat_id=c.id "
                "GROUP BY c.id, c.created_at, c.run_id, c.stock_code "
                "ORDER BY updated_at DESC, c.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_chat(self, chat_id: str) -> bool:
        with self.connect() as connection:
            connection.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
            cursor = connection.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        return cursor.rowcount > 0

    def delete_chats(self, chat_ids: list[str]) -> int:
        placeholders = ",".join("?" for _ in chat_ids)
        with self.connect() as connection:
            connection.execute(
                f"DELETE FROM chat_messages WHERE chat_id IN ({placeholders})",
                chat_ids,
            )
            cursor = connection.execute(
                f"DELETE FROM chats WHERE id IN ({placeholders})",
                chat_ids,
            )
        return cursor.rowcount
