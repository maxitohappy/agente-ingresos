"""Despliegue de una respuesta del agente en el chat."""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from core import agente, indicadores
from core.formato import millones, numero, porcentaje
from core.indicadores import Valor
from ui.comun import ingresos, md, preferencias, tabla, tarifas


def _graficos():
    from ui import graficos

    return graficos


def _excel():
    from core import excel  # xlsxwriter: se importa al generar el primer Excel

    return excel


def _nombre_archivo(resp) -> str:
    titulo = resp.resultado.titulo if resp.resultado else (resp.grafico or {}).get("titulo", "consulta")
    base = re.sub(r"[^\w]+", "_", titulo)[:60].strip("_")
    return f"Agente_Ingresos_{base}_{resp.fecha[:10]}.xlsx"


def _grafico_unidades(r):
    pu = r.por_unidad.head(12)
    if pu.empty:
        return None
    d = pu.rename(columns={"unidad": "Unidad", "monto": "Base", "escenario": "Escenario"})
    series = ["Base", "Escenario"] if r.es_simulacion else ["Base"]
    return _graficos().barras(d, "Unidad", series, "Por unidad (millones de $)", horizontal=True, escala=1e6)


def _grafico_meses(r):
    pm = r.por_mes
    if pm.empty:
        return None
    d = pm.assign(Periodo=[m + (" (proy.)" if p else "") for m, p in zip(pm["Mes"], pm["proyectado"])]).rename(
        columns={"monto": "Base", "escenario": "Escenario"})
    series = ["Base", "Escenario"] if r.es_simulacion else ["Base"]
    return _graficos().barras(d, "Periodo", series, "Por mes (millones de $)", escala=1e6)


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


PORCENTUALES = ("Var", "Variación", "Participación", "ASK", "RPK")


def mostrar_tablas(resp, clave: str) -> None:
    """Respuestas de tráfico aéreo (JAC / OACI): texto, gráfico, tablas y Excel."""
    for p in resp.resena:
        st.markdown(md(p) if not p.startswith("Fuente:") else p)
    g = resp.grafico
    if g is not None and not g["datos"].empty:
        porcentual = all(s.startswith(PORCENTUALES) for s in g["series"])
        st.vega_lite_chart(*_graficos().barras(g["datos"], g["x"], g["series"], g["titulo"], porcentual=porcentual,
                                        horizontal=porcentual), width="stretch", key=f"gt_{clave}")
    for nombre, df in resp.tablas.items():
        with st.expander(nombre, expanded=len(resp.tablas) == 1):
            tabla(df, porcentajes=[c for c in df.columns if str(c).startswith(PORCENTUALES)])
    if "excel" not in resp.__dict__:
        resp.__dict__["excel"] = _excel().generar_tablas(resp)
    st.download_button("📥 Descargar Excel", resp.__dict__["excel"], file_name=_nombre_archivo(resp),
                       key=f"dl_{clave}", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def mostrar_compacto(resp, clave: str) -> None:
    """Respuesta anterior en versión breve: conclusión, Excel y botón para ver el detalle."""
    texto = resp.resena[0] if resp.resena else resp.mensaje
    st.markdown(md(texto))
    if resp.resultado is None and not resp.tablas:
        return
    c1, c2, _ = st.columns([1.3, 1, 2])
    if c1.button("Ver detalle completo", key=f"abrir_{clave}", icon=":material/expand_more:"):
        st.session_state.setdefault("abiertas", set()).add(resp.id)
        st.rerun()
    if "excel" not in resp.__dict__:
        resp.__dict__["excel"] = (_excel().generar(resp) if resp.resultado is not None
                                  else _excel().generar_tablas(resp))
    c2.download_button("📥 Excel", resp.__dict__["excel"], file_name=_nombre_archivo(resp), key=f"dlc_{clave}",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def mostrar(resp, clave: str) -> None:
    if resp.tablas and resp.resultado is None:
        mostrar_tablas(resp, clave)
        return
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
        for nombre, df_ in resp.tablas.items():
            with st.expander(nombre, expanded=True):
                tabla(df_, porcentajes=[c_ for c_ in df_.columns if str(c_).startswith(PORCENTUALES)],
                      decimales=0)
        t1, t2, t3, t4 = st.tabs(["Gráficos", "Niveles", "Detalle", "Supuestos y fuentes"])
        with t1:
            g1, g2 = st.columns(2)
            f1, f2 = _grafico_unidades(r), _grafico_meses(r)
            if f1 is not None:
                g1.vega_lite_chart(*f1, width="stretch", key=f"gu_{clave}")
            if f2 is not None:
                g2.vega_lite_chart(*f2, width="stretch", key=f"gm_{clave}")
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
            resp.__dict__["excel"] = _excel().generar(resp)
        b1, b2 = st.columns([1, 2])
        b1.download_button("📥 Descargar Excel (cálculos, gráficos y reseña)", resp.__dict__["excel"],
                           file_name=_nombre_archivo(resp), key=f"dl_{clave}",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if r.es_simulacion and resp.consulta.concepto == "Derecho de Embarque":
            with b2.popover("Ajustar supuestos y recalcular"):
                with st.form(f"ajuste_{clave}", border=False):
                    pp = st.number_input("Precio promedio del pasaje (CLP por tramo)", min_value=0.0,
                                         value=resp.consulta.precio_pasaje, step=1000.0, format="%.0f",
                                         help="Necesario para estimar el efecto en pasajeros.")
                    e = st.number_input("Elasticidad respecto del precio del pasaje (0 = ver escenarios 0,5/1,0/1,5)",
                                        0.0, 10.0, float(resp.consulta.elasticidad or 0), 0.1, format="%.2f")
                    vp = st.number_input("o variación directa de pasajeros % (vacío = usar elasticidad)",
                                         value=resp.consulta.var_pasajeros, step=1.0, format="%.1f")
                    tc = st.number_input("Tipo de cambio (CLP/USD)", 0.0, 5000.0, float(resp.tc or 0), 1.0,
                                         format="%.2f")
                    if st.form_submit_button("Recalcular", type="primary"):
                        _recalcular(resp, elasticidad=e or None, var_pasajeros=vp, tipo_cambio=tc or None,
                                    precio_pasaje=pp or None)
                        st.rerun()
    if resp.faltantes:
        faltantes(resp, clave)
