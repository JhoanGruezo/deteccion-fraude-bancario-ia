"""Pruebas del inicio de sesión, los roles, el CSRF y el desbloqueo humano (SPEC, RF6, RF7, RS6).

Con base real y la autenticación ENCENDIDA (el resto de las pruebas de rutas la apagan porque
usan dobles sin tabla de sesiones).
"""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import sesion
from app.pruebas.base_de_pruebas import base_migrada, como_dueno
from app.pruebas.test_flujo import MotorFalso, compra
from app.riesgo import acciones, flujo

CLAVES = {"analista": "clave-analista-prueba", "supervisor": "clave-supervisor-prueba"}


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    original = (config.ANALISTA_CLAVE, config.SUPERVISOR_CLAVE)
    config.ANALISTA_CLAVE, config.SUPERVISOR_CLAVE = CLAVES["analista"], CLAVES["supervisor"]
    try:
        with base_migrada("fraude_pruebas_sesion", str(tmp_path_factory.mktemp("sin_semilla"))) as resultado:
            yield resultado
    finally:
        config.ANALISTA_CLAVE, config.SUPERVISOR_CLAVE = original


@pytest.fixture
def app_con_sesion(base, monkeypatch):
    monkeypatch.setattr(config, "AUTENTICACION", True)
    sesion.intentos._fallos.clear()
    from app.principal import crear_app
    return crear_app()


def cliente(app):
    return TestClient(app, raise_server_exceptions=False)


def ingresar(http, usuario):
    respuesta = http.post("/api/sesion/ingresar", json={"usuario": usuario, "clave": CLAVES[usuario]})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["csrf"]


def test_la_migracion_crea_los_usuarios_con_scrypt(base):
    assert base["usuarios_creados"] == ["analista", "supervisor"]
    hashes = [fila[0] for fila in como_dueno("select hash_clave from usuarios order by usuario")]
    assert all(h.startswith("scrypt$") and CLAVES["analista"] not in h for h in hashes)


def test_sin_sesion_la_api_responde_401_salvo_la_salud(app_con_sesion):
    with cliente(app_con_sesion) as http:
        assert http.get("/api/casos").status_code == 401
        assert http.get("/api/transacciones/recientes").status_code == 401
        assert http.post("/api/transacciones", json={}).status_code == 401
        assert http.get("/api/salud").status_code == 200
        assert http.get("/").status_code == 200                      # la página de ingreso sí carga


def test_clave_incorrecta_no_dice_si_el_usuario_existe_y_se_bloquea_tras_5_intentos(app_con_sesion):
    with cliente(app_con_sesion) as http:
        existe = http.post("/api/sesion/ingresar", json={"usuario": "analista", "clave": "mala"})
        no_existe = http.post("/api/sesion/ingresar", json={"usuario": "nadie", "clave": "mala"})
        assert existe.status_code == no_existe.status_code == 401
        assert existe.json()["error"] == no_existe.json()["error"]
        for _ in range(4):
            http.post("/api/sesion/ingresar", json={"usuario": "analista", "clave": "mala"})
        bloqueado = http.post("/api/sesion/ingresar", json={"usuario": "analista", "clave": CLAVES["analista"]})
        assert bloqueado.status_code == 429


def test_con_sesion_lee_y_sin_csrf_no_escribe(app_con_sesion):
    with cliente(app_con_sesion) as http:
        csrf = ingresar(http, "analista")
        assert http.get("/api/casos").status_code == 200
        assert http.get("/api/sesion").json()["usuario"]["rol"] == "analista"
        cuerpo = {"tarjeta": "TAR-0000", "monto": 10, "categoria": "x"}
        assert http.post("/api/transacciones", json=cuerpo).status_code == 403            # sin token
        assert http.post("/api/transacciones", json=cuerpo, headers={"X-CSRF-Token": "falso"}).status_code == 403
        assert http.post("/api/transacciones", json=cuerpo, headers={"X-CSRF-Token": csrf}).status_code == 404


def test_la_cookie_es_httponly_y_samesite_strict(app_con_sesion):
    with cliente(app_con_sesion) as http:
        respuesta = http.post("/api/sesion/ingresar", json={"usuario": "analista", "clave": CLAVES["analista"]})
        cookie = respuesta.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        token = http.cookies.get(sesion.COOKIE)
        guardados = [fila[0] for fila in como_dueno("select token_hash from sesiones")]
        assert token not in guardados and len(guardados[-1]) == 64       # solo el hash SHA-256


