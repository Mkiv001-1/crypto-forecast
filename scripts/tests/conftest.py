"""Shared pytest fixtures."""

import os
import sys
import tempfile

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.bootstrap import bootstrap_paths

bootstrap_paths(_PROJECT_ROOT)


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def db_manager(temp_db_path):
    from scripts.core.app_context import init_context, reset_context
    from scripts.core.sqlite_manager import SQLiteManager

    reset_context()
    manager = SQLiteManager(temp_db_path)
    init_context(db_file=temp_db_path)
    yield manager
    reset_context()
