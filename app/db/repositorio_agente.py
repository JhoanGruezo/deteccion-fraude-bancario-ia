"""La vista del repositorio que reciben las herramientas del agente (SPEC, RS3).

Existe para que el mínimo privilegio no dependa del prompt ni de la buena conducta del
código de las herramientas:

- **Lista cerrada de operaciones.** Las herramientas reciben este objeto, no el módulo
  `repositorio`, así que solo pueden llamar a lo que aparece aquí. Cualquier otra función
  (resolver propuestas, registrar decisiones, leer la etiqueta) no existe para ellas.
- **Las lecturas van con el rol `agente` de Postgres**, que solo puede leer y no ve la
  columna `fraude_confirmado_dataset`. Si mañana alguien escribe una herramienta que pida
  esa columna o intente un UPDATE, la base lo rechaza.
- **Las escrituras son explícitas y pocas.** `crear_propuesta` va con el rol `app` porque
  el agente sí puede proponer; la propuesta queda pendiente hasta que un humano la confirme.

Envuelve a cualquier objeto con la interfaz del repositorio, así que las pruebas pueden
pasarle un doble sin base de datos.
"""

from app.db.conexion import usar_rol


class RepositorioDelAgente:
    def __init__(self, base):
        self._base = base

    # --- Lecturas: rol "agente" (solo lectura, sin la etiqueta del dataset) ---------------
    def obtener_caso(self, id_caso):
        with usar_rol("agente"):
            return self._base.obtener_caso(id_caso)

    def obtener_historial(self, id_caso, dias=30, limite=60):
        with usar_rol("agente"):
            return self._base.obtener_historial(id_caso, dias=dias, limite=limite)

    def listar_casos(self, **filtros):
        with usar_rol("agente"):
            return self._base.listar_casos(**filtros)

    # --- Escrituras permitidas: rol "app", solo lo que el agente puede proponer -----------
    def crear_propuesta(self, id_caso, tarea_id, accion, argumento):
        with usar_rol("app"):
            return self._base.crear_propuesta(id_caso, tarea_id, accion, argumento)
