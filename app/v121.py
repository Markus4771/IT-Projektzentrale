from __future__ import annotations

"""Version 1.2.1: zentrale Laufzeit-Versionskorrektur.

Das Basismodul stellt gemeinsame Routen wie /health bereit. Damit diese Routen
nicht den historischen Versionswert aus app.main ausgeben, wird die aktive
Release-Version beim Start an einer Stelle auf alle Laufzeitobjekte übertragen.
"""

import app.main as base
from app.v120 import app

VERSION = "1.2.1"

# Gemeinsame Routen und Templates lesen VERSION aus app.main.
base.VERSION = VERSION
# FastAPI/OpenAPI führt zusätzlich eine eigene Versionsangabe.
app.version = VERSION
