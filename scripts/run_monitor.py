#!/usr/bin/env python3
"""Launch jin10_monitor.py with .env loaded safely for launchd."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON_BIN = PROJECT_DIR / ".venv" / "bin" / "python"
APP_FILE = PROJECT_DIR / "jin10_monitor.py"
ENV_FILE = PROJECT_DIR / ".env"


def main() -> None:
    os.chdir(PROJECT_DIR)
    (PROJECT_DIR / "logs").mkdir(parents=True, exist_ok=True)
    load_dotenv(ENV_FILE, override=True)
    os.execv(str(PYTHON_BIN), [str(PYTHON_BIN), str(APP_FILE)])


if __name__ == "__main__":
    main()
