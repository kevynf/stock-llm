from __future__ import annotations

import json
import sqlite3

from .base import SQLiteRepository


class ResearchRunRepository(SQLiteRepository):
    @staticmethod
    def _save_run(
        connection: sqlite3.Connection,
        run_id: str,
        created_at: str,
        payload: dict,
    ) -> None:
        connection.execute(
            "INSERT INTO selection_runs(id, created_at, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET created_at=excluded.created_at, payload=excluded.payload",
            (run_id, created_at, json.dumps(payload, ensure_ascii=False)),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 AS sequence FROM run_events WHERE run_id=?",
            (run_id,),
        ).fetchone()
        connection.execute(
            "INSERT INTO run_events(run_id, sequence, event_type, payload) VALUES (?, ?, ?, ?)",
            (run_id, int(row["sequence"]), event_type, json.dumps(payload, ensure_ascii=False)),
        )

    def save_run(self, run_id: str, created_at: str, payload: dict) -> None:
        with self.connect() as connection:
            self._save_run(connection, run_id, created_at, payload)

    def save_run_and_append_event(
        self,
        run_id: str,
        created_at: str,
        payload: dict,
        event_type: str,
        event_payload: dict,
    ) -> None:
        """Persist a visible run transition and its SSE event in one transaction."""
        with self.connect() as connection:
            self._save_run(connection, run_id, created_at, payload)
            self._append_event(connection, run_id, event_type, event_payload)

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM selection_runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM selection_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE chat_id IN "
                "(SELECT id FROM chats WHERE run_id=?)",
                (run_id,),
            )
            connection.execute("DELETE FROM chats WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            cursor = connection.execute("DELETE FROM selection_runs WHERE id=?", (run_id,))
        return cursor.rowcount > 0

    def delete_runs(self, run_ids: list[str]) -> int:
        placeholders = ",".join("?" for _ in run_ids)
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE chat_id IN "
                f"(SELECT id FROM chats WHERE run_id IN ({placeholders}))",
                run_ids,
            )
            connection.execute(
                f"DELETE FROM chats WHERE run_id IN ({placeholders})",
                run_ids,
            )
            connection.execute(
                f"DELETE FROM run_events WHERE run_id IN ({placeholders})",
                run_ids,
            )
            cursor = connection.execute(
                f"DELETE FROM selection_runs WHERE id IN ({placeholders})",
                run_ids,
            )
        return cursor.rowcount

    def save_events(self, run_id: str, events: list[tuple[str, dict]]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            connection.executemany(
                "INSERT INTO run_events(run_id, sequence, event_type, payload) VALUES (?, ?, ?, ?)",
                [
                    (run_id, index, event_type, json.dumps(payload, ensure_ascii=False))
                    for index, (event_type, payload) in enumerate(events)
                ],
            )

    def get_events(self, run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, payload FROM run_events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [
            {"sequence": row["sequence"], "type": row["event_type"], "payload": json.loads(row["payload"])}
            for row in rows
        ]

    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        with self.connect() as connection:
            self._append_event(connection, run_id, event_type, payload)

    def get_events_after(self, run_id: str, sequence: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, payload FROM run_events "
                "WHERE run_id=? AND sequence>=? ORDER BY sequence",
                (run_id, sequence),
            ).fetchall()
        return [
            {"sequence": row["sequence"], "type": row["event_type"], "payload": json.loads(row["payload"])}
            for row in rows
        ]
