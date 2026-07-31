from __future__ import annotations

"""Produktiver Einstiegspunkt für Version 2.2.0.

Wichtig: Zusatzmodule müssen mit Alias importiert werden. Ein normales
``import app.remote_agent_compat`` würde den Namen ``app`` im Modul auf das
Python-Paket umbiegen und damit das FastAPI-Objekt überschreiben.
"""

import app.main as base
from app.v220 import app
from app import remote_agent_compat as _remote_agent_compat  # noqa: F401

VERSION = "2.2.0"
base.VERSION = VERSION
app.version = VERSION
