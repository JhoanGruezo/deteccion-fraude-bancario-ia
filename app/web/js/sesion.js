/**
 * Sesión del usuario: quién está trabajando, con qué rol, y la pantalla de ingreso.
 *
 * - Al cargar, principal.js pregunta GET /api/sesion. Si responde 401 se muestra la
 *   pantalla de ingreso; si no, se entra directo (la cookie sigue vigente).
 * - Cualquier 401 posterior (sesión vencida) vuelve a esta pantalla sin tocar el hash de
 *   la URL: tras ingresar, el usuario sigue en la vista o el caso donde estaba.
 * - El rol decide qué controles se ven habilitados; el servidor lo vuelve a revisar en
 *   cada escritura, así que esconder un botón es comodidad, no seguridad.
 * - La firma de las decisiones la pone el servidor con el usuario de la sesión; aquí solo
 *   se muestra ("Firmará: …") para que nadie crea que firma con otro nombre.
 */

import { api, fijarCsrf } from "./api.js";

const ROLES = { supervisor: "Supervisor", analista: "Analista" };

export const sesion = {
  usuario: null, // {usuario, nombre, rol}
  get esSupervisor() {
    return this.usuario?.rol === "supervisor";
  },
  get firma() {
    return this.usuario ? `${this.usuario.nombre} (${this.usuario.usuario})` : "—";
  },
  get rolLegible() {
    return ROLES[this.usuario?.rol] || this.usuario?.rol || "";
  },
};

/**
 * Prepara la pantalla de ingreso. `alEntrar(datos)` se llama tras un ingreso exitoso
 * con la respuesta del servidor ({usuario, csrf, expira_en}).
 */
export function crearIngreso({ alEntrar }) {
  const $ = (id) => document.getElementById(id);
  const pantalla = $("pantalla-ingreso");
  const formulario = $("form-ingreso");
  const campoUsuario = $("ingreso-usuario");
  const campoClave = $("ingreso-clave");
  const error = $("ingreso-error");
  const boton = $("ingreso-boton");
  const nota = $("ingreso-nota");

  function mostrarError(mensaje) {
    error.textContent = mensaje || "";
    error.hidden = !mensaje;
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const usuario = campoUsuario.value.trim();
    const clave = campoClave.value;
    if (!usuario || !clave) {
      mostrarError("Escribe tu usuario y tu contraseña.");
      (usuario ? campoClave : campoUsuario).focus();
      return;
    }
    mostrarError("");
    boton.disabled = true;
    boton.textContent = "Ingresando…";
    try {
      const datos = await api.ingresar(usuario, clave);
      campoClave.value = "";
      alEntrar(datos);
    } catch (fallo) {
      // El mensaje del servidor es genérico a propósito (no dice si el usuario existe).
      mostrarError(fallo.message || "No se pudo iniciar sesión.");
      campoClave.select();
      campoClave.focus();
    } finally {
      boton.disabled = false;
      boton.textContent = "Ingresar";
    }
  });

  return {
    /** Muestra la pantalla. `motivo` es el texto de por qué (p. ej. sesión vencida). */
    mostrar(motivo) {
      fijarCsrf(null);
      sesion.usuario = null;
      nota.textContent = motivo || "";
      nota.hidden = !motivo;
      mostrarError("");
      pantalla.hidden = false;
      campoUsuario.focus();
    },
    ocultar() {
      pantalla.hidden = true;
    },
  };
}

/** Fija la sesión con la respuesta de /api/sesion o de /api/sesion/ingresar. */
export function fijarSesion(datos) {
  sesion.usuario = datos?.usuario || null;
  fijarCsrf(datos?.csrf || null);
}
