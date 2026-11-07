# -*- coding: utf-8 -*-
"""Туннель ngrok через библиотеку Python (если ngrok.exe нет)."""
import json
import sys
import time
from pathlib import Path

import ngrok

BASE = Path(__file__).resolve().parent
cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
listener = ngrok.forward(f"127.0.0.1:{cfg.get('port', 8765)}", authtoken=cfg["ngrok_authtoken"],
                         domain=cfg["ngrok_domain"])
print("tunnel up:", listener.url(), flush=True)
while True:
    time.sleep(3600)
