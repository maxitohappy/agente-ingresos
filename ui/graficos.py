"""Gráficos de barras como especificación Vega-Lite directa.

Se arma el diccionario Vega-Lite a mano en vez de usar Altair: Altair valida cada gráfico contra su esquema
completo, lo que en el navegador costaba ~0,2 s por gráfico. El resultado visual es el mismo.
"""
from __future__ import annotations

import pandas as pd

from core.formato import numero, porcentaje

# Paleta validada (skill dataviz): base/serie 1, escenario/serie 2, serie 3.
COLORES = ["#2a78d6", "#eb6834", "#1baf7a"]
# Formato chileno en ejes: punto de miles, coma decimal.
EJE_MILES = "replace(format(datum.value, ',.0f'), /,/g, '.')"
EJE_PCT = "replace(format(datum.value, '.0%'), /[.]/g, ',')"


def barras(datos: pd.DataFrame, categoria: str, series: list[str], titulo: str, horizontal: bool = False,
           escala: float = 1.0, unidad: str = "", porcentual: bool = False, orden: list[str] | None = None,
           alto: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Barras agrupadas por serie. Devuelve (datos en formato largo, especificación) para st.vega_lite_chart."""
    largo = datos[[categoria] + series].melt(id_vars=categoria, var_name="Serie", value_name="valor")
    largo["valor"] = largo["valor"].astype(float) / escala
    largo["Valor"] = [porcentaje(v, 1) if porcentual else numero(v, 1 if escala > 1 else 0) + unidad
                      for v in largo["valor"]]
    largo[categoria] = largo[categoria].astype(str)
    orden = orden or list(datos[categoria].astype(str))
    color = {"field": "Serie", "type": "nominal", "scale": {"domain": series, "range": COLORES[: len(series)]},
             "legend": {"orient": "bottom", "title": None} if len(series) > 1 else None}
    eje_valor = {"field": "valor", "type": "quantitative",
                 "axis": {"labelExpr": EJE_PCT if porcentual else EJE_MILES, "title": None, "gridColor": "#8888881f"}}
    eje_cat = {"field": categoria, "type": "nominal", "sort": orden}
    tooltip = [{"field": categoria, "type": "nominal"}, {"field": "Serie", "type": "nominal"},
               {"field": "Valor", "type": "nominal"}]
    if horizontal:
        cod = {"y": {**eje_cat, "axis": {"title": None, "labelLimit": 220}}, "x": eje_valor,
               "yOffset": {"field": "Serie", "sort": series}}
        # Alto por categoría ("step"): con un alto total fijo, varias unidades quedaban comprimidas.
        alto = alto or {"step": 14 * len(series) + 12}
    else:
        cod = {"x": {**eje_cat, "axis": {"title": None, "labelAngle": -40, "labelOverlap": False}}, "y": eje_valor,
               "xOffset": {"field": "Serie", "sort": series}}
        alto = alto or 300
    spec = {"title": titulo, "height": alto, "mark": {"type": "bar", "cornerRadiusEnd": 4},
            "encoding": {**cod, "color": color, "tooltip": tooltip}}
    return largo, spec
