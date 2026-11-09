"""Pruebas del flujo en vivo (SPEC, RF1 y RF2) contra un Postgres real.

Con un motor falso de score controlado se prueba la lógica que importa: en qué banda cae
cada caso, cuándo se abre, cuándo sube de banda (y avisa), que una tarjeta bloqueada
rechaza la compra, que reenviar la misma compra no la duplica y que la etiqueta del
dataset se guarda pero la app no la puede leer. Una prueba final usa el modelo real.
"""

from datetime import datetime, timedelta

import pytest

from app.db import repositorio, repositorio_en_vivo
from app.pruebas.base_de_pruebas import base_migrada, como_dueno
from app.riesgo import flujo
from app.riesgo.perfil_incremental import EstadoTarjeta, actualizar

INICIO = datetime(2020, 7, 1, 1, 0, 0)
CASA = (40.0, -90.0)


class MotorFalso:
    """Mismo contrato que MotorEnVivo, con el score que diga la transacción (_score)."""
    nombre = "motor_falso"
    umbral_verificacion = 0.95
    umbral_bloqueo = 0.97

    def evaluar(self, estado, transaccion, con_senales=None):
        score = transaccion.get("_score", 0.1)
        senales = [{"senal": "monto", "descripcion": "Monto inusual.", "percentil_rareza": 99.0,
                    "contribucion_modelo": 0.5, "relevante": True}] if score >= 0.95 or con_senales else []
        return {"score": score, "viaje_imposible": transaccion.get("_viaje", False), "desviaciones": senales,
                "features": {}, "n_previas": estado.n, "latencia_puntuacion_ms": 1.0, "latencia_total_ms": 2.0}


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with base_migrada("fraude_pruebas_flujo", str(tmp_path_factory.mktemp("sin_semilla"))) as resultado:
        yield resultado


@pytest.fixture
def eventos():
    recibidos = []
    flujo.quitar_oyentes()
    flujo.al_cambiar_caso(recibidos.append)
    yield recibidos
    flujo.quitar_oyentes()


_contador = iter(range(1, 10_000))


def compra(tarjeta, minutos, score=0.1, **extra):
    return {"fuente": "sparkov", "id_cuenta": tarjeta, "id_transaccion": f"{tarjeta}-{next(_contador)}",
            "fecha_hora": INICIO + timedelta(minutes=minutos), "monto": 120.0, "categoria": "shopping_net",
            "comercio": "Tienda", "latitud": CASA[0], "longitud": CASA[1], "_score": score, **extra}


def evaluar(transaccion, **kwargs):
    return flujo.evaluar_transaccion(transaccion, origen="simulador", motor=MotorFalso(), domicilio=CASA, **kwargs)


def test_compra_normal_no_abre_caso_pero_actualiza_el_perfil(base, eventos):
    resultado = evaluar(compra("1001", 0))
    assert resultado["banda"] == "sin_alerta" and resultado["id_caso"] is None and resultado["decision"] == "aprobada"
    assert repositorio_en_vivo.estado_de("sparkov", "1001")["n"] == 1
    assert eventos == []


def test_primera_compra_sobre_bloqueo_abre_caso_en_banda_alta(base, eventos):
    resultado = evaluar(compra("1002", 0, score=0.98))
    assert resultado["evento"] == "caso_abierto" and resultado["banda"] == "alta"
    assert resultado["id_caso"].startswith("VIV-")
    assert eventos == [{"id_caso": resultado["id_caso"], "banda": "alta", "evento": "caso_abierto"}]
    caso = repositorio.obtener_caso(resultado["id_caso"])     # el agente lo lee igual que uno de la semilla
    assert caso["transacciones"][0]["score"] == 0.98 and caso["nivel_recomendacion"] == "verificar_cliente"


def test_compra_media_abre_caso_medio(base, eventos):
    resultado = evaluar(compra("1003", 0, score=0.955))
    assert resultado["banda"] == "media" and eventos[0]["banda"] == "media"


def test_segunda_compra_sobre_bloqueo_sube_a_critica_y_avisa(base, eventos):
    primera = evaluar(compra("1004", 0, score=0.98))
    segunda = evaluar(compra("1004", 30, score=0.99))
    assert segunda["id_caso"] == primera["id_caso"]
    assert segunda["banda"] == "critica" and segunda["evento"] == "subio_de_banda"
    assert [e["evento"] for e in eventos] == ["caso_abierto", "subio_de_banda"]
    caso = repositorio.obtener_caso(primera["id_caso"])
    assert caso["nivel_recomendacion"] == "bloquear_tarjeta" and len(caso["transacciones"]) == 2


