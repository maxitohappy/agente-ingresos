"""Construye el sitio estático para GitHub Pages en _site/ (Streamlit en el navegador vía stlite).

Prueba local:  python scripts/construir_sitio.py && python -m http.server -d _site 8000
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SITIO = RAIZ / "_site"
STLITE = "1.9.2"
CARPETAS = ["core", "paginas", "ui", "datos"]
ARCHIVOS = ["app.py"]
EXTENSIONES = {".py", ".json", ".csv"}
REQUISITOS = ["openpyxl", "xlsxwriter", "pypdf"]

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
  <title>Agente Ingresos</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@__STLITE__/build/stlite.css" />
  <style>
    body { margin: 0; font-family: "Source Sans Pro", system-ui, sans-serif; background: #fff; }
    /* Pantalla de carga propia (reemplaza los avisos en inglés de stlite). */
    #cargando { position: fixed; inset: 0; z-index: 10000; background: #fff; display: flex; align-items: center;
                justify-content: center; padding: 16px; transition: opacity .4s ease; }
    #cargando.fuera { opacity: 0; pointer-events: none; }
    #cargando .tarjeta { width: 100%; max-width: 440px; text-align: center; color: #1f3864; }
    #cargando .icono { width: 56px; height: 56px; margin: 0 auto 14px; border-radius: 50%; background: #eaf2fc;
                       display: flex; align-items: center; justify-content: center; font-size: 28px; }
    #cargando h1 { font-size: 26px; margin: 0 0 6px; font-weight: 700; }
    #cargando .paso { color: #52514e; font-size: 16px; min-height: 24px; margin: 14px 0 10px; }
    #cargando .barra { height: 6px; background: #edf0f4; border-radius: 3px; overflow: hidden; }
    #cargando .avance { height: 100%; width: 3%; background: #2a78d6; border-radius: 3px; transition: width .7s ease; }
    #cargando .nota { color: #8a8984; font-size: 13px; margin-top: 12px; line-height: 1.45; }
  </style>
</head>
<body>
  <div id="cargando" role="status" aria-live="polite">
    <div class="tarjeta">
      <div class="icono" aria-hidden="true">✈️</div>
      <h1>Agente Ingresos</h1>
      <div class="paso" id="paso">Preparando el entorno de cálculo…</div>
      <div class="barra"><div class="avance" id="avance"></div></div>
      <div class="nota">La aplicación se ejecuta en tu navegador. La primera carga toma unos 20 segundos.</div>
    </div>
  </div>
  <div id="root"></div>
  <script type="module">
    import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@__STLITE__/build/stlite.js";
    const archivos = __ARCHIVOS__;
    const files = Object.fromEntries(archivos.map((ruta) => [ruta, { url: "./" + ruta }]));
    mount(
      {
        requirements: __REQUISITOS__,
        entrypoint: "app.py",
        files,
        idbfsMountpoints: ["/mnt"],
        env: { AGENTE_DATA_DIR: "/mnt/datos" },
        streamlitConfig: { "client.toolbarMode": "viewer", "theme.primaryColor": "#2a78d6" },
        // Sin avisos de progreso en inglés (se muestra la pantalla de carga propia); los de error se mantienen.
        disableProgressToasts: true,
        disableModuleAutoLoadToasts: true,
      },
      document.getElementById("root"),
    );
    // Pantalla de carga: pasos aproximados por tiempo; se retira cuando la app ya dibujó su menú o el chat.
    const pasos = [[0, "Preparando el entorno de cálculo…"], [4, "Cargando librerías de análisis de datos…"],
                   [9, "Iniciando la aplicación…"], [13, "Consultando tarifario DGAC e indicadores…"],
                   [20, "Ya casi está listo…"]];
    const inicio = Date.now();
    const reloj = setInterval(() => {
      const s = (Date.now() - inicio) / 1000;
      document.getElementById("paso").textContent = pasos.filter((p) => s >= p[0]).pop()[1];
      document.getElementById("avance").style.width = Math.min(95, 3 + (92 * s) / 22) + "%";
    }, 500);
    const listo = () => document.querySelector('[data-testid="stSidebarNav"], [data-testid="stChatInput"], [data-testid="stMainBlockContainer"] h1');
    const retirar = () => {
      clearInterval(reloj);
      const c = document.getElementById("cargando");
      if (!c) return;
      document.getElementById("avance").style.width = "100%";
      c.classList.add("fuera");
      setTimeout(() => c.remove(), 450);
    };
    const observador = new MutationObserver(() => {
      if (listo()) { observador.disconnect(); retirar(); }
    });
    observador.observe(document.getElementById("root"), { childList: true, subtree: true });
    setTimeout(retirar, 120000);  // nunca dejar la pantalla de carga tapando la app
    // stlite pone en los enlaces del menú una dirección interna ficticia (https://stlite.invalid/...), que el
    // navegador muestra al pasar el mouse y que falla al abrirla en otra pestaña. Se reemplaza por la real.
    const arreglarEnlaces = () => document.querySelectorAll('a[href*="stlite.invalid"]').forEach((a) =>
      a.setAttribute("href", a.getAttribute("href").replace(new RegExp("^https?://stlite[.]invalid(:[0-9]+)?"), location.origin)));
    new MutationObserver(arreglarEnlaces).observe(document.getElementById("root"),
      { subtree: true, childList: true, attributes: true, attributeFilter: ["href"] });
  </script>
</body>
</html>
"""

REDIRECCION = """<!doctype html>
<html lang="es"><head><meta charset="UTF-8" /><title>Agente Ingresos</title>
<script>
  var partes = location.pathname.split("/").filter(Boolean);
  var raiz = location.hostname.endsWith("github.io") && partes.length ? "/" + partes[0] + "/" : "/";
  location.replace(raiz);
</script></head><body>Redirigiendo…</body></html>
"""


def construir() -> list[str]:
    if SITIO.exists():
        shutil.rmtree(SITIO)
    SITIO.mkdir()
    rutas = list(ARCHIVOS)
    for carpeta in CARPETAS:
        for p in sorted((RAIZ / carpeta).rglob("*")):
            if p.is_file() and p.suffix in EXTENSIONES and "__pycache__" not in p.parts:
                rutas.append(p.relative_to(RAIZ).as_posix())
    for r in rutas:
        destino = SITIO / r
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / r, destino)
    html = (PLANTILLA.replace("__STLITE__", STLITE)
            .replace("__ARCHIVOS__", json.dumps(rutas, ensure_ascii=False))
            .replace("__REQUISITOS__", json.dumps(REQUISITOS)))
    (SITIO / "index.html").write_text(html, encoding="utf-8")
    (SITIO / ".nojekyll").write_text("", encoding="utf-8")
    (SITIO / "404.html").write_text(REDIRECCION, encoding="utf-8")
    print(f"Sitio construido en {SITIO} ({len(rutas)} archivos)")
    return rutas


if __name__ == "__main__":
    construir()
