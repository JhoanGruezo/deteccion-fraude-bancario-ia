"""Pruebas de la API de la vista del analista (rutas, SSE y manejo de errores).

La base y el agente los construyen otros módulos en paralelo, así que aquí se
reemplazan por dobles en `sys.modules`: `app.db.repositorio`, `app.db.migrar` y
`app.agente.servicio`. Las rutas importan esos módulos en el momento de usarlos, por
eso basta con instalar los dobles antes de cada prueba, sin recargar nada.

Se corre desde la raíz del proyecto:
    python -m pytest app/pruebas/test_api.py -q
"""

import json
import sys
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient

import app.agente
import app.db
from app import config
from app.api import sse

TARJETA_COMPLETA = "180011453250192"

CASO = {
    "id_caso": "SPK-000001",
    "fuente": "sparkov",
    "id_cuenta": TARJETA_COMPLETA,          # el doble lo "filtra" a propósito
    "tarjeta_enmascarada": "**** **** **** 0192",
    "inicio_ventana": "2020-07-30 00:06:13",
    "fin_ventana": "2020-08-01 00:06:13",
    "tipos_fraude": ["uso_no_autorizado"],
    "score_maximo": 0.997685,
    "nivel_recomendacion": "bloquear_tarjeta",
    "motivo_recomendacion": "5 transacciones en 48 h superan el umbral de bloqueo.",
    "senal_principal": "monto",
    "fraude_confirmado_dataset": 1,          # nunca debe salir hacia la interfaz
    "estado": "pendiente",
    "perfil_previo": {"n_transacciones_previas": 2250, "sin_historial": False, "monto_promedio": 96.05},
    "transacciones": [
        {
            "id_transaccion": "t1",
            "fecha_hora": "2020-07-30 01:22:08",
            "monto": 291.8,
            "score": 0.98,
            "viaje_imposible": False,
            "desviaciones": [
                {"senal": "monto", "descripcion": "Monto de 291,80", "percentil_rareza": 96.3,
                 "contribucion_modelo": 0.98, "relevante": True},
            ],
        }
    ],
}

EXPLICACION = {
    "que_paso": "Cinco compras en 48 h.",
    "por_que_es_riesgo": "Montos de 3,0 veces su promedio.",
    "recomendacion": {"accion": "bloquear_tarjeta", "objetivo": "tarjeta terminada en 0192", "argumento": "…"},
    "senales_citadas": ["monto"],
    "nivel_riesgo_en_palabras": "Muy alto",
    "lo_que_no_se_sabe": "Si el cliente reconoce las compras.",
}


def leer_eventos(texto: str) -> list[tuple[int, str, dict]]:
    """Parsea el cuerpo SSE en (id, tipo, datos), ignorando los comentarios `: ping`."""
    eventos = []
    for bloque in texto.split("\n\n"):
        if not bloque.strip() or bloque.startswith(":"):
            continue
        campos = dict(linea.split(": ", 1) for linea in bloque.split("\n"))
        eventos.append((int(campos["id"]), campos["event"], json.loads(campos["data"])))
    return eventos


class PropuestaYaResuelta(Exception):
    """Igual que en app/db/repositorio.py: NO hereda de ValueError (por eso se prueba)."""


