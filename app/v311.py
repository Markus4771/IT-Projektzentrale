from __future__ import annotations

"""Version 3.1.1 LTS: Stabilität, Diagnose und Upgrade-Sicherheit."""

import app.main as base
from app.v310 import app

VERSION = "3.1.1"
base.VERSION = VERSION
app.version = VERSION
