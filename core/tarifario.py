"""Tarifas de derecho de embarque y su vigencia; lectura automática desde la DGAC.

Las tarifas en pesos cambian el día 10 de enero, abril, julio y octubre. Para un mes con cambio
se usa la tarifa promedio ponderada por días (días 1-9 con la tarifa anterior).
"""
from __future__ import annotations

import calendar
import html as html_lib
import json
import re
from datetime import date, datetime

from . import almacen, backend, red
from .datos import RAIZ

BASE = RAIZ / "datos" / "tarifario.json"
LOCAL = "tarifario_local.json"
URL_DGAC = "https://servicios.dgac.gob.cl/dgac_backend/api/v1/public/paginas/tasa-embarque"
PAGINA_DGAC = "https://www.dgac.gob.cl/tarifario/"
TASA_A_CLASE = {21101: "NAC_1C", 21102: "NAC_2C", 21103: "NAC_270", 21201: "INT_MAS500", 21202: "INT_MENOS500"}


def cargar() -> dict:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    extra = almacen.leer_json(LOCAL, {"vigencias": []})
    base["vigencias"] = base["vigencias"] + extra.get("vigencias", [])
    base["ultima_revision"] = extra.get("ultima_revision")
    return base


def clase_de(tasa: int, moneda: str = "P") -> str | None:
    return TASA_A_CLASE.get(int(tasa))


def _vigencias(tar: dict, clase: str) -> list[dict]:
    igual = tar["clases"].get(clase, {}).get("igual_a")
    c = igual or clase
    # Si hay dos registros con la misma fecha, manda el último agregado (actualizaciones locales).
    por_fecha = {}
    for v in tar["vigencias"]:
        if v["clase"] == c:
            por_fecha[v["desde"]] = v
    return [por_fecha[k] for k in sorted(por_fecha)]


def tarifa_en(tar: dict, clase: str, dia: date) -> dict | None:
    vig = None
    for v in _vigencias(tar, clase):
        if date.fromisoformat(v["desde"]) <= dia:
            vig = v
    return vig


def tarifa_mes(tar: dict, clase: str, anio: int, mes: int) -> float | None:
    """Tarifa promedio del mes, ponderada por los días de cada vigencia."""
    dias = calendar.monthrange(anio, mes)[1]
    valores = []
    for d in range(1, dias + 1):
        v = tarifa_en(tar, clase, date(anio, mes, d))
        if v is None:
            return None
        valores.append(float(v["valor"]))
    return sum(valores) / len(valores)


def moneda(tar: dict, clase: str) -> str:
    return tar["clases"][clase]["moneda"]


def vigente_hoy(tar: dict, hoy: date | None = None) -> dict[str, dict]:
    hoy = hoy or date.today()
    return {c: tarifa_en(tar, c, hoy) for c in tar["clases"]}


def tabla(tar: dict):
    import pandas as pd

    filas = [{"Clase": tar["clases"][v["clase"]]["nombre"], "Vigente desde": v["desde"], "Valor": v["valor"],
              "Moneda": tar["clases"][v["clase"]]["moneda"], "Fuente": v.get("fuente", "")}
             for v in tar["vigencias"]]
    return pd.DataFrame(filas).sort_values(["Clase", "Vigente desde"]).reset_index(drop=True)


# --- Lectura desde la DGAC ---------------------------------------------------------------

def _inicio_trimestre(hoy: date) -> date:
    candidatos = [date(hoy.year, m, 10) for m in (1, 4, 7, 10)] + [date(hoy.year - 1, 10, 10)]
    return max(c for c in candidatos if c <= hoy)


def _numero(s: str) -> float:
    return float(s.replace(".", "").replace(" ", "").replace(",", "."))


def interpretar_pagina(texto_html: str) -> dict[str, float]:
    """Extrae las tarifas de embarque del HTML de la página 'Tasa Embarque' de la DGAC."""
    t = html_lib.unescape(re.sub(r"<[^>]+>", " ", texto_html))
    t = re.sub(r"\s+", " ", t)
    patrones = {
        "NAC_1C": r"Primera Categor[ií]a\s*»?\s*\$\s*([\d.\s]{3,9}\d)",
        "NAC_2C": r"Segunda Categor[ií]a\s*»?\s*\$\s*([\d.\s]{3,9}\d)",
        "NAC_270": r"menos de 270 Km\.?\s*»?\s*\$\s*([\d.\s]{3,9}\d)",
        "INT_MAS500": r"m[aá]s de 500 kil[oó]metros[^$]{0,80}?US\$\s*([\d.,]+)",
    }
    salida = {}
    for clase, p in patrones.items():
        m = re.search(p, t, re.I)
        if m:
            try:
                salida[clase] = _numero(m.group(1).strip().rstrip("."))
            except ValueError:
                pass
    return salida


def leer_dgac() -> tuple[dict[str, float], str]:
    """Tarifas publicadas hoy por la DGAC. En el navegador pasa por el backend (CORS)."""
    if red.EN_NAVEGADOR:
        j = backend.get("pagina_dgac", slug="tasa-embarque")
    else:
        j = red.get_json(URL_DGAC)
    html = " ".join(b.get("html", "") for s in j.get("secciones", []) for b in s.get("contenido", {}).get("bloques", [])
                    if isinstance(b, dict))
    if not html:
        html = json.dumps(j, ensure_ascii=False)
    fecha = (j.get("pagina") or {}).get("fechaActualizacion", "")
    return interpretar_pagina(html), fecha


def actualizar_desde_dgac(hoy: date | None = None) -> str:
    """Agrega una vigencia nueva si la DGAC publica valores distintos a los registrados."""
    hoy = hoy or date.today()
    tar = cargar()
    try:
        valores, fecha = leer_dgac()
    except Exception as e:  # noqa: BLE001
        return f"No se pudo leer el tarifario de la DGAC ({e}); se usan las tarifas registradas."
    if not valores:
        return "La página de la DGAC no trajo tarifas reconocibles; se usan las registradas."
    desde = _inicio_trimestre(hoy)
    extra = almacen.leer_json(LOCAL, {"vigencias": []})
    nuevas = []
    for clase, valor in valores.items():
        actual = tarifa_en(tar, clase, hoy)
        if actual is None or abs(float(actual["valor"]) - valor) > 0.001:
            v = {"clase": clase, "desde": desde.isoformat(), "valor": valor,
                 "fuente": f"DGAC, página Tasa Embarque (actualizada {fecha[:10]}), leída {hoy.isoformat()}"}
            extra["vigencias"].append(v)
            nuevas.append(f"{tar['clases'][clase]['nombre']}: {valor:,.0f}".replace(",", "."))
    extra["ultima_revision"] = datetime.now().isoformat(timespec="seconds")
    almacen.escribir_json(LOCAL, extra)
    if nuevas:
        return "Tarifario actualizado desde la DGAC: " + "; ".join(nuevas)
    return "Tarifario al día: los valores publicados por la DGAC coinciden con los registrados."


def agregar_manual(clase: str, desde: str, valor: float, fuente: str) -> None:
    extra = almacen.leer_json(LOCAL, {"vigencias": []})
    extra["vigencias"].append({"clase": clase, "desde": desde, "valor": float(valor), "fuente": fuente})
    almacen.escribir_json(LOCAL, extra)
