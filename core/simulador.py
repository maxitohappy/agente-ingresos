"""Cálculo de escenarios sobre el agregado de ingresos.

Derecho de embarque (cambio por pasajero, % o tarifa nueva):
    pasajeros   = monto ÷ tarifa del mes (en CLP; los internacionales en USD usan el monto en USD)
    pax nuevos  = pasajeros × (1 + var. pasajeros)  ó  pasajeros × (1 − elasticidad × Δ% tarifa)
    monto nuevo = pax nuevos × tarifa nueva (× tipo de cambio de la fila si la tarifa es en USD)
Otros conceptos: monto nuevo = monto × (1 + variación %).
Meses sin datos (si se pide el año completo): promedio mensual observado de pasajeros (embarque,
valorizado con la tarifa vigente de cada mes) o de monto (resto).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import tarifario
from .datos import MESES, meses_disponibles, tipo_cambio_mensual
from .interprete import Consulta

EMBARQUE = "Derecho de Embarque"


@dataclass
class Resultado:
    consulta: Consulta
    titulo: str
    meses: list[int]
    meses_proyectados: list[int]
    niveles: pd.DataFrame                 # Nivel, Base, Escenario, Diferencia, Variación
    por_unidad: pd.DataFrame
    por_mes: pd.DataFrame
    por_descripcion: pd.DataFrame
    detalle: pd.DataFrame                 # filas de cálculo (para la hoja con fórmulas)
    supuestos: list[tuple[str, str, str]] = field(default_factory=list)   # (supuesto, valor, fuente)
    avisos: list[str] = field(default_factory=list)
    pasajeros_base: float = 0.0
    pasajeros_escenario: float = 0.0
    es_simulacion: bool = True

    @property
    def impacto(self) -> float:
        return float(self.niveles["Diferencia"].iloc[0]) if not self.niveles.empty else 0.0


def _filtro(df: pd.DataFrame, c: Consulta, con_unidades: bool = True, con_concepto: bool = True) -> pd.Series:
    m = pd.Series(True, index=df.index)
    if con_concepto and c.concepto:
        m &= df["concepto"] == c.concepto
        if c.filtro_descripcion:
            m &= df["descripcion"].str.contains(c.filtro_descripcion, case=False, regex=False)
        if c.ambito != "todos":
            m &= df["tipo_ingreso"].str.lower() == c.ambito
    if con_unidades and c.unidades:
        m &= df["unidad_cod"].isin(c.unidades)
    return m


def _convertir(valor: float, de: str, a: str, tc: float | None, uf: float | None, utm: float | None) -> float:
    """Convierte un monto por pasajero entre monedas (CLP, USD, UF, UTM)."""
    if de == a:
        return valor
    clp = valor
    if de == "USD":
        clp = valor * tc
    elif de == "UF":
        clp = valor * uf
    elif de == "UTM":
        clp = valor * utm
    return clp / tc if a == "USD" else clp


def _proyectar(df: pd.DataFrame, anio: int, meses_futuros: list[int]) -> pd.DataFrame:
    """Filas de meses sin datos: promedio mensual observado por combinación."""
    if not meses_futuros:
        return df.iloc[0:0]
    disp = [m for a, m in meses_disponibles(df) if a == anio]
    claves = ["anio", "unidad_cod", "unidad", "concepto", "categoria", "subproducto", "descripcion", "tasa", "moneda",
              "tipo_ingreso"]
    base = df[df["anio"] == anio].groupby(claves, as_index=False)[["monto", "monto_usd", "pax"]].sum()
    for col in ("monto", "monto_usd", "pax"):
        base[col] = base[col] / max(len(disp), 1)
    filas = []
    for mes in meses_futuros:
        b = base.copy()
        b["mes"] = mes
        filas.append(b)
    p = pd.concat(filas, ignore_index=True)
    p["proyectado"] = True
    return p


def _pasajeros(df: pd.DataFrame, tar: dict) -> pd.DataFrame:
    """Agrega clase tarifaria, tarifa del mes, tipo de cambio de la fila y pasajeros inferidos."""
    d = df.copy()
    tc_mes = tipo_cambio_mensual(df)
    tc_prom = float(np.mean(list(tc_mes.values()))) if tc_mes else np.nan
    d["clase"] = None
    d["tarifa_base"] = np.nan
    d["moneda_tarifa"] = ""
    d["tc_fila"] = np.nan
    d["pax"] = 0.0
    emb = d["concepto"] == EMBARQUE
    memo: dict = {}
    for i in d.index[emb]:
        clase = tarifario.clase_de(d.at[i, "tasa"])
        if clase is None:
            continue
        a, m = int(d.at[i, "anio"]), int(d.at[i, "mes"])
        if (clase, a, m) not in memo:
            memo[(clase, a, m)] = tarifario.tarifa_mes(tar, clase, a, m)
        t = memo[(clase, a, m)]
        if not t:
            continue
        mon = tarifario.moneda(tar, clase)
        d.at[i, "clase"], d.at[i, "tarifa_base"], d.at[i, "moneda_tarifa"] = clase, t, mon
        if mon == "USD":
            if d.at[i, "monto_usd"] > 0:
                tc = d.at[i, "monto"] / d.at[i, "monto_usd"]
                d.at[i, "pax"] = d.at[i, "monto_usd"] / t
            else:
                tc = tc_mes.get((a, m), tc_prom)
                d.at[i, "pax"] = d.at[i, "monto"] / (t * tc)
            d.at[i, "tc_fila"] = tc
        else:
            d.at[i, "pax"] = d.at[i, "monto"] / t
    return d


def ejecutar(df: pd.DataFrame, c: Consulta, tar: dict, tc: float | None = None, uf: float | None = None,
             utm: float | None = None) -> Resultado:
    anio = c.anio if c.anio in df["anio"].unique() else int(df["anio"].max())
    disp = [m for a, m in meses_disponibles(df) if a == anio]
    pedidos = c.meses or disp
    meses = [m for m in pedidos if m in disp]
    futuros = [m for m in pedidos if m not in disp] if c.anualizar else []
    avisos = []
    sin_datos = [m for m in pedidos if m not in disp and not c.anualizar]
    if sin_datos:
        avisos.append("Sin datos para " + ", ".join(MESES[m - 1] for m in sin_datos) +
                      f" {anio}; se usan solo los meses disponibles (pide 'año completo' para proyectar).")
    if not meses and not futuros:
        meses = disp
    d = _pasajeros(df[(df["anio"] == anio) & df["mes"].isin(disp)], tar)
    d["proyectado"] = False
    proy = _proyectar(d, anio, futuros)
    if not proy.empty:
        # Embarque proyectado: pasajeros promedio × tarifa vigente de cada mes futuro.
        proy = proy.drop(columns=[c_ for c_ in ("clase", "tarifa_base", "moneda_tarifa", "tc_fila") if c_ in proy])
        proy["clase"] = proy["tasa"].map(lambda x: tarifario.clase_de(x))
        proy["tarifa_base"] = [tarifario.tarifa_mes(tar, k, anio, int(m)) if isinstance(k, str) else np.nan
                               for k, m in zip(proy["clase"], proy["mes"])]
        proy["moneda_tarifa"] = proy["clase"].map(lambda k: tarifario.moneda(tar, k) if isinstance(k, str) else "")
        tc_prom_obs = np.mean(list(tipo_cambio_mensual(df).values())) if tipo_cambio_mensual(df) else np.nan
        proy["tc_fila"] = np.where(proy["moneda_tarifa"] == "USD", tc or tc_prom_obs, np.nan)
        emb = proy["clase"].notna() & proy["tarifa_base"].notna()
        valor_pax = np.where(proy["moneda_tarifa"] == "USD", proy["tarifa_base"] * proy["tc_fila"], proy["tarifa_base"])
        proy.loc[emb, "monto"] = (proy["pax"] * valor_pax)[emb].round(0)
        if (proy["moneda_tarifa"] == "USD").any() and not tc:
            avisos.append("Meses proyectados en USD valorizados con el tipo de cambio promedio observado en la planilla.")
    d = pd.concat([d[d["mes"].isin(meses)], proy], ignore_index=True)

    afectado = _filtro(d, c)
    d["escenario"] = d["monto"].astype(float)
    d["pax_escenario"] = d["pax"].astype(float)
    d["tarifa_nueva"] = d["tarifa_base"]
    supuestos = []
    es_sim = c.tipo == "simulacion" and c.cambio_tipo is not None

    if es_sim and c.concepto == EMBARQUE and c.cambio_tipo in ("absoluto", "nuevo_valor", "porcentaje"):
        filas = d.index[afectado & d["clase"].notna()]
        if c.cambio_tipo == "nuevo_valor" and c.cambio_moneda:
            # "Bajar a USD 20" fija la tarifa de las clases cobradas en esa moneda; el resto no cambia.
            moneda_cambio = "USD" if c.cambio_moneda == "USD" else "CLP"
            otras = [i for i in filas if d.at[i, "moneda_tarifa"] != moneda_cambio]
            if otras:
                avisos.append(f"La tarifa nueva en {moneda_cambio} se aplicó solo a las clases cobradas en esa moneda; "
                              f"{len(otras)} filas de otras clases (${d.loc[otras, 'monto'].sum():,.0f}) "
                              "quedan sin cambio.".replace(",", "."))
                filas = [i for i in filas if i not in set(otras)]
                afectado = afectado.copy()
                afectado.loc[otras] = False
        necesita_tc = c.cambio_tipo != "porcentaje" and any(
            (c.cambio_moneda or "CLP") != ("CLP" if d.at[i, "moneda_tarifa"] == "CLP" else "USD") for i in filas)
        if necesita_tc and not tc:
            raise ValueError("FALTA_TC")
        if c.cambio_moneda in ("UF", "UTM") and not (uf if c.cambio_moneda == "UF" else utm):
            raise ValueError("FALTA_" + c.cambio_moneda)
        for i in filas:
            mon = d.at[i, "moneda_tarifa"]
            t0 = float(d.at[i, "tarifa_base"])
            if c.cambio_tipo == "porcentaje":
                t1 = t0 * (1 + c.cambio_valor / 100)
            elif c.cambio_tipo == "absoluto":
                t1 = t0 + _convertir(c.cambio_valor, c.cambio_moneda or "CLP", mon, tc, uf, utm)
            else:
                t1 = _convertir(c.cambio_valor, c.cambio_moneda or mon, mon, tc, uf, utm)
            t1 = max(t1, 0.0)
            delta = t1 / t0 - 1 if t0 else 0.0
            if c.var_pasajeros is not None:
                factor = 1 + c.var_pasajeros / 100
            elif c.elasticidad:
                factor = max(1 - c.elasticidad * delta, 0.0)
            else:
                factor = 1.0
            pax1 = d.at[i, "pax"] * factor
            valor = t1 * (d.at[i, "tc_fila"] if mon == "USD" else 1)
            d.at[i, "tarifa_nueva"], d.at[i, "pax_escenario"], d.at[i, "escenario"] = t1, pax1, pax1 * valor
        sin_clase = afectado & d["clase"].isna() & (d["concepto"] == EMBARQUE)
        if sin_clase.any() and c.cambio_tipo == "porcentaje":
            d.loc[sin_clase, "escenario"] = d.loc[sin_clase, "monto"] * (1 + c.cambio_valor / 100)
        elif sin_clase.any():
            avisos.append(f"{int(sin_clase.sum())} filas de embarque sin código de tasa conocido quedan sin cambio "
                          f"(${d.loc[sin_clase, 'monto'].sum():,.0f}).".replace(",", "."))
        if c.elasticidad and c.var_pasajeros is None:
            supuestos.append(("Elasticidad de pasajeros al derecho de embarque", f"{c.elasticidad:g}".replace(".", ","),
                              "Indicada por el usuario: Δ% pasajeros = −elasticidad × Δ% tarifa"))
        if c.var_pasajeros is not None:
            supuestos.append(("Variación de pasajeros", f"{c.var_pasajeros:+g}%".replace(".", ","), "Indicada por el usuario"))
        if not c.elasticidad and c.var_pasajeros is None:
            supuestos.append(("Pasajeros", "Sin cambio (impacto directo)", "Supuesto por defecto"))
    elif es_sim:
        if c.cambio_tipo != "porcentaje":
            raise ValueError("SOLO_PORCENTAJE")
        d.loc[afectado, "escenario"] = d.loc[afectado, "monto"] * (1 + c.cambio_valor / 100)

    d["diferencia"] = d["escenario"] - d["monto"]

    # Niveles de impacto: selección -> concepto completo -> total de ingresos.
    def fila(nombre, mascara):
        b, e = float(d.loc[mascara, "monto"].sum()), float(d.loc[mascara, "escenario"].sum())
        return {"Nivel": nombre, "Base": b, "Escenario": e, "Diferencia": e - b, "Variación": (e / b - 1) if b else 0.0}

    nombre_sel = _nombre_seleccion(c, d)
    niveles = [fila(nombre_sel, afectado)]
    if c.unidades and c.concepto:
        niveles.append(fila(f"{c.concepto} – {_nombre_unidades(c, d)} (todas sus líneas)",
                            _filtro(d, Consulta(texto="", concepto=c.concepto, unidades=c.unidades))))
    if c.unidades:
        niveles.append(fila(f"Total de ingresos – {_nombre_unidades(c, d)}", _filtro(d, c, con_concepto=False)))
    if c.concepto:
        niveles.append(fila(f"{c.concepto} – todas las unidades", d["concepto"] == c.concepto))
    niveles.append(fila("Total de ingresos – todas las unidades", pd.Series(True, index=d.index)))
    niveles = pd.DataFrame(niveles).drop_duplicates("Base", keep="first").reset_index(drop=True)

    sel = d[afectado]
    por_unidad = (sel.groupby("unidad", as_index=False)[["monto", "escenario", "diferencia", "pax", "pax_escenario"]]
                  .sum().sort_values("monto", ascending=False))
    total_concepto = d.loc[d["concepto"] == c.concepto, "monto"].sum() if c.concepto else d["monto"].sum()
    if not c.unidades:
        por_unidad["participacion"] = por_unidad["monto"] / total_concepto if total_concepto else 0
    else:
        base_conc = (d[_filtro(d, c, con_unidades=False)].groupby("unidad")["monto"].sum())
        por_unidad["participacion"] = por_unidad["monto"] / base_conc.sum() if base_conc.sum() else 0
    por_mes = sel.groupby("mes", as_index=False)[["monto", "escenario", "diferencia", "pax", "pax_escenario"]].sum()
    por_mes["proyectado"] = por_mes["mes"].isin(futuros)
    por_mes["Mes"] = por_mes["mes"].map(lambda m: MESES[m - 1])
    por_desc = (sel.groupby(["concepto", "descripcion"], as_index=False)[["monto", "escenario", "diferencia"]]
                .sum().sort_values("monto", ascending=False))

    columnas = ["unidad", "mes", "concepto", "descripcion", "tasa", "clase", "moneda", "moneda_tarifa", "tc_fila",
                "monto", "monto_usd", "tarifa_base", "pax", "tarifa_nueva", "pax_escenario", "escenario", "diferencia",
                "proyectado"]
    detalle = sel[columnas].sort_values(["unidad", "mes", "descripcion"]).reset_index(drop=True)

    if c.concepto == EMBARQUE and es_sim:
        for clase in sorted(set(sel["clase"].dropna())):
            v = tarifario.tarifa_en(tar, clase, pd.Timestamp.today().date())
            if v:
                supuestos.append((f"Tarifa vigente {tar['clases'][clase]['nombre']}",
                                  f"{tar['clases'][clase]['moneda']} {v['valor']:,.0f}".replace(",", "."), v.get("fuente", "")))
    if tc and (es_sim and c.cambio_tipo != "porcentaje" or futuros):
        supuestos.append(("Tipo de cambio para convertir el cambio tarifario", f"{tc:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), "Definido por el usuario (sugerido: dólar observado)"))
    if futuros:
        supuestos.append(("Meses proyectados", ", ".join(MESES[m - 1] for m in futuros),
                          "Promedio mensual observado de pasajeros/montos del año"))

    return Resultado(
        consulta=c, titulo=_titulo(c, d), meses=meses, meses_proyectados=futuros, niveles=niveles,
        por_unidad=por_unidad.reset_index(drop=True), por_mes=por_mes, por_descripcion=por_desc.reset_index(drop=True),
        detalle=detalle, supuestos=supuestos, avisos=avisos + list(c.notas),
        pasajeros_base=float(sel["pax"].sum()), pasajeros_escenario=float(sel["pax_escenario"].sum()),
        es_simulacion=es_sim,
    )


def _nombre_unidades(c: Consulta, d: pd.DataFrame) -> str:
    if c.region and len(c.unidades) > 1:
        return f"región de {c.region}"
    nombres = sorted(d.loc[d["unidad_cod"].isin(c.unidades), "unidad"].unique())
    return ", ".join(nombres) if nombres else "unidades seleccionadas"


def _nombre_seleccion(c: Consulta, d: pd.DataFrame) -> str:
    partes = [c.concepto or "Total de ingresos"]
    if c.filtro_descripcion:
        partes.append(f"({c.filtro_descripcion})")
    if c.ambito != "todos":
        partes.append(c.ambito + ("es" if c.ambito.endswith("l") else ""))
    if c.unidades:
        partes.append("– " + _nombre_unidades(c, d))
    else:
        partes.append("– todas las unidades")
    return " ".join(partes)


def _titulo(c: Consulta, d: pd.DataFrame) -> str:
    sel = _nombre_seleccion(c, d)
    if c.tipo == "simulacion" and c.cambio_tipo:
        d = c.descripcion_cambio()
        return f"{d[:1].upper()}{d[1:]} en {sel}"
    return sel


def texto_meses(r: Resultado) -> str:
    todos = sorted(r.meses + r.meses_proyectados)
    if not todos:
        return ""
    if todos == list(range(todos[0], todos[-1] + 1)) and len(todos) > 1:
        txt = f"{MESES[todos[0] - 1]} a {MESES[todos[-1] - 1]}"
    else:
        txt = ", ".join(MESES[m - 1] for m in todos)
    return f"{txt} {r.consulta.anio}" + (" (incluye meses proyectados)" if r.meses_proyectados else "")
