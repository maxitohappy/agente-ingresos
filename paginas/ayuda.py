import streamlit as st

from core import agente, backend
from ui.comun import barra_lateral, inicializar

inicializar()
barra_lateral()
st.title("Ayuda")

st.markdown("""
### Qué puedes preguntar
- **Simulaciones de derecho de embarque**: rebajas o alzas por pasajero en dólares o pesos (*"rebaja de 5 dólares"*,
  *"alza de 500 pesos"*), en porcentaje (*"baja 10%"*), una tarifa nueva (*"bajar a 20 dólares"*) o su eliminación.
- **Otros conceptos** (tasas, combustible, concesiones, otros ingresos): variaciones porcentuales
  (*"alza de 5% en las tasas de aterrizaje internacional"*).
- **Consultas** sin escenario: *"¿cuánto representa Calama en concesiones?"*, *"ingresos de combustible de Antofagasta"*.
- **Filtros**: aeropuerto o ciudad (*Punta Arenas, Calama, Santiago…*), región (*"región de Aysén"*),
  nacional/internacional, meses (*"entre marzo y agosto"*, *"primer semestre"*) o *"año completo"* (proyecta los
  meses sin datos).
- **Supuestos de demanda**: *"con elasticidad 0,5"* o *"pasajeros aumentan 4%"*. Tipo de cambio: *"con dólar a 950"*.
- **Informar un indicador** para que el agente lo recuerde: *"el PIB regional de Magallanes 2024 es 5.900 miles de millones"*.

### Cómo calcula
1. **Pasajeros** = monto de derecho de embarque ÷ tarifa vigente de cada mes (tarifario DGAC; los valores de
   2026 calzan exactamente con los montos de la planilla). Los internacionales (> 500 km) usan US\$ 25 y el tipo de
   cambio de cada documento.
2. **Escenario** = pasajeros × (1 + variación de pasajeros) × tarifa nueva. Con elasticidad *e*:
   Δ% pasajeros = −*e* × Δ% tarifa.
3. Se informa el impacto en la selección, en el total del concepto y en el **total de ingresos**.
4. El Excel incluye la hoja *Cálculo* con **fórmulas vivas**: cambia la elasticidad o el tipo de cambio (celdas
   amarillas) y todo se recalcula.

### Datos que busca solo
Tarifario de embarque (API pública de la DGAC), dólar observado, UF, UTM, IPC, IMACEC y TPM (mindicador.cl; API CMF
y Banco Central si se configuran en el backend). Si un dato no está disponible (por ejemplo el **PIB regional**),
lo pide en el chat y lo guarda en la **memoria compartida** para las próximas consultas.

### Privacidad
El repositorio y la página publican solo **totales agregados** por unidad, concepto y mes (sin clientes, RUT ni
documentos). A la IA (Gemini) se envía solo el texto de la pregunta.
""")

st.subheader("Ejemplos")
for e in agente.EJEMPLOS:
    st.code(e, language=None)

st.subheader("Backend compartido")
if backend.configurado():
    st.success(f"Conectado a {backend.url()[:60]}…")
else:
    st.warning("Sin backend: el historial y la memoria quedan solo en este navegador, y la interpretación con IA "
               "está desactivada. Ver `backend/LEEME.md` en el repositorio para activarlo (5 minutos, gratis).")
