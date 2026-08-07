from __future__ import annotations

import json

from .base import SQLiteRepository


class DiagnosticsRepository(SQLiteRepository):
    def diagnostic_business_data(self) -> dict[str, list[dict]]:
        with self.connect() as connection:
            runs = [json.loads(row["payload"]) for row in connection.execute(
                "SELECT payload FROM selection_runs ORDER BY created_at DESC LIMIT 50"
            ).fetchall()]
            chats = [dict(row) for row in connection.execute(
                "SELECT id, created_at, run_id, stock_code FROM chats ORDER BY created_at DESC LIMIT 100"
            ).fetchall()]
            messages = [dict(row) for row in connection.execute(
                "SELECT id, chat_id, role, content, created_at, tool_traces FROM chat_messages "
                "ORDER BY created_at DESC LIMIT 500"
            ).fetchall()]
        return {"research_snapshots": runs, "chats": chats, "messages": messages}
