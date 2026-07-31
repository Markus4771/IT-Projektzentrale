from __future__ import annotations

"""Version 3.0.2: Upgrade-, Datenbank- und Dienststart-Stabilisierung."""

import app.main as base
from app.v301 import app

VERSION = "3.0.2"
base.VERSION = VERSION
app.version = VERSION
