"""Indicadores económicos: fuentes públicas -> memoria del usuario -> preguntar.

Orden de búsqueda de un indicador:
  1. Fuentes públicas en línea (mindicador.cl, API CMF, API BDE del Banco Central; en el navegador
     a través del backend). Se guardan en caché local por 6 horas.
  2. Memoria: valores que algún usuario ingresó antes (hoja compartida del backend, o archivo local).
  3. Respaldo publicado en datos/indicadores.json (últimos valores públicos conocidos, con fecha).
  4. Si nada de lo anterior existe, la app pide el valor al usuario y lo guarda en la memoria.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from . import almacen, backend, red
from .datos import RAIZ

RESPALDO = RAIZ / "datos" / "indicadores.json"
CACHE = "indicadores_cache.json"
MEMORIA_LOCAL = "memoria_indicadores.json"
HORAS_CACHE = 6

CATALOGO = {
    "dolar": {"nombre": "Dólar observado", "unidad": "CLP por USD", "frecuencia": "diaria"},
    "euro": {"nombre": "Euro", "unidad": "CLP por EUR", "frecuencia": "diaria"},
    "uf": {"nombre": "Unidad de Fomento (UF)", "unidad": "CLP", "frecuencia": "diaria"},
    "utm": {"nombre": "Unidad Tributaria Mensual (UTM)", "unidad": "CLP", "frecuencia": "mensual"},
    "ipc": {"nombre": "IPC, variación mensual", "unidad": "%", "frecuencia": "mensual"},
    "imacec": {"nombre": "IMACEC, variación anual", "unidad": "%", "frecuencia": "mensual"},
    "tpm": {"nombre": "Tasa de Política Monetaria", "unidad": "%", "frecuencia": "diaria"},
    "desempleo": {"nombre": "Tasa de desempleo", "unidad": "%", "frecuencia": "mensual"},
    "pib": {"nombre": "PIB nacional anual (precios corrientes)", "unidad": "miles de millones de CLP",
            "frecuencia": "anual"},
    "pib_regional": {"nombre": "PIB regional anual (precios corrientes)", "unidad": "miles de millones de CLP",
                     "frecuencia": "anual"},
    "tarifa_pasaje": {"nombre": "Tarifa promedio del pasaje por tramo", "unidad": "CLP", "frecuencia": "anual"},
    "turistas": {"nombre": "Llegadas de turistas extranjeros", "unidad": "personas", "frecuencia": "anual"},
}
MINDICADOR = {"dolar": "dolar", "euro": "euro", "uf": "uf", "utm": "utm", "ipc": "ipc", "imacec": "imacec",
              "tpm": "tpm", "tasa_desempleo": "desempleo"}


@dataclass
class Valor:
    indicador: str            # clave del catálogo; regionales como "pib_regional|Magallanes"
    periodo: str              # "2026-10-20", "2026-10" o "2025"
    valor: float
    unidad: str = ""
    fuente: str = ""
    origen: str = "publico"   # publico | usuario | respaldo
    usuario: str = ""
    fecha_registro: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def etiqueta(self) -> str:
        base, _, region = self.indicador.partition("|")
        nombre = CATALOGO.get(base, {}).get("nombre", base)
        return f"{nombre} {region}".strip()

    def cita(self) -> str:
        if self.origen == "usuario":
            quien = f" por {self.usuario}" if self.usuario else ""
            return f"Ingresado{quien} el {self.fecha_registro[:10]} ({self.fuente or 'sin fuente indicada'})"
        if self.origen == "respaldo":
            return f"{self.fuente} (respaldo publicado, valor del {self.periodo})"
        return f"{self.fuente}, {self.periodo}"


def clave(indicador: str, region: str | None = None) -> str:
    return f"{indicador}|{region}" if region else indicador


# --- 1. Fuentes públicas -------------------------------------------------------------------

def _mindicador() -> list[Valor]:
    j = red.get_json("https://mindicador.cl/api", timeout=10)
    salida = []
    for codigo, ind in MINDICADOR.items():
        d = j.get(codigo)
        if isinstance(d, dict) and d.get("valor") is not None:
            fecha = str(d.get("fecha", ""))[:10]
            per = fecha if CATALOGO[ind]["frecuencia"] == "diaria" else fecha[:7]
            salida.append(Valor(ind, per, float(d["valor"]), CATALOGO[ind]["unidad"], "mindicador.cl"))
    return salida


def _cmf(clave_api: str) -> list[Valor]:
    salida = []
    for recurso, llave, ind in (("dolar", "Dolares", "dolar"), ("uf", "UFs", "uf"), ("utm", "UTMs", "utm"),
                                ("ipc", "IPCs", "ipc"), ("euro", "Euros", "euro")):
        j = red.get_json(f"https://api.cmfchile.cl/api-sbifv3/recursos_api/{recurso}",
                         {"apikey": clave_api, "formato": "json"}, timeout=20)
        obs = (j.get(llave) or [{}])[0]
        if obs.get("Valor"):
            v = float(str(obs["Valor"]).replace(".", "").replace(",", "."))
            per = obs["Fecha"][:10] if CATALOGO[ind]["frecuencia"] == "diaria" else obs["Fecha"][:7]
            salida.append(Valor(ind, per, v, CATALOGO[ind]["unidad"], "API CMF"))
    return salida


def consultar_publicos() -> tuple[list[Valor], list[str]]:
    """Lee las fuentes públicas en línea. Devuelve valores y mensajes de estado."""
    import os

    valores, estado = [], []
    if red.EN_NAVEGADOR:
        try:
            valores = _valores_de(backend.get("indicadores"))
            estado.append(f"backend: {len(valores)} valores")
        except Exception as e:  # noqa: BLE001
            estado.append(f"backend: {e}")
        return valores, estado
    for nombre, funcion in (("mindicador.cl", _mindicador),
                            ("API CMF", lambda: _cmf(os.environ["CMF_APIKEY"]) if os.environ.get("CMF_APIKEY") else [])):
        try:
            nuevos = funcion()
            valores += [v for v in nuevos if not any(x.indicador == v.indicador for x in valores)]
            estado.append(f"{nombre}: {len(nuevos)} valores")
        except Exception as e:  # noqa: BLE001
            estado.append(f"{nombre}: sin respuesta ({type(e).__name__})")
    return valores, estado


def _valores_de(filas) -> list[Valor]:
    return [Valor(**{k: d[k] for k in ("indicador", "periodo", "valor", "unidad", "fuente") if k in d})
            for d in filas or []]


def actualizar_cache(forzar: bool = False, precargados: list[dict] | None = None) -> list[str]:
    """Actualiza la caché de indicadores públicos (6 h). `precargados` viene de la llamada de inicio."""
    cache = almacen.leer_json(CACHE, {})
    if precargados is None and not forzar and cache.get("fecha"):
        if datetime.now() - datetime.fromisoformat(cache["fecha"]) < timedelta(hours=HORAS_CACHE):
            return cache.get("estado", [])
    if precargados is not None:
        valores, estado = _valores_de(precargados), [f"backend: {len(precargados)} valores"]
    else:
        valores, estado = consultar_publicos()
    if valores:
        cache = {"fecha": datetime.now().isoformat(timespec="seconds"), "estado": estado,
                 "valores": [asdict(v) for v in valores]}
    else:
        # Sin datos nuevos: se conserva la caché anterior pero se reintenta en 30 minutos.
        cache["estado"] = estado
        cache["fecha"] = (datetime.now() - timedelta(hours=HORAS_CACHE) + timedelta(minutes=30)).isoformat(
            timespec="seconds")
    almacen.escribir_json(CACHE, cache)
    return estado


def _publicos_en_cache() -> list[Valor]:
    return [Valor(**v) for v in almacen.leer_json(CACHE, {}).get("valores", [])]


_RESPALDO: list = []


def _respaldo() -> list[Valor]:
    if _RESPALDO:
        return _RESPALDO[0]
    try:
        j = json.loads(RESPALDO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hoy = date.today().isoformat()
    # Se descartan períodos futuros (ej. la UF ya publicada del mes siguiente).
    valores = [Valor(r["indicador"], r["periodo"], float(r["valor"]), r.get("unidad", ""), r.get("fuente", ""),
                     origen="respaldo") for r in j.get("registros", []) if str(r["periodo"]) <= hoy[:len(str(r["periodo"]))]]
    _RESPALDO.append(valores)
    return valores


# --- 2. Memoria del usuario ----------------------------------------------------------------

# Caché en memoria del proceso: evita ir al backend en cada cambio de página.
SEGUNDOS_MEMORIA = 300
_memoria = {"filas": None, "hora": 0.0}


def precargar_memoria(filas: list[dict]) -> None:
    import time

    _memoria.update(filas=filas, hora=time.time())


def _invalidar_memoria() -> None:
    _memoria.update(filas=None, hora=0.0)


def _filas_memoria() -> list[dict]:
    import time

    if _memoria["filas"] is not None and time.time() - _memoria["hora"] < SEGUNDOS_MEMORIA:
        return _memoria["filas"]
    filas = backend.get("memoria") or []
    precargar_memoria(filas)
    return filas


def listar_memoria() -> list[Valor]:
    if backend.configurado():
        try:
            filas = _filas_memoria()
            salida = []
            for f in filas:
                d = {k: str(f[k]) for k in Valor.__dataclass_fields__ if f.get(k) not in (None, "")}
                try:
                    d["valor"] = float(str(f["valor"]).replace(",", "."))
                except (KeyError, ValueError):
                    continue
                d["origen"] = "usuario"
                salida.append(Valor(**d))
            return salida
        except Exception:  # noqa: BLE001 - se usa la memoria local
            pass
    return [Valor(**v) for v in almacen.leer_json(MEMORIA_LOCAL, [])]


def guardar_en_memoria(v: Valor) -> str:
    v.origen = "usuario"
    d = asdict(v)
    destino = "memoria compartida"
    try:
        backend.post("guardar_memoria", {"registro": d})
    except Exception:  # noqa: BLE001
        destino = "memoria de este navegador"
    _invalidar_memoria()
    local = almacen.leer_json(MEMORIA_LOCAL, [])
    local.append(d)
    almacen.escribir_json(MEMORIA_LOCAL, local)
    return destino


def borrar_de_memoria(id_: str) -> None:
    try:
        backend.post("borrar_memoria", {"id": id_})
    except Exception:  # noqa: BLE001
        pass
    _invalidar_memoria()
    almacen.escribir_json(MEMORIA_LOCAL, [v for v in almacen.leer_json(MEMORIA_LOCAL, []) if v.get("id") != id_])


# --- Búsqueda --------------------------------------------------------------------------------

def _mejor(candidatos: list[Valor], periodo: str | None) -> Valor | None:
    if periodo:
        exactos = [v for v in candidatos if v.periodo == periodo]
        if exactos:
            return max(exactos, key=lambda v: v.fecha_registro)
        # Para un año se acepta el valor más reciente de ese año (ej. dólar de un día de 2026).
        del_periodo = [v for v in candidatos if str(v.periodo).startswith(periodo)]
        if del_periodo:
            return max(del_periodo, key=lambda v: (v.periodo, v.fecha_registro))
        return None
    if not candidatos:
        return None
    return max(candidatos, key=lambda v: (v.periodo, v.fecha_registro))


def obtener(indicador: str, region: str | None = None, periodo: str | None = None,
            memoria: list[Valor] | None = None) -> Valor | None:
    """Valor de un indicador siguiendo el orden: público -> memoria -> respaldo."""
    k = clave(indicador, region)
    elegido = None
    for fuente in (_publicos_en_cache, lambda: memoria if memoria is not None else listar_memoria(), _respaldo):
        v = _mejor([x for x in fuente() if x.indicador == k], periodo)
        # Manda la fuente de mayor prioridad, salvo que otra tenga un período más reciente
        # (ej. mindicador con un IPC desactualizado frente al respaldo).
        if v is not None and (elegido is None or str(v.periodo) > str(elegido.periodo)):
            elegido = v
    return elegido


def tabla_actual(memoria: list[Valor] | None = None):
    import pandas as pd

    filas = []
    vistos = set()
    for origen, valores in (("Fuente pública", _publicos_en_cache()),
                            ("Memoria (usuario)", memoria if memoria is not None else listar_memoria()),
                            ("Respaldo publicado", _respaldo())):
        for ind in sorted({v.indicador for v in valores}):
            if ind in vistos:
                continue
            v = _mejor([x for x in valores if x.indicador == ind], None)
            vistos.add(ind)
            filas.append({"Indicador": v.etiqueta, "Período": v.periodo, "Valor": v.valor, "Unidad": v.unidad,
                          "Origen": origen, "Fuente": v.cita()})
    return pd.DataFrame(filas)
