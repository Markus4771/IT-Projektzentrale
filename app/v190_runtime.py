from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 1.9.0."""

import app.main as base
import app.v180_runtime  # lädt alle Funktionen bis einschließlich 1.8.0
import app.v190 as infrastructure
from app.v190 import app

VERSION = "1.9.0"
base.VERSION = VERSION
infrastructure.VERSION = VERSION
app.version = VERSION
