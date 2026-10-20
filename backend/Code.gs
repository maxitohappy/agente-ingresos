/**
 * Backend gratuito de "Agente Ingresos" (Google Apps Script).
 *
 * - Historial compartido y memoria de indicadores en una Google Sheet.
 * - Interpretación de preguntas con Gemini (la clave queda oculta en las Propiedades del script).
 * - Lectura de páginas públicas (DGAC, mindicador, CMF, Banco Central) sin restricciones CORS.
 *
 * Instalación: ver LEEME.md. Propiedades del script (Configuración del proyecto > Propiedades):
 *   GEMINI_API_KEY  (obligatoria para la IA; gratis en https://aistudio.google.com/apikey)
 *   GEMINI_MODEL    (opcional, por defecto gemini-flash-latest)
 *   CMF_APIKEY      (opcional, https://api.cmfchile.cl)
 *   BCCH_USER / BCCH_PASS (opcional, https://si3.bcentral.cl/estadisticas/Principal1/Web_Services/index.htm)
 *   SHEET_ID        (se crea solo al ejecutar `configurar`)
 */

const HOJA_HISTORIAL = 'historial';
const HOJA_MEMORIA = 'memoria';
const COLS_HISTORIAL = ['id', 'fecha', 'usuario', 'pregunta', 'resumen', 'impacto', 'tc', 'consulta'];
const COLS_MEMORIA = ['id', 'indicador', 'periodo', 'valor', 'unidad', 'fuente', 'usuario', 'fecha_registro', 'origen'];
const DGAC_API = 'https://servicios.dgac.gob.cl/dgac_backend/api/v1/public/paginas/';

/** Ejecutar UNA vez desde el editor: crea la planilla de datos y guarda su ID. */
function configurar() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('SHEET_ID');
  if (!id) {
    const ss = SpreadsheetApp.create('Agente Ingresos – historial y memoria');
    id = ss.getId();
    props.setProperty('SHEET_ID', id);
  }
  const ss = SpreadsheetApp.openById(id);
  hoja_(ss, HOJA_HISTORIAL, COLS_HISTORIAL);
  hoja_(ss, HOJA_MEMORIA, COLS_MEMORIA);
  const sobrante = ss.getSheetByName('Hoja 1') || ss.getSheetByName('Sheet1');
  if (sobrante && ss.getSheets().length > 2) ss.deleteSheet(sobrante);
  Logger.log('Planilla lista: ' + ss.getUrl());
  Logger.log('Gemini configurado: ' + (props.getProperty('GEMINI_API_KEY') ? 'sí' : 'NO (agrega GEMINI_API_KEY)'));
}

function hoja_(ss, nombre, columnas) {
  let h = ss.getSheetByName(nombre);
  if (!h) {
    h = ss.insertSheet(nombre);
    h.appendRow(columnas);
    h.setFrozenRows(1);
  }
  return h;
}

function libro_() {
  const id = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (id) return SpreadsheetApp.openById(id);
  // Primera llamada: crea la planilla (con bloqueo para no crear dos).
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (!PropertiesService.getScriptProperties().getProperty('SHEET_ID')) configurar();
  } finally {
    lock.releaseLock();
  }
  return SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty('SHEET_ID'));
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  const p = (e && e.parameter) || {};
  try {
    switch (p.accion) {
      case 'ping': return json_({ok: true, datos: {hora: new Date().toISOString(), ia: !!prop_('GEMINI_API_KEY')}});
      case 'inicio': return json_({ok: true, datos: inicio_()});
      case 'indicadores': return json_({ok: true, datos: indicadores_()});
      case 'jac_informe': return json_({ok: true, datos: jacInforme_()});
      case 'pagina_dgac': return json_({ok: true, datos: paginaDgac_(p.slug || 'tasa-embarque')});
      case 'archivo': return json_({ok: true, datos: archivo_(p.url)});
      case 'historial': return json_({ok: true, datos: leerCache_(HOJA_HISTORIAL, Number(p.limite) || 300)});
      case 'memoria': return json_({ok: true, datos: leerCache_(HOJA_MEMORIA, 2000)});
      default: return json_({ok: false, error: 'acción desconocida: ' + p.accion});
    }
  } catch (err) {
    return json_({ok: false, error: String(err && err.message || err)});
  }
}

