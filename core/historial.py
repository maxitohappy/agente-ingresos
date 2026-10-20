"""Historial de consultas: hoja compartida en el backend y copia local.

Se guarda la pregunta, la consulta interpretada (JSON) y el resultado resumido; el Excel se
regenera desde la consulta cuando alguien la vuelve a abrir.
"""
from __future__ import annotations

import json

from . import almacen, backend

LOCAL = "historial.json"
MAXIMO_LOCAL = 500


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
    if backend.configurado():
        try:
            backend.post("guardar_historial", {"registro": reg})
            return "compartido"
        except Exception:  # noqa: BLE001
            return "local"
    return "local"


def listar(limite: int = 300) -> tuple[list[dict], str]:
    """Registros más recientes primero y el origen ('compartido' o 'local')."""
    if backend.configurado():
        try:
            filas = backend.get("historial", limite=limite) or []
            return sorted(filas, key=lambda x: str(x.get("fecha", "")), reverse=True), "compartido"
        except Exception:  # noqa: BLE001
            pass
    local = almacen.leer_json(LOCAL, [])
    return sorted(local, key=lambda x: str(x.get("fecha", "")), reverse=True)[:limite], "local"