class Dobles:
    """Repositorio, migración y servicio falsos, con registro de cómo se los llamó."""

    def __init__(self):
        self.llamadas = []
        self.falla_base = False
        self.explotar_en = None          # nombre de función del repositorio que lanza
        self.resolucion = "ok"           # ok | no_existe | ya_resuelta
        self.servicio_modo = "normal"    # normal | explota | sin_fin

    # --- repositorio -------------------------------------------------------------
    def _registrar(self, nombre, *args, **kwargs):
        self.llamadas.append((nombre, args, kwargs))
        if self.explotar_en == nombre:
            raise RuntimeError("detalle interno secreto: psycopg.OperationalError en 10.0.0.5")

    def listar_casos(self, **filtros):
        self._registrar("listar_casos", **filtros)
        resumen = {k: CASO[k] for k in ("id_caso", "fuente", "id_cuenta", "nivel_recomendacion", "estado")}
        return [dict(resumen, fraude_confirmado_dataset=1)]

    def contar_casos(self):
        self._registrar("contar_casos")
        return {"fuente": {"sparkov": 1}, "nivel": {"bloquear_tarjeta": 1}, "estado": {"pendiente": 1}}

    def obtener_caso(self, id_caso):
        self._registrar("obtener_caso", id_caso)
        return json.loads(json.dumps(CASO)) if id_caso == CASO["id_caso"] else None

    def obtener_historial(self, id_caso, dias=30, limite=60):
        self._registrar("obtener_historial", id_caso, dias=dias, limite=limite)
        return [{"id_transaccion": "t0", "id_cuenta": TARJETA_COMPLETA, "monto": 10.0, "en_caso": False}]

    def explicacion_vigente(self, id_caso):
        return {"contenido": EXPLICACION, "es_respaldo": False, "proveedor": "gemini"}

    def propuestas_pendientes(self, id_caso):
        return [{"id": 7, "accion": "confirmar_bloqueo", "argumento": "…", "estado": "pendiente"}]

    def decisiones_del_caso(self, id_caso):
        return []

    def ultima_tarea(self, id_caso):
        return None

    def resolver_propuesta(self, propuesta_id, confirmar, analista, comentario=None):
        self._registrar("resolver_propuesta", propuesta_id, confirmar, analista, comentario)
        if self.resolucion == "no_existe":
            return None
        if self.resolucion == "ya_resuelta":
            raise PropuestaYaResuelta("La propuesta ya fue confirmada.")
        if self.resolucion == "valor_invalido":
            raise ValueError("propuesta ya resuelta")
        return {"propuesta_id": propuesta_id, "estado": "confirmada" if confirmar else "rechazada"}

    def registrar_decision(self, id_caso, accion, analista, comentario=None, propuesta_id=None):
        self._registrar("registrar_decision", id_caso, accion, analista, comentario)
        return {"id": 1, "id_caso": id_caso, "accion": accion, "analista": analista}

    def listar_trazas(self, tarea_id):
        return [{"paso": 1, "tipo": "inicio", "detalle": {}}]

    def resumen_metricas(self, desde=None):
        return {"n": 3, "tasa_exito": 0.67}

    # --- migración ---------------------------------------------------------------
    def preparar_base(self):
        self.llamadas.append(("preparar_base", (), {}))
        if self.falla_base:
            raise ConnectionError("could not connect to server: Connection refused")

    # --- servicio del agente -----------------------------------------------------
    def explicar_caso(self, id_caso, regenerar=False, falla_forzada=None):
        self.llamadas.append(("explicar_caso", (id_caso,), {"regenerar": regenerar, "falla_forzada": falla_forzada}))
        yield {"tipo": "inicio", "tarea_id": "11111111-1111-1111-1111-111111111111", "id_caso": id_caso}
        yield {"tipo": "estado", "texto": "Llamando a Gemini…"}
        if self.servicio_modo == "explota":
            raise RuntimeError("Traceback interno: KeyError 'que_paso'")
        yield {"tipo": "modelo_llamado", "proveedor": "gemini", "modelo": "gemini-3.8-flash", "iteracion": 1}
        yield {"tipo": "herramienta", "nombre": "obtener_caso", "argumentos": {"id_caso": id_caso}}
        yield {"tipo": "resultado_herramienta", "nombre": "obtener_caso", "duracion_ms": 12,
               "resumen": {"id_cuenta": TARJETA_COMPLETA, "fraude_confirmado_dataset": 1}}
        for fragmento in ('{"que_paso": "Cin', 'co compras', ' en 48 h."}'):
            yield {"tipo": "token", "texto": fragmento}
        yield {"tipo": "explicacion", "datos": {"contenido": EXPLICACION}}   # forma anidada
        if self.servicio_modo != "sin_fin":
            yield {"tipo": "fin", "datos": {"motivo_fin": "completada", "ttft_ms": 340, "iteraciones": 2}}

    def responder_pregunta(self, id_caso, pregunta, falla_forzada=None):
        self.llamadas.append(("responder_pregunta", (id_caso, pregunta), {"falla_forzada": falla_forzada}))
        yield {"tipo": "inicio", "tarea_id": "22222222-2222-2222-2222-222222222222"}
        yield {"tipo": "token", "texto": "La compra más rara fue "}
        yield {"tipo": "respuesta", "texto": "La compra más rara fue la de 291,80."}
        yield {"tipo": "fin", "motivo_fin": "completada"}

    def llamadas_a(self, nombre):
        return [c for c in self.llamadas if c[0] == nombre]


def _modulo(nombre, doble, funciones):
    modulo = types.ModuleType(nombre)
    for funcion in funciones:
        setattr(modulo, funcion, getattr(doble, funcion))
    return modulo


