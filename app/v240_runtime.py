from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 2.4.0."""

import app.main as base
from app.v240 import app

VERSION = "2.4.0"
base.VERSION = VERSION
app.version = VERSION