def test_compra_en_la_misma_banda_actualiza_sin_volver_a_avisar(base, eventos):
    evaluar(compra("1005", 0, score=0.96))
    segunda = evaluar(compra("1005", 10, score=0.955))
    assert segunda["evento"] == "caso_actualizado" and len(eventos) == 1


def test_fuera_de_la_ventana_de_48_h_abre_otro_caso(base, eventos):
    primera = evaluar(compra("1006", 0, score=0.98))
    otra = evaluar(compra("1006", 49 * 60, score=0.98))
    assert otra["id_caso"] != primera["id_caso"] and otra["evento"] == "caso_abierto"


def test_viaje_imposible_no_abre_caso_en_sparkov_pero_si_en_sinteticos(base, eventos):
    sparkov = evaluar(compra("1007", 0, _viaje=True))
    assert sparkov["viaje_imposible"] is True and sparkov["id_caso"] is None
    sintetica = evaluar({**compra("1008", 0, _viaje=True), "fuente": "sinteticos"})
    assert sintetica["banda"] == "critica"


def test_tarjeta_bloqueada_rechaza_la_compra_sin_tocar_perfil_ni_caso(base, eventos):
    abierta = evaluar(compra("1009", 0, score=0.99))
    with repositorio_en_vivo.transaccion() as cur:
        cur.execute("""insert into bloqueos (id_caso, fuente, id_cuenta, tipo, actor, banda, motivo)
                       values (%s, 'sparkov', '1009', 'tarjeta', 'regla', 'alta', 'prueba')""", (abierta["id_caso"],))
    antes = repositorio_en_vivo.estado_de("sparkov", "1009")["n"]
    rechazada = evaluar(compra("1009", 5, score=0.99))
    assert rechazada["decision"] == "rechazada_por_bloqueo" and rechazada["evento"] is None
    assert repositorio_en_vivo.estado_de("sparkov", "1009")["n"] == antes
    assert len(repositorio.obtener_caso(abierta["id_caso"])["transacciones"]) == 1


def test_la_misma_compra_dos_veces_no_se_duplica(base, eventos):
    transaccion = compra("1010", 0, score=0.98)
    primera = evaluar(transaccion)
    repetida = evaluar(transaccion)
    assert repetida["repetida"] is True and repetida["id_caso"] == primera["id_caso"]
    assert repositorio_en_vivo.estado_de("sparkov", "1010")["n"] == 1


def test_la_etiqueta_se_guarda_pero_la_app_no_la_lee(base, eventos):
    resultado = evaluar(compra("1011", 0), etiqueta=1)
    assert como_dueno("select es_fraude_dataset from transacciones_evaluadas where id = %s",
                      (resultado["id"],))[0][0] == 1
    feed = repositorio_en_vivo.ultimas_evaluadas(limite=500)
    assert all("es_fraude_dataset" not in fila and "id_cuenta" not in fila for fila in feed)


@pytest.mark.parametrize("cambio,mensaje", [
    ({"monto": -5}, "monto"), ({"latitud": 200}, "coordenadas"), ({"fecha_hora": "ayer"}, "fecha"),
    ({"categoria": ""}, "categoria"),
])
def test_transaccion_invalida_se_rechaza_en_espanol(base, cambio, mensaje):
    with pytest.raises(flujo.TransaccionInvalida, match=mensaje):
        evaluar({**compra("1012", 0), **cambio})


def test_tarjeta_sin_perfil_ni_domicilio_se_rechaza(base):
    with pytest.raises(flujo.TransaccionInvalida, match="domicilio"):
        flujo.evaluar_transaccion(compra("9999", 0), motor=MotorFalso())