@pytest.fixture
def dobles(monkeypatch):
    doble = Dobles()
    repositorio = _modulo("app.db.repositorio", doble, [
        "listar_casos", "contar_casos", "obtener_caso", "obtener_historial", "explicacion_vigente",
        "propuestas_pendientes", "decisiones_del_caso", "ultima_tarea", "resolver_propuesta",
        "registrar_decision", "listar_trazas", "resumen_metricas",
    ])
    repositorio.PropuestaYaResuelta = PropuestaYaResuelta
    migrar = _modulo("app.db.migrar", doble, ["preparar_base"])
    servicio = _modulo("app.agente.servicio", doble, ["explicar_caso", "responder_pregunta"])
    for paquete, nombre, modulo in ((app.db, "repositorio", repositorio), (app.db, "migrar", migrar),
                                    (app.agente, "servicio", servicio)):
        monkeypatch.setitem(sys.modules, modulo.__name__, modulo)
        monkeypatch.setattr(paquete, nombre, modulo, raising=False)
    monkeypatch.setattr(config, "PERMITIR_FALLAS_DESDE_UI", True)
    monkeypatch.setattr(config, "FALLA_FORZADA", "")
    return doble


@pytest.fixture
def cliente(dobles):
    from app.principal import crear_app

    # raise_server_exceptions=False: queremos ver lo que vería el navegador, no la excepción.
    with TestClient(crear_app(), raise_server_exceptions=False) as cliente_http:
        yield cliente_http


# --- Arranque y salud -----------------------------------------------------------------

def test_arranque_prepara_la_base_y_sirve_el_frontend(cliente, dobles):
    assert dobles.llamadas_a("preparar_base"), "el arranque debe llamar a preparar_base()"
    inicio = cliente.get("/")
    assert inicio.status_code == 200 and "text/html" in inicio.headers["content-type"]
    estilos = cliente.get("/static/estilos.css")
    assert estilos.status_code == 200 and estilos.headers["cache-control"] == "no-cache"
    assert cliente.get("/static/js/principal.js").status_code == 200


def test_la_app_arranca_aunque_la_base_no_este(dobles):
    from app.principal import crear_app

    dobles.falla_base = True
    dobles.explotar_en = "contar_casos"
    with TestClient(crear_app(), raise_server_exceptions=False) as cliente_http:
        respuesta = cliente_http.get("/api/salud")
    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert cuerpo["base"]["disponible"] is False
    assert "base de datos" in cuerpo["base"]["mensaje"]
    assert "Connection refused" not in respuesta.text and "psycopg" not in respuesta.text


def test_salud_no_expone_llaves(cliente, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "llave-secreta-de-prueba")
    cuerpo = cliente.get("/api/salud").json()
    assert cuerpo["base"]["casos_cargados"] == 1
    gemini = next(p for p in cuerpo["proveedores"] if p["nombre"] == "gemini")
    assert gemini["con_llave"] is True
    assert "llave-secreta-de-prueba" not in json.dumps(cuerpo)


# --- Bandeja y detalle ----------------------------------------------------------------

def test_bandeja_pasa_filtros_y_normaliza_contadores(cliente, dobles):
    respuesta = cliente.get("/api/casos", params={"fuente": "sparkov", "nivel": "bloquear_tarjeta", "q": " 0192 "})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["contadores"]["por_nivel"] == {"bloquear_tarjeta": 1}
    assert cuerpo["contadores"]["total"] == 1
    _, _, filtros = dobles.llamadas_a("listar_casos")[0]
    assert filtros == {"fuente": "sparkov", "nivel": "bloquear_tarjeta", "estado": None,
                       "busqueda": "0192", "orden": "score", "limite": 300}


def test_bandeja_rechaza_filtro_invalido_en_espanol(cliente):
    respuesta = cliente.get("/api/casos", params={"nivel": "borrar_todo"})
    assert respuesta.status_code == 422
    assert "no admite" in respuesta.json()["error"]


def test_detalle_no_expone_tarjeta_completa_ni_etiqueta_del_dataset(cliente):
    for ruta in ("/api/casos/SPK-000001", "/api/casos", "/api/casos/SPK-000001/historial"):
        texto = cliente.get(ruta).text
        assert "fraude_confirmado_dataset" not in texto, ruta
        assert TARJETA_COMPLETA not in texto, ruta
    detalle = cliente.get("/api/casos/SPK-000001").json()
    assert detalle["caso"]["tarjeta_enmascarada"] == "**** **** **** 0192"
    assert detalle["explicacion"]["contenido"]["senales_citadas"] == ["monto"]
    assert detalle["propuestas"][0]["id"] == 7


