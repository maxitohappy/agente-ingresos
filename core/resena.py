"""Reseña automática (texto) de cada resultado, a partir de plantillas."""
from __future__ import annotations

from .formato import millones, numero, porcentaje
from .simulador import EMBARQUE, Resultado, texto_meses


def _nivel(r: Resultado, empieza: str):
    f = r.niveles[r.niveles["Nivel"].str.startswith(empieza)]
    return f.iloc[0] if not f.empty else None


def generar(r: Resultado, contexto: list[dict] | None = None) -> list[str]:
    """Párrafos en Markdown."""
    c = r.consulta
    periodo = texto_meses(r)
    sel = r.niveles.iloc[0]
    parrafos = []
    if r.es_simulacion:
        verbo = "reduce" if sel["Diferencia"] < 0 else "aumenta"
        parrafos.append(
            f"**{r.titulo}.** En {periodo}, el escenario {verbo} los ingresos de la selección en "
            f"**{millones(abs(sel['Diferencia']))}** ({porcentaje(sel['Variación'], signo=True)}): de "
            f"{millones(sel['Base'])} a {millones(sel['Escenario'])}.")
        total = r.niveles.iloc[-1]
        conc = _nivel(r, f"{c.concepto} – todas") if c.concepto else None
        partes = []
        if conc is not None and conc["Nivel"] != sel["Nivel"]:
            partes.append(f"{porcentaje(conc['Variación'], 2, True)} en el total de {c.concepto} "
                          f"({millones(conc['Base'])})")
        partes.append(f"{porcentaje(total['Variación'], 2, True)} en el total de ingresos de la DGAC "
                      f"({millones(total['Base'])})")
        parrafos.append("Efecto sobre los totales: " + " y ".join(partes) + ".")
        if c.concepto == EMBARQUE and r.pasajeros_base:
            txt = (f"Se estiman **{numero(r.pasajeros_base)} pasajeros embarcados** en la selección "
                   f"(monto ÷ tarifa vigente de cada mes, según el tarifario DGAC).")
            if abs(r.pasajeros_escenario - r.pasajeros_base) > 0.5:
                dp = r.pasajeros_escenario / r.pasajeros_base - 1
                txt += (f" Con el supuesto de demanda, los pasajeros {'aumentan' if dp > 0 else 'disminuyen'} "
                        f"{porcentaje(abs(dp))} ({numero(abs(r.pasajeros_escenario - r.pasajeros_base))} pasajeros).")
            parrafos.append(txt)
            # Variación de tarifa promedio y pasajeros necesarios para compensar.
            d = r.detalle
            base_dir = (d["pax"] * d["tarifa_nueva"] * d["tc_fila"].where(d["moneda_tarifa"] == "USD", 1)).sum()
            if d["monto"].sum() and base_dir:
                delta = base_dir / d["monto"].sum() - 1
                if delta < -0.0001 and delta > -0.999:
                    necesario = -delta / (1 + delta)
                    parrafos.append(
                        f"La tarifa promedio cae {porcentaje(abs(delta))}. Para compensar íntegramente la menor "
                        f"recaudación, los pasajeros deberían crecer **{porcentaje(necesario)}** (elasticidad de "
                        f"equilibrio {numero(1 / (1 + delta), 2)}).")
        if len(r.por_unidad) > 1 and r.es_simulacion:
            top = r.por_unidad.reindex(r.por_unidad["diferencia"].abs().sort_values(ascending=False).index).head(3)
            parrafos.append("Unidades más afectadas: " + "; ".join(
                f"{u.unidad} ({millones(u.diferencia)})" for u in top.itertuples()) + ".")
    else:
        parrafos.append(f"**{r.titulo}.** En {periodo} los ingresos suman **{millones(sel['Base'])}**.")
        conc = _nivel(r, f"{c.concepto} – todas") if c.concepto else None
        tot_u = _nivel(r, "Total de ingresos – ") if c.unidades else None
        total = r.niveles.iloc[-1]
        partes = []
        if conc is not None and conc["Nivel"] != sel["Nivel"] and conc["Base"]:
            partes.append(f"{porcentaje(sel['Base'] / conc['Base'], 2)} del total de {c.concepto} ({millones(conc['Base'])})")
        if tot_u is not None and tot_u["Nivel"] != sel["Nivel"] and tot_u["Base"]:
            partes.append(f"{porcentaje(sel['Base'] / tot_u['Base'], 1)} de los ingresos de la(s) unidad(es)")
        if total["Base"] and total["Nivel"] != sel["Nivel"]:
            partes.append(f"{porcentaje(sel['Base'] / total['Base'], 2)} de los ingresos totales de la DGAC")
        if partes:
            parrafos.append("Representa el " + ", el ".join(partes) + ".")
        if not r.por_mes.empty and len(r.por_mes) > 1:
            mx = r.por_mes.loc[r.por_mes["monto"].idxmax()]
            mn = r.por_mes.loc[r.por_mes["monto"].idxmin()]
            parrafos.append(f"Mes de mayor ingreso: {mx['Mes']} ({millones(mx['monto'])}); menor: {mn['Mes']} "
                            f"({millones(mn['monto'])}).")
        if c.concepto == EMBARQUE and r.pasajeros_base:
            parrafos.append(f"Pasajeros embarcados estimados: **{numero(r.pasajeros_base)}**.")
    for ctx in contexto or []:
        if ctx["texto"].startswith("No indicaste"):
            parrafos.insert(1, ctx["texto"])
        else:
            parrafos.append(ctx["texto"])
    return parrafos
