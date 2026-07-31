from __future__ import annotations

"""Kanonisches Versionsmodul für Release 1.6.0."""

import app.main as base
from app.v160_runtime import app

VERSION = "1.6.0"
base.VERSION = VERSION
app.version = VERSION
