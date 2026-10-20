"""Despliegue de una respuesta del agente en el chat."""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import agente, excel, indicadores
from core.formato import millones, numero, porcentaje
from core.indicadores import Valor
from ui.comun import COLOR_BASE, COLOR_ESCENARIO, ingresos, md, preferencias, tabla, tarifas

LAYOUT = dict(margin=dict(l=8, r=8, t=40, b=8), legend=dict(orientation="h", y=-0.15),
              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="closest",
              separators=",.", font=dict(size=12))


def _nombre_archivo(resp) -> str:
    base = re.sub(r"[^\w]+", "_", resp.resultado.titulo if resp.resultado else "consulta")[:60].strip("_")
    return f"Agente_Ingresos_{base}_{resp.fecha[:10]}.xlsx"


def _grafico_unidades(r) -> go.Figure | None:
    pu = r.por_unidad.head(12)
    if pu.empty:
        return None
    fig = go.Figure()
    fig.add_bar(y=pu["unidad"], x=pu["monto"] / 1e6, name="Base", orientation="h", marker_color=COLOR_BASE,
                hovertemplate="%{y}<br>Base: $%{x:,.1f} millones<extra></extra>")
    if r.es_simulacion:
        fig.add_bar(y=pu["unidad"], x=pu["escenario"] / 1e6, name="Escenario", orientation="h",
                    marker_color=COLOR_ESCENARIO, hovertemplate="%{y}<br>Escenario: $%{x:,.1f} millones<extra></extra>")
    fig.update_layout(title="Por unidad (millones de $)", barmode="group", bargap=0.25, bargroupgap=0.08,
                      height=max(260, 34 * len(pu) * (2 if r.es_simulacion else 1) // 1.6 + 90),
                      yaxis=dict(autorange="reversed"), xaxis=dict(gridcolor="rgba(128,128,128,0.15)", tickformat=",.0f"),
                      showlegend=r.es_simulacion, **LAYOUT)
    fig.update_traces(marker_cornerradius=4)
    return fig


def _grafico_meses(r) -> go.Figure | None:
    pm = r.por_mes
    if pm.empty:
        return None
    fig = go.Figure()
    etiquetas = [m + (" (proy.)" if p else "") for m, p in zip(pm["Mes"], pm["proyectado"])]
    fig.add_bar(x=etiquetas, y=pm["monto"] / 1e6, name="Base", marker_color=COLOR_BASE,
                hovertemplate="%{x}<br>Base: $%{y:,.1f} millones<extra></extra>")
    if r.es_simulacion:
        fig.add_bar(x=etiquetas, y=pm["escenario"] / 1e6, name="Escenario", marker_color=COLOR_ESCENARIO,
                    hovertemplate="%{x}<br>Escenario: $%{y:,.1f} millones<extra></extra>")
    fig.update_layout(title="Por mes (millones de $)", barmode="group", bargap=0.25, bargroupgap=0.08, height=320,
                      yaxis=dict(gridcolor="rgba(128,128,128,0.15)", tickformat=",.0f"), showlegend=r.es_simulacion, **LAYOUT)
    fig.update_traces(marker_cornerradius=4)
    return fig


def _recalcular(resp, **cambios) -> None:
    c = agente.Consulta.desde_dict({**resp.consulta.a_dict(), **cambios})
    nueva = agente.responder(resp.pregunta, ingresos(), tarifas(), tc_usuario=cambios.get("tipo_cambio") or resp.tc,
                             usuario=preferencias().get("usuario", ""), consulta=c)
    nueva.id = resp.id
    st.session_state.respuestas[resp.id] = nueva


def faltantes(resp, clave: str) -> None:
    """Formulario para que el usuario aporte un indicador que no se encontró; queda en la memoria."""
    for i, f in enumerate(resp.faltantes):
        with st.form(f"faltante_{clave}_{i}", border=True):
            icono = "⚠️" if f.obligatorio else "💡"
            st.markdown(f"{icono} **No encontré {f.nombre}** {f.motivo}. "
                        f"{'Es necesario para el cálculo.' if f.obligatorio else 'Es opcional: completa la reseña.'} "
                        "Si lo ingresas, quedará guardado para futuras consultas.")
            c1, c2, c3 = st.columns([1.2, 0.8, 1.5])
            valor = c1.number_input(f"Valor ({f.unidad})", min_value=0.0, value=None, step=1.0, format="%.2f")
            periodo = c2.text_input("Período", value=f.periodo)
            fuente = c3.text_input("Fuente (opcional)", placeholder="Ej.: Banco Central, Cuentas Nacionales 2024")
            if st.form_submit_button("Guardar y recalcular", type="primary"):
                if valor is None:
                    st.error("Ingresa un valor.")
                else:
                    v = Valor(indicador=indicadores.clave(f.indicador, f.region), periodo=periodo.strip(),
                              valor=float(valor), unidad=f.unidad, fuente=fuente.strip() or "Ingresado en el chat",
                              origen="usuario", usuario=preferencias().get("usuario", ""))
                    destino = indicadores.guardar_en_memoria(v)
                    st.toast(f"Guardado en la {destino}.")
                    _recalcular(resp, tipo_cambio=float(valor) if f.indicador == "dolar" else resp.consulta.tipo_cambio)
                    st.rerun()


def mostrar(resp, clave: str) -> None:
    if resp.mensaje and resp.resultado is None:
        st.markdown(md(resp.mensaje))
    r = resp.resultado
    if r is not None:
        for p in resp.resena[:1]:
            st.markdown(md(p))
        sel, total = r.niveles.iloc[0], r.niveles.iloc[-1]
        cols = st.columns(4)
        if r.es_simulacion:
            cols[0].metric("Impacto en la selección", millones(sel["Diferencia"]), porcentaje(sel["Variación"], 1, True),
                           delta_color="normal")
            cols[1].metric("Ingresos selección (escenario)", millones(sel["Escenario"]))
            cols[2].metric("Efecto en el total de ingresos", porcentaje(total["Variación"], 2, True))
            if r.pasajeros_base:
                cols[3].metric("Pasajeros estimados", numero(r.pasajeros_escenario),
                               f"{numero(r.pasajeros_escenario - r.pasajeros_base)}" if abs(
                                   r.pasajeros_escenario - r.pasajeros_base) > 0.5 else None)
        else:
            cols[0].metric("Ingresos de la selección", millones(sel["Base"]))
            c = resp.consulta
            conc = r.niveles[r.niveles["Nivel"] == f"{c.concepto} – todas las unidades"] if c.concepto else None
            if conc is not None and not conc.empty and conc.iloc[0]["Nivel"] != sel["Nivel"] and conc.iloc[0]["Base"]:
                cols[1].metric(f"Participación en {c.concepto} (todas las unidades)",
                               porcentaje(sel["Base"] / conc.iloc[0]["Base"], 2))
            cols[2].metric("Participación en el total DGAC", porcentaje(sel["Base"] / total["Base"], 2))
            if r.pasajeros_base:
                cols[3].metric("Pasajeros estimados", numero(r.pasajeros_base))
        for p in resp.resena[1:]:
            st.markdown(md(p))
        for a in r.avisos:
            st.caption(md("ℹ️ " + a))
        t1, t2, t3, t4 = st.tabs(["Gráficos", "Niveles", "Detalle", "Supuestos y fuentes"])
        with t1:
            g1, g2 = st.columns(2)
            f1, f2 = _grafico_unidades(r), _grafico_meses(r)
            if f1:
                g1.plotly_chart(f1, width="stretch", key=f"gu_{clave}")
            if f2:
                g2.plotly_chart(f2, width="stretch", key=f"gm_{clave}")
        with t2:
            tabla(r.niveles if r.es_simulacion else r.niveles[["Nivel", "Base"]], porcentajes=["Variación"])
        with t3:
            pu = r.por_unidad.rename(columns={"unidad": "Unidad", "monto": "Base", "escenario": "Escenario",
                                              "diferencia": "Diferencia", "pax": "Pasajeros base",
                                              "pax_escenario": "Pasajeros escenario", "participacion": "Participación"})
            if not r.es_simulacion:
                pu = pu.drop(columns=["Escenario", "Diferencia", "Pasajeros escenario"])
            if not r.pasajeros_base:
                pu = pu.drop(columns=[c for c in ("Pasajeros base", "Pasajeros escenario") if c in pu])
            tabla(pu, porcentajes=["Participación"])
        with t4:
            tabla(pd.DataFrame(r.supuestos, columns=["Supuesto", "Valor", "Fuente"]))
            c = resp.consulta
            st.caption(f"Interpretación ({c.origen}): concepto **{c.concepto or 'todos'}**, ámbito **{c.ambito}**, "
                       f"cambio **{c.descripcion_cambio()}**, meses **{', '.join(map(str, c.meses)) or 'todos'}**.")
        if "excel" not in resp.__dict__:
            resp.__dict__["excel"] = excel.generar(resp)
        b1, b2 = st.columns([1, 2])
        b1.download_button("📥 Descargar Excel (cálculos, gráficos y reseña)", resp.__dict__["excel"],
                           file_name=_nombre_archivo(resp), key=f"dl_{clave}",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if r.es_simulacion and resp.consulta.concepto == "Derecho de Embarque":
            with b2.popover("Ajustar supuestos y recalcular"):
                with st.form(f"ajuste_{clave}", border=False):
                    e = st.number_input("Elasticidad (magnitud)", 0.0, 10.0, float(resp.consulta.elasticidad or 0),
                                        0.1, format="%.2f")
                    vp = st.number_input("o variación directa de pasajeros % (vacío = usar elasticidad)",
                                         value=resp.consulta.var_pasajeros, step=1.0, format="%.1f")
                    tc = st.number_input("Tipo de cambio (CLP/USD)", 0.0, 5000.0, float(resp.tc or 0), 1.0,
                                         format="%.2f")
                    if st.form_submit_button("Recalcular", type="primary"):
                        _recalcular(resp, elasticidad=e or None, var_pasajeros=vp, tipo_cambio=tc or None)
                        st.rerun()
    if resp.faltantes:
        faltantes(resp, clave)
