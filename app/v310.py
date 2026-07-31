from __future__ import annotations

"""Version 3.1.0: Architektur- und Importstabilisierung.

Die Release-Schicht setzt nur noch die öffentliche Version. Die eigentliche
Anwendung wird einmal aus der stabilisierten 3.0.2-Kette übernommen. Der in
2.2.0 vorhandene Namenskonflikt zwischen dem FastAPI-Objekt ``app`` und dem
Python-Paket ``app`` ist in ``v220_runtime`` behoben.
"""

import app.main as base
from app.v302 import app

VERSION = "3.1.0"
base.VERSION = VERSION
app.version = VERSION
