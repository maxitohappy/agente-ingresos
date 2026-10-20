"""Actualiza datos/indicadores.json (respaldo publicado de indicadores públicos).

Toma los valores en línea (mindicador.cl, API CMF si existe CMF_APIKEY) y, opcionalmente, un
archivo economicos.json de la app "Proyección de Ingresos" (mensuales de dólar, UF, IPC, IMACEC).
Uso: python scripts/actualizar_respaldo.py [ruta/economicos.json]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import indicadores  # noqa: E402

UNIDADES = {k: v["unidad"] for k, v in indicadores.CATALOGO.items()}


def main() -> int:
    actual = {}
    if indicadores.RESPALDO.exists():
        for r in json.loads(indicadores.RESPALDO.read_text(encoding="utf-8")).get("registros", []):
            actual[(r["indicador"], r["periodo"])] = r
    if len(sys.argv) > 1:
        for r in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("registros", []):
            ind = r["indicador"]
            if ind in UNIDADES:
                actual.setdefault((ind, r["periodo"]), {
                    "indicador": ind, "periodo": r["periodo"], "valor": round(r["valor"], 4),
                    "unidad": UNIDADES[ind] + (" (promedio mensual)" if ind in ("dolar", "uf") else ""),
                    "fuente": r.get("fuente", "")})
    valores, estado = indicadores.consultar_publicos()
    print("; ".join(estado))
    for v in valores:
        actual[(v.indicador, v.periodo)] = {"indicador": v.indicador, "periodo": v.periodo, "valor": v.valor,
                                            "unidad": v.unidad, "fuente": v.fuente}
    salida = {"actualizado": datetime.now().isoformat(timespec="seconds"),
              "nota": "Últimos valores públicos conocidos; la app los usa solo si las fuentes en línea no responden.",
              "registros": sorted(actual.values(), key=lambda r: (r["indicador"], r["periodo"]))}
    indicadores.RESPALDO.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(actual)} registros en {indicadores.RESPALDO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
