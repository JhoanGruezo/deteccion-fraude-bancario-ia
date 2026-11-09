// Aplica el tema guardado antes de pintar, para que no parpadee el tema equivocado.
// Es un script clásico (no módulo) y se carga en el <head> sin defer, a propósito: tiene
// que correr antes del primer pintado. Vive en un archivo, y no en línea dentro del HTML,
// porque la política de seguridad de contenido (CSP) prohíbe los scripts en línea
// (SPEC, RS9): un script en línea es justo lo que aprovecharía una inyección de HTML.
try {
  var tema = localStorage.getItem("tema");
  if (tema === "claro" || tema === "oscuro") document.documentElement.dataset.tema = tema;
} catch (e) { /* sin almacenamiento: se usa el del sistema */ }
