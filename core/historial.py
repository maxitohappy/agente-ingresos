"""Historial de consultas: hoja compartida en el backend y copia local.

Se guarda la pregunta, la consulta interpretada (JSON) y el resultado resumido; el Excel se
regenera desde la consulta cuando alguien la vuelve a abrir.
"""
from __future__ import annotations

import json

from . import almacen, backend

LOCAL = "historial.json"
MAXIMO_LOCAL = 500
SEGUNDOS_CACHE = 60
_cache = {"filas": None, "hora": 0.0}


def registro(resp, usuario: str = "") -> dict:
    r = resp.resultado
    return {
        "id": resp.id, "fecha": resp.fecha, "usuario": usuario, "pregunta": resp.pregunta,
        "resumen": resp.resumen().replace("**", ""),
        "impacto": float(r.niveles.iloc[0]["Diferencia"]) if r is not None and r.es_simulacion else None,
        "tc": resp.tc, "consulta": json.dumps(resp.consulta.a_dict(), ensure_ascii=False),
    }


def guardar(resp, usuario: str = "") -> str:
    reg = registro(resp, usuario)
    local = almacen.leer_json(LOCAL, [])
    local = [x for x in local if x.get("id") != reg["id"]] + [reg]
    almacen.escribir_json(LOCAL, local[-MAXIMO_LOCAL:])
    _cache.update(filas=None)
    if backend.configurado():
        try:
            backend.post("guardar_historial", {"registro": reg})
            return "compartido"
        except Exception:  # noqa: BLE001
            return "local"
    return "local"


def borrar(id_: str) -> bool:
    """Elimina un registro del historial (compartido y local). False si falló el borrado compartido."""
    almacen.escribir_json(LOCAL, [x for x in almacen.leer_json(LOCAL, []) if x.get("id") != id_])
    _cache.update(filas=None)
    if backend.configurado():
        try:
            backend.post("borrar_historial", {"id": id_})
        except Exception:  # noqa: BLE001
            return False
    return True


def listar(limite: int = 300, forzar: bool = False) -> tuple[list[dict], str]:
    """Registros más recientes primero y el origen ('compartido' o 'local')."""
    import time

    if backend.configurado():
        if not forzar and _cache["filas"] is not None and time.time() - _cache["hora"] < SEGUNDOS_CACHE:
            return _cache["filas"], "compartido"
        try:
            filas = sorted(backend.get("historial", limite=limite) or [], key=lambda x: str(x.get("fecha", "")),
                           reverse=True)
            _cache.update(filas=filas, hora=time.time())
            return filas, "compartido"
        except Exception:  # noqa: BLE001
            pass
    local = almacen.leer_json(LOCAL, [])
    return sorted(local, key=lambda x: str(x.get("fecha", "")), reverse=True)[:limite], "local"
