"""Revisa los archivos que se publicarán y bloquea datos sensibles antes de cada push.

Comprueba que no haya planillas ni documentos de oficina, que no haya RUT con formato y que no
aparezca ningún cliente o RUT de la lista local tests/datos_locales/palabras_bloqueadas.txt (se
genera desde el Excel real con --generar-lista y nunca se publica).

Uso: python scripts/verificar_publicacion.py [--generar-lista "ruta/Ingresos.xlsx"]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BINARIOS = {".xlsx", ".xls", ".xlsm", ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".zip", ".parquet", ".pkl"}
RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b")
LISTA_LOCAL = RAIZ / "tests" / "datos_locales" / "palabras_bloqueadas.txt"
COLUMNAS_PROHIBIDAS = ["RUT_", "CLIENTE_", "NUMERO_", "DETALLE_"]


def generar_lista(excel: str) -> None:
    import pandas as pd

    df = pd.read_excel(excel)
    clientes = {re.sub(r"\s+", " ", str(c)).strip().upper() for c in df["CLIENTE_"].dropna()}
    ruts = {str(int(r)) for r in df["RUT_"].dropna() if int(r) > 1_000_000}
    LISTA_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    # Solo nombres largos (evita falsos positivos con palabras comunes).
    lineas = sorted(c for c in clientes if len(c) >= 12) + sorted(ruts)
    LISTA_LOCAL.write_text("# Generada localmente; NO publicar\n" + "\n".join(lineas), encoding="utf-8")
    print(f"Lista local con {len(lineas)} términos -> {LISTA_LOCAL}")


def archivos_a_publicar() -> list[str]:
    salida = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    return [l for l in salida.splitlines() if l.strip()]


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--generar-lista":
        generar_lista(sys.argv[2])
    bloqueadas = []
    if LISTA_LOCAL.exists():
        bloqueadas = [l.strip().upper() for l in LISTA_LOCAL.read_text(encoding="utf-8").splitlines()
                      if l.strip() and not l.startswith("#")]
    numeros = {b for b in bloqueadas if b.isdigit()}
    nombres = [b for b in bloqueadas if not b.isdigit()]
    problemas = []
    for rel in archivos_a_publicar():
        p = RAIZ / rel
        if not p.exists():
            continue
        if p.suffix.lower() in BINARIOS:
            problemas.append(f"{rel}: archivo binario/de oficina")
            continue
        if rel.startswith("tests/datos_locales/") or rel.startswith("data/"):
            problemas.append(f"{rel}: datos locales no deben publicarse")
            continue
        try:
            texto = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if rel.endswith(".csv"):
            cabecera = texto.splitlines()[0] if texto else ""
            if any(c in cabecera for c in COLUMNAS_PROHIBIDAS):
                problemas.append(f"{rel}: contiene columnas de detalle (RUT/cliente/documento)")
        if RUT.search(texto):
            problemas.append(f"{rel}: contiene un RUT con formato ({RUT.search(texto).group(0)})")
        mayus = texto.upper()
        encontrados = set(re.findall(r"(?<![\d.,])\d{7,9}(?![\d.,])", mayus)) & numeros
        if encontrados or any(n in mayus for n in nombres):
            problemas.append(f"{rel}: contiene un término de la lista de clientes/RUT reales")
    if problemas:
        print("PUBLICACIÓN BLOQUEADA:")
        for pr in problemas:
            print(" -", pr)
        return 1
    aviso = "" if bloqueadas else " (sin lista local de términos bloqueados)"
    print(f"OK: no se detectaron datos sensibles en los archivos a publicar{aviso}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
