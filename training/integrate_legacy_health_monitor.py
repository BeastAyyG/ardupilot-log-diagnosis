#!/usr/bin/env python3
"""Compatibility wrapper for companion-health integration script.

The canonical script now lives under `companion_health/scripts/` to keep
companion-health data workflows separate from core diagnosis training.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from companion_health.scripts.integrate_legacy_health_monitor import main


if __name__ == "__main__":
    print("Note: using companion_health/scripts/integrate_legacy_health_monitor.py")
    main()
