# Backend compartido (Google Apps Script) – 5 minutos, gratis

El backend es opcional. Sin él, la app funciona igual, pero la memoria de indicadores queda solo en cada
navegador y no hay interpretación con IA. Con él:

- **Memoria compartida de indicadores**: un PIB regional ingresado por una persona queda disponible para todos.
- **IA (Gemini)** para preguntas que las reglas no entienden. Solo se envía el texto de la pregunta.
- **Lectura de páginas públicas** (DGAC, mindicador, CMF, Banco Central). El navegador no puede leerlas
  directamente por restricciones CORS.

## Pasos

1. Entra a <https://script.google.com> con tu cuenta Google y crea un **Proyecto nuevo**. Llámalo
   "Agente Ingresos backend".
2. Borra el contenido de `Código.gs`, pega todo el archivo [`Code.gs`](Code.gs) y guarda (Ctrl+S).
3. **Clave de Gemini (gratis)**: en <https://aistudio.google.com/apikey> crea una API key. En el editor de Apps
   Script ve a ⚙️ **Configuración del proyecto → Propiedades del script → Agregar propiedad**:
   - `GEMINI_API_KEY` = tu clave
   - Opcionales: `CMF_APIKEY` (<https://api.cmfchile.cl>), `BCCH_USER` y `BCCH_PASS` (Banco Central, API BDE).
4. Vuelve al editor, elige la función **`configurar`** en la barra superior y pulsa **Ejecutar**. Autoriza los
   permisos (Google advierte que la app no está verificada porque es tuya: *Configuración avanzada → Ir a…*).
   En el registro aparecerá el enlace de la planilla creada.
5. **Implementar → Nueva implementación** → tipo **Aplicación web**:
   - Ejecutar como: **Yo**
   - Quién tiene acceso: **Cualquier usuario** (necesario para que la página pública pueda llamarlo)
   Pulsa *Implementar* y copia la **URL de la aplicación web**, que termina en `/exec`.
6. Pega esa URL en `datos/config.json` (`"backend_url": "https://script.google.com/macros/s/.../exec"`) y vuelve
   a publicar el sitio, o envíasela a quien mantiene el repositorio.

Para probarla, abre `TU_URL?accion=ping` en el navegador. Debe responder `{"ok":true,...}`.

## Notas

- Si cambias el código, usa **Implementar → Administrar implementaciones → Editar → Versión nueva**, así se
  mantiene la misma URL.
- La URL `/exec` es pública: cualquiera que la conozca puede leer y escribir la memoria de indicadores. No guardes ahí
  información sensible. La app solo envía preguntas e indicadores.
- Cuotas gratuitas: Apps Script permite 20.000 llamadas externas al día; Gemini, en su capa gratuita, limita las
  solicitudes por minuto. Ambas sobran para el uso de un equipo.

## Implementación actual y actualización con clasp

El backend está implementado en la cuenta del dueño del repositorio, y su URL está en `datos/config.json`. Para
actualizar el código sin cambiar la URL (requiere `clasp login` y el `.clasp.json` local, que no se publica):

```bash
cd backend
clasp push -f
clasp redeploy <ID de la implementación> -d "descripción"
```

Acciones disponibles: GET `ping`, `inicio`, `indicadores`, `pagina_dgac`, `archivo`, `jac_informe`, `memoria`;
POST `interpretar`, `guardar_memoria`, `borrar_memoria`, `guardar_jac`.
