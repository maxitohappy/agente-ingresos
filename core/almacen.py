"""Archivos locales de la app (historial y memoria sin backend, caché de indicadores, datos subidos).

En el navegador la carpeta es /mnt/datos (IndexedDB, persiste entre visitas en ese equipo);
en local es data/ dentro del proyecto (ignorada por git).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .datos import RAIZ

CARPETA = Path(os.environ.get("AGENTE_DATA_DIR") or RAIZ / "data")


def ruta(nombre: str) -> Path:
    CARPETA.mkdir(parents=True, exist_ok=True)
    return CARPETA / nombre


def leer_json(nombre: str, defecto):
    p = ruta(nombre)
    if not p.exists():
        return defecto
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir_json(nombre: str, datos) -> None:
    p = ruta(nombre)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)


def borrar(nombre: str) -> None:
    p = ruta(nombre)
    if p.exists():
        p.unlink()