def test_con_el_modelo_real_una_compra_rara_se_marca(base, eventos):
    # Tarjeta con 60 compras pequeñas de día y, de golpe, una grande de madrugada en línea.
    estado = EstadoTarjeta("2001", *CASA)
    for dia in range(60):
        actualizar(estado, {"fecha_hora": datetime(2020, 5, 1, 14) + timedelta(days=dia), "monto": 25.0,
                            "categoria": "grocery_pos", "latitud": CASA[0] + 0.05, "longitud": CASA[1] + 0.05})
    with repositorio_en_vivo.transaccion() as cur:
        repositorio_en_vivo.crear_perfil(cur, "sparkov", "2001", estado.a_dict(), alias="TAR-9001")
    rara = {"fuente": "sparkov", "id_cuenta": "2001", "id_transaccion": "real-1",
            "fecha_hora": datetime(2020, 7, 1, 2, 30), "monto": 950.0, "categoria": "shopping_net",
            "comercio": "Tienda en línea", "latitud": CASA[0] + 0.1, "longitud": CASA[1] + 0.1}
    resultado = flujo.evaluar_transaccion(rara, origen="api")
    assert resultado["score"] >= 0.95 and resultado["id_caso"] is not None
    assert resultado["latencia_total_ms"] < 500
    assert repositorio_en_vivo.tarjeta_por_alias("tar-9001") == ("sparkov", "2001")


# --- Ruta HTTP ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cliente(base):
    from fastapi.testclient import TestClient

    from app.principal import crear_app
    estado = EstadoTarjeta("3001", *CASA)
    for dia in range(30):
        actualizar(estado, {"fecha_hora": datetime(2020, 6, 1, 15) + timedelta(days=dia), "monto": 30.0,
                            "categoria": "grocery_pos", "latitud": CASA[0], "longitud": CASA[1]})
    with repositorio_en_vivo.transaccion() as cur:
        repositorio_en_vivo.crear_perfil(cur, "sparkov", "4000123412343001", estado.a_dict(), alias="TAR-3001")
    with TestClient(crear_app(), raise_server_exceptions=False) as http:
        yield http


def test_ruta_recibe_por_alias_con_fecha_y_lugar_por_defecto(cliente):
    respuesta = cliente.post("/api/transacciones", json={"tarjeta": "tar-3001", "monto": 25, "categoria": "grocery_pos",
                                                          "comercio": "Supermercado"})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tarjeta"] == "TAR-3001" and cuerpo["decision"] == "aprobada"
    assert "4000123412343001" not in respuesta.text


def test_ruta_tarjeta_inexistente_404_y_cuerpo_invalido_422_en_espanol(cliente):
    assert cliente.post("/api/transacciones", json={"tarjeta": "TAR-0000", "monto": 5, "categoria": "x"}).status_code == 404
    malo = cliente.post("/api/transacciones", json={"tarjeta": "TAR-3001", "monto": -1, "categoria": "x"})
    assert malo.status_code == 422 and "monto" in malo.json()["error"]
    fecha = cliente.post("/api/transacciones", json={"tarjeta": "TAR-3001", "monto": 5, "categoria": "x",
                                                      "fecha_hora": "mañana"})
    assert fecha.status_code == 422 and "fecha" in fecha.json()["error"]


def test_feed_y_tarjetas_sin_numero_completo(cliente):
    feed = cliente.get("/api/transacciones/recientes").json()["transacciones"]
    tarjetas = cliente.get("/api/tarjetas").json()["tarjetas"]
    assert feed and tarjetas
    assert "4000123412343001" not in str(feed) + str(tarjetas)
    assert any(t["alias"] == "TAR-3001" and t["tarjeta_enmascarada"].endswith("3001") for t in tarjetas)


def test_reiniciar_en_vivo_borra_lo_generado_y_conserva_la_semilla(cliente):
    from app.db import migrar
    evaluar(compra("1020", 0, score=0.99))
    antes_semilla = {fila[0] for fila in como_dueno("select id_transaccion from historial where origen = 'semilla'")}
    borrados = migrar.reiniciar_en_vivo()
    assert borrados["casos"] > 0 and borrados["transacciones_evaluadas"] > 0
    assert como_dueno("select count(*) from casos where origen = 'en_vivo'")[0][0] == 0
    assert como_dueno("select count(*) from historial where origen = 'en_vivo'")[0][0] == 0
    # Ninguna fila de la semilla se pierde (el reinicio además recarga el historial del simulador).
    despues_semilla = {fila[0] for fila in como_dueno("select id_transaccion from historial where origen = 'semilla'")}
    assert antes_semilla <= despues_semilla
    # La numeración de casos vuelve a empezar.
    assert evaluar(compra("1021", 0, score=0.99))["id_caso"] == "VIV-000001"
