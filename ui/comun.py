"""Estado compartido e utilidades de interfaz."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import almacen, backend, datos, indicadores, red, tarifario
from core.formato import numero, porcentaje

EN_NAVEGADOR = red.EN_NAVEGADOR
# Paleta validada (skill dataviz, app anterior): base, escenario.
COLOR_BASE = "#2a78d6"
COLOR_ESCENARIO = "#eb6834"
DATOS_USUARIO = "agregado_usuario.csv"
PREFERENCIAS = "preferencias.json"


def preferencias() -> dict:
    if "prefs" not in st.session_state:
        st.session_state.prefs = almacen.leer_json(PREFERENCIAS, {"usuario": "", "usar_ia": True})
    return st.session_state.prefs


def guardar_preferencias() -> None:
    almacen.escribir_json(PREFERENCIAS, st.session_state.prefs)


def ingresos() -> pd.DataFrame:
    """Agregado vigente: el que subió el usuario en este equipo o el publicado."""
    if "df" not in st.session_state:
        propio = almacen.ruta(DATOS_USUARIO)
        if propio.exists():
            st.session_state.df = datos.cargar_agregado(propio)
            st.session_state.df_origen = "Excel cargado en este equipo"
        else:
            st.session_state.df = datos.cargar_agregado()
            st.session_state.df_origen = "Datos publicados (Ingresos acumulados 2026, agregados)"
    return st.session_state.df


def tarifas() -> dict:
    if "tar" not in st.session_state:
        st.session_state.tar = tarifario.cargar()
    return st.session_state.tar


def inicializar() -> None:
    """Primera carga de la sesión: actualiza tarifario e indicadores sin que el usuario lo pida."""
    if st.session_state.get("inicializado"):
        return
    with st.spinner("Consultando tarifario DGAC e indicadores económicos…"):
        msgs = []
        if not EN_NAVEGADOR or backend.configurado():
            msgs.append(tarifario.actualizar_desde_dgac())
            st.session_state.pop("tar", None)
        estado = indicadores.actualizar_cache()
        msgs.append("Indicadores: " + "; ".join(estado))
    st.session_state.estado_fuentes = msgs
    st.session_state.inicializado = True


def tc_sugerido() -> indicadores.Valor | None:
    return indicadores.obtener("dolar")


def barra_lateral() -> None:
    p = preferencias()
    with st.sidebar:
        st.markdown("### Supuestos")
        sug = tc_sugerido()
        if "tc" not in st.session_state:
            st.session_state.tc = round(sug.valor, 2) if sug else None
        st.session_state.tc = st.number_input(
            "Tipo de cambio para conversiones (CLP por USD)", min_value=0.0, value=st.session_state.tc,
            step=1.0, format="%.2f", placeholder="Ingresa el valor",
            help="Se usa para convertir rebajas en dólares a pesos (y viceversa). Sugerido: dólar observado. "
                 "También puedes indicarlo en la pregunta: 'con dólar a 950'.")
        if sug:
            st.caption(f"Sugerido: {numero(sug.valor, 2)} – {sug.cita()}")
        else:
            st.caption("Sin dólar observado disponible: ingrésalo para simular cambios en dólares.")
        nombre = st.text_input("Tu nombre (para el historial)", value=p.get("usuario", ""), max_chars=40)
        ia = st.toggle("Usar IA (Gemini) si las reglas no entienden", value=p.get("usar_ia", True),
                       disabled=not backend.configurado(),
                       help="Solo se envía el texto de la pregunta, nunca los montos." if backend.configurado()
                       else "Requiere configurar el backend (ver Ayuda).")
        if nombre != p.get("usuario") or ia != p.get("usar_ia"):
            p["usuario"], p["usar_ia"] = nombre, ia
            guardar_preferencias()
        st.divider()
        estado = "🟢 conectado" if backend.configurado() else "⚪ sin backend (modo local)"
        st.caption(f"Backend compartido: {estado}")
        st.caption(f"Datos: {st.session_state.get('df_origen', '')}")


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


def editor(df: pd.DataFrame, clave: str, **kwargs) -> pd.DataFrame:
    """`st.data_editor` compatible con stlite 1.9.2 (con key y filas fijas falla en el navegador)."""
    if EN_NAVEGADOR and kwargs.get("num_rows", "fixed") == "fixed":
        d = df.copy()
        d["_editor"] = clave
        config = dict(kwargs.pop("column_config", None) or {})
        config["_editor"] = None
        if isinstance(kwargs.get("disabled"), list):
            kwargs["disabled"] = kwargs["disabled"] + ["_editor"]
        return st.data_editor(d, column_config=config, **kwargs).drop(columns="_editor")
    return st.data_editor(df, key=clave, **kwargs)
