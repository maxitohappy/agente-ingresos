"""Formato chileno de números (punto de miles, coma decimal)."""
from __future__ import annotations

import math


def numero(v, decimales: int = 0) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return f"{v:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pesos(v, decimales: int = 0) -> str:
    return ("−" if v < 0 else "") + "$" + numero(abs(v), decimales)


def millones(v, decimales: int = 1) -> str:
    """$1.234,5 millones (o miles de millones si corresponde)."""
    signo = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1e12:
        return f"{signo}${numero(a / 1e9, 0)} mil millones"
    if a >= 1e6:
        return f"{signo}${numero(a / 1e6, decimales)} millones"
    return f"{signo}${numero(a, 0)}"


def porcentaje(v, decimales: int = 1, signo: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = f"{v * 100:+.{decimales}f}" if signo else f"{v * 100:.{decimales}f}"
    return s.replace("-", "−").replace(".", ",") + "%"
