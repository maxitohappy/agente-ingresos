"""Estadísticas de tráfico aéreo de la Junta de Aeronáutica Civil (JAC).

Dos fuentes:
- Base histórica (BD_Trafico_aereo, Excel 2014 en adelante): se preprocesa con scripts/actualizar_jac.py en
  datos/jac_embarques.csv = pasajeros EMBARCADOS por aeropuerto chileno, mes y tipo (nacional/internacional).
  Son los pasajeros que pagan derecho de embarque, solo en vuelos comerciales informados a la JAC.
- Informe Mensual de Tráfico Aéreo (PDF): se descarga en línea vía backend (el sitio de la JAC rechaza
  conexiones directas) y trae pasajeros mensuales domésticos/internacionales, variaciones y rutas principales.
"""
from __future__ import annotations

import base64
import io
import re
from datetime import datetime, timedelta

import pandas as pd

from . import alias, almacen, backend, red
from .datos import RAIZ, sin_tildes

EMBARQUES = RAIZ / "datos" / "jac_embarques.csv"
CACHE_INFORME = "jac_informe.json"
MESES_ABR = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9,
             "oct": 10, "nov": 11, "dic": 12}

# Nombres de aeropuerto de la JAC -> código de unidad DGAC (los demás se resuelven por alias de ciudad).
AEROPUERTOS = {"SANTIAGO": 5201, "ISLA DE PASCUA": 2301, "CONCEPCION": 2701, "PUERTO MONTT": 3301,
               "LA SERENA": 2201, "COPIAPO": 1601, "BALMACEDA": 3601, "CASTRO (CHILOE)": 3701, "CHILOE": 3701,
               "ANTARTICA CHILENA": 4105, "COYHAIQUE": 3501, "OSORNO": 3201, "VALDIVIA": 3401}


