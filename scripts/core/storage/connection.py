"""SQLite connection helpers."""

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional


@contextmanager
def db_connection(db_file: str, *, timeout: int = 30) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(db_file, timeout=timeout)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
