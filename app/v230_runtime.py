from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 2.3.0."""

import app.main as base
from app.v230 import app

VERSION = "2.3.0"
base.VERSION = VERSION
app.version = VERSION
