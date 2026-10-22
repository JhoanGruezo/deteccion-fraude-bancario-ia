/**
 * Formato en español (es-CO) y vocabulario de la interfaz.
 *
 * Un solo lugar para cómo se ven montos, fechas y porcentajes, y para traducir los
 * códigos internos (bloquear_tarjeta, monto_24h, grocery_pos…) a palabras que un
 * analista entiende sin conocer el modelo. Si una etiqueta cambia, cambia aquí.
 */

const LOCAL = "es-CO";

// Sparkov está en dólares y los sintéticos en pesos colombianos: la moneda se fija
// según la fuente del caso abierto (detalle.js llama a fijarMonedaDeFuente).
const FORMATOS_MONEDA = {
  USD: new Intl.NumberFormat(LOCAL, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  COP: new Intl.NumberFormat(LOCAL, { style: "currency", currency: "COP", minimumFractionDigits: 0, maximumFractionDigits: 0 }),
};
let fmtMoneda = FORMATOS_MONEDA.USD;

export function fijarMonedaDeFuente(fuente) {
  fmtMoneda = fuente === "sinteticos" ? FORMATOS_MONEDA.COP : FORMATOS_MONEDA.USD;
}
const fmtCosto = new Intl.NumberFormat(LOCAL, { style: "currency", currency: "USD", minimumFractionDigits: 4, maximumFractionDigits: 6 });
const fmtFechaHora = new Intl.DateTimeFormat(LOCAL, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtFecha = new Intl.DateTimeFormat(LOCAL, { day: "numeric", month: "short", year: "numeric" });
const fmtDia = new Intl.DateTimeFormat(LOCAL, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const fmtHora = new Intl.DateTimeFormat(LOCAL, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtHoraSegundos = new Intl.DateTimeFormat(LOCAL, { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });

const vacio = (v) => v === null || v === undefined || v === "" || Number.isNaN(Number(v));

export const moneda = (v) => (vacio(v) ? "—" : fmtMoneda.format(Number(v)));
export const costo = (v) => (vacio(v) ? "—" : fmtCosto.format(Number(v)));

export function numero(v, decimales = 0) {
  if (vacio(v)) return "—";
  return new Intl.NumberFormat(LOCAL, { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(Number(v));
}

export const porcentaje = (v, decimales = 1) => (vacio(v) ? "—" : `${numero(v, decimales)} %`);
export const puntaje = (v) => numero(v, 2);

/** Las fechas del motor vienen sin zona ("2020-07-30 00:06:13"): se leen como hora local. */
export function aFecha(texto) {
  if (!texto) return null;
  if (texto instanceof Date) return texto;
  const fecha = new Date(String(texto).replace(" ", "T"));
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

const conFecha = (fmt) => (texto) => {
  const fecha = aFecha(texto);
  return fecha ? fmt.format(fecha) : "—";
};
export const fechaHora = conFecha(fmtFechaHora);
export const fecha = conFecha(fmtFecha);
export const dia = conFecha(fmtDia);
export const hora = conFecha(fmtHora);
export const horaSegundos = conFecha(fmtHoraSegundos);
export const claveDia = (texto) => (aFecha(texto) ? String(texto).slice(0, 10) : "");

export function duracion(ms) {
  if (vacio(ms)) return "—";
  const valor = Number(ms);
  return valor < 1000 ? `${numero(valor)} ms` : `${numero(valor / 1000, 1)} s`;
}

/** "**** **** **** 1234" → "•••• 1234": la tarjeta jamás se muestra completa. */
export function tarjetaCorta(enmascarada) {
  const ultimos = String(enmascarada || "").replace(/[^0-9]/g, "").slice(-4);
  return ultimos ? `•••• ${ultimos}` : "••••";
}

export const NIVELES = {
  bloquear_tarjeta: { etiqueta: "Bloquear tarjeta", corta: "Tarjeta", clase: "tarjeta" },
  bloquear_acceso_cuenta: { etiqueta: "Bloquear acceso a la cuenta", corta: "Acceso", clase: "acceso" },
  verificar_cliente: { etiqueta: "Verificar con el cliente", corta: "Verificar", clase: "verificar" },
};

export const ESTADOS = {
  pendiente: { etiqueta: "Pendiente", cerrado: false },
  bloqueo_confirmado: { etiqueta: "Bloqueo confirmado", cerrado: true },
  descartado: { etiqueta: "Descartado", cerrado: true },
  escalado: { etiqueta: "Escalado", cerrado: true },
};

export const ACCIONES = {
  confirmar_bloqueo: "Confirmar bloqueo",
  descartar: "Descartar",
  escalar: "Escalar",
};

export const FUENTES = { sparkov: "Sparkov", sinteticos: "Sintéticos" };

export const SENALES = {
  monto: "Monto",
  hora: "Hora",
  categoria: "Categoría",
  distancia: "Distancia",
  monto_24h: "Gasto en 24 h",
  ritmo_24h: "Ritmo en 24 h",
  historial: "Historial",
  ubicacion: "Ubicación",
};
export const senal = (codigo) => SENALES[codigo] || String(codigo || "—").replace(/_/g, " ");

const CATEGORIAS = {
  entertainment: "Entretenimiento",
  food_dining: "Restaurantes",
  gas_transport: "Gasolina y transporte",
  grocery_net: "Mercado en línea",
  grocery_pos: "Mercado presencial",
  health_fitness: "Salud y ejercicio",
  home: "Hogar",
  kids_pets: "Niños y mascotas",
  misc_net: "Varios en línea",
  misc_pos: "Varios presencial",
  personal_care: "Cuidado personal",
  shopping_net: "Compras en línea",
  shopping_pos: "Compras presenciales",
  travel: "Viajes",
};
export const categoria = (codigo) => (codigo ? CATEGORIAS[codigo] || String(codigo).replace(/_/g, " ") : "");

export const PROVEEDORES = { gemini: "Gemini", claude: "Claude", plantilla: "Plantilla" };
export const proveedor = (codigo) => PROVEEDORES[codigo] || codigo || "—";

export const MOTIVOS_FIN = {
  completada: "Completada",
  limite_iteraciones: "Límite de iteraciones",
  limite_tokens: "Límite de tokens",
  timeout: "Tiempo agotado",
  respaldo: "Respaldo por plantilla",
  error: "Error",
  rechazo: "Fuera de alcance (rechazo)",
  cache: "Servida desde caché",
};
export const motivoFin = (codigo) => MOTIVOS_FIN[codigo] || codigo || "—";

/**
 * Lee un número escrito en español ("1.234,56", "96,05", "3") a Number.
 * Lo usa el enlace de cifras de la explicación con la evidencia.
 */
export function leerNumeroEspanol(texto) {
  const limpio = String(texto).replace(/\./g, "").replace(",", ".");
  const valor = Number(limpio);
  return Number.isFinite(valor) ? valor : null;
}
