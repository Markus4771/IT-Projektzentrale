from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 2.1.0."""

import app.main as base
from app.v210 import app

VERSION = "2.1.0"
base.VERSION = VERSION
app.version = VERSION
