from datetime import date

import pandas as pd
import streamlit as st

from core import datos, indicadores, tarifario
from core.indicadores import CATALOGO, Valor
from ui.comun import barra_lateral, ingresos, inicializar, preferencias, tabla, tarifas

barra_lateral()
st.title("Datos e indicadores")

t1, t2, t3, t4 = st.tabs(["Indicadores y memoria", "Tarifario DGAC", "Ingresos", "Estado de las fuentes"])

with t1:
    st.markdown("El agente busca cada indicador en este orden: **fuente pública en línea → memoria (valores "
                "ingresados por usuarios) → respaldo publicado**. Si no lo encuentra, te lo pide en el chat y lo "
                "guarda aquí.")
    memoria = indicadores.listar_memoria()
    tabla(indicadores.tabla_actual(memoria), decimales=2)
    if st.button("Actualizar desde las fuentes públicas"):
        with st.spinner("Consultando…"):
            st.session_state.estado_fuentes = indicadores.actualizar_cache(forzar=True)
        st.rerun()

    st.subheader("Memoria de indicadores ingresados por usuarios")
    if memoria:
        mdf = pd.DataFrame([{"id": v.id, "Indicador": v.etiqueta, "Período": v.periodo, "Valor": v.valor,
                             "Unidad": v.unidad, "Fuente": v.fuente, "Ingresado por": v.usuario,
                             "Fecha": v.fecha_registro[:16].replace("T", " ")} for v in memoria])
        tabla(mdf.drop(columns="id"), decimales=2)
        borrar = st.selectbox("Borrar un valor de la memoria", [None] + list(mdf["id"]),
                              format_func=lambda i: "—" if i is None else
                              " | ".join(str(x) for x in mdf.loc[mdf["id"] == i, ["Indicador", "Período", "Valor"]].iloc[0]))
        if borrar and st.button("Borrar", type="secondary"):
            indicadores.borrar_de_memoria(borrar)
            st.rerun()
    else:
        st.caption("Aún no hay valores en la memoria.")

    with st.form("nuevo_indicador"):
        st.markdown("**Agregar o corregir un indicador** (también puedes escribirlo en el chat, p. ej. "
                    "*'el PIB regional de Magallanes 2024 es 5.900 miles de millones'*).")
        c1, c2, c3 = st.columns(3)
        ind = c1.selectbox("Indicador", list(CATALOGO), format_func=lambda k: CATALOGO[k]["nombre"])
        from core.alias import ALIAS_REGION

        region = c2.selectbox("Región (solo PIB regional)", [None] + sorted(set(ALIAS_REGION.values())),
                              format_func=lambda r: "—" if r is None else r)
        periodo = c3.text_input("Período (2025, 2026-09 o 2026-10-20)", value=str(date.today().year - 1))
        c4, c5 = st.columns([1, 2])
        valor = c4.number_input("Valor", value=None, format="%.4f")
        fuente = c5.text_input("Fuente")
        if st.form_submit_button("Guardar en la memoria", type="primary"):
            if valor is None:
                st.error("Ingresa un valor.")
            else:
                destino = indicadores.guardar_en_memoria(Valor(
                    indicador=indicadores.clave(ind, region if ind == "pib_regional" else None), periodo=periodo,
                    valor=float(valor), unidad=CATALOGO[ind]["unidad"], fuente=fuente or "Ingresado manualmente",
                    origen="usuario", usuario=preferencias().get("usuario", "")))
                st.success(f"Guardado en la {destino}.")
                st.rerun()

with t2:
    tar = tarifas()
    st.markdown("Derechos de embarque por pasajero (DAR 50, art. 60). Los valores en pesos se reajustan por IPC el "
                f"10 de enero, abril, julio y octubre. Fuente en línea: [tarifario DGAC]({tarifario.PAGINA_DGAC}).")
    vig = tarifario.vigente_hoy(tar)
    cols = st.columns(len(vig))
    for col, (clase, v) in zip(cols, vig.items()):
        if v:
            col.metric(tar["clases"][clase]["nombre"], f"{tar['clases'][clase]['moneda']} {v['valor']:,.0f}".replace(",", "."))
    tabla(tarifario.tabla(tar), decimales=0)
    if st.button("Volver a leer el tarifario de la DGAC"):
        st.info(tarifario.actualizar_desde_dgac())
        st.session_state.pop("tar", None)
    with st.form("tarifa_manual"):
        st.markdown("**Registrar una tarifa manualmente**")
        c1, c2, c3 = st.columns(3)
        clase = c1.selectbox("Clase", [k for k in tar["clases"] if "igual_a" not in tar["clases"][k]],
                             format_func=lambda k: tar["clases"][k]["nombre"])
        desde = c2.date_input("Vigente desde", value=date.today())
        valor = c3.number_input("Valor", min_value=0.0, value=None, format="%.2f")
        if st.form_submit_button("Guardar tarifa") and valor:
            tarifario.agregar_manual(clase, desde.isoformat(), valor, f"Ingresada por {preferencias().get('usuario') or 'usuario'}")
            st.session_state.pop("tar", None)
            st.rerun()

with t3:
    df = ingresos()
    st.caption("Origen: planilla Ingresos acumulados 2026 (agregada; se actualiza con scripts/agregar_datos.py). Meses: "
               + ", ".join(f"{datos.MESES[m - 1]} {a}" for a, m in datos.meses_disponibles(df)))
    resumen = df.pivot_table(index="concepto", columns="mes", values="monto", aggfunc="sum", fill_value=0)
    resumen.columns = [datos.MESES[m - 1][:3] for m in resumen.columns]
    resumen["Total"] = resumen.sum(axis=1)
    resumen.loc["Total"] = resumen.sum()
    tabla(resumen.reset_index().rename(columns={"concepto": "Concepto"}))

with t4:
    for m in st.session_state.get("estado_fuentes", []):
        st.write("• " + str(m))

inicializar()
