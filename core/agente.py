"""Orquestador del agente: pregunta -> interpretación -> indicadores -> cálculo -> reseña."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from . import backend, indicadores, interprete, resena, simulador
from .formato import millones, numero, porcentaje
from .indicadores import CATALOGO, Valor
from .interprete import Consulta

EJEMPLOS = [
    "¿Cómo impacta en el total de ingresos una rebaja de 5 dólares del derecho de embarque?",
    "¿Cómo impacta en el derecho de embarque de Punta Arenas una rebaja de 5 dólares aplicada solo a Punta Arenas "
    "para fomentar el turismo, con elasticidad 0,5?",
    "Sube 10% las tasas de aterrizaje internacional entre marzo y agosto",
    "¿Cuánto representa Calama en el total de concesiones?",
    "Eliminar el derecho de embarque nacional en la región de Aysén durante el primer semestre",
    "Si el embarque internacional baja a 20 dólares en Santiago y los pasajeros aumentan 4%, ¿cuánto se recauda en el año completo?",
    "El PIB regional de Magallanes 2024 es 5.900 miles de millones",
]


@dataclass
class Faltante:
    indicador: str
    region: str | None
    periodo: str
    motivo: str
    obligatorio: bool

    @property
    def nombre(self) -> str:
        n = CATALOGO.get(self.indicador, {}).get("nombre", self.indicador)
        return f"{n} de {self.region}" if self.region else n

    @property
    def unidad(self) -> str:
        return CATALOGO.get(self.indicador, {}).get("unidad", "")


@dataclass
class Respuesta:
    pregunta: str
    consulta: Consulta
    resultado: simulador.Resultado | None = None
    resena: list[str] = field(default_factory=list)
    faltantes: list[Faltante] = field(default_factory=list)
    usados: list[Valor] = field(default_factory=list)
    mensaje: str = ""
    tc: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    fecha: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def resumen(self) -> str:
        if self.resultado is None:
            return self.mensaje[:200]
        sel = self.resultado.niveles.iloc[0]
        if self.resultado.es_simulacion:
            return (f"{millones(sel['Diferencia'])} ({porcentaje(sel['Variación'], signo=True)}) en "
                    f"{sel['Nivel']}; total ingresos {porcentaje(self.resultado.niveles.iloc[-1]['Variación'], 2, True)}")
        return f"{sel['Nivel']}: {millones(sel['Base'])}"


def _catalogo(df: pd.DataFrame) -> dict[int, str]:
    return dict(zip(df["unidad_cod"], df["unidad"]))


def interpretar(pregunta: str, df: pd.DataFrame, usar_ia: bool = True) -> Consulta:
    cat = _catalogo(df)
    c = interprete.interpretar(pregunta, cat, int(df["anio"].max()))
    if usar_ia and backend.configurado() and (c.tipo == "desconocida" or c.confianza < 0.6):
        try:
            c = interprete.con_gemini(c, cat)
        except Exception as e:  # noqa: BLE001 - se sigue con las reglas
            c.notas.append(f"No se pudo consultar la IA ({e}).")
    return c


def guardar_dato(dato: dict, usuario: str = "") -> str:
    ind = dato["indicador"]
    v = Valor(indicador=indicadores.clave(ind, dato.get("region")), periodo=str(dato["periodo"]),
              valor=float(dato["valor"]), unidad=CATALOGO.get(ind, {}).get("unidad", ""),
              fuente=dato.get("fuente") or "Informado por el usuario en el chat", origen="usuario", usuario=usuario)
    destino = indicadores.guardar_en_memoria(v)
    return f"Guardé **{v.etiqueta} {v.periodo} = {numero(v.valor, 2).rstrip('0').rstrip(',')} {v.unidad}** en la {destino}. " \
           "Lo usaré automáticamente en las próximas consultas."


def _contexto(r: simulador.Resultado, df: pd.DataFrame, memoria, usados, faltantes) -> list[dict]:
    c = r.consulta
    salida = []
    meses = len(r.meses) + len(r.meses_proyectados)
    sel = r.niveles.iloc[0]
    monto = sel["Diferencia"] if r.es_simulacion else sel["Base"]
    if not monto or not meses:
        return salida
    anual = monto * 12 / meses
    ind, region = ("pib_regional", c.region) if c.region else ("pib", None)
    if c.unidades and not c.region:
        return salida
    v = indicadores.obtener(ind, region, memoria=memoria)
    if v is None:
        faltantes.append(Faltante(ind, region, str(c.anio - 1),
                                  f"para expresar el resultado como % del {'PIB regional' if region else 'PIB'}",
                                  obligatorio=False))
        return salida
    usados.append(v)
    pib_clp = v.valor * 1e9      # miles de millones -> pesos
    texto = (f"Contexto económico: {'el impacto' if r.es_simulacion else 'el ingreso'} anualizado "
             f"({millones(anual)}) equivale al **{porcentaje(abs(anual) / pib_clp, 3)}** del {v.etiqueta} "
             f"{v.periodo} ({numero(v.valor)} {v.unidad}; fuente: {v.cita()}).")
    salida.append({"texto": texto})
    return salida


def _ranking(r: simulador.Resultado, df: pd.DataFrame) -> list[dict]:
    c = r.consulta
    if r.es_simulacion or not c.concepto or len(c.unidades) != 1:
        return []
    meses = r.meses
    d = df[(df["anio"] == c.anio) & df["mes"].isin(meses) & (df["concepto"] == c.concepto)]
    rk = d.groupby("unidad_cod")["monto"].sum().sort_values(ascending=False)
    if c.unidades[0] not in rk.index:
        return []
    pos = list(rk.index).index(c.unidades[0]) + 1
    return [{"texto": f"Ocupa el lugar **{pos} de {len(rk)}** unidades con ingresos por {c.concepto}."}]


def responder(pregunta: str, df: pd.DataFrame, tar: dict, tc_usuario: float | None = None,
              usar_ia: bool = True, usuario: str = "", consulta: Consulta | None = None) -> Respuesta:
    c = consulta or interpretar(pregunta, df, usar_ia)
    resp = Respuesta(pregunta=pregunta, consulta=c)
    if c.tipo == "dato" and c.dato:
        resp.mensaje = guardar_dato(c.dato, usuario)
        return resp
    if c.tipo == "desconocida":
        resp.mensaje = ("No logré interpretar la consulta. Indica qué concepto (derecho de embarque, tasas, "
                        "combustible, concesiones u otros ingresos), qué cambio (p. ej. 'rebaja de 5 dólares' o "
                        "'alza de 10%') y, si corresponde, qué aeropuerto o región y qué meses.")
        if not backend.configurado():
            resp.mensaje += " (La interpretación con IA no está activa: falta configurar el backend.)"
        return resp

    memoria = indicadores.listar_memoria()
    tc = c.tipo_cambio or tc_usuario
    if tc is None:
        v = indicadores.obtener("dolar", memoria=memoria)
        if v:
            tc = v.valor
            resp.usados.append(v)
    resp.tc = tc
    uf = utm = None
    for ind in ("uf", "utm"):
        if c.cambio_moneda == ind.upper():
            v = indicadores.obtener(ind, memoria=memoria)
            if v:
                resp.usados.append(v)
                uf, utm = (v.valor, utm) if ind == "uf" else (uf, v.valor)
    try:
        r = simulador.ejecutar(df, c, tar, tc=tc, uf=uf, utm=utm)
    except ValueError as e:
        codigo = str(e)
        if codigo == "FALTA_TC":
            resp.faltantes.append(Faltante("dolar", None, date.today().isoformat(),
                                           "para convertir el cambio tarifario entre dólares y pesos", True))
            resp.mensaje = "Necesito el tipo de cambio para calcular este escenario."
        elif codigo.startswith("FALTA_"):
            ind = codigo.split("_")[1].lower()
            resp.faltantes.append(Faltante(ind, None, date.today().isoformat()[:7], "para convertir el monto", True))
            resp.mensaje = f"Necesito el valor de la {ind.upper()} para calcular este escenario."
        elif codigo == "SOLO_PORCENTAJE":
            resp.mensaje = (f"Para {c.concepto} solo puedo simular variaciones porcentuales (los cobros dependen de "
                            "toneladas, kilómetros o contratos que la planilla no trae). Prueba, por ejemplo, "
                            f"'alza de 5% en {c.concepto.lower()}'.")
        else:
            raise
        return resp
    resp.resultado = r
    contexto = _ranking(r, df) + _contexto(r, df, memoria, resp.usados, resp.faltantes)
    resp.resena = resena.generar(r, contexto)
    for v in resp.usados:
        r.supuestos.append((v.etiqueta, f"{numero(v.valor, 2)} {v.unidad}", v.cita()))
    return resp
