import streamlit as st

from core import agente, historial
from ui import respuesta
from ui.comun import md, barra_lateral, ingresos, inicializar, preferencias, tarifas

inicializar()
df = ingresos()
barra_lateral()

st.title("Agente Ingresos")
st.caption("Pregunta en lenguaje natural por el impacto de cambios tarifarios o por los ingresos de una unidad. "
           "Cada respuesta trae cálculos, gráficos, reseña y un Excel descargable, y queda en el historial.")

if "mensajes" not in st.session_state:
    st.session_state.mensajes = []
    st.session_state.respuestas = {}


def procesar(pregunta: str) -> None:
    p = preferencias()
    with st.spinner("Calculando…"):
        resp = agente.responder(pregunta, df, tarifas(), tc_usuario=st.session_state.get("tc") or None,
                                usar_ia=p.get("usar_ia", True), usuario=p.get("usuario", ""))
    st.session_state.respuestas[resp.id] = resp
    st.session_state.mensajes += [{"rol": "user", "texto": pregunta}, {"rol": "assistant", "id": resp.id}]
    if resp.resultado is not None or resp.consulta.tipo == "dato":
        historial.guardar(resp, p.get("usuario", ""))


pendiente = st.session_state.pop("pregunta_pendiente", None)
if pendiente:
    procesar(pendiente)

if not st.session_state.mensajes:
    st.markdown("**Prueba con alguna de estas consultas:**")
    for i, ej in enumerate(agente.EJEMPLOS):
        if st.button(ej, key=f"ej_{i}", width="stretch"):
            st.session_state.pregunta_pendiente = ej
            st.rerun()

for i, m in enumerate(st.session_state.mensajes):
    with st.chat_message(m["rol"], avatar=":material/person:" if m["rol"] == "user" else ":material/flight_takeoff:"):
        if m["rol"] == "user":
            st.markdown(md(m["texto"]))
        else:
            respuesta.mostrar(st.session_state.respuestas[m["id"]], f"{m['id']}_{i}")

if pregunta := st.chat_input("Ej.: ¿cómo impacta una rebaja de 5 dólares del derecho de embarque en Punta Arenas?"):
    st.session_state.pregunta_pendiente = pregunta
    st.rerun()
