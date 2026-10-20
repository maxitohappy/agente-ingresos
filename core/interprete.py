"""Intérprete de consultas en lenguaje natural (reglas) con respaldo opcional de Gemini.

Convierte frases como "¿cómo impacta una rebaja de 5 dólares del derecho de embarque solo en
Punta Arenas?" en una `Consulta` estructurada. Si las reglas no alcanzan, se envía SOLO el texto
de la pregunta y el catálogo de nombres al backend (Gemini); nunca montos ni datos de la planilla.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from . import alias
from .datos import CONCEPTOS, sin_tildes

MESES_TXT = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
             "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
             "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9,
             "oct": 10, "nov": 11, "dic": 12}
NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
BAJA = r"rebaj\w*|reduc\w*|disminu\w*|baj[ae]\w*|descuento\w*|bajar|recort\w*|menos"
ALZA = r"alza\w*|aument\w*|sub[eiao]\w*|subir|increment\w*|reajust\w*|mas|encarec\w*|suba"
CERO = r"elimin\w*|exencion|exentar|exime\w*|eximir|gratuit\w*|suprim\w*|liber\w* (?:del|de) pago"
INTENCION = (r"\b(bajar|baja|bajen|rebajar|rebaja|rebajen|reducir|reduzca|reduccion|disminuir|disminucion|"
             r"descuento|subir|suba|alza|aumentar|aumento|incrementar|incremento|reajustar|modificar|cambiar)\b")
TRAFICO = (r"\b(jac|junta (?:de )?aeronautica|oaci|icao|trafico aereo|trafico de pasajeros|rutas?|aerolineas?|"
           r"operador(?:es)?|lineas aereas|capacidad aerea|ask|rpk|mercado aereo|estadisticas? de trafico)\b")


@dataclass
class Consulta:
    texto: str
    tipo: str = "desconocida"           # simulacion | consulta | trafico | dato | desconocida
    fuente: str | None = None           # trafico: jac | oaci | ambas
    concepto: str | None = None
    filtro_descripcion: str | None = None
    ambito: str = "todos"               # todos | nacional | internacional
    unidades: list[int] = field(default_factory=list)
    region: str | None = None
    meses: list[int] = field(default_factory=list)
    anio: int = 0
    anualizar: bool = False
    cambio_tipo: str | None = None      # absoluto | porcentaje | nuevo_valor
    cambio_valor: float = 0.0           # con signo: negativo = rebaja
    cambio_moneda: str | None = None    # USD | CLP | UF | UTM
    elasticidad: float | None = None    # magnitud; se aplica con signo negativo
    var_pasajeros: float | None = None  # % directo de variación de pasajeros
    sensibilidad: bool = False          # se pidió un cambio sin magnitud: escenario central + tabla de sensibilidad
    efecto_pasajeros: bool = False      # se pregunta por el efecto en pasajeros de una tasa que paga la aerolínea
    tipo_cambio: float | None = None
    dato: dict | None = None            # para tipo "dato": indicador, region, periodo, valor
    origen: str = "reglas"              # reglas | gemini | reglas+gemini
    confianza: float = 0.0
    notas: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, d: dict) -> "Consulta":
        campos = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in campos})

    def descripcion_cambio(self) -> str:
        if self.cambio_tipo is None:
            return "sin cambio tarifario"
        if self.cambio_tipo == "porcentaje":
            if self.cambio_valor == -100:
                return "eliminación (−100%)"
            return f"{'alza' if self.cambio_valor > 0 else 'rebaja'} de {abs(self.cambio_valor):g}%".replace(".", ",")
        mon = {"USD": "US$", "CLP": "$", "UF": "UF ", "UTM": "UTM "}.get(self.cambio_moneda or "", "")
        v = f"{abs(self.cambio_valor):,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")
        if self.cambio_tipo == "nuevo_valor":
            return f"nueva tarifa de {mon}{v}"
        return f"{'alza' if self.cambio_valor > 0 else 'rebaja'} de {mon}{v} por pasajero"


def normalizar(texto: str) -> str:
    t = sin_tildes(texto.lower())
    t = t.replace("us$", " usd ").replace("u$s", " usd ").replace("°", " ")
    t = re.sub(r"[¿?¡!;:\"“”()]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def numero(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        return float(s.replace(".", "").replace(",", "."))
    return float(s.replace(",", "."))


def _quitar(t: str, m: re.Match) -> str:
    return t[: m.start()] + " " * (m.end() - m.start()) + t[m.end():]


def _buscar_alias(t: str, pares: list[tuple[str, object]]) -> tuple[list, str]:
    """Busca alias (el más largo primero) como palabras completas y los borra del texto."""
    encontrados = []
    for a, valor in sorted(pares, key=lambda p: -len(p[0])):
        patron = r"(?<![\w])" + re.escape(a) + r"(?![\w])"
        m = re.search(patron, t)
        while m:
            if valor not in encontrados:
                encontrados.append(valor)
            t = _quitar(t, m)
            m = re.search(patron, t)
    return encontrados, t


def _pares_unidades(catalogo: dict[int, str] | None) -> list[tuple[str, int]]:
    pares = [(a, cod) for cod, (_, als) in alias.UNIDADES.items() for a in als]
    for cod, nombre in (catalogo or {}).items():
        n = normalizar(nombre)
        n2 = re.sub(r"^(ap|ad|e\.a)\.?\s*", "", n).strip()
        pares += [(n, cod)] + ([(n2, cod)] if len(n2) > 3 else [])
    return pares


def _meses(t: str, consulta: Consulta) -> str:
    if re.search(r"\b(anual\w*|ano completo|todo el ano|12 meses|doce meses|cierre del? ano|ano 20\d\d completo)\b", t):
        consulta.anualizar = True
        consulta.meses = list(range(1, 13))
    rangos = {r"primer trimestre|1er trimestre|1 trimestre|q1": [1, 2, 3],
              r"segundo trimestre|2do trimestre|2 trimestre|q2": [4, 5, 6],
              r"tercer trimestre|3er trimestre|3 trimestre|q3": [7, 8, 9],
              r"cuarto trimestre|4to trimestre|4 trimestre|q4": [10, 11, 12],
              r"primer semestre|1er semestre": list(range(1, 7)), r"segundo semestre|2do semestre": list(range(7, 13)),
              r"verano|temporada alta": [1, 2, 12], r"invierno|vacaciones de invierno": [7, 8]}
    for patron, meses in rangos.items():
        m = re.search(r"\b(" + patron + r")\b", t)
        if m:
            consulta.meses = sorted(set(consulta.meses) | set(meses)) if not consulta.anualizar else consulta.meses
            t = _quitar(t, m)
    nombres = "|".join(sorted(MESES_TXT, key=len, reverse=True))
    m = re.search(rf"\b(?:entre|desde|de)\s+({nombres})\s+(?:y|a|hasta)\s+({nombres})\b", t)
    if m:
        a, b = MESES_TXT[m.group(1)], MESES_TXT[m.group(2)]
        consulta.meses = list(range(a, b + 1)) if a <= b else list(range(a, 13)) + list(range(1, b + 1))
        consulta.anualizar = False
        return _quitar(t, m)
    sueltos = [MESES_TXT[x] for x in re.findall(rf"\b({nombres})\b", t)
               if not (x in ("mar", "may") and not re.search(rf"\b(en|de|y|,)\s+{x}\b", t))]
    if sueltos and not consulta.anualizar:
        consulta.meses = sorted(set(consulta.meses) | set(sueltos))
    return t


def _dato(t: str, original: str) -> dict | None:
    """Detecta 'el PIB regional de Magallanes 2025 es 5.200 (miles de millones)' para guardarlo."""
    m = re.search(r"\b(pib|producto interno bruto|turistas|uf|utm|dolar|ipc|imacec|desempleo)\b(.*?)"
                  r"\b(es|era|fue|son|fueron|vale|=|equivale a|alcanzo|asciende a)\s*(?:de\s*)?\$?\s*" + NUM, t)
    if not m or re.search(r"\b(rebaj|aument|impact|simul|si se|que pasa)", t):
        return None
    ind = {"producto interno bruto": "pib"}.get(m.group(1), m.group(1))
    resto = m.group(2)
    region = None
    if ind == "pib":
        regiones, _ = _buscar_alias(resto, list(alias.ALIAS_REGION.items()))
        if not regiones:
            unidades, _ = _buscar_alias(resto, _pares_unidades(None))
            regiones = [alias.UNIDADES[u][0] for u in unidades]
        if regiones or "regional" in resto:
            ind, region = "pib_regional", (regiones[0] if regiones else None)
    anio = re.search(r"\b((?:19|20)\d\d)\b", resto)
    periodo = anio.group(1) if anio else (str(date.today().year - 1) if ind.startswith("pib") or ind == "turistas"
                                          else date.today().isoformat()[:7])
    valor = numero(m.group(4))
    escala = t[m.end(): m.end() + 40]
    if re.search(r"\b(billon|billones)\b", escala):
        valor *= 1000          # billones de pesos -> miles de millones
    elif re.search(r"\bmillones\b", escala) and "miles de millones" not in escala and ind.startswith("pib"):
        valor /= 1000          # millones -> miles de millones
    return {"indicador": ind, "region": region, "periodo": periodo, "valor": valor, "texto": original}


def interpretar(texto: str, catalogo_unidades: dict[int, str] | None = None, anio_datos: int | None = None) -> Consulta:
    c = Consulta(texto=texto, anio=anio_datos or date.today().year)
    t = normalizar(texto)

    d = _dato(t, texto)
    if d:
        c.tipo, c.dato, c.confianza = "dato", d, 0.9
        return c

    # Supuestos explícitos: elasticidad, tipo de cambio, variación de pasajeros.
    m = re.search(r"elasticidad(?:\s+precio)?(?:\s+de(?:\s+la\s+demanda)?)?\s*(?:de|del|igual a|=|es)?\s*(-?\s*" + NUM + ")", t)
    if m:
        c.elasticidad = abs(numero(m.group(2)))
        t = _quitar(t, m)
    m = re.search(r"(?:tipo de cambio|\btc\b|dolar(?:\s+observado)?|valor del dolar)\s*(?:de|a|=|en|es|del?)?\s*\$?\s*"
                  r"(\d{3}(?:[.,]\d+)?|1\.\d{3}(?:,\d+)?)\b(?!\s*%)", t)
    if m and 300 <= numero(m.group(1)) <= 2000:
        c.tipo_cambio = numero(m.group(1))
        t = _quitar(t, m)
    m = re.search(r"(?:pasajeros|demanda|trafico|flujo de pasajeros|turistas)\s+(?:\w+\s+){0,3}?"
                  r"(aument\w*|crec\w*|sub\w*|disminu\w*|ca[ei]\w*|baj\w*)?\s*(?:en|un|de)?\s*(?:un\s+)?" + NUM + r"\s*%", t)
    if m:
        signo = -1 if m.group(1) and re.match(r"disminu|ca|baj", m.group(1)) else 1
        c.var_pasajeros = signo * numero(m.group(2))
        t = _quitar(t, m)

    m = re.search(r"\b(20\d\d)\b", t)
    if m:
        c.anio = int(m.group(1))
        t = _quitar(t, m)
    t = _meses(t, c)

    # Unidades y regiones.
    regiones, t = _buscar_alias(t, [(a, r) for a, r in alias.ALIAS_REGION.items() if " " in a or a in (
        "magallanes", "aysen", "aisen", "araucania", "biobio", "maule", "nuble", "coquimbo", "tarapaca", "metropolitana",
        "ohiggins", "o'higgins")] + [("region de " + sin_tildes(r.lower()), r) for r in set(alias.ALIAS_REGION.values())]
        + [("region del " + sin_tildes(r.lower()), r) for r in set(alias.ALIAS_REGION.values())])
    unidades, t = _buscar_alias(t, _pares_unidades(catalogo_unidades))
    if regiones:
        c.region = regiones[0]
        c.unidades = sorted({u for u, (r, _) in alias.UNIDADES.items() if r in regiones} | set(unidades))
    else:
        c.unidades = unidades
        regs = {alias.UNIDADES[u][0] for u in unidades if u in alias.UNIDADES}
        c.region = regs.pop() if len(regs) == 1 else None

    # Ámbito nacional / internacional.
    t = re.sub(r"\b(a nivel nacional|nivel nacional|todo el pais|a nivel pais|total nacional|red nacional)\b", " ", t)
    nac = re.search(r"\b(nacional\w*|domestic\w*)\b", t)
    inter = re.search(r"\b(internacional\w*|extranjer\w*)\b", t)
    if nac and not inter:
        c.ambito = "nacional"
    elif inter and not nac:
        c.ambito = "internacional"

    # Concepto y filtro de descripción.
    for palabra, filtro in sorted(alias.DESCRIPCIONES.items(), key=lambda p: -len(p[0])):
        if re.search(r"\b" + re.escape(palabra) + r"\b", t):
            c.filtro_descripcion = filtro
            break
    conceptos, _ = _buscar_alias(t, [(a, k) for k, als in alias.CONCEPTOS.items() for a in als])
    if conceptos:
        c.concepto = conceptos[0]
    if re.search(r"\b(total de ingresos|ingresos totales|total general|todos los conceptos)\b", t) and not conceptos:
        c.concepto = None

    # Cambio tarifario.
    if re.search(r"\b(" + CERO + r")\b", t):
        c.cambio_tipo, c.cambio_valor = "porcentaje", -100.0
    else:
        monedas = r"(usd|dolares|dolar|us|pesos|clp|peso|uf|utm|%|por ciento|porciento)"
        m_nuevo = re.search(r"\b(?:a|en|de)\s+(?:usd\s*)?" + NUM + r"\s*" + monedas + r"?\s*(?:por pasajero)?\s*"
                            r"(?:en vez de|en lugar de)", t) or re.search(
            r"\b(?:fij|dej|qued|llev|baj|sub|rebaj|aument|pas|cambi|reduc|disminu)\w*\s+"
            r"(?:la tarifa|el derecho|la tasa|el valor)?[^\d]{0,30}?\ba\s+(?:usd\s*|\$\s*)?" + NUM + r"\s*" + monedas + r"?", t)
        m_cant = None
        for m in re.finditer(r"(usd|\$)?\s*" + NUM + r"\s*" + monedas + r"?", t):
            if m.group(1) or m.group(3):
                m_cant = m
                break
        if m_nuevo and not re.search(r"\b(" + BAJA + "|" + ALZA + r")\s+(de|en)\s+(usd\s*)?\d", t):
            c.cambio_tipo = "nuevo_valor"
            c.cambio_valor = numero(m_nuevo.group(1))
            mon = m_nuevo.group(2) or ""
            c.cambio_moneda = _moneda(mon) or ("USD" if re.search(r"\busd\b", m_nuevo.group(0)) else None)
        elif m_cant:
            mon = m_cant.group(3) or ("usd" if m_cant.group(1) == "usd" else "pesos" if m_cant.group(1) == "$" else "")
            valor = numero(m_cant.group(2))
            antes = t[max(0, m_cant.start() - 60): m_cant.start()]
            despues = t[m_cant.end(): m_cant.end() + 25]
            signo = 0
            if re.search(r"\b(" + BAJA + r")\b", antes) or re.search(r"\b(" + BAJA + r")\b", despues):
                signo = -1
            if re.search(r"\b(" + ALZA + r")\b", antes) or re.search(r"\b(" + ALZA + r")\b", despues):
                signo = 1 if signo == 0 or re.search(r"\b(" + ALZA + r")\b", antes[-25:]) else signo
            if signo == 0 and re.search(r"\b(" + BAJA + r")\b", t):
                signo = -1
            elif signo == 0 and re.search(r"\b(" + ALZA + r")\b", t):
                signo = 1
            if signo:
                if _moneda(mon) == "%":
                    c.cambio_tipo, c.cambio_valor = "porcentaje", signo * valor
                else:
                    c.cambio_tipo, c.cambio_valor = "absoluto", signo * valor
                    c.cambio_moneda = _moneda(mon)
    if c.cambio_tipo == "absoluto" and c.cambio_moneda is None:
        c.cambio_moneda = "USD" if c.cambio_valor and abs(c.cambio_valor) < 100 else "CLP"
        c.notas.append(f"No se indicó la moneda; se asumió {c.cambio_moneda}.")

    # Intención de cambio sin magnitud ("bajar la tasa de aterrizaje"): escenario central ±10% y sensibilidad.
    if c.cambio_tipo is None and (c.concepto or c.filtro_descripcion) and re.search(INTENCION, t):
        signo = -1 if re.search(r"\b(" + BAJA + "|" + CERO + r")\b", t) else 1
        c.cambio_tipo, c.cambio_valor, c.sensibilidad = "porcentaje", signo * 10.0, True
        if c.concepto is None:
            c.concepto = "Tasas"
    if c.cambio_tipo:
        c.tipo = "simulacion"
        if c.concepto is None:
            if re.search(r"\b(embarque|pasajer)", t):
                c.concepto = "Derecho de Embarque"
            elif c.cambio_tipo in ("absoluto", "nuevo_valor"):
                c.concepto = "Derecho de Embarque"
                c.notas.append("No se indicó el concepto; un monto por pasajero corresponde al derecho de embarque.")
        if c.concepto != "Derecho de Embarque" and c.cambio_tipo in ("absoluto", "nuevo_valor"):
            c.notas.append("Para conceptos distintos del derecho de embarque solo se pueden simular cambios en %; "
                           "indica la variación porcentual.")
            c.confianza = 0.3
        else:
            c.confianza = 0.9 if c.concepto else 0.5
    elif re.search(TRAFICO, t) or re.search(r"\bpasajeros\b.*\bsegun\b", t):
        c.tipo = "trafico"
        oaci = bool(re.search(r"\b(oaci|icao|ask|rpk|mundial|latinoamerica|regional|regiones)\b", t))
        jac = bool(re.search(r"\b(jac|junta|rutas?|aerolineas?|operador|chile)\b", t)) or bool(c.unidades)
        c.fuente = "ambas" if oaci and jac else ("oaci" if oaci else "jac")
        c.confianza = 0.85
    elif re.search(r"\b(cuanto|cuantos|total|participacion|representa|ranking|ingreso|ingresos|muestra|mostrar|"
                   r"cual|cuales|monto|pasajeros|compar|evolucion|recaud|distribucion)\w*\b", t):
        c.tipo = "consulta"
        c.confianza = 0.8
    if c.elasticidad is None and c.var_pasajeros is None and re.search(r"fomentar|incentiv|estimular|turismo", t):
        c.notas.append("La consulta menciona fomento del turismo: puedes agregar una elasticidad (p. ej. "
                       "'con elasticidad 0,5') o un aumento de pasajeros (p. ej. 'pasajeros aumentan 5%').")
    if c.anualizar:
        c.notas.append("Los meses sin datos se proyectan con el promedio mensual observado.")
    c.efecto_pasajeros = c.tipo == "simulacion" and c.concepto != "Derecho de Embarque" and bool(
        re.search(r"\bpasajer", t))
    return c


def _moneda(s: str) -> str | None:
    s = (s or "").strip()
    if s in ("usd", "dolares", "dolar", "us"):
        return "USD"
    if s in ("pesos", "clp", "peso"):
        return "CLP"
    if s in ("uf", "utm"):
        return s.upper()
    if s in ("%", "por ciento", "porciento"):
        return "%"
    return None


# --- Respaldo con Gemini (vía backend) ---------------------------------------------------------

ESQUEMA_GEMINI = {
    "tipo": "simulacion | consulta | dato | desconocida",
    "concepto": "uno de: " + ", ".join(CONCEPTOS) + " o null (= total de ingresos)",
    "filtro_descripcion": "palabra para filtrar la descripción (ej. Aterrizajes) o null",
    "ambito": "todos | nacional | internacional",
    "unidades": "lista de nombres de aeropuertos/ciudades mencionados (vacía = todos)",
    "region": "región de Chile o null",
    "meses": "lista de números de mes 1-12 (vacía = todos los disponibles)",
    "anualizar": "true si pide el año completo",
    "cambio_tipo": "absoluto | porcentaje | nuevo_valor | null",
    "cambio_valor": "número con signo (negativo = rebaja)",
    "cambio_moneda": "USD | CLP | UF | UTM | null",
    "elasticidad": "número o null",
    "var_pasajeros": "% de variación de pasajeros o null",
    "tipo_cambio": "CLP por USD o null",
    "dato": "si el usuario informa un indicador: {indicador, region, periodo, valor} o null",
}


def con_gemini(c: Consulta, catalogo_unidades: dict[int, str]) -> Consulta:
    """Completa la consulta con Gemini (solo se envía la pregunta y nombres de catálogo)."""
    from . import backend

    r = backend.post("interpretar", {"pregunta": c.texto, "esquema": ESQUEMA_GEMINI,
                                     "unidades": sorted(set(catalogo_unidades.values())),
                                     "hoy": date.today().isoformat()})
    if isinstance(r, str):
        r = json.loads(re.sub(r"^```(?:json)?|```$", "", r.strip()))
    g = Consulta(texto=c.texto, anio=c.anio, origen="gemini")
    for k in ("tipo", "filtro_descripcion", "anualizar", "cambio_tipo", "cambio_moneda", "region"):
        if r.get(k) not in (None, "", "null"):
            setattr(g, k, r[k])
    if r.get("concepto") in CONCEPTOS:
        g.concepto = r["concepto"]
    if r.get("ambito") in ("todos", "nacional", "internacional"):
        g.ambito = r["ambito"]
    for k in ("cambio_valor", "elasticidad", "var_pasajeros", "tipo_cambio"):
        try:
            if r.get(k) is not None:
                setattr(g, k, float(r[k]))
        except (TypeError, ValueError):
            pass
    g.meses = [int(m) for m in (r.get("meses") or []) if str(m).isdigit() and 1 <= int(m) <= 12]
    if r.get("dato"):
        g.dato = r["dato"]
    nombres = " | ".join(str(u) for u in (r.get("unidades") or []))
    if nombres:
        g.unidades, _ = _buscar_alias(normalizar(nombres), _pares_unidades(catalogo_unidades))
    if g.region and not g.unidades:
        reg = alias.ALIAS_REGION.get(normalizar(g.region).replace("region de ", ""), g.region)
        g.region = reg
        g.unidades = sorted(u for u, (r_, _) in alias.UNIDADES.items() if r_ == reg)
    if g.elasticidad is not None:
        g.elasticidad = abs(g.elasticidad)
    # Lo que las reglas detectaron con certeza se conserva.
    for k in ("concepto", "cambio_tipo", "tipo_cambio", "elasticidad", "var_pasajeros"):
        if getattr(c, k) is not None and getattr(g, k) is None:
            setattr(g, k, getattr(c, k))
    if c.unidades and not g.unidades:
        g.unidades, g.region = c.unidades, c.region
    if c.meses and not g.meses:
        g.meses = c.meses
    g.origen = "reglas+gemini"
    g.confianza = 0.8 if g.tipo in ("simulacion", "consulta", "dato") else 0.2
    g.notas = c.notas + ["Consulta interpretada con apoyo de IA (Gemini); revisa los supuestos."]
    return g