def test_caso_inexistente_responde_404_en_espanol(cliente):
    for ruta in ("/api/casos/SPK-999999", "/api/casos/SPK-999999/historial",
                 "/api/casos/SPK-999999/explicacion/stream"):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 404, ruta
        assert respuesta.json() == {"error": "Caso no encontrado"}


def test_ruta_inexistente_responde_en_espanol(cliente):
    respuesta = cliente.get("/api/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.json() == {"error": "Recurso no encontrado"}


# --- Propuestas y decisiones (confirmación humana) ---------------------------------

def test_confirmar_sin_nombre_de_analista_es_422_y_no_escribe(cliente, dobles):
    respuesta = cliente.post("/api/propuestas/7/confirmar", json={"analista": "   "})
    assert respuesta.status_code == 422
    assert respuesta.json()["error"] == "Escribe tu nombre de analista para registrar la decisión."
    assert not dobles.llamadas_a("resolver_propuesta")


def test_confirmar_y_rechazar_propuesta(cliente, dobles):
    confirmada = cliente.post("/api/propuestas/7/confirmar", json={"analista": "Ana Pérez", "comentario": " ok "})
    assert confirmada.status_code == 200 and confirmada.json()["resultado"]["estado"] == "confirmada"
    rechazada = cliente.post("/api/propuestas/7/rechazar", json={"analista": "Ana Pérez"})
    assert rechazada.json()["resultado"]["estado"] == "rechazada"
    assert dobles.llamadas_a("resolver_propuesta")[0][1] == (7, True, "Ana Pérez", "ok")


def test_propuesta_ya_resuelta_es_409_e_inexistente_404(cliente, dobles):
    dobles.resolucion = "ya_resuelta"
    respuesta = cliente.post("/api/propuestas/7/confirmar", json={"analista": "Ana"})
    assert respuesta.status_code == 409 and "ya fue resuelta" in respuesta.json()["error"]
    dobles.resolucion = "valor_invalido"
    assert cliente.post("/api/propuestas/7/confirmar", json={"analista": "Ana"}).status_code == 409
    dobles.resolucion = "no_existe"
    assert cliente.post("/api/propuestas/99/rechazar", json={"analista": "Ana"}).status_code == 404


def test_decision_manual_valida_accion_y_analista(cliente, dobles):
    assert cliente.post("/api/casos/SPK-000001/decisiones", json={"accion": "borrar", "analista": "Ana"}).status_code == 422
    assert cliente.post("/api/casos/SPK-000001/decisiones", json={"accion": "escalar"}).status_code == 422
    assert cliente.post("/api/casos/SPK-999999/decisiones", json={"accion": "escalar", "analista": "Ana"}).status_code == 404
    ok = cliente.post("/api/casos/SPK-000001/decisiones", json={"accion": "escalar", "analista": "Ana"})
    assert ok.status_code == 200 and ok.json()["decision"]["accion"] == "escalar"


def test_cuerpo_mal_formado_responde_en_espanol(cliente):
    respuesta = cliente.post("/api/propuestas/abc/confirmar", json={"analista": "Ana"})
    assert respuesta.status_code == 422
    assert respuesta.json()["error"].startswith("La solicitud no tiene el formato esperado")


# --- SSE ----------------------------------------------------------------------------

def test_stream_de_explicacion_es_sse_real_en_orden_y_termina_en_fin(cliente, dobles):
    with cliente.stream("GET", "/api/casos/SPK-000001/explicacion/stream") as respuesta:
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("text/event-stream")
        assert respuesta.headers["cache-control"] == "no-cache"
        assert respuesta.headers["x-accel-buffering"] == "no"
        cuerpo = "".join(respuesta.iter_text())

    eventos = leer_eventos(cuerpo)
    tipos = [tipo for _, tipo, _ in eventos]
    assert tipos == ["estado", "inicio", "estado", "modelo_llamado", "herramienta", "resultado_herramienta",
                     "token", "token", "token", "explicacion", "fin"]
    assert [i for i, _, _ in eventos] == list(range(1, len(eventos) + 1)), "ids incrementales"
    assert eventos[0][2] == {"texto": "Consultando el caso…", "origen": "api"}
    assert eventos[-2][2]["contenido"]["que_paso"] == EXPLICACION["que_paso"]   # forma anidada aplanada
    assert "".join(d["texto"] for _, t, d in eventos if t == "token") == '{"que_paso": "Cinco compras en 48 h."}'
    assert TARJETA_COMPLETA not in cuerpo and "fraude_confirmado_dataset" not in cuerpo
    # "" = ninguna falla (None le diría al servicio "usa la del entorno").
    assert dobles.llamadas_a("explicar_caso")[0][2] == {"regenerar": False, "falla_forzada": ""}


def test_stream_garantiza_fin_y_no_filtra_trazas_si_el_agente_falla(cliente, dobles):
    dobles.servicio_modo = "explota"
    cuerpo = cliente.get("/api/casos/SPK-000001/explicacion/stream").text
    eventos = leer_eventos(cuerpo)
    assert [t for _, t, _ in eventos][-2:] == ["error", "fin"]
    error = eventos[-2][2]
    assert error["accion"] == "reintentar" and len(error["referencia"]) == 12
    assert eventos[-1][2]["motivo_fin"] == "error"
    assert "Traceback" not in cuerpo and "KeyError" not in cuerpo


def test_stream_cierra_con_fin_propio_si_el_agente_no_lo_emite(cliente, dobles):
    dobles.servicio_modo = "sin_fin"
    eventos = leer_eventos(cliente.get("/api/casos/SPK-000001/explicacion/stream?regenerar=1").text)
    assert eventos[-1][1] == "fin" and eventos[-1][2]["incompleto"] is True
    assert dobles.llamadas_a("explicar_caso")[0][2]["regenerar"] is True


def test_stream_de_pregunta(cliente, dobles):
    assert cliente.get("/api/casos/SPK-000001/preguntas/stream", params={"q": "  "}).status_code == 422
    with cliente.stream("GET", "/api/casos/SPK-000001/preguntas/stream",
                        params={"q": "¿Cuál fue la compra más rara?"}) as respuesta:
        eventos = leer_eventos("".join(respuesta.iter_text()))
    assert [t for _, t, _ in eventos] == ["estado", "inicio", "token", "respuesta", "fin"]
    assert dobles.llamadas_a("responder_pregunta")[0][1] == ("SPK-000001", "¿Cuál fue la compra más rara?")


def test_primer_evento_sale_antes_de_tocar_al_agente():
    """El TTFT honesto exige que el primer byte no espere al modelo."""
    llamado = threading.Event()

    def producir():
        llamado.set()
        yield {"tipo": "fin"}

    flujo = sse.transmitir(producir, "Consultando el caso…")
    primero = next(flujo)
    assert primero.startswith("id: 1\nevent: estado\n")
    assert not llamado.is_set(), "el agente no debe arrancar antes del primer evento"
    assert list(flujo)[-1].startswith("id: 2\nevent: fin")


def test_ping_mientras_el_modelo_piensa(monkeypatch):
    monkeypatch.setattr(sse, "INTERVALO_PING_S", 0.05)

    def producir():
        time.sleep(0.3)
        yield {"tipo": "fin"}

    cuerpo = "".join(sse.transmitir(producir, "Consultando…"))
    assert ": ping\n\n" in cuerpo
    assert "incompleto" not in cuerpo, "el fin debe ser el del agente, no el de rescate"


def test_si_el_navegador_se_va_la_generacion_termina_igual():
    guardado = threading.Event()

    def producir():
        yield {"tipo": "inicio"}
        time.sleep(0.1)
        yield {"tipo": "token", "texto": "…"}
        guardado.set()   # equivale a "guardar la explicación" al final del servicio
        yield {"tipo": "fin"}

    flujo = sse.transmitir(producir, "Consultando…")
    next(flujo)
    next(flujo)
    flujo.close()        # el analista cerró el panel
    assert guardado.wait(2), "el hilo del agente debe seguir hasta terminar y guardar"


# --- Manejador global y panel de demo ------------------------------------------------

def test_manejador_global_no_filtra_trazas(cliente, dobles):
    dobles.explotar_en = "listar_casos"
    respuesta = cliente.get("/api/casos")
    assert respuesta.status_code == 500
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"error", "referencia"}
    assert cuerpo["error"].startswith("Ocurrió un error inesperado")
    for filtrado in ("Traceback", "RuntimeError", "psycopg", "10.0.0.5", "secreto"):
        assert filtrado not in respuesta.text


