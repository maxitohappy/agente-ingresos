"""Descarga el último ICAO Air Transport Monthly Monitor y actualiza datos/oaci.json.

Debe ejecutarse desde un PC (la OACI bloquea servidores en la nube y lecturas desde el navegador).
Uso: python scripts/actualizar_oaci.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import oaci  # noqa: E402


def main() -> int:
    for edicion in oaci.candidatos():
        url = oaci.URL.format(edicion)
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", ""):
            datos = oaci.interpretar_monitor(r.content)
            datos.update({"edicion": edicion, "url": url, "actualizado": datetime.now().isoformat(timespec="seconds")})
            oaci.ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"Monitor {edicion}: {len(datos['regiones'])} regiones -> {oaci.ARCHIVO}")
            return 0
    print("No se encontró un Monthly Monitor reciente.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
