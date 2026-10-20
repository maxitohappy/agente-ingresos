"""Gráficos con Altair (incluido en Streamlit: no agrega descargas al abrir la app)."""
from __future__ import annotations

import altair as alt
import pandas as pd

from core.formato import numero, porcentaje

# Paleta validada (skill dataviz): base/serie 1, escenario/serie 2, serie 3.
COLORES = ["#2a78d6", "#eb6834", "#1baf7a"]
# Formato chileno en ejes: punto de miles, coma decimal.
EJE_MILES = "replace(format(datum.value, ',.0f'), /,/g, '.')"
EJE_PCT = "replace(format(datum.value, '.0%'), /[.]/g, ',')"


def barras(datos: pd.DataFrame, categoria: str, series: list[str], titulo: str, horizontal: bool = False,
           escala: float = 1.0, unidad: str = "", porcentual: bool = False, orden: list[str] | None = None,
           alto: int | None = None) -> alt.Chart:
    """Barras agrupadas por serie. Tooltips con formato chileno."""
    largo = datos[[categoria] + series].melt(id_vars=categoria, var_name="Serie", value_name="valor")
    largo["valor"] = largo["valor"].astype(float) / escala
    largo["Valor"] = [porcentaje(v, 1) if porcentual else numero(v, 1 if escala > 1 else 0) + unidad
                      for v in largo["valor"]]
    orden = orden or list(datos[categoria].astype(str))
    largo[categoria] = largo[categoria].astype(str)
    color = alt.Color("Serie:N", scale=alt.Scale(domain=series, range=COLORES[: len(series)]),
                      legend=alt.Legend(orient="bottom", title=None) if len(series) > 1 else None)
    eje_valor = alt.Axis(labelExpr=EJE_PCT if porcentual else EJE_MILES, title=None, grid=True,
                         gridColor="#8888881f")
    eje_cat = alt.Axis(title=None, labelLimit=220)
    marca = alt.Chart(largo).mark_bar(cornerRadiusEnd=4)
    tooltip = [alt.Tooltip(f"{categoria}:N", title=categoria), alt.Tooltip("Serie:N"), alt.Tooltip("Valor:N")]
    if horizontal:
        graf = marca.encode(y=alt.Y(f"{categoria}:N", sort=orden, axis=eje_cat),
                            x=alt.X("valor:Q", axis=eje_valor), color=color, tooltip=tooltip,
                            yOffset=alt.YOffset("Serie:N", sort=series))
        alto = alto or max(180, len(orden) * (16 * len(series) + 10) + 40)
    else:
        graf = marca.encode(x=alt.X(f"{categoria}:N", sort=orden, axis=alt.Axis(title=None, labelAngle=-40, labelOverlap=False)),
                            y=alt.Y("valor:Q", axis=eje_valor), color=color, tooltip=tooltip,
                            xOffset=alt.XOffset("Serie:N", sort=series))
        alto = alto or 300
    return graf.properties(title=titulo, height=alto)