function doPost(e) {
  let d = {};
  try {
    d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    switch (d.accion) {
      case 'interpretar': return json_({ok: true, datos: interpretar_(d)});
      case 'guardar_historial': return json_({ok: true, datos: invalidar_(HOJA_HISTORIAL, agregar_(HOJA_HISTORIAL, COLS_HISTORIAL, d.registro))});
      case 'guardar_memoria': return json_({ok: true, datos: invalidar_(HOJA_MEMORIA, agregar_(HOJA_MEMORIA, COLS_MEMORIA, d.registro))});
      case 'borrar_memoria': return json_({ok: true, datos: invalidar_(HOJA_MEMORIA, borrar_(HOJA_MEMORIA, d.id))});
      case 'guardar_jac': return json_({ok: true, datos: guardarJac_(d.informe)});
      case 'borrar_historial': return json_({ok: true, datos: invalidar_(HOJA_HISTORIAL, borrar_(HOJA_HISTORIAL, d.id))});
      default: return json_({ok: false, error: 'acción desconocida: ' + d.accion});
    }
  } catch (err) {
    return json_({ok: false, error: String(err && err.message || err)});
  }
}

function prop_(k) {
  return PropertiesService.getScriptProperties().getProperty(k);
}

// --- Inicio: todo lo que la app necesita al abrirse, en una sola llamada ---------------------------

function inicio_() {
  const salida = {ia: !!prop_('GEMINI_API_KEY')};
  [['indicadores', indicadores_], ['pagina_dgac', function () { return paginaDgac_('tasa-embarque'); }],
   ['memoria', function () { return leerCache_(HOJA_MEMORIA, 2000); }],
   ['jac', function () { const j = prop_('JAC_INFORME'); return j ? JSON.parse(j) : null; }]].forEach(function (x) {
    try { salida[x[0]] = x[1](); } catch (e) { salida[x[0] + '_error'] = String(e && e.message || e); }
  });
  return salida;
}

// --- Planilla ----------------------------------------------------------------------------------

/** Lectura con caché de 10 minutos; se invalida en cada escritura. */
function leerCache_(nombre, limite) {
  const cache = CacheService.getScriptCache();
  const k = 'hoja_' + nombre + '_' + limite;
  const c = cache.get(k);
  if (c) return JSON.parse(c);
  const filas = leer_(nombre, limite);
  try { cache.put(k, JSON.stringify(filas), 600); } catch (e) { /* más de 100 KB: sin caché */ }
  return filas;
}

function invalidar_(nombre, resultado) {
  const cache = CacheService.getScriptCache();
  cache.removeAll(['hoja_' + nombre + '_2000', 'hoja_' + nombre + '_300', 'hoja_' + nombre + '_500']);
  return resultado;
}

function leer_(nombre, limite) {
  const h = libro_().getSheetByName(nombre);
  const n = h.getLastRow();
  if (n < 2) return [];
  const desde = Math.max(2, n - limite + 1);
  const cab = h.getRange(1, 1, 1, h.getLastColumn()).getValues()[0];
  return h.getRange(desde, 1, n - desde + 1, cab.length).getValues().map(function (fila) {
    const o = {};
    cab.forEach(function (c, i) {
      o[c] = fila[i] instanceof Date ? fila[i].toISOString() : fila[i];
    });
    return o;
  }).reverse();
}

function agregar_(nombre, columnas, registro) {
  if (!registro || typeof registro !== 'object') throw new Error('registro vacío');
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const h = hoja_(libro_(), nombre, columnas);
    h.appendRow(columnas.map(function (c) {
      let v = registro[c];
      if (v === undefined || v === null) return '';
      if (typeof v === 'object') v = JSON.stringify(v);
      // Texto acotado y siempre como texto: el apóstrofo evita que Sheets convierta "2026-10" en fecha
      // o interprete fórmulas; getValues() lo devuelve sin el apóstrofo.
      if (typeof v === 'string') v = "'" + v.slice(0, 5000);
      return v;
    }));
    return {guardado: true};
  } finally {
    lock.releaseLock();
  }
}

function borrar_(nombre, id) {
  const h = libro_().getSheetByName(nombre);
  const ids = h.getRange(1, 1, h.getLastRow(), 1).getValues();
  for (let i = ids.length - 1; i >= 1; i--) {
    if (String(ids[i][0]) === String(id)) h.deleteRow(i + 1);
  }
  return {borrado: true};
}

// --- Páginas públicas ----------------------------------------------------------------------------

function get_(url) {
  const r = UrlFetchApp.fetch(url, {muteHttpExceptions: true, headers: {'User-Agent': 'Mozilla/5.0 agente-ingresos'}});
  if (r.getResponseCode() >= 400) throw new Error(url.split('?')[0] + ' respondió ' + r.getResponseCode());
  return JSON.parse(r.getContentText());
}

