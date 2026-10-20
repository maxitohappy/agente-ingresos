"""Genera datos/ingresos_agregados.csv a partir del Excel transaccional de ingresos.

El agregado no contiene clientes, RUT, números de documento ni detalle de cada línea.
Uso: python scripts/agregar_datos.py "ruta/Ingresos acumulados 2026.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import datos  # noqa: E402

ORIGEN = Path.home() / "Desktop" / "APP Edgardo" / "Ingresos acumulados 2026.xlsx"


def main() -> int:
    origen = Path(sys.argv[1]) if len(sys.argv) > 1 else ORIGEN
    print(f"Leyendo {origen} …")
    agregado = datos.leer_excel(origen)
    datos.guardar_agregado(agregado)
    print(f"{len(agregado):,} filas agregadas; total {agregado['monto'].sum():,.0f} CLP -> {datos.ARCHIVO_AGREGADO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
