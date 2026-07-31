from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 2.2.0."""

import app.main as base
from app.v220 import app

VERSION = "2.2.0"
base.VERSION = VERSION
app.version = VERSION
