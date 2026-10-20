import json

import pandas as pd
import streamlit as st

from core import agente, excel, historial
from ui.comun import barra_lateral, ingresos, inicializar, preferencias, tabla, tarifas

inicializar()
barra_lateral()
st.title("Historial de consultas")

registros, origen = historial.listar()
if origen == "compartido":
    st.caption("Historial compartido entre todos los usuarios (Google Sheet del backend).")
else:
    st.caption("Historial guardado en este equipo. Configura el backend (ver Ayuda) para compartirlo entre usuarios.")

if not registros:
    st.info("Aún no hay consultas registradas.")
    st.stop()

df = pd.DataFrame(registros)
filtro = st.text_input("Buscar", placeholder="Filtra por texto de la pregunta o usuario")
if filtro:
    m = df["pregunta"].str.contains(filtro, case=False, na=False) | df["usuario"].astype(str).str.contains(
        filtro, case=False, na=False)
    df = df[m]
vista = df[["fecha", "usuario", "pregunta", "resumen"]].rename(columns={
    "fecha": "Fecha", "usuario": "Usuario", "pregunta": "Pregunta", "resumen": "Resultado"})
vista["Fecha"] = vista["Fecha"].astype(str).str.replace("T", " ").str[:16]
tabla(vista, height=min(600, 38 * len(vista) + 40))

c1, c2 = st.columns([2, 1])
opciones = {f"{str(r['fecha'])[:16].replace('T', ' ')} – {r['pregunta'][:90]}": r for r in df.to_dict("records")}
elegida = c1.selectbox("Volver a abrir una consulta (se recalcula con los datos e indicadores actuales)",
                       list(opciones), index=None, placeholder="Selecciona…")
c2.download_button("📥 Descargar historial en Excel", excel.historial(df.to_dict("records")),
                   file_name="Historial_Agente_Ingresos.xlsx", width="stretch",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
if elegida and st.button("Abrir en el chat", type="primary"):
    reg = opciones[elegida]
    try:
        c = agente.Consulta.desde_dict(json.loads(reg["consulta"]))
    except (TypeError, ValueError):
        c = None
    resp = agente.responder(reg["pregunta"], ingresos(), tarifas(),
                            tc_usuario=float(reg["tc"]) if reg.get("tc") not in (None, "") else st.session_state.get("tc"),
                            usuario=preferencias().get("usuario", ""), consulta=c)
    st.session_state.setdefault("mensajes", [])
    st.session_state.setdefault("respuestas", {})
    st.session_state.respuestas[resp.id] = resp
    st.session_state.mensajes += [{"rol": "user", "texto": reg["pregunta"]}, {"rol": "assistant", "id": resp.id}]
    st.switch_page("paginas/chat.py")
