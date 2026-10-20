"""Actualiza datos/jac_embarques.csv desde la base histórica de tráfico aéreo de la JAC.

El sitio de la JAC rechaza conexiones directas desde algunos equipos, así que el archivo se descarga a
través del backend (acción "archivo"). También se puede pasar un .xls ya descargado.
Uso: python scripts/actualizar_jac.py [ruta/BD_Trafico_aereo.xls | URL del .xls]
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import backend, jac  # noqa: E402

URL_BD = "https://www.jac.gob.cl/wp-content/uploads/2025/10/BD_Trafico_aereo-2014-2025-1.xls"


def main() -> int:
    origen = sys.argv[1] if len(sys.argv) > 1 else URL_BD
    if origen.startswith("http"):
        print(f"Descargando {origen} vía backend…")
        d = backend.get("archivo", url=origen)
        contenido = io.BytesIO(base64.b64decode(d["base64"]))
    else:
        contenido = origen
    bd = pd.read_excel(contenido)
    emb = jac.preparar_embarques(bd)
    emb.to_csv(jac.EMBARQUES, sep=";", index=False, encoding="utf-8")
    sin = sorted(emb.loc[emb["unidad_cod"].isna(), "aeropuerto"].unique())
    print(f"{len(emb):,} filas ({emb['anio'].min()}-{emb['anio'].max()}) -> {jac.EMBARQUES}")
    if sin:
        print("Aeropuertos sin unidad DGAC asociada:", ", ".join(sin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
