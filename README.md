# Agente Ingresos

Chat en lenguaje natural para simular el impacto de cambios tarifarios sobre los ingresos de la DGAC
(derecho de embarque, tasas aeronáuticas, combustible, concesiones y otros ingresos) por unidad, región y mes.
Cada respuesta incluye cálculos, gráficos, una reseña y un **Excel descargable** con fórmulas vivas, y queda
registrada en un **historial**.

**App:** <https://maxitohappy.github.io/agente-ingresos/> (se abre en el navegador; la primera carga toma unos
20–60 segundos)

## Ejemplos de consultas

- ¿Cómo impacta en el total de ingresos una rebaja de 5 dólares del derecho de embarque?
- ¿Cómo impacta en el embarque de Punta Arenas una rebaja de 5 dólares aplicada solo a Punta Arenas para fomentar
  el turismo, con elasticidad 0,5?
- Sube 10% las tasas de aterrizaje internacional entre marzo y agosto.
- ¿Cuánto representa Calama en el total de concesiones?
- Eliminar el derecho de embarque nacional en la región de Aysén durante el primer semestre.
- El PIB regional de Magallanes 2024 es 5.900 miles de millones (queda en la memoria para próximas consultas).

## Cómo funciona

| Pieza | Detalle |
|---|---|
| Intérprete | Reglas en español (conceptos, ciudades y aeropuertos, regiones, meses, monedas, elasticidad). Si no alcanzan, Gemini (opcional, vía backend; solo recibe el texto de la pregunta). |
| Cálculo | Pasajeros = monto ÷ tarifa vigente de cada mes (tarifario DGAC, verificado contra la planilla). Escenario = pasajeros × (1 + Δ pasajeros) × tarifa nueva. Para otros conceptos, variación %. |
| Datos públicos | Tarifario de embarque desde la API pública de la DGAC; dólar, UF, UTM, IPC, IMACEC y TPM desde mindicador.cl (y CMF / Banco Central si se configuran). |
| Memoria | Si falta un indicador (p. ej. PIB regional), la app lo pide y lo guarda para futuras consultas. |
| Historial | Compartido en una Google Sheet a través del backend; sin backend, local en cada navegador. |
| Excel | Hojas Resumen, Cálculo (celdas editables y fórmulas), Por unidad, Por mes, Gráficos, Indicadores y fuentes. |

## Datos y privacidad

`datos/ingresos_agregados.csv` contiene **solo totales** por mes, unidad, concepto, descripción, código de tasa y
moneda. No incluye clientes, RUT, números de documento ni detalle. Antes de cada publicación se ejecuta
`scripts/verificar_publicacion.py`, que bloquea planillas, RUT y nombres de clientes.

Para actualizar los datos con una planilla nueva:

```bash
python scripts/agregar_datos.py "C:/ruta/Ingresos acumulados 2026.xlsx"
python scripts/verificar_publicacion.py --generar-lista "C:/ruta/Ingresos acumulados 2026.xlsx"
```

También se puede cargar una planilla en la propia app (*Datos e indicadores → Ingresos*). En ese caso se procesa
solo en ese navegador.

## Backend compartido (opcional, gratis)

Ver [backend/LEEME.md](backend/LEEME.md): un Google Apps Script con historial y memoria compartidos, Gemini y
lectura de páginas públicas.

## Desarrollo

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/streamlit run app.py          # local
.venv/Scripts/python -m pytest              # pruebas
python scripts/construir_sitio.py           # sitio estático en _site/ (stlite)
```
