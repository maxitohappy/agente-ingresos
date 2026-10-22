"""Carga de ingresos: agregado público o Excel transaccional subido por el usuario.

El Excel original (una fila por documento) se agrega por mes × unidad × concepto × descripción ×
código de tasa × moneda. El agregado no contiene clientes, RUT, números de documento ni detalle,
y es lo único que se publica en el repositorio.
"""
from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_AGREGADO = RAIZ / "datos" / "ingresos_agregados.csv"

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
         "Octubre", "Noviembre", "Diciembre"]
CONCEPTOS = ["Derecho de Embarque", "Tasas", "Combustible", "Concesiones", "Otros Ingresos"]

# Columnas del Excel transaccional -> nombre interno.
COLUMNAS = {
    "UNIDAD_PRESTACION_SERVICIO_": "unidad_cod",
    "DESC_UNID_PRESTACION_SERVICIO_": "unidad",
    "MES_": "mes",
    "Concepto": "concepto",
    "Categoria": "categoria",
    "Subproducto": "subproducto",
    "Descripcion": "descripcion",
    "TASA_": "tasa",
    "MONEDA_": "moneda",
    "Tipo de Ingreso": "tipo_ingreso",
    "MONTO_": "monto",
    "TIPO_DE_CAMBIO_": "tipo_cambio",
}
CLAVES = ["anio", "mes", "unidad_cod", "unidad", "concepto", "categoria", "subproducto", "descripcion",
          "tasa", "moneda", "tipo_ingreso"]


def limpiar_texto(s) -> str:
    """Quita espacios sobrantes y repara la Ñ que el sistema exporta como 'ﾑ'."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s).replace("ﾑ", "Ñ").replace("�", "Ñ")
    return re.sub(r"\s+", " ", s).strip()


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def agregar(df: pd.DataFrame, anio: int | None = None) -> pd.DataFrame:
    """Agrega el Excel transaccional. Para filas en dólares guarda también el monto en USD."""
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ValueError("Al Excel le faltan columnas: " + ", ".join(faltan))
    d = df[list(COLUMNAS)].rename(columns=COLUMNAS)
    d = d[d["monto"].notna() & d["mes"].notna()].copy()
    col_anio = next((c for c in df.columns if sin_tildes(limpiar_texto(c)).upper() in ("ANO", "AÑO", "ANIO")), None)
    if col_anio is not None:
        d["anio"] = df.loc[d.index, col_anio].astype(int)
    else:
        d["anio"] = anio or pd.Timestamp.today().year
    for c in ["unidad", "concepto", "categoria", "subproducto", "descripcion", "moneda", "tipo_ingreso"]:
        d[c] = d[c].map(limpiar_texto)
    d["mes"] = d["mes"].astype(int)
    d["unidad_cod"] = d["unidad_cod"].astype(int)
    d["tasa"] = pd.to_numeric(d["tasa"], errors="coerce").fillna(0).astype(int)
    en_usd = (d["moneda"] == "D") & d["tipo_cambio"].gt(0)
    d["monto_usd"] = 0.0
    d.loc[en_usd, "monto_usd"] = d.loc[en_usd, "monto"] / d.loc[en_usd, "tipo_cambio"]
    d["documentos"] = 1
    g = d.groupby(CLAVES, dropna=False, as_index=False)[["monto", "monto_usd", "documentos"]].sum()
    g["monto"] = g["monto"].round(0)
    g["monto_usd"] = g["monto_usd"].round(2)
    return g.sort_values(CLAVES).reset_index(drop=True)


def leer_excel(contenido: bytes | str | Path) -> pd.DataFrame:
    """Lee el Excel transaccional (primera hoja con las columnas esperadas) y lo agrega."""
    origen = io.BytesIO(contenido) if isinstance(contenido, bytes) else contenido
    hojas = pd.read_excel(origen, sheet_name=None)
    for hoja in hojas.values():
        if "MONTO_" in hoja.columns and "Concepto" in hoja.columns:
            return agregar(hoja)
    raise ValueError("No se encontró una hoja con las columnas MONTO_ y Concepto.")


def cargar_agregado(ruta: Path = ARCHIVO_AGREGADO) -> pd.DataFrame:
    df = pd.read_csv(ruta, sep=";", encoding="utf-8")
    df["unidad"] = df["unidad"].fillna("")
    for c in ["categoria", "subproducto", "descripcion", "tipo_ingreso", "moneda"]:
        df[c] = df[c].fillna("")
    return df


def guardar_agregado(df: pd.DataFrame, ruta: Path = ARCHIVO_AGREGADO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, sep=";", index=False, encoding="utf-8")


def catalogo_unidades(df: pd.DataFrame) -> pd.DataFrame:
    """Unidades con su total, ordenadas de mayor a menor."""
    return (df.groupby(["unidad_cod", "unidad"], as_index=False)["monto"].sum()
            .sort_values("monto", ascending=False).reset_index(drop=True))


def tipo_cambio_mensual(df: pd.DataFrame) -> dict[tuple[int, int], float]:
    """Tipo de cambio implícito de cada mes en las filas en dólares (CLP por USD)."""
    d = df[(df["moneda"] == "D") & (df["monto_usd"] > 0)]
    g = d.groupby(["anio", "mes"])[["monto", "monto_usd"]].sum()
    return {(int(a), int(m)): float(r.monto / r.monto_usd) for (a, m), r in g.iterrows()}


def meses_disponibles(df: pd.DataFrame) -> list[tuple[int, int]]:
    return sorted({(int(a), int(m)) for a, m in df[["anio", "mes"]].drop_duplicates().itertuples(index=False)})
