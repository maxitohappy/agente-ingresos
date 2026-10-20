import json

import pandas as pd
import streamlit as st

from core import agente, excel, historial
from ui.comun import barra_lateral, ingresos, inicializar, md, preferencias, tabla, tarifas

inicializar()
barra_lateral()
st.title("Historial de consultas")

if aviso := st.session_state.pop("aviso_historial", None):
    st.success(aviso)

registros, origen = historial.listar()
if origen == "compartido":
    st.caption("Historial compartido entre todos los usuarios (Google Sheet del backend).")
else:
    st.caption("Historial guardado en este equipo. Configura el backend (ver Ayuda) para compartirlo entre usuarios.")

if not registros:
    st.info("Aún no hay consultas registradas.")
    st.stop()

df = pd.DataFrame(registros)
c_buscar, c_excel = st.columns([2, 1])
filtro = c_buscar.text_input("Buscar", placeholder="Filtra por texto de la pregunta o usuario")
if filtro:
    m = df["pregunta"].str.contains(filtro, case=False, na=False) | df["usuario"].astype(str).str.contains(
        filtro, case=False, na=False)
    df = df[m]
c_excel.markdown("&nbsp;")
c_excel.download_button("📥 Descargar historial en Excel", excel.historial(df.to_dict("records")),
                        file_name="Historial_Agente_Ingresos.xlsx", width="stretch",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
vista = df[["fecha", "usuario", "pregunta", "resumen"]].rename(columns={
    "fecha": "Fecha", "usuario": "Usuario", "pregunta": "Pregunta", "resumen": "Resultado"})
vista["Fecha"] = vista["Fecha"].astype(str).str.replace("T", " ").str[:16]
tabla(vista, height=min(600, 38 * len(vista) + 40))

st.subheader("Acciones sobre una consulta")
opciones = {r["id"]: r for r in df.to_dict("records")}
elegido = st.selectbox(
    "Selecciona una consulta", list(opciones), index=None, placeholder="Selecciona…",
    format_func=lambda i: f"{str(opciones[i]['fecha'])[:16].replace('T', ' ')} – {opciones[i]['pregunta'][:100]}")

if elegido:
    reg = opciones[elegido]
    st.caption(md(f"**Resultado guardado:** {reg.get('resumen', '')}"))
    b1, b2, _ = st.columns([1, 1, 2])
    abrir = b1.button("Abrir en el chat", type="primary", width="stretch",
                      help="Se recalcula con los datos e indicadores actuales.")
    if b2.button("🗑️ Eliminar", width="stretch"):
        st.session_state.confirmar_borrado = elegido
    if st.session_state.get("confirmar_borrado") == elegido:
        alcance = "para todos los usuarios" if origen == "compartido" else "de este equipo"
        st.warning(f"¿Eliminar esta consulta del historial {alcance}? Esta acción no se puede deshacer.")
        s1, s2, _ = st.columns([1, 1, 2])
        if s1.button("Sí, eliminar", type="primary", width="stretch"):
            ok = historial.borrar(elegido)
            st.session_state.pop("confirmar_borrado", None)
            st.session_state.aviso_historial = ("Consulta eliminada del historial." if ok else
                                                "Se eliminó de este equipo, pero no se pudo eliminar del historial compartido.")
            st.rerun()
        if s2.button("Cancelar", width="stretch"):
            st.session_state.pop("confirmar_borrado", None)
            st.rerun()
    if abrir:
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
