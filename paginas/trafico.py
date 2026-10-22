import pandas as pd
import streamlit as st

from core import jac, oaci
from core.datos import MESES
from core.formato import numero, porcentaje
from ui import graficos
from ui.comun import barra_lateral, inicializar, tabla

barra_lateral()
st.title("Tráfico aéreo (JAC y OACI)")
st.caption("Estadísticas públicas que el agente usa para validar los pasajeros inferidos, proyectar con "
           "estacionalidad y dar contexto. También puedes preguntar en el chat: *'¿cómo va el tráfico según la JAC?'*.")

t1, t2, t3 = st.tabs(["Informe mensual JAC", "Embarques por aeropuerto (JAC)", "OACI"])

with t1:
    with st.spinner("Leyendo el último informe de la JAC…"):
        inf = jac.informe()
    if not inf:
        st.warning("No se pudo obtener el informe mensual de la JAC (requiere el backend).")
    else:
        u = jac.ultimo_mes(inf)
        st.subheader(f"Informe de tráfico aéreo – {inf['periodo']}")
        if u:
            c1, c2, c3 = st.columns(3)
            c1.metric("Pasajeros (total)", numero(u["total"]), porcentaje(u["var_total"], 1, True))
            c2.metric("Domésticos", numero(u["domestico"]), porcentaje(u["var_dom"], 1, True))
            c3.metric("Internacionales", numero(u["internacional"]), porcentaje(u["var_int"], 1, True))
        for p in inf.get("resumen", [])[:4]:
            st.markdown("• " + p)
        s = jac.serie_df(inf)
        if not s.empty:
            s["Mes"] = [f"{MESES[m - 1][:3].lower()}-{str(a)[2:]}" for a, m in zip(s["anio"], s["mes"])]
            s = s.rename(columns={"domestico": "Doméstico", "internacional": "Internacional", "total": "Total",
                                  "var_dom": "Var. doméstico", "var_int": "Var. internacional", "var_total": "Var. total"})
            st.altair_chart(graficos.barras(s, "Mes", ["Doméstico", "Internacional"], "Pasajeros transportados por mes"),
                            width="stretch")
            tabla(s[["Mes", "Doméstico", "Internacional", "Total", "Var. doméstico", "Var. internacional", "Var. total"]],
                  porcentajes=["Var. doméstico", "Var. internacional", "Var. total"])
        rutas = pd.DataFrame(inf.get("rutas", []))
        if not rutas.empty:
            st.markdown("**Rutas principales del mes**")
            tabla(rutas.rename(columns={"tipo": "Tipo", "ruta": "Ruta", "anterior": "Año anterior", "actual": "Mes",
                                        "variacion": "Variación", "participacion": "Participación"}),
                  porcentajes=["Variación", "Participación"])
        st.caption(f"Fuente: [Junta de Aeronáutica Civil]({inf.get('url', 'https://www.jac.gob.cl/estadisticas/')}). "
                   "Pasajeros transportados por tramo; los internacionales incluyen salidas y llegadas.")

with t2:
    emb = jac.embarques()
    if emb.empty:
        st.info("Sin base histórica de la JAC.")
    else:
        aeropuertos = (emb.groupby("aeropuerto")["pasajeros"].sum().sort_values(ascending=False).index.tolist())
        sel = st.multiselect("Aeropuertos", aeropuertos, default=aeropuertos[:1])
        e = emb[emb["aeropuerto"].isin(sel)] if sel else emb
        ultimo = int(e["anio"].max())
        meses = sorted(e.loc[e["anio"] == ultimo, "mes"].unique())
        anual = (e[e["mes"].isin(meses)].groupby(["anio", "tipo"])["pasajeros"].sum().unstack(fill_value=0))
        anual["Total"] = anual.sum(axis=1)
        anual = anual.reset_index().rename(columns={"anio": "Año", "nacional": "Nacional", "internacional": "Internacional"})
        anual["Año"] = anual["Año"].astype(str)
        st.altair_chart(graficos.barras(anual, "Año", ["Total"],
                                        f"Pasajeros embarcados, {MESES[meses[0] - 1][:3].lower()}–"
                                        f"{MESES[meses[-1] - 1][:3].lower()} de cada año"), width="stretch")
        tabla(anual)
        st.caption("Fuente: base histórica de tráfico aéreo de la JAC (vuelos comerciales; embarques = pasajeros que "
                   "salen de cada aeropuerto). Se actualiza con `scripts/actualizar_jac.py`.")

with t3:
    o = oaci.cargar()
    if not o:
        st.info("Sin datos de la OACI.")
    else:
        reg = pd.DataFrame([{"Región": k, **v} for k, v in o["regiones"].items()]).rename(columns={
            "ask_total": "ASK total", "ask_internacional": "ASK internacional", "rpk_total": "RPK total"})
        st.subheader(f"ICAO Air Transport Monthly Monitor – {o['periodo']}")
        st.altair_chart(graficos.barras(reg, "Región", ["ASK total", "ASK internacional"],
                                        "Capacidad (asientos-km), variación interanual", horizontal=True,
                                        porcentual=True), width="stretch")
        tabla(reg, porcentajes=[c for c in reg.columns if c != "Región"])
        st.caption(f"Fuente: [OACI]({o['url']}). El sitio de la OACI no permite lectura automática desde la nube; "
                   f"se actualiza con `scripts/actualizar_oaci.py` (última actualización {o['actualizado'][:10]}).")

inicializar()
