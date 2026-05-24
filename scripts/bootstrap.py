"""Single entry-point for Python path setup."""

import os
import sys
from typing import Optional


def get_project_root() -> str:
    """Return repository root (parent of scripts/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bootstrap_paths(project_root: Optional[str] = None) -> str:
    """Add project root and scripts/ to sys.path. Idempotent."""
    root = project_root or get_project_root()
    scripts_dir = os.path.join(root, "scripts")
    for path in (root, scripts_dir):
        if path not in sys.path:
            sys.path.insert(0, path)
    return root
