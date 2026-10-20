"""Agente Ingresos – punto de entrada (Streamlit / stlite)."""
import streamlit as st

st.set_page_config(page_title="Agente Ingresos", page_icon=":material/flight_takeoff:", layout="wide")

paginas = [
    st.Page("paginas/chat.py", title="Chat", icon=":material/chat:", default=True),
    st.Page("paginas/historial.py", title="Historial", icon=":material/history:"),
    st.Page("paginas/datos.py", title="Datos e indicadores", icon=":material/database:"),
    st.Page("paginas/trafico.py", title="Tráfico aéreo (JAC/OACI)", icon=":material/flight:"),
    st.Page("paginas/ayuda.py", title="Ayuda", icon=":material/help:"),
]
st.navigation(paginas).run()
