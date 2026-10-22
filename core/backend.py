"""Cliente del backend gratuito en Google Apps Script (ver backend/LEEME.md).

El backend guarda la memoria de indicadores en una Google Sheet compartida,
consulta Gemini con la clave guardada en el propio script y lee páginas públicas que el
navegador no puede leer directamente por CORS. Si no está configurado o no responde, la app
sigue funcionando con almacenamiento local.
"""
from __future__ import annotations

import json
import os

from . import red
from .datos import RAIZ

CONFIG = RAIZ / "datos" / "config.json"
_estado = {"caido": False}


def url() -> str:
    if os.environ.get("AGENTE_SIN_BACKEND"):
        return ""
    env = os.environ.get("AGENTE_BACKEND_URL", "").strip()
    if env:
        return env
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("backend_url", "").strip()
    except (OSError, ValueError):
        return ""


def configurado() -> bool:
    return bool(url()) and not _estado["caido"]


def _respuesta(r) -> dict:
    if not isinstance(r, dict) or not r.get("ok"):
        raise red.ErrorRed((r or {}).get("error", "respuesta inválida del backend") if isinstance(r, dict)
                           else "respuesta inválida del backend")
    return r.get("datos")


def get(accion: str, timeout: int = 40, **params):
    if not configurado():
        raise red.ErrorRed("backend no configurado")
    try:
        return _respuesta(red.get_json(url(), {"accion": accion, **params}, timeout=timeout))
    except red.ErrorRed as e:
        if "no se pudo conectar" in str(e).lower():
            _estado["caido"] = True
        raise


def post(accion: str, datos: dict):
    if not configurado():
        raise red.ErrorRed("backend no configurado")
    return _respuesta(red.post_json(url(), {"accion": accion, **datos}, timeout=90))