def test_panel_de_demo_respeta_la_bandera(cliente, dobles, monkeypatch):
    monkeypatch.setattr(config, "PERMITIR_FALLAS_DESDE_UI", False)
    bloqueado = cliente.post("/api/demo/falla", json={"tipo": "429"})
    assert bloqueado.status_code == 403 and "deshabilitado" in bloqueado.json()["error"]
    # Con la bandera apagada, tampoco cuenta el parámetro ?falla= del stream.
    cliente.get("/api/casos/SPK-000001/explicacion/stream?falla=todo")
    assert dobles.llamadas_a("explicar_caso")[-1][2]["falla_forzada"] == ""


def test_panel_de_demo_fija_la_falla_para_las_siguientes_tareas(cliente, dobles):
    assert cliente.post("/api/demo/falla", json={"tipo": "rayo"}).status_code == 422
    assert cliente.post("/api/demo/falla", json={"tipo": "429"}).json() == {"falla_forzada": "429"}
    assert cliente.get("/api/salud").json()["falla_forzada"] == "429"
    cliente.get("/api/casos/SPK-000001/explicacion/stream")
    cliente.get("/api/casos/SPK-000001/preguntas/stream", params={"q": "¿y?"})
    assert dobles.llamadas_a("explicar_caso")[-1][2]["falla_forzada"] == "429"
    assert dobles.llamadas_a("responder_pregunta")[-1][2]["falla_forzada"] == "429"
    # El parámetro del stream gana sobre la falla fijada; null la apaga.
    cliente.get("/api/casos/SPK-000001/explicacion/stream?falla=json")
    assert dobles.llamadas_a("explicar_caso")[-1][2]["falla_forzada"] == "json"
    assert cliente.post("/api/demo/falla", json={"tipo": None}).json() == {"falla_forzada": None}
    # Apagada desde el panel, la siguiente tarea va sin falla aunque el entorno tuviera una.
    cliente.get("/api/casos/SPK-000001/explicacion/stream")
    assert dobles.llamadas_a("explicar_caso")[-1][2]["falla_forzada"] == ""


