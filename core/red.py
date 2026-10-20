"""Peticiones HTTP que funcionan igual en Python local y en el navegador (stlite/Pyodide).

En el navegador Python corre dentro de un Web Worker, donde XMLHttpRequest síncrono está
permitido; así no se necesita código asíncrono en las páginas de Streamlit.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlencode

EN_NAVEGADOR = sys.platform == "emscripten"
TIMEOUT = 25


class ErrorRed(Exception):
    pass


def _xhr(metodo: str, url: str, cuerpo: str | None = None) -> str:
    from js import XMLHttpRequest  # type: ignore  # solo existe en Pyodide

    req = XMLHttpRequest.new()
    req.open(metodo, url, False)
    if cuerpo is not None:
        # text/plain evita la consulta previa CORS (preflight), que Apps Script no responde.
        req.setRequestHeader("Content-Type", "text/plain;charset=utf-8")
    try:
        req.send(cuerpo)
    except Exception as e:  # noqa: BLE001 - errores de red o CORS
        raise ErrorRed(f"No se pudo conectar con {url.split('?')[0]}: {e}") from e
    if req.status >= 400 or req.status == 0:
        raise ErrorRed(f"{url.split('?')[0]} respondió {req.status}")
    return str(req.responseText)


def get_texto(url: str, params: dict | None = None, timeout: int = TIMEOUT) -> str:
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    if EN_NAVEGADOR:
        return _xhr("GET", url)
    import requests

    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 agente-ingresos"})
        r.raise_for_status()
        return r.text
    except Exception as e:  # noqa: BLE001
        raise ErrorRed(str(e)) from e


def get_json(url: str, params: dict | None = None, timeout: int = TIMEOUT):
    return json.loads(get_texto(url, params, timeout))


def post_json(url: str, datos: dict, timeout: int = 60):
    cuerpo = json.dumps(datos, ensure_ascii=False)
    if EN_NAVEGADOR:
        return json.loads(_xhr("POST", url, cuerpo))
    import requests

    try:
        r = requests.post(url, data=cuerpo.encode("utf-8"), timeout=timeout,
                          headers={"Content-Type": "text/plain;charset=utf-8"})
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        raise ErrorRed(str(e)) from e
