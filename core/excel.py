"""Libro Excel de cada consulta: resumen, cálculo con fórmulas vivas, tablas, gráficos e indicadores."""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell as celda

from . import tarifario
from .datos import MESES
from .simulador import EMBARQUE, texto_meses

AZUL = "#1F3864"
CELESTE = "#2A78D6"
CELESTE_CLARO = "#86B6EF"
NARANJO = "#EB6834"
GRIS = "#F2F4F7"


def _formatos(wb):
    f = {}
    f["titulo"] = wb.add_format({"bold": True, "font_size": 16, "font_color": AZUL})
    f["subtitulo"] = wb.add_format({"bold": True, "font_size": 12, "font_color": AZUL})
    f["etq"] = wb.add_format({"bold": True, "font_color": "#52514E"})
    f["txt"] = wb.add_format({"text_wrap": True, "valign": "top"})
    f["head"] = wb.add_format({"bold": True, "bg_color": AZUL, "font_color": "white", "text_wrap": True,
                               "valign": "vcenter", "border": 1})
    f["clp"] = wb.add_format({"num_format": "#,##0", "border": 1})
    f["clp_b"] = wb.add_format({"num_format": "#,##0", "border": 1, "bold": True, "bg_color": GRIS})
    f["dec"] = wb.add_format({"num_format": "#,##0.00", "border": 1})
    f["pax"] = wb.add_format({"num_format": "#,##0.0", "border": 1})
    f["pct"] = wb.add_format({"num_format": "0.00%", "border": 1})
    f["pct_b"] = wb.add_format({"num_format": "0.00%", "border": 1, "bold": True, "bg_color": GRIS})
    f["borde"] = wb.add_format({"border": 1, "text_wrap": True, "valign": "top"})
    f["input"] = wb.add_format({"bg_color": "#FFF2CC", "border": 1, "num_format": "#,##0.00", "bold": True})
    f["input_t"] = wb.add_format({"bg_color": "#FFF2CC", "border": 1, "bold": True})
    f["nota"] = wb.add_format({"italic": True, "font_color": "#6B6A66", "text_wrap": True})
    f["aviso"] = wb.add_format({"font_color": "#9C5700", "text_wrap": True})
    return f


def _tabla(ws, fila: int, col: int, df: pd.DataFrame, f, formatos: dict[str, str] | None = None) -> int:
    formatos = formatos or {}
    for j, c in enumerate(df.columns):
        ws.write(fila, col + j, c, f["head"])
    for i, r in enumerate(df.itertuples(index=False), start=1):
        for j, (c, v) in enumerate(zip(df.columns, r)):
            fmt = f[formatos.get(c, "clp" if isinstance(v, (int, float)) and not isinstance(v, bool) else "borde")]
            if isinstance(v, float) and pd.isna(v):
                ws.write_blank(fila + i, col + j, None, fmt)
            else:
                ws.write(fila + i, col + j, v, fmt)
    return fila + len(df) + 1


