"""Serialize writes from local web requests and separate assistant processes."""

import sqlite3
from contextlib import contextmanager

from common import WorkspaceError, project_dir


@contextmanager
def review_lock(slug: str):
    # SQLite's OS-backed write reservation releases automatically if the writer
    # exits. The workspace records themselves remain portable JSON files.
    folder = project_dir(slug) / "work"
    folder.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(folder / "review-lock.sqlite3", timeout=30)
    try:
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            raise WorkspaceError("Another invoice operation is busy. Try again shortly.") from error
        yield
    finally:
        connection.close()
