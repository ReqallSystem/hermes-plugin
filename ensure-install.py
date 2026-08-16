#!/usr/bin/env python3
"""CLI entry: symlink this plugin into every Hermes profile that enabled it."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reqall.install import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