def generar(resp) -> bytes:
    r = resp.resultado
    c = resp.consulta
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    wb.set_properties({"title": r.titulo, "subject": resp.pregunta, "author": "Agente Ingresos",
                       "comments": "Generado automáticamente por Agente Ingresos"})
    f = _formatos(wb)
    resumen = wb.add_worksheet("Resumen")
    calculo = wb.add_worksheet("Cálculo") if r.es_simulacion else None
    hoja_u = wb.add_worksheet("Por unidad")
    hoja_m = wb.add_worksheet("Por mes")
    graficos = wb.add_worksheet("Gráficos")
    hoja_i = wb.add_worksheet("Indicadores y fuentes")
    for nombre, df_ in getattr(resp, "tablas", {}).items():
        w = wb.add_worksheet(nombre[:31])
        w.set_column(0, len(df_.columns), 22)
        w.write("A1", nombre, f["subtitulo"])
        pct = {c_: "pct" for c_ in df_.columns if str(c_).startswith(("Var", "Variación"))}
        fmt = {c_: "dec" for c_ in df_.columns if str(c_).startswith("Elasticidad")}
        _tabla(w, 2, 0, df_, f, {**pct, **fmt})

    total_dif = None
    if calculo is not None:
        total_dif = _hoja_calculo(calculo, resp, f)

    # --- Resumen ---------------------------------------------------------------------------
    ws = resumen
    ws.set_column("A:A", 46)
    ws.set_column("B:E", 19)
    ws.write("A1", "Agente Ingresos – " + ("Simulación" if r.es_simulacion else "Consulta"), f["titulo"])
    ws.write("A2", f"Generado el {datetime.now():%d-%m-%Y %H:%M}", f["nota"])
    ws.write("A4", "Pregunta", f["etq"])
    ws.merge_range("B4:E4", resp.pregunta, f["txt"])
    ws.set_row(3, 45)
    filas = [("Escenario", r.titulo), ("Período", texto_meses(r)),
             ("Interpretación", f"{c.origen}; concepto: {c.concepto or 'todos'}; ámbito: {c.ambito}; "
                                f"unidades: {', '.join(sorted(r.detalle['unidad'].unique())[:8]) or 'todas'}")]
    fila = 4
    for etq, val in filas:
        ws.write(fila, 0, etq, f["etq"])
        ws.merge_range(fila, 1, fila, 4, val, f["txt"])
        fila += 1
    fila += 1
    ws.write(fila, 0, "Resultados", f["subtitulo"])
    fila += 1
    cab = ["Nivel", "Base (CLP)", "Escenario (CLP)", "Diferencia (CLP)", "Variación"]
    for j, h in enumerate(cab):
        ws.write(fila, j, h, f["head"])
    primera = fila + 1
    for i, n in enumerate(r.niveles.itertuples(index=False)):
        rr = primera + i
        ws.write(rr, 0, n.Nivel, f["borde"])
        ws.write_number(rr, 1, n.Base, f["clp"])
        if total_dif:
            # El escenario de cada nivel = base + diferencia total calculada en la hoja Cálculo.
            ws.write_formula(rr, 2, f"={celda(rr, 1)}+{total_dif}", f["clp"], n.Escenario)
        else:
            ws.write_number(rr, 2, n.Escenario, f["clp"])
        ws.write_formula(rr, 3, f"={celda(rr, 2)}-{celda(rr, 1)}", f["clp_b"], n.Diferencia)
        ws.write_formula(rr, 4, f"=IF({celda(rr, 1)}=0,0,{celda(rr, 3)}/{celda(rr, 1)})", f["pct_b"], n.Variación)
    fila = primera + len(r.niveles) + 1
    if r.pasajeros_base:
        ws.write(fila, 0, "Pasajeros embarcados estimados (base)", f["etq"])
        ws.write_number(fila, 1, round(r.pasajeros_base), f["clp"])
        if r.es_simulacion:
            ws.write(fila + 1, 0, "Pasajeros embarcados estimados (escenario)", f["etq"])
            ws.write_number(fila + 1, 1, round(r.pasajeros_escenario), f["clp"])
            fila += 1
        fila += 2
    ws.write(fila, 0, "Reseña", f["subtitulo"])
    fila += 1
    for p in resp.resena:
        ws.merge_range(fila, 0, fila, 4, p.replace("**", ""), f["txt"])
        ws.set_row(fila, 15 * max(2, len(p) // 95 + 1))
        fila += 1
    if r.avisos:
        fila += 1
        ws.write(fila, 0, "Avisos", f["subtitulo"])
        fila += 1
        for a in r.avisos:
            ws.merge_range(fila, 0, fila, 4, "• " + a, f["aviso"])
            ws.set_row(fila, 15 * max(1, len(a) // 95 + 1))
            fila += 1
    fila += 1
    ws.write(fila, 0, "Supuestos y fuentes", f["subtitulo"])
    fila += 1
    sup = pd.DataFrame(r.supuestos, columns=["Supuesto", "Valor", "Fuente"]) if r.supuestos else \
        pd.DataFrame([("—", "", "")], columns=["Supuesto", "Valor", "Fuente"])
    for j, h in enumerate(["Supuesto", "Valor", "Fuente"]):
        ws.write(fila, j if j < 2 else 2, h, f["head"])
    ws.merge_range(fila, 2, fila, 4, "Fuente", f["head"])
    for i, s in enumerate(sup.itertuples(index=False), start=1):
        ws.write(fila + i, 0, s.Supuesto, f["borde"])
        ws.write(fila + i, 1, s.Valor, f["borde"])
        ws.merge_range(fila + i, 2, fila + i, 4, s.Fuente, f["borde"])
    fila += len(sup) + 2
    ws.merge_range(fila, 0, fila, 4,
                   "Datos: planilla 'Ingresos acumulados' (agregada por unidad, concepto y mes). Pasajeros inferidos "
                   "como monto ÷ tarifa vigente de cada mes según el tarifario DGAC (DAR 50).", f["nota"])
    ws.set_row(fila, 30)

    # --- Por unidad / Por mes -----------------------------------------------------------------
    pu = r.por_unidad.rename(columns={"unidad": "Unidad", "monto": "Base (CLP)", "escenario": "Escenario (CLP)",
                                      "diferencia": "Diferencia (CLP)", "pax": "Pasajeros base",
                                      "pax_escenario": "Pasajeros escenario", "participacion": "Participación"})
    if not r.es_simulacion:
        pu = pu.drop(columns=["Escenario (CLP)", "Diferencia (CLP)", "Pasajeros escenario"])
    if not r.pasajeros_base:
        pu = pu.drop(columns=[c_ for c_ in ("Pasajeros base", "Pasajeros escenario") if c_ in pu])
    hoja_u.set_column("A:A", 38)
    hoja_u.set_column("B:G", 17)
    hoja_u.write("A1", "Resultado por unidad", f["subtitulo"])
    fin_u = _tabla(hoja_u, 2, 0, pu, f, {"Participación": "pct", "Pasajeros base": "pax", "Pasajeros escenario": "pax"})
    pm = r.por_mes.assign(Proyectado=r.por_mes["proyectado"].map({True: "Sí", False: "No"}))
    pm = pm[["Mes", "monto", "escenario", "diferencia", "pax", "pax_escenario", "Proyectado"]].rename(columns={
        "monto": "Base (CLP)", "escenario": "Escenario (CLP)", "diferencia": "Diferencia (CLP)",
        "pax": "Pasajeros base", "pax_escenario": "Pasajeros escenario"})
    if not r.es_simulacion:
        pm = pm.drop(columns=["Escenario (CLP)", "Diferencia (CLP)", "Pasajeros escenario"])
    if not r.pasajeros_base:
        pm = pm.drop(columns=[c_ for c_ in ("Pasajeros base", "Pasajeros escenario") if c_ in pm])
    hoja_m.set_column("A:A", 14)
    hoja_m.set_column("B:G", 17)
    hoja_m.write("A1", "Resultado por mes", f["subtitulo"])
    fin_m = _tabla(hoja_m, 2, 0, pm, f, {"Pasajeros base": "pax", "Pasajeros escenario": "pax"})
    pdsc = r.por_descripcion.rename(columns={"concepto": "Concepto", "descripcion": "Descripción", "monto": "Base (CLP)",
                                             "escenario": "Escenario (CLP)", "diferencia": "Diferencia (CLP)"})
    if not r.es_simulacion:
        pdsc = pdsc.drop(columns=["Escenario (CLP)", "Diferencia (CLP)"])
    hoja_m.write(fin_m + 2, 0, "Resultado por descripción", f["subtitulo"])
    hoja_m.set_column("H:H", 2)
    _tabla(hoja_m, fin_m + 3, 0, pdsc, f)

    # --- Gráficos ------------------------------------------------------------------------------
    graficos.write("A1", "Gráficos", f["titulo"])
    n_u = min(len(pu), 15)
    ch = wb.add_chart({"type": "bar"})
    ch.add_series({"name": "Base", "categories": ["Por unidad", 3, 0, 2 + n_u, 0],
                   "values": ["Por unidad", 3, 1, 2 + n_u, 1], "fill": {"color": CELESTE}})
    if r.es_simulacion:
        ch.add_series({"name": "Escenario", "categories": ["Por unidad", 3, 0, 2 + n_u, 0],
                       "values": ["Por unidad", 3, 2, 2 + n_u, 2], "fill": {"color": NARANJO}})
    ch.set_title({"name": "Ingresos por unidad (principales)", "name_font": {"size": 12}})
    ch.set_y_axis({"reverse": True})
    ch.set_x_axis({"num_format": "#,##0,,\" M\"", "major_gridlines": {"visible": True, "line": {"color": "#E5E7EB"}}})
    ch.set_legend({"position": "bottom"})
    ch.set_size({"width": 760, "height": max(320, 28 * n_u + 120)})
    graficos.insert_chart("A3", ch)
    n_m = len(pm)
    ch2 = wb.add_chart({"type": "column"})
    ch2.add_series({"name": "Base", "categories": ["Por mes", 3, 0, 2 + n_m, 0], "values": ["Por mes", 3, 1, 2 + n_m, 1],
                    "fill": {"color": CELESTE}})
    if r.es_simulacion:
        ch2.add_series({"name": "Escenario", "categories": ["Por mes", 3, 0, 2 + n_m, 0],
                        "values": ["Por mes", 3, 2, 2 + n_m, 2], "fill": {"color": NARANJO}})
    ch2.set_title({"name": "Ingresos por mes", "name_font": {"size": 12}})
    ch2.set_y_axis({"num_format": "#,##0,,\" M\"", "major_gridlines": {"visible": True, "line": {"color": "#E5E7EB"}}})
    ch2.set_legend({"position": "bottom"})
    ch2.set_size({"width": 760, "height": 340})
    fila_g = 3 + max(17, (max(320, 28 * n_u + 120)) // 20 + 1)
    graficos.insert_chart(fila_g, 0, ch2)
    fila_g += 19
    # Impacto por nivel (simulación) o participación (consulta).
    if r.es_simulacion:
        ch3 = wb.add_chart({"type": "bar"})
        n_n = len(r.niveles)
        ch3.add_series({"name": "Variación", "categories": ["Resumen", primera, 0, primera + n_n - 1, 0],
                        "values": ["Resumen", primera, 4, primera + n_n - 1, 4], "fill": {"color": NARANJO},
                        "data_labels": {"value": True, "num_format": "0.0%"}})
        ch3.set_title({"name": "Variación porcentual por nivel", "name_font": {"size": 12}})
        ch3.set_y_axis({"reverse": True})
        ch3.set_x_axis({"num_format": "0%"})
        ch3.set_legend({"none": True})
        ch3.set_size({"width": 760, "height": 300})
        graficos.insert_chart(fila_g, 0, ch3)
    else:
        sel = r.niveles.iloc[0]
        resto = r.niveles.iloc[1] if len(r.niveles) > 1 else None
        if resto is not None and resto["Base"] > sel["Base"]:
            graficos.write(fila_g, 10, "Selección")
            graficos.write(fila_g, 11, float(sel["Base"]))
            graficos.write(fila_g + 1, 10, "Resto")
            graficos.write(fila_g + 1, 11, float(resto["Base"] - sel["Base"]))
            ch3 = wb.add_chart({"type": "doughnut"})
            ch3.add_series({"name": "Participación", "categories": ["Gráficos", fila_g, 10, fila_g + 1, 10],
                            "values": ["Gráficos", fila_g, 11, fila_g + 1, 11],
                            "points": [{"fill": {"color": CELESTE}}, {"fill": {"color": "#D9DEE7"}}],
                            "data_labels": {"percentage": True}})
            ch3.set_title({"name": f"Participación en: {resto['Nivel']}", "name_font": {"size": 11}})
            ch3.set_size({"width": 520, "height": 320})
            graficos.insert_chart(fila_g, 0, ch3)

    # --- Indicadores y fuentes ----------------------------------------------------------------
    hoja_i.set_column("A:A", 44)
    hoja_i.set_column("B:C", 16)
    hoja_i.set_column("D:D", 70)
    hoja_i.write("A1", "Indicadores utilizados", f["subtitulo"])
    ind = pd.DataFrame([{"Indicador": v.etiqueta, "Período": v.periodo, "Valor": v.valor, "Fuente": v.cita()}
                        for v in resp.usados]) if resp.usados else pd.DataFrame(
        [{"Indicador": "—", "Período": "", "Valor": None, "Fuente": "No se usaron indicadores externos"}])
    fin = _tabla(hoja_i, 2, 0, ind, f, {"Valor": "dec"})
    hoja_i.write(fin + 2, 0, "Tarifario de derechos de embarque registrado", f["subtitulo"])
    from . import tarifario as t_
    _tabla(hoja_i, fin + 3, 0, t_.tabla(t_.cargar())[["Clase", "Vigente desde", "Valor", "Moneda", "Fuente"]], f,
           {"Valor": "dec"})
    hoja_i.set_column("E:E", 60)

    resumen.activate()
    wb.close()
    return buf.getvalue()


def _hoja_calculo(ws, resp, f) -> str:
    """Hoja con parámetros editables y fórmulas por fila. Devuelve la celda con la diferencia total."""
    r, c = resp.resultado, resp.consulta
    d = r.detalle.copy()
    ws.write("A1", "Cálculo del escenario (las celdas amarillas son editables y todo se recalcula)", f["subtitulo"])
    embarque = c.concepto == EMBARQUE
    ws.set_column("A:A", 34)
    ws.set_column("B:B", 16)
    ws.set_column("C:C", 36)
    ws.set_column("D:O", 15)
    valor_cambio, moneda_cambio = c.cambio_valor, c.cambio_moneda or "CLP"
    if moneda_cambio in ("UF", "UTM"):
        v = next((x.valor for x in resp.usados if x.indicador == moneda_cambio.lower()), None)
        if v:
            valor_cambio, moneda_cambio = valor_cambio * v, "CLP"
    params = [("Tipo de cambio (CLP por USD)", resp.tc or 0, "input"),
              ("Tipo de cambio tarifario", c.cambio_tipo or "", "input_t"),
              ("Valor del cambio (con signo; % si es porcentual)", valor_cambio, "input"),
              ("Moneda del cambio (USD / CLP)", moneda_cambio if c.cambio_tipo != "porcentaje" else "%", "input_t"),
              ("Elasticidad respecto del precio del pasaje (magnitud)", c.elasticidad or 0, "input"),
              ("Variación directa de pasajeros % (vacío = usar elasticidad)", c.var_pasajeros, "input"),
              ("Precio promedio del pasaje CLP (vacío = sin efecto de elasticidad)", c.precio_pasaje, "input")]
    for i, (etq, val, fmt) in enumerate(params):
        ws.write(2 + i, 0, etq, f["etq"])
        if val is None:
            ws.write_blank(2 + i, 1, None, f[fmt])
        else:
            ws.write(2 + i, 1, val, f[fmt])
    TC, VAL, MON, ELA, VPX, PRE = "$B$3", "$B$5", "$B$6", "$B$7", "$B$8", "$B$9"
    ws.write("C3", "Fórmulas: pasajeros = monto ÷ tarifa (÷ TC si la tarifa es en USD); pasajeros escenario = "
                   "pasajeros × (1 + var.%) o × (1 − elasticidad × Δ derecho por pasajero en $ ÷ precio del pasaje); "
                   "monto escenario = pasajeros escenario × "
                   "tarifa nueva (× TC de la fila si es USD).", f["nota"])
    ws.set_row(2, 30)
    h0 = 10
    if embarque:
        cab = ["Unidad", "Mes", "Descripción", "Clase", "Moneda tarifa", "TC fila", "Monto base (CLP)", "Tarifa base",
               "Pasajeros base", "Tarifa nueva", "Factor demanda", "Pasajeros escenario", "Monto escenario (CLP)",
               "Diferencia (CLP)", "Proyectado"]
    else:
        cab = ["Unidad", "Mes", "Descripción", "Concepto", "Monto base (CLP)", "Variación %", "Monto escenario (CLP)",
               "Diferencia (CLP)", "Proyectado"]
    for j, h in enumerate(cab):
        ws.write(h0, j, h, f["head"])
    ws.set_row(h0, 32)
    ws.freeze_panes(h0 + 1, 1)
    for i, x in enumerate(d.itertuples(index=False)):
        fila = h0 + 1 + i
        rr = fila + 1  # fila en notación A1
        ws.write(fila, 0, x.unidad, f["borde"])
        ws.write(fila, 1, MESES[int(x.mes) - 1], f["borde"])
        ws.write(fila, 2, x.descripcion, f["borde"])
        if embarque:
            ws.write(fila, 3, x.clase or "", f["borde"])
            ws.write(fila, 4, x.moneda_tarifa, f["borde"])
            ws.write(fila, 5, x.tc_fila if pd.notna(x.tc_fila) else "", f["dec"])
            ws.write_number(fila, 6, x.monto, f["clp"])
            ws.write_number(fila, 7, x.tarifa_base if pd.notna(x.tarifa_base) else 0, f["dec"])
            ws.write_formula(fila, 8, f'=IF(H{rr}=0,0,IF(E{rr}="USD",G{rr}/(H{rr}*F{rr}),G{rr}/H{rr}))', f["pax"], x.pax)
            conv = f'IF({MON}=E{rr},{VAL},IF(E{rr}="USD",{VAL}/{TC},{VAL}*{TC}))'
            if c.cambio_tipo == "porcentaje":
                ft = f"=MAX(0,H{rr}*(1+{VAL}/100))"
            elif c.cambio_tipo == "nuevo_valor":
                ft = f"=MAX(0,{conv})"
            else:
                ft = f"=MAX(0,H{rr}+{conv})"
            ws.write_formula(fila, 9, ft, f["dec"], x.tarifa_nueva)
            ws.write_formula(fila, 10, f'=IF({VPX}<>"",1+{VPX}/100,IF(OR({PRE}="",{PRE}=0),1,'
                                       f'MAX(0,1-{ELA}*(J{rr}-H{rr})*IF(E{rr}="USD",F{rr},1)/{PRE})))',
                             f["dec"], (x.pax_escenario / x.pax) if x.pax else 1)
            ws.write_formula(fila, 11, f"=I{rr}*K{rr}", f["pax"], x.pax_escenario)
            ws.write_formula(fila, 12, f'=L{rr}*J{rr}*IF(E{rr}="USD",F{rr},1)', f["clp"], x.escenario)
            ws.write_formula(fila, 13, f"=M{rr}-G{rr}", f["clp"], x.diferencia)
            ws.write(fila, 14, "Sí" if x.proyectado else "No", f["borde"])
        else:
            ws.write(fila, 3, x.concepto, f["borde"])
            ws.write_number(fila, 4, x.monto, f["clp"])
            ws.write_formula(fila, 5, f"={VAL}/100", f["pct"], c.cambio_valor / 100)
            ws.write_formula(fila, 6, f"=E{rr}*(1+F{rr})", f["clp"], x.escenario)
            ws.write_formula(fila, 7, f"=G{rr}-E{rr}", f["clp"], x.diferencia)
            ws.write(fila, 8, "Sí" if x.proyectado else "No", f["borde"])
    ultima = h0 + len(d)
    tot = ultima + 1
    ws.write(tot, 0, "TOTAL", f["head"])
    cols = {"Monto base (CLP)": "clp_b", "Pasajeros base": "clp_b", "Pasajeros escenario": "clp_b",
            "Monto escenario (CLP)": "clp_b", "Diferencia (CLP)": "clp_b"}
    origen = {"Monto base (CLP)": "monto", "Pasajeros base": "pax", "Pasajeros escenario": "pax_escenario",
              "Monto escenario (CLP)": "escenario", "Diferencia (CLP)": "diferencia"}
    for j, h in enumerate(cab):
        if h in cols:
            rango = f"{celda(h0 + 1, j)}:{celda(ultima, j)}"
            ws.write_formula(tot, j, f"=SUM({rango})", f[cols[h]], float(d[origen[h]].sum()))
    if not embarque:
        ws.write(2, 2, "Variación % aplicada a cada fila = celda B5 / 100.", f["nota"])
    col_dif = cab.index("Diferencia (CLP)")
    ws.autofilter(h0, 0, ultima, len(cab) - 1)
    return "'Cálculo'!" + celda(tot, col_dif, row_abs=True, col_abs=True)


def generar_tablas(resp) -> bytes:
    """Excel de respuestas de tráfico (JAC / OACI): resumen, una hoja por tabla y gráfico."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    f = _formatos(wb)
    ws = wb.add_worksheet("Resumen")
    ws.set_column("A:A", 110)
    ws.write("A1", "Agente Ingresos – Tráfico aéreo", f["titulo"])
    ws.write("A2", f"Generado el {datetime.now():%d-%m-%Y %H:%M}", f["nota"])
    ws.write("A4", "Pregunta: " + resp.pregunta, f["txt"])
    import re as _re

    for i, p in enumerate(resp.resena, start=5):
        limpio = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", p.replace("**", ""))
        ws.write(i, 0, limpio, f["txt"])
        ws.set_row(i, 15 * max(1, len(limpio) // 120 + 1))
    hojas = {}
    for nombre, df in resp.tablas.items():
        hoja = _re.sub(r"[\[\]:*?/\\]", "", nombre)[:31]
        w = wb.add_worksheet(hoja)
        w.set_column(0, len(df.columns), 18)
        w.write("A1", nombre, f["subtitulo"])
        pct = {c: "pct" for c in df.columns if str(c).startswith(("Var", "Variación", "Participación", "ASK", "RPK"))}
        _tabla(w, 2, 0, df, f, pct)
        hojas[nombre] = (hoja, df)
    g = resp.grafico
    if g is not None:
        hoja, df = next(((h, d) for h, d in hojas.values() if g["x"] in d.columns and all(s in d.columns for s in g["series"])),
                        (None, None))
        if hoja:
            ch = wb.add_chart({"type": "column"})
            n = len(df)
            colx = list(df.columns).index(g["x"])
            for k, s in enumerate(g["series"]):
                cs = list(df.columns).index(s)
                ch.add_series({"name": s, "categories": [hoja, 3, colx, 2 + n, colx], "values": [hoja, 3, cs, 2 + n, cs],
                               "fill": {"color": [CELESTE, NARANJO, "#1BAF7A"][k % 3]}})
            ch.set_title({"name": g["titulo"], "name_font": {"size": 12}})
            ch.set_legend({"position": "bottom"})
            ch.set_size({"width": 760, "height": 360})
            ws.insert_chart(len(resp.resena) + 7, 0, ch)
    wb.close()
    return buf.getvalue()
