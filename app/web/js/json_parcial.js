/**
 * Parser tolerante de JSON incompleto.
 *
 * Por qué existe: el agente responde con el contrato JSON de la explicación
 * (diseno/agente.md) y ese JSON llega por SSE de a fragmentos. Para pintar cada bloque
 * mientras llega —sin inventar nada: solo lo que ya se recibió— hay que poder leer
 * un JSON cortado a la mitad, por ejemplo:
 *
 *   {"que_paso": "Entre el 30 y el 31 de julio la tarjeta hizo cin
 *
 * La estrategia es recorrer el texto una vez llevando la pila de contenedores
 * abiertos y lo que cada uno espera a continuación (clave, dos puntos, valor o coma).
 * Al final se "cierra" lo pendiente: se termina la cadena abierta, se quita un literal
 * a medio escribir o una coma colgante, se completa una clave sin valor con null y se
 * cierran llaves y corchetes en orden inverso. Luego JSON.parse hace el resto.
 */

const LITERAL_COMPLETO = /^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)$/;

/**
 * @param {string} texto  lo recibido hasta ahora (puede traer cercos de markdown antes)
 * @returns {{valor: any, completo: boolean, claveEnCurso: string|null} | null}
 *          null si todavía no hay un objeto que leer.
 */
export function parsearJsonParcial(texto) {
  const inicio = typeof texto === "string" ? texto.indexOf("{") : -1;
  if (inicio < 0) return null;
  const s = texto.slice(inicio);

  const pila = []; // { tipo: "objeto"|"lista", espera: "clave"|"dospuntos"|"valor"|"coma" }
  let enCadena = false;
  let cadenaEsClave = false;
  let escape = false;
  let inicioLiteral = -1;
  let claveActual = null;
  let inicioCadena = -1;
  let ultimaClaveRaiz = null;

  const tope = () => pila[pila.length - 1];
  const valorTerminado = () => {
    const t = tope();
    if (t) t.espera = "coma";
  };
  const cerrarLiteral = () => {
    if (inicioLiteral >= 0) {
      inicioLiteral = -1;
      valorTerminado();
    }
  };

  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (enCadena) {
      if (escape) escape = false;
      else if (c === "\\") escape = true;
      else if (c === '"') {
        enCadena = false;
        if (cadenaEsClave) {
          tope().espera = "dospuntos";
          try { claveActual = JSON.parse(s.slice(inicioCadena, i + 1)); } catch { claveActual = null; }
          if (pila.length === 1) ultimaClaveRaiz = claveActual;
        } else valorTerminado();
      }
      continue;
    }
    if (inicioLiteral >= 0 && /[\s,}\]]/.test(c)) cerrarLiteral();

    switch (c) {
      case "{":
        pila.push({ tipo: "objeto", espera: "clave" });
        break;
      case "[":
        pila.push({ tipo: "lista", espera: "valor" });
        break;
      case "}":
      case "]":
        pila.pop();
        if (pila.length === 0) {
          // Objeto raíz completo: lo que venga después (un cerco ```) no importa.
          try {
            return { valor: JSON.parse(s.slice(0, i + 1)), completo: true, claveEnCurso: null };
          } catch {
            return null;
          }
        }
        valorTerminado();
        break;
      case '"':
        enCadena = true;
        inicioCadena = i;
        cadenaEsClave = tope()?.tipo === "objeto" && tope().espera === "clave";
        if (cadenaEsClave && pila.length === 1) ultimaClaveRaiz = null; // el campo anterior ya terminó
        break;
      case ":":
        if (tope()) tope().espera = "valor";
        break;
      case ",":
        if (tope()) tope().espera = tope().tipo === "objeto" ? "clave" : "valor";
        break;
      default:
        if (!/\s/.test(c) && inicioLiteral < 0) inicioLiteral = i;
    }
  }

  // --- Cerrar lo que quedó abierto ---------------------------------------------------
  let reparado = s;
  if (enCadena) {
    // Una secuencia de escape a medias (\ o \u00e) rompería el JSON: se descarta.
    reparado = reparado.replace(/\\u[0-9a-fA-F]{0,3}$/, "");
    if (escape) reparado = reparado.slice(0, -1);
    reparado += '"';
    if (cadenaEsClave) reparado += ":null";
  } else if (inicioLiteral >= 0) {
    // "12" sirve tal cual (aunque luego llegue "12.5"); "tru" o "1." no: se quitan.
    const literal = s.slice(inicioLiteral).trim();
    if (LITERAL_COMPLETO.test(literal)) valorTerminado();
    else reparado = s.slice(0, inicioLiteral);
  }

  reparado = reparado.replace(/\s+$/, "");
  const t = tope();
  if (t && !enCadena) {
    if (t.espera === "dospuntos") reparado += ":null";
    else if (t.espera === "valor" && t.tipo === "objeto") reparado += "null";
    else if (t.espera === "clave" || (t.espera === "valor" && t.tipo === "lista")) {
      reparado = reparado.replace(/,$/, "");
    }
  }
  for (let i = pila.length - 1; i >= 0; i--) reparado += pila[i].tipo === "objeto" ? "}" : "]";

  try {
    return { valor: JSON.parse(reparado), completo: false, claveEnCurso: ultimaClaveRaiz };
  } catch {
    return null;
  }
}
