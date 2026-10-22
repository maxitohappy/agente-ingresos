"""Indicadores de la OACI (ICAO Air Transport Monthly Monitor).

El sitio de la OACI bloquea a los servidores de Google y no permite lectura desde el navegador (CORS), así
que el Monitor se descarga desde un PC con scripts/actualizar_oaci.py y se publica en datos/oaci.json.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date

from .datos import RAIZ

ARCHIVO = RAIZ / "datos" / "oaci.json"
URL = "https://www.icao.int/sites/default/files/sustainability/Documents/ICAO-Monthly-Monitor_{}.pdf"
REGIONES_ES = {"Africa": "África", "Asia/Pacific": "Asia/Pacífico", "Europe": "Europa",
               "Latin America/Caribbean": "Latinoamérica/Caribe", "Middle East": "Medio Oriente",
               "North America": "Norteamérica"}
MESES_EN = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                        "September", "October", "November", "December"], start=1)}


def interpretar_monitor(pdf: bytes) -> dict:
    from pypdf import PdfReader

    texto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    regiones, periodo = {}, ""
    region = None
    for linea in texto.splitlines():
        l = linea.strip()
        if l in REGIONES_ES:
            region = l
            continue
        m = re.search(r"(ASK|RPK|FTK)\s*\((total|international) services\) saw a\s*(-?[\d.]+)%\s*(increase|decline)\s+in\s+"
                      r"(\w+) (\d{4})", l)
        if m and region:
            v = float(m.group(3))
            if m.group(4) == "decline" and v > 0:
                v = -v
            clave = f"{m.group(1).lower()}_{'total' if m.group(2) == 'total' else 'internacional'}"
            regiones.setdefault(REGIONES_ES[region], {})[clave] = v / 100
            periodo = f"{m.group(6)}-{MESES_EN.get(m.group(5), 0):02d}"
    return {"periodo": periodo, "regiones": regiones}


def cargar() -> dict | None:
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def candidatos(hoy: date | None = None, meses: int = 6) -> list[str]:
    hoy = hoy or date.today()
    salida = []
    a, m = hoy.year, hoy.month
    for _ in range(meses):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        salida.append(f"{a}{m:02d}")
    return salida


def texto_region(o: dict | None, region: str = "Latinoamérica/Caribe") -> str | None:
    if not o or region not in o.get("regiones", {}):
        return None
    r = o["regiones"][region]
    partes = []
    if "ask_total" in r:
        partes.append(f"capacidad total (ASK) {r['ask_total'] * 100:+.1f}%".replace(".", ","))
    if "ask_internacional" in r:
        partes.append(f"internacional {r['ask_internacional'] * 100:+.1f}%".replace(".", ","))
    if "rpk_total" in r:
        partes.append(f"tráfico (RPK) {r['rpk_total'] * 100:+.1f}%".replace(".", ","))
    a, m = o["periodo"].split("-")
    return f"OACI ({m}/{a}): en {region}, " + ", ".join(partes) + " interanual."