function paginaDgac_(slug) {
  if (!/^[a-z0-9\-]+$/.test(slug)) throw new Error('slug inválido');
  const cache = CacheService.getScriptCache();
  const k = 'dgac_' + slug;
  const c = cache.get(k);
  if (c) return JSON.parse(c);
  const j = get_(DGAC_API + slug);
  try { cache.put(k, JSON.stringify(j), 21600); } catch (e) { /* página muy grande para la caché */ }
  return j;
}

// Archivos públicos de sitios permitidos (JAC, OACI): HTML como texto; PDF/Excel en base64.
const DOMINIOS_PERMITIDOS = /^https:\/\/(www\.)?(jac\.gob\.cl|icao\.int|www2023\.icao\.int|data\.icao\.int|applications\.icao\.int)\//;

function archivo_(url) {
  if (!DOMINIOS_PERMITIDOS.test(String(url || ''))) throw new Error('dominio no permitido');
  const cache = CacheService.getScriptCache();
  const k = 'arch_' + Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, url));
  const c = cache.get(k);
  if (c) return JSON.parse(c);
  const r = UrlFetchApp.fetch(url, {muteHttpExceptions: true, validateHttpsCertificates: false, followRedirects: true,
    headers: {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36'}});
  const tipo = String(r.getHeaders()['Content-Type'] || r.getHeaders()['content-type'] || '');
  const salida = {estado: r.getResponseCode(), tipo: tipo};
  if (/text|json|html|xml/.test(tipo)) salida.texto = r.getContentText();
  else salida.base64 = Utilities.base64Encode(r.getContent());
  try { cache.put(k, JSON.stringify(salida), 21600); } catch (e) { /* demasiado grande para la caché */ }
  return salida;
}

/** Guarda el informe JAC ya procesado por un cliente (máx. 9 KB) para entregarlo en `inicio`. */
function guardarJac_(informe) {
  const texto = JSON.stringify({fecha: new Date().toISOString(), informe: informe});
  if (texto.length > 9000) throw new Error('informe demasiado grande');
  PropertiesService.getScriptProperties().setProperty('JAC_INFORME', texto);
  return {guardado: true};
}

/** Último Informe Mensual de Tráfico Aéreo de la JAC (PDF): URL wp-content/uploads/AAAA/MM/AAAAMM-Informe.pdf. */
function jacInforme_() {
  const cache = CacheService.getScriptCache();
  let url = cache.get('jac_informe_url');
  if (!url) {
    const hoy = new Date();
    for (let atras = 1; atras <= 8 && !url; atras++) {
      const r = new Date(hoy.getFullYear(), hoy.getMonth() - atras, 1);
      const rep = Utilities.formatDate(r, 'GMT', 'yyyyMM');
      for (let sub = 1; sub <= 2 && !url; sub++) {
        const c = new Date(r.getFullYear(), r.getMonth() + sub, 1);
        const cand = 'https://www.jac.gob.cl/wp-content/uploads/' + Utilities.formatDate(c, 'GMT', 'yyyy/MM') + '/' + rep + '-Informe.pdf';
        const resp = UrlFetchApp.fetch(cand, {muteHttpExceptions: true, validateHttpsCertificates: false});
        if (resp.getResponseCode() === 200 && /pdf/.test(String(resp.getHeaders()['Content-Type'] || ''))) url = cand;
      }
    }
    if (!url) throw new Error('No se encontró un informe mensual reciente de la JAC');
    cache.put('jac_informe_url', url, 43200);
  }
  const a = archivo_(url);
  a.url = url;
  return a;
}

const UNIDADES_IND = {
  dolar: 'CLP por USD', euro: 'CLP por EUR', uf: 'CLP', utm: 'CLP', ipc: '%', imacec: '%', tpm: '%', desempleo: '%'
};
const DIARIOS = {dolar: true, euro: true, uf: true, tpm: true};

function indicadores_() {
  const cache = CacheService.getScriptCache();
  const c = cache.get('indicadores');
  if (c) return JSON.parse(c);
  const salida = {};
  const poner = function (ind, fecha, valor, fuente) {
    if (salida[ind] || valor === null || valor === undefined || isNaN(valor)) return;
    salida[ind] = {indicador: ind, periodo: DIARIOS[ind] ? fecha.slice(0, 10) : fecha.slice(0, 7), valor: Number(valor),
                   unidad: UNIDADES_IND[ind], fuente: fuente};
  };
  // 1) mindicador.cl
  try {
    const j = get_('https://mindicador.cl/api');
    const mapa = {dolar: 'dolar', euro: 'euro', uf: 'uf', utm: 'utm', ipc: 'ipc', imacec: 'imacec', tpm: 'tpm',
                  tasa_desempleo: 'desempleo'};
    Object.keys(mapa).forEach(function (k) {
      if (j[k]) poner(mapa[k], String(j[k].fecha), j[k].valor, 'mindicador.cl');
    });
  } catch (e) { Logger.log('mindicador: ' + e); }
  // 2) API CMF
  const cmf = prop_('CMF_APIKEY');
  if (cmf) {
    [['dolar', 'Dolares'], ['uf', 'UFs'], ['utm', 'UTMs'], ['ipc', 'IPCs'], ['euro', 'Euros']].forEach(function (x) {
      try {
        const j = get_('https://api.cmfchile.cl/api-sbifv3/recursos_api/' + x[0] + '?apikey=' + cmf + '&formato=json');
        const o = (j[x[1]] || [])[0];
        if (o) poner(x[0], o.Fecha, Number(String(o.Valor).replace(/\./g, '').replace(',', '.')), 'API CMF');
      } catch (e) { Logger.log('CMF ' + x[0] + ': ' + e); }
    });
  }
  // 3) API BDE Banco Central (dólar, UF y PIB si hay credenciales)
  const u = prop_('BCCH_USER'), pw = prop_('BCCH_PASS');
  if (u && pw) {
    const hoy = new Date();
    const desde = Utilities.formatDate(new Date(hoy.getTime() - 400 * 864e5), 'GMT', 'yyyy-MM-dd');
    [['dolar', 'F073.TCO.PRE.Z.D'], ['uf', 'F073.UFF.PRE.Z.D']].forEach(function (x) {
      try {
        const j = get_('https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx?user=' + encodeURIComponent(u) +
          '&pass=' + encodeURIComponent(pw) + '&function=GetSeries&timeseries=' + x[1] + '&firstdate=' + desde);
        const obs = ((j.Series || {}).Obs || []).filter(function (o) { return o.statusCode === 'OK'; });
        const o = obs[obs.length - 1];
        if (o) {
          const f = o.indexDateString.split('-');
          poner(x[0], f[2] + '-' + f[1] + '-' + f[0], Number(o.value), 'Banco Central (BDE)');
        }
      } catch (e) { Logger.log('BCCh ' + x[0] + ': ' + e); }
    });
  }
  const lista = Object.keys(salida).map(function (k) { return salida[k]; });
  if (lista.length) cache.put('indicadores', JSON.stringify(lista), 21600);
  return lista;
}

// --- Gemini ---------------------------------------------------------------------------------------

function interpretar_(d) {
  const clave = prop_('GEMINI_API_KEY');
  if (!clave) throw new Error('Falta GEMINI_API_KEY en las propiedades del script');
  const pregunta = String(d.pregunta || '').slice(0, 1500);
  const modelo = prop_('GEMINI_MODEL') || 'gemini-flash-latest';
  const instrucciones =
    'Eres el intérprete de consultas de un simulador de ingresos de la Dirección General de Aeronáutica Civil de Chile ' +
    '(DGAC). Convierte la pregunta en un JSON con exactamente estos campos: ' + JSON.stringify(d.esquema) + '. ' +
    'Reglas: una rebaja es un cambio negativo; "eliminar" el derecho equivale a porcentaje -100; si dice "bajar a X" ' +
    'es nuevo_valor X; el derecho de embarque internacional se cobra en USD (25 por pasajero) y el nacional en pesos; ' +
    'las unidades deben ser nombres de esta lista o ciudades chilenas: ' + JSON.stringify((d.unidades || []).slice(0, 120)) +
    '. Hoy es ' + d.hoy + '. Si la pregunta no es sobre ingresos, tarifas o indicadores, usa tipo "desconocida". ' +
    'Responde solo el JSON.';
  const cuerpo = {
    contents: [{role: 'user', parts: [{text: instrucciones + '\n\nPregunta: ' + pregunta}]}],
    generationConfig: {temperature: 0, responseMimeType: 'application/json'}
  };
  const r = UrlFetchApp.fetch('https://generativelanguage.googleapis.com/v1beta/models/' + modelo + ':generateContent', {
    method: 'post', contentType: 'application/json', payload: JSON.stringify(cuerpo), muteHttpExceptions: true,
    headers: {'x-goog-api-key': clave}
  });
  if (r.getResponseCode() >= 400) throw new Error('Gemini respondió ' + r.getResponseCode() + ': ' + r.getContentText().slice(0, 200));
  const j = JSON.parse(r.getContentText());
  const texto = (((j.candidates || [])[0] || {}).content || {}).parts[0].text;
  return JSON.parse(texto.replace(/^```(json)?|```$/g, '').trim());
}
