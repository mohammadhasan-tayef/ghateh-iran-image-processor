#!/usr/bin/env python3
"""Launch the Windows UI."""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    # Required on Windows when Free tier uses ProcessPoolExecutor
    multiprocessing.freeze_support()
    from ghate_editor.app import main as run_ui

    run_ui()


if __name__ == "__main__":
    main()