def _numero(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def unidad_de(aeropuerto: str) -> int | None:
    n = sin_tildes(str(aeropuerto)).upper().strip()
    if n in AEROPUERTOS:
        return AEROPUERTOS[n]
    t = n.lower()
    mejor = None
    for cod, (_, als) in alias.UNIDADES.items():
        for a in als:
            if re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", t) and (mejor is None or len(a) > mejor[1]):
                mejor = (cod, len(a))
    return mejor[0] if mejor else None


# --- Base histórica ---------------------------------------------------------------------------

def preparar_embarques(bd: pd.DataFrame) -> pd.DataFrame:
    """BD_Trafico_aereo -> pasajeros embarcados por aeropuerto chileno (origen del tramo)."""
    d = bd[bd["ORIG_1_PAIS"].astype(str).str.upper().str.strip() == "CHILE"].copy()
    d["aeropuerto"] = d["ORIG_1_N"].astype(str).str.strip().str.upper()
    d["tipo"] = d["NAC"].astype(str).str.strip().str.lower()
    g = (d.groupby(["Año", "Mes", "aeropuerto", "tipo"], as_index=False)["PASAJEROS"].sum()
         .rename(columns={"Año": "anio", "Mes": "mes", "PASAJEROS": "pasajeros"}))
    g["unidad_cod"] = g["aeropuerto"].map(unidad_de).astype("Int64")
    return g.sort_values(["anio", "mes", "aeropuerto", "tipo"]).reset_index(drop=True)


_EMBARQUES: list = []


def embarques() -> pd.DataFrame:
    if not _EMBARQUES:
        try:
            _EMBARQUES.append(pd.read_csv(EMBARQUES, sep=";", dtype={"unidad_cod": "Int64"}))
        except (OSError, ValueError):
            return pd.DataFrame(columns=["anio", "mes", "aeropuerto", "tipo", "pasajeros", "unidad_cod"])
    return _EMBARQUES[0]


def embarques_unidades(unidades: list[int], meses: list[int], ambito: str = "todos") -> pd.DataFrame:
    """Pasajeros embarcados por año (meses indicados) para las unidades: tabla anio × pasajeros."""
    e = embarques()
    if e.empty:
        return e
    if unidades:
        e = e[e["unidad_cod"].isin(unidades)]
    if meses:
        e = e[e["mes"].isin(meses)]
    if ambito != "todos":
        e = e[e["tipo"] == ambito]
    return e.groupby("anio", as_index=False)["pasajeros"].sum()


def estacionalidad(unidades: list[int], ambito: str = "todos") -> dict[int, float] | None:
    """Peso de cada mes en el último año completo de la JAC (promedio = 1)."""
    e = embarques()
    if e.empty:
        return None
    if unidades:
        e = e[e["unidad_cod"].isin(unidades)]
    if ambito != "todos":
        e = e[e["tipo"] == ambito]
    completos = [a for a, n in e.groupby("anio")["mes"].nunique().items() if n == 12]
    if not completos:
        return None
    m = e[e["anio"] == max(completos)].groupby("mes")["pasajeros"].sum()
    if m.sum() <= 0 or len(m) < 12:
        return None
    return {int(k): float(v / m.mean()) for k, v in m.items()}


# --- Informe mensual -------------------------------------------------------------------------

def interpretar_informe(pdf: bytes) -> dict:
    from pypdf import PdfReader

    return interpretar_paginas([p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages])


def interpretar_paginas(paginas: list[str]) -> dict:
    texto = "\n".join(paginas)
    titulo = re.search(r"INFORME MENSUAL DE TR[AÁ]FICO A[EÉ]REO EN CHILE\s+([A-ZÁÉÍÓÚ]+ \d{4})", texto)
    patron = re.compile(r"^\s*(ene|feb|mar|abr|may|jun|jul|ago|sept?|oct|nov|dic)-(\d\d)\s+([\d.]+)\s+([\d.]+)\s+"
                        r"([\d.]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)", re.I | re.M)
    serie = []
    for m in patron.finditer(texto):
        fila = {"anio": 2000 + int(m.group(2)), "mes": MESES_ABR[m.group(1).lower()],
                "domestico": _numero(m.group(3)), "internacional": _numero(m.group(4)), "total": _numero(m.group(5)),
                "var_dom": _numero(m.group(6)) / 100, "var_int": _numero(m.group(7)) / 100,
                "var_total": _numero(m.group(8)) / 100}
        if serie and (fila["anio"], fila["mes"]) <= (serie[-1]["anio"], serie[-1]["mes"]):
            break  # empieza la tabla de carga
        serie.append(fila)
    acum = re.search(r"Acum\.\s*(\d{4})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)", texto)
    rutas = []
    for seccion, tipo in ((r"vuelos dom[eé]sticos por ruta", "nacional"), (r"vuelos internacionales por ruta", "internacional")):
        s = re.search(seccion + r".*?\n(.*?)TOTAL", texto, re.S | re.I)
        if not s:
            continue
        for m in re.finditer(r"^\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .]+? - [A-ZÁÉÍÓÚÑ .]+?)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)\s+(-?[\d,]+)",
                             s.group(1), re.M):
            rutas.append({"tipo": tipo, "ruta": re.sub(r"\s+", " ", m.group(1)).strip(),
                          "anterior": _numero(m.group(2)), "actual": _numero(m.group(3)),
                          "variacion": _numero(m.group(4)) / 100, "participacion": _numero(m.group(5)) / 100})
    resumen = []
    for linea in re.split(r"\n\s*\n", paginas[0]):
        l = re.sub(r"\s+", " ", linea).strip(" -")
        l = re.sub(r"([a-zé]) ([a-zé]{2,})", lambda m: m.group(0) if m.group(1) in "aeoy" else m.group(1) + m.group(2), l)
        l = re.sub(r"e l", "el", l)
        digitos = sum(ch.isdigit() for ch in l) / max(len(l), 1)
        if re.search(r"pasajeros|tr[aá]fico|mercado", l, re.I) and len(l) > 60 and digitos < 0.12:
            # Las viñetas del informe vienen unidas con " - ".
            resumen += [x.strip() for x in re.split(r"\s+-\s+(?=[A-ZÁÉÍÓÚ])", l) if x.strip()]
        if len(resumen) >= 4:
            break
    return {"periodo": titulo.group(1).title() if titulo else "", "serie": serie,
            "acumulado": {"anio": int(acum.group(1)), "domestico": _numero(acum.group(2)),
                          "internacional": _numero(acum.group(3)), "total": _numero(acum.group(4)),
                          "var_total": _numero(acum.group(7)) / 100} if acum else None,
            "rutas": rutas, "resumen": resumen}


def vencido() -> bool:
    cache = almacen.leer_json(CACHE_INFORME, {})
    return not cache.get("fecha") or datetime.now() - datetime.fromisoformat(cache["fecha"]) >= timedelta(hours=24)


def informe(forzar: bool = False, descargar: bool = True) -> dict | None:
    """Último informe mensual (caché local de 24 horas). None si no está disponible.

    Con descargar=False nunca espera la descarga del PDF: devuelve lo que haya en caché, aunque esté vencido
    (la actualización se hace en la carga en segundo plano de la app).
    """
    cache = almacen.leer_json(CACHE_INFORME, {})
    if not descargar or (not forzar and not vencido()):
        return cache.get("informe")
    try:
        if backend.configurado():
            d = backend.get("jac_informe")
            pdf, url = base64.b64decode(d["base64"]), d.get("url", "")
        else:
            raise red.ErrorRed("sin backend")
        inf = interpretar_informe(pdf)
        inf["url"] = url
        inf["resumen"] = inf.get("resumen", [])[:3]
        almacen.escribir_json(CACHE_INFORME, {"fecha": datetime.now().isoformat(timespec="seconds"), "informe": inf})
        try:  # se comparte ya procesado para que otros usuarios no esperen la descarga del PDF
            backend.post("guardar_jac", {"informe": inf})
        except Exception:  # noqa: BLE001
            pass
        return inf
    except Exception:  # noqa: BLE001 - se usa la caché anterior, aunque esté vencida
        return cache.get("informe")


def precargar(guardado: dict | None) -> None:
    """Informe ya procesado que entrega el backend al iniciar ({"fecha": ISO, "informe": {...}})."""
    if not guardado or not guardado.get("informe"):
        return
    local = almacen.leer_json(CACHE_INFORME, {})
    fecha = str(guardado.get("fecha", ""))[:19]
    if fecha and fecha > str(local.get("fecha", "")):
        almacen.escribir_json(CACHE_INFORME, {"fecha": fecha, "informe": guardado["informe"]})


def serie_df(inf: dict | None) -> pd.DataFrame:
    if not inf or not inf.get("serie"):
        return pd.DataFrame()
    return pd.DataFrame(inf["serie"])


def ultimo_mes(inf: dict | None) -> dict | None:
    s = (inf or {}).get("serie") or []
    return s[-1] if s else None
