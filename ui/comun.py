"""Estado compartido e utilidades de interfaz."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import almacen, backend, datos, indicadores, jac, red, tarifario
from core.formato import numero, porcentaje

EN_NAVEGADOR = red.EN_NAVEGADOR
# Paleta validada (skill dataviz, app anterior): base, escenario.
COLOR_BASE = "#2a78d6"
COLOR_ESCENARIO = "#eb6834"
PREFERENCIAS = "preferencias.json"


def preferencias() -> dict:
    if "prefs" not in st.session_state:
        st.session_state.prefs = almacen.leer_json(PREFERENCIAS, {"usuario": "", "usar_ia": True})
    return st.session_state.prefs


def guardar_preferencias() -> None:
    almacen.escribir_json(PREFERENCIAS, st.session_state.prefs)


def ingresos() -> pd.DataFrame:
    if "df" not in st.session_state:
        st.session_state.df = datos.cargar_agregado()
    return st.session_state.df


def tarifas() -> dict:
    if "tar" not in st.session_state:
        st.session_state.tar = tarifario.cargar()
    return st.session_state.tar


def inicializar() -> None:
    """Actualiza tarifario, indicadores, memoria e informe JAC con una sola llamada al backend.

    La primera pantalla se dibuja de inmediato con los datos guardados. El navegador solo muestra los elementos
    cuando termina una ejecución, así que la carga se hace en un fragmento con temporizador que el navegador
    dispara después de dibujar; al terminar, la página se vuelve a dibujar una vez con los valores del día.
    """
    if st.session_state.get("inicializado"):
        return

    @st.fragment(run_every=0.5)
    def _cargar_en_segundo_plano():
        if not st.session_state.get("pantalla_dibujada"):
            st.session_state.pantalla_dibujada = True   # primera ejecución: solo dibujar
            return
        if not st.session_state.get("inicializado"):
            _cargar()
            st.rerun(scope="app")

    _cargar_en_segundo_plano()


def _cargar() -> None:
    st.session_state.inicializado = True
    # Se aprovecha esta ejecución (la pantalla ya está visible) para cargar las librerías de gráficos y Excel,
    # así la primera consulta no espera por ellas.
    from core import excel  # noqa: F401
    from ui import graficos  # noqa: F401

    msgs = []
    inicio = None
    if backend.configurado():
        try:
            inicio = backend.get("inicio", timeout=15)
        except Exception as e:  # noqa: BLE001
            msgs.append(f"Backend sin respuesta ({e}); se usan datos guardados.")
    if inicio:
        msgs.append(tarifario.actualizar_desde_dgac(pagina=inicio.get("pagina_dgac"))
                    if inicio.get("pagina_dgac") else "Tarifario DGAC: " + inicio.get("pagina_dgac_error", "sin datos"))
        if "indicadores" in inicio:
            msgs.append("Indicadores: " + "; ".join(indicadores.actualizar_cache(precargados=inicio["indicadores"])))
        if "memoria" in inicio:
            indicadores.precargar_memoria(inicio["memoria"])
        jac.precargar(inicio.get("jac"))
        st.session_state.ia_disponible = bool(inicio.get("ia"))
    else:
        if not EN_NAVEGADOR:
            msgs.append(tarifario.actualizar_desde_dgac())
        msgs.append("Indicadores: " + "; ".join(indicadores.actualizar_cache()))
    if jac.vencido():   # informe JAC del día: se descarga aquí, con la pantalla ya visible
        jac.informe()
    st.session_state.estado_fuentes = msgs
    st.session_state.pop("tar", None)
    # Si el usuario no cambió el tipo de cambio sugerido, se reemplaza por el del día.
    nuevo = tc_sugerido()
    if nuevo and st.session_state.get("tc") == st.session_state.get("tc_inicial"):
        st.session_state.tc = st.session_state.tc_inicial = round(nuevo.valor, 2)


def tc_sugerido() -> indicadores.Valor | None:
    # Antes de la carga inicial no se consulta la memoria compartida (evita esperar al backend).
    return indicadores.obtener("dolar", memoria=None if st.session_state.get("inicializado") else [])


def barra_lateral() -> None:
    p = preferencias()
    with st.sidebar:
        st.markdown("### Supuestos")
        sug = tc_sugerido()
        if "tc" not in st.session_state:
            st.session_state.tc = st.session_state.tc_inicial = round(sug.valor, 2) if sug else None
        st.session_state.tc = st.number_input(
            "Tipo de cambio para conversiones (CLP por USD)", min_value=0.0, value=st.session_state.tc,
            step=1.0, format="%.2f", placeholder="Ingresa el valor",
            help="Se usa para convertir rebajas en dólares a pesos (y viceversa). Sugerido: dólar observado. "
                 "También puedes indicarlo en la pregunta: 'con dólar a 950'.")
        if sug:
            st.caption(f"Sugerido: {numero(sug.valor, 2)} – {sug.cita()}")
        else:
            st.caption("Sin dólar observado disponible: ingrésalo para simular cambios en dólares.")
        nombre = st.text_input("Tu nombre (opcional)", value=p.get("usuario", ""), max_chars=40,
                               help="Se registra junto a los indicadores que ingreses en la memoria compartida.")
        ia_ok = backend.configurado() and st.session_state.get("ia_disponible", True)
        ia = st.toggle("Usar IA (Gemini) si las reglas no entienden", value=p.get("usar_ia", True) and ia_ok,
                       disabled=not ia_ok,
                       help="Solo se envía el texto de la pregunta, nunca los montos." if ia_ok
                       else "Requiere el backend con la clave GEMINI_API_KEY (ver Ayuda).")
        if nombre != p.get("usuario") or ia != p.get("usar_ia"):
            p["usuario"], p["usar_ia"] = nombre, ia
            guardar_preferencias()
        st.divider()
        estado = "🟢 conectado" if backend.configurado() else "⚪ sin backend (modo local)"
        st.caption(f"Backend compartido: {estado}")
        st.caption("Datos: Ingresos acumulados 2026 (agregados por unidad, concepto y mes)")


def md(texto: str) -> str:
    """Escapa $ para que Streamlit no lo interprete como fórmula LaTeX."""
    return str(texto).replace("$", "\\$")


def tabla(df: pd.DataFrame, decimales: int = 0, porcentajes: list[str] | None = None, **kwargs) -> None:
    if df is None or df.empty:
        st.info("Sin datos para mostrar.")
        return
    porcentajes = porcentajes or []
    numericas = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c not in porcentajes
                 and not pd.api.types.is_bool_dtype(df[c])]
    formatos = {c: (lambda v, dd=decimales: numero(v, dd)) for c in numericas}
    formatos.update({c: (lambda v: porcentaje(v, 2)) for c in porcentajes if c in df.columns})
    st.dataframe(df.style.format(formatos), hide_index=True, width="stretch", **kwargs)