def test_solo_el_supervisor_cambia_ajustes(app_con_sesion):
    with cliente(app_con_sesion) as http:
        csrf = ingresar(http, "analista")
        apagar = {"clave": "autonomia_agente", "valor": False}
        assert http.post("/api/ajustes", json=apagar, headers={"X-CSRF-Token": csrf}).status_code == 403
        assert http.post("/api/demo/falla", json={"tipo": "429"}, headers={"X-CSRF-Token": csrf}).status_code == 403
    with cliente(app_con_sesion) as http:
        csrf = ingresar(http, "supervisor")
        assert http.post("/api/ajustes", json=apagar, headers={"X-CSRF-Token": csrf}).status_code == 200
        assert como_dueno("select valor from ajustes_sistema where clave = 'autonomia_agente'")[0][0] is False
        malo = http.post("/api/ajustes", json={"clave": "tope_bloqueos_autonomos_por_hora", "valor": 9999},
                         headers={"X-CSRF-Token": csrf})
        assert malo.status_code == 422
        http.post("/api/ajustes", json={"clave": "autonomia_agente", "valor": True}, headers={"X-CSRF-Token": csrf})


def test_desbloqueo_humano_firmado_por_la_sesion(app_con_sesion):
    abierto = flujo.evaluar_transaccion(compra("6001", 0, score=0.99), motor=MotorFalso(), domicilio=(40.0, -90.0))
    bloqueo = acciones.bloquear(abierto["id_caso"], "tarjeta", "regla")
    with cliente(app_con_sesion) as http:
        csrf = ingresar(http, "analista")
        ruta = f"/api/bloqueos/{bloqueo['bloqueo_id']}/desbloquear"
        corto = http.post(ruta, json={"motivo": "ok"}, headers={"X-CSRF-Token": csrf})
        assert corto.status_code == 422 and "al menos 10" in corto.json()["error"]
        bien = http.post(ruta, json={"motivo": "El titular confirmó la compra por la línea oficial."},
                         headers={"X-CSRF-Token": csrf})
        assert bien.status_code == 200 and bien.json()["firmado_por"] == "Analista de turno (analista)"
        assert http.post(ruta, json={"motivo": "otra vez lo mismo"}, headers={"X-CSRF-Token": csrf}).status_code == 409
        activos = http.get("/api/bloqueos?estado=activo").json()["bloqueos"]
        assert all(b["id"] != bloqueo["bloqueo_id"] for b in activos)
        todos = http.get("/api/bloqueos").json()["bloqueos"]
        assert todos and all("id_cuenta" not in b and b["tarjeta_enmascarada"].startswith("****") for b in todos)


def test_la_decision_queda_firmada_por_la_sesion_y_no_por_el_cuerpo(app_con_sesion):
    abierto = flujo.evaluar_transaccion(compra("6002", 0, score=0.99), motor=MotorFalso(), domicilio=(40.0, -90.0))
    with cliente(app_con_sesion) as http:
        csrf = ingresar(http, "analista")
        respuesta = http.post(f"/api/casos/{abierto['id_caso']}/decisiones",
                              json={"accion": "escalar", "analista": "Supervisor General (impostor)"},
                              headers={"X-CSRF-Token": csrf})
        assert respuesta.status_code == 200, respuesta.text
    firma = como_dueno("select analista from decisiones where id_caso = %s", (abierto["id_caso"],))[0][0]
    assert firma == "Analista de turno (analista)"


def test_el_titular_responde_desde_el_buzon_y_salir_cierra_la_sesion(app_con_sesion):
    abierto = flujo.evaluar_transaccion(compra("6003", 0, score=0.98), motor=MotorFalso(), domicilio=(40.0, -90.0))
    acciones.solicitar_verificacion(abierto["id_caso"], "regla")
    with cliente(app_con_sesion) as http:
        csrf = ingresar(http, "analista")
        aviso = next(a for a in http.get("/api/avisos").json()["avisos"] if a["id_caso"] == abierto["id_caso"])
        ruta = f"/api/avisos/{aviso['id']}/responder"
        assert http.post(ruta, json={"respuesta": "fui_yo"}, headers={"X-CSRF-Token": csrf}).status_code == 200
        assert http.post(ruta, json={"respuesta": "no_fui_yo"}, headers={"X-CSRF-Token": csrf}).status_code == 409
        assert http.get("/api/supervision").status_code == 200
        http.post("/api/sesion/salir", headers={"X-CSRF-Token": csrf})
        assert http.get("/api/casos").status_code == 401