def test_trazas_y_metricas(cliente):
    assert cliente.get("/api/tareas/no-es-uuid/trazas").status_code == 422
    trazas = cliente.get("/api/tareas/11111111-1111-1111-1111-111111111111/trazas").json()
    assert trazas["trazas"][0]["tipo"] == "inicio"
    assert cliente.get("/api/metricas").json()["n"] == 3
    assert cliente.get("/api/config").json()["limites"]["max_iteraciones"] == config.MAX_ITERACIONES


# --- Hallazgo 6: base caída → 503 claro ------------------------------------------------

@pytest.mark.parametrize("excepcion", ["operational", "pool_timeout"])
def test_base_caida_responde_503_con_mensaje_claro_y_sin_traza(cliente, dobles, monkeypatch, excepcion):
    import psycopg
    import psycopg_pool

    def caida(**filtros):
        if excepcion == "operational":
            raise psycopg.OperationalError("connection to server at 10.0.0.5 failed: Connection refused")
        raise psycopg_pool.PoolTimeout("couldn't get a connection after 3.00 sec")

    monkeypatch.setattr(sys.modules["app.db.repositorio"], "listar_casos", caida)
    respuesta = cliente.get("/api/casos")
    assert respuesta.status_code == 503
    assert respuesta.json() == {"error": "La base de datos no responde; intente de nuevo en unos segundos."}
    for filtrado in ("Traceback", "OperationalError", "PoolTimeout", "10.0.0.5"):
        assert filtrado not in respuesta.text


def test_el_pool_espera_poco_por_una_conexion():
    from app.db import conexion
    assert conexion.TIMEOUT_POOL_S <= 3


def test_cuerpo_ilegible_responde_400_en_espanol(cliente):
    respuesta = cliente.post("/api/casos/SPK-000001/decisiones", content=b'{"accion": "\xff"}',
                             headers={"Content-Type": "application/json"})
    assert respuesta.status_code in (400, 422)
    assert "error parsing" not in respuesta.text


def test_detalle_trae_el_nivel_de_riesgo_armado_en_codigo(cliente):
    nivel = cliente.get("/api/casos/SPK-000001").json()["explicacion"]["contenido"]["nivel_riesgo_en_palabras"]
    assert nivel != "Muy alto" and nivel.startswith("Riesgo alto")
