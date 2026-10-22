import streamlit as st

from core import agente, backend
from ui.comun import barra_lateral, inicializar

barra_lateral()
st.title("Ayuda")

st.markdown(r"""
### Qué puedes preguntar
- **Simulaciones de derecho de embarque**: rebajas o alzas por pasajero en dólares o pesos (*"rebaja de 5 dólares"*,
  *"alza de 500 pesos"*), en porcentaje (*"baja 10%"*), una tarifa nueva (*"bajar a 20 dólares"*) o su eliminación.
- **Otros conceptos** (tasas, combustible, concesiones, otros ingresos): variaciones porcentuales
  (*"alza de 5% en las tasas de aterrizaje internacional"*).
- **Consultas** sin escenario: *"¿cuánto representa Calama en concesiones?"*, *"ingresos de combustible de Antofagasta"*.
- **Filtros**: aeropuerto o ciudad (*Punta Arenas, Calama, Santiago…*), región (*"región de Aysén"*),
  nacional/internacional, meses (*"entre marzo y agosto"*, *"primer semestre"*) o *"año completo"* (proyecta los
  meses sin datos).
- **Efecto en pasajeros**: indica el precio promedio del pasaje (*"con pasaje promedio de 80.000"*) y el agente
  calcula escenarios con elasticidades de referencia **0,5 / 1,0 / 1,5**. También puedes fijar una elasticidad
  (*"con elasticidad 1"*) o un cambio directo (*"pasajeros aumentan 4%"*). Tipo de cambio: *"con dólar a 950"*.
- **Informar un indicador** para que el agente lo recuerde: *"el PIB regional de Magallanes 2024 es 5.900 miles de millones"*.

### Cómo calcula
1. **Pasajeros** = monto de derecho de embarque ÷ tarifa vigente de cada mes (tarifario DGAC; los valores de
   2026 calzan exactamente con los montos de la planilla). Los internacionales (> 500 km) usan US\$ 25 y el tipo de
   cambio de cada documento.
2. **Escenario** = pasajeros × (1 + variación de pasajeros) × tarifa nueva. Con elasticidad *e*:
   Δ% pasajeros = −*e* × (cambio del derecho por pasajero ÷ precio promedio del pasaje). La elasticidad se aplica
   sobre el **precio total del pasaje**, que es lo que percibe el viajero: una rebaja de US\$ 5 sobre un pasaje de
   \$80.000 es −6%, no el −60% del derecho. Las elasticidades 0,5 / 1,0 / 1,5 son rangos habituales de los estudios
   internacionales de demanda aérea.
3. Se informa el impacto en la selección, en el total del concepto y en el **total de ingresos**.
4. El Excel incluye la hoja *Cálculo* con **fórmulas vivas**: cambia la elasticidad o el tipo de cambio (celdas
   amarillas) y todo se recalcula.

### Tráfico aéreo (JAC y OACI)
- **JAC – informe mensual** (se descarga y procesa solo): pasajeros domésticos e internacionales de los últimos 13
  meses, variación interanual y rutas principales. Pregunta: *"¿cómo va el tráfico aéreo según la JAC?"*.
- **JAC – base histórica** (2014 en adelante): pasajeros embarcados por aeropuerto y mes. Se usa para **validar** los
  pasajeros que infiere el agente y para **proyectar con estacionalidad** los meses sin datos. Pregunta:
  *"pasajeros embarcados en Calama según la JAC"*.
- **OACI – Monthly Monitor**: variación de la capacidad aérea (ASK) por región del mundo. Pregunta: *"datos de la OACI"*.
- En las simulaciones de embarque la reseña agrega automáticamente la comparación con la JAC, la tendencia del último
  informe y el dato regional de la OACI.

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
    st.warning("Sin backend: la memoria de indicadores queda solo en este navegador, y la interpretación con IA "
               "está desactivada. Ver `backend/LEEME.md` en el repositorio para activarlo (5 minutos, gratis).")

inicializar()
