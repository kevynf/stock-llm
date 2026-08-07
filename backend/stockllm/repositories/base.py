from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager


class SQLiteRepository:
    def connect(self) -> AbstractContextManager[sqlite3.Connection]:
        raise NotImplementedError
