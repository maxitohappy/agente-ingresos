"""Nombres coloquiales -> unidades, regiones y conceptos.

Las unidades se identifican por su código (columna UNIDAD_PRESTACION_SERVICIO_). Cada alias se
compara sin tildes y en minúsculas, buscando la palabra completa en la consulta.
"""
from __future__ import annotations

REGIONES = {
    "arica": "Arica y Parinacota", "tarapaca": "Tarapacá", "antofagasta": "Antofagasta", "atacama": "Atacama",
    "coquimbo": "Coquimbo", "valparaiso": "Valparaíso", "metropolitana": "Metropolitana", "ohiggins": "O'Higgins",
    "maule": "Maule", "nuble": "Ñuble", "biobio": "Biobío", "araucania": "La Araucanía", "los rios": "Los Ríos",
    "los lagos": "Los Lagos", "aysen": "Aysén", "magallanes": "Magallanes",
}

# código de unidad -> (región, alias coloquiales)
UNIDADES = {
    1101: ("Arica y Parinacota", ["arica", "chacalluta"]),
    1201: ("Tarapacá", ["iquique", "diego aracena"]),
    1301: ("Antofagasta", ["antofagasta", "andres sabella", "cerro moreno"]),
    1401: ("Antofagasta", ["calama", "el loa"]),
    1402: ("Antofagasta", ["san pedro de atacama"]),
    1601: ("Atacama", ["copiapo", "desierto de atacama", "caldera"]),
    1602: ("Atacama", ["chamonate"]),
    1604: ("Atacama", ["vallenar"]),
    1605: ("Atacama", ["el salvador"]),
    1907: ("Antofagasta", ["cerro pajonales"]),
    2201: ("Coquimbo", ["la serena", "la florida"]),
    2301: ("Valparaíso", ["isla de pascua", "rapa nui", "mataveri", "hanga roa"]),
    2501: ("Maule", ["curico", "general freire", "gral freire"]),
    2701: ("Biobío", ["concepcion", "carriel sur", "talcahuano"]),
    2702: ("Biobío", ["los angeles", "maria dolores"]),
    2703: ("Ñuble", ["chillan", "bernardo ohiggins", "b.o'higgins"]),
    2705: ("Maule", ["los pehuenches"]),
    2914: ("Metropolitana", ["peldehue"]),
    3103: ("La Araucanía", ["victoria"]),
    3104: ("La Araucanía", ["traiguen"]),
    3105: ("La Araucanía", ["angol", "los confines"]),
    3201: ("Los Lagos", ["osorno", "canal bajo"]),
    3301: ("Los Lagos", ["puerto montt", "pto montt", "tepual", "el tepual"]),
    3303: ("Los Lagos", ["quellon"]),
    3304: ("Los Lagos", ["chaiten", "nuevo chaiten"]),
    3305: ("Los Lagos", ["futaleufu"]),
    3306: ("Los Lagos", ["alto palena", "palena"]),
    3310: ("Los Lagos", ["marcel marchant"]),
    3311: ("Aysén", ["melinka"]),
    3312: ("Los Lagos", ["santa barbara"]),
    3401: ("Los Ríos", ["valdivia", "pichoy"]),
    3501: ("Aysén", ["coyhaique", "coihaique", "teniente vidal", "tte vidal"]),
    3502: ("Aysén", ["chile chico"]),
    3503: ("Aysén", ["cochrane"]),
    3505: ("Aysén", ["puerto aysen"]),
    3601: ("Aysén", ["balmaceda"]),
    3701: ("Los Lagos", ["castro", "chiloe", "mocopulli"]),
    3801: ("La Araucanía", ["temuco", "la araucania aerodromo", "freire temuco"]),
    4101: ("Magallanes", ["punta arenas", "pta arenas", "carlos ibanez", "carlos ibanez del campo"]),
    4102: ("Magallanes", ["puerto natales", "natales"]),
    4103: ("Magallanes", ["porvenir"]),
    4104: ("Magallanes", ["puerto williams", "pto williams"]),
    4105: ("Magallanes", ["teniente marsh", "tte marsh", "antartica"]),
    5201: ("Metropolitana", ["santiago", "arturo merino benitez", "amb", "a.m.b", "pudahuel", "nuevo pudahuel"]),
    5207: ("Metropolitana", ["tobalaba", "eulogio sanchez"]),
    5208: ("Valparaíso", ["santo domingo"]),
    5209: ("Valparaíso", ["robinson crusoe", "juan fernandez"]),
    5210: ("Valparaíso", ["rodelillo"]),
    5211: ("Valparaíso", ["vina del mar", "vina"]),
    5216: ("Metropolitana", ["curacavi"]),
    5219: ("O'Higgins", ["rancagua", "de la independencia"]),
}

# Alias de región (para "región de Magallanes", "en Aysén", etc.)
ALIAS_REGION = {
    "arica y parinacota": "Arica y Parinacota", "tarapaca": "Tarapacá", "region de antofagasta": "Antofagasta",
    "region de atacama": "Atacama", "coquimbo": "Coquimbo", "region de valparaiso": "Valparaíso",
    "valparaiso": "Valparaíso", "metropolitana": "Metropolitana", "region metropolitana": "Metropolitana",
    "ohiggins": "O'Higgins", "o'higgins": "O'Higgins", "maule": "Maule", "nuble": "Ñuble", "biobio": "Biobío",
    "bio bio": "Biobío", "araucania": "La Araucanía", "los rios": "Los Ríos", "los lagos": "Los Lagos",
    "aysen": "Aysén", "aisen": "Aysén", "magallanes": "Magallanes", "zona austral": "Magallanes",
}

# Concepto -> palabras clave
CONCEPTOS = {
    "Derecho de Embarque": ["derecho de embarque", "derechos de embarque", "tasa de embarque", "tasas de embarque",
                            "embarque", "embarques", "d° embarque", "de embarque"],
    "Tasas": ["tasas aeronauticas", "tasa aeronautica", "tasas", "aterrizaje", "aterrizajes", "estacionamiento",
              "iluminacion", "ils", "servicio en ruta", "servicios en ruta", "sobrevuelo", "sobrevuelos", "tasa"],
    "Combustible": ["combustible", "combustibles", "venta de combustible", "ventas de combustible"],
    "Concesiones": ["concesion", "concesiones", "arriendo", "arriendos", "terrenos", "locales comerciales",
                    "hangares", "rent a car"],
    "Otros Ingresos": ["otros ingresos", "licencias", "habilitaciones", "certificaciones", "ticas",
                       "meteorologia", "multas", "intereses"],
}

# Palabras de la consulta -> filtro sobre la columna Descripcion (dentro del concepto)
DESCRIPCIONES = {
    "aterrizaje": "Aterrizajes", "aterrizajes": "Aterrizajes", "estacionamiento": "Estacion",
    "iluminacion": "Iluminaci", "ils": "Ils", "en ruta": "Ruta", "sobrevuelo": "Sobrevuelos",
    "sobrevuelos": "Sobrevuelos", "locales comerciales": "Locales Comerciales", "terrenos": "Terreno",
    "hangares": "Hangares", "rent a car": "Rent A Car", "cafeteria": "Cafeteria", "licencias": "Licencias",
    "ticas": "Ticas", "intereses": "Intereses",
}
