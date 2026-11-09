"""Pruebas del aviso al titular (SPEC, RF5): validación del motivo, plantilla y canal.

Los casos salen de lo que pasó de verdad: el 2026-11-08 el triaje real escribió la fecha como
"20/07/2020" y la validación la confundía con un monto inventado. Y de los ataques que
importan: enlaces, teléfonos, pedidos de claves y montos que no están en la evidencia.
"""

import pytest

from app import config
from app.riesgo import avisos

CASO = {
    "tarjeta_enmascarada": "**** **** **** 2291",
    "perfil_previo": {"monto_promedio": 55.21},
    "transacciones": [
        {"monto": 956.22, "score": 0.99, "fecha_hora": "2020-07-19 23:40:00", "categoria": "shopping_net",
         "desviaciones": [{"descripcion": "Monto de 956,22: 17,3 veces su promedio previo (55,21)."}]},
        {"monto": 1850.0, "score": 0.98, "fecha_hora": "2020-07-20 03:11:00", "categoria": "shopping_net",
         "desviaciones": []},
    ],
}


@pytest.mark.parametrize("motivo", [
    "Detuvimos una compra de 1.850,00 en una tienda en línea el 20/07/2020 a las 03:11.",
    "Una compra de 956,22 USD el 2020-07-19 a las 23:40, 17,3 veces su promedio de 55,21.",
    "Compra de 1850.00 USD el 20 de julio de 2020, muy por encima de su promedio.",
    "Dos compras en línea seguidas por 2.806,22 USD en total, de madrugada.",
    "Compras en línea de madrugada, algo que casi nunca hace.",
])
def test_motivos_legitimos_pasan(motivo):
    assert avisos.validar_motivo(motivo, CASO) == []


@pytest.mark.parametrize("motivo,problema", [
    ("Para desbloquearla entre a www.banco-seguro.co.", "enlace"),
    ("Confirme en https://bit.ly/desbloqueo", "enlace"),
    ("Escriba a soporte@banco-demo.com", "correo"),
    ("Llame al 300 555 1234 para desbloquear.", "teléfono"),
    ("Llame al +57 (601) 555-1234.", "teléfono"),
    ("Responda con su clave para verificar.", "claves"),
    ("Envíenos el código que le llegó por SMS.", "claves"),
    ("Se detectó una compra de 9.999,99 USD.", "9.999,99"),
    ("Su tarjeta 4512 3456 7890 1234 fue bloqueada.", "número largo"),
    ("x" * 301, "300 caracteres"),
    ("   ", "vacío"),
])
def test_motivos_peligrosos_o_inventados_se_rechazan(motivo, problema):
    errores = avisos.validar_motivo(motivo, CASO)
    assert errores and any(problema in e for e in errores), errores


def test_motivo_rechazado_sale_con_la_plantilla_y_queda_registrado():
    aviso = avisos.armar("bloqueo", CASO, "Entre a www.malo.co ya")
    assert aviso["autor_motivo"] == "plantilla" and aviso["errores_validacion"]
    assert "malo.co" not in aviso["cuerpo"] and aviso["motivo_agente"] == "Entre a www.malo.co ya"
    assert "956,22 USD" in aviso["cuerpo"]             # la plantilla cita la compra más riesgosa (score 0,99)


def test_el_cuerpo_tiene_la_tarjeta_enmascarada_y_la_advertencia_fija():
    aviso = avisos.armar("verificacion", CASO, "Una compra de 956,22 USD en línea de madrugada.")
    assert aviso["autor_motivo"] == "agente" and "2291" in aviso["cuerpo"]
    assert "Nunca le pediremos claves ni le enviaremos enlaces." in aviso["cuerpo"]
    assert config.TELEFONO_OFICIAL_BANCO in aviso["cuerpo"]


def test_el_correo_solo_sale_a_la_lista_blanca(monkeypatch):
    monkeypatch.setattr(config, "CANAL_AVISOS", "correo")
    monkeypatch.setattr(config, "CORREO_DEMO_TITULAR", "titular@ejemplo.com")
    monkeypatch.setattr(config, "CORREOS_PERMITIDOS", set())
    sin_lista = avisos.armar("bloqueo", CASO, None)
    assert sin_lista["canal"] == "simulado"                       # sin lista blanca, nunca sale
    monkeypatch.setattr(config, "CORREOS_PERMITIDOS", {"titular@ejemplo.com"})
    con_lista = avisos.armar("bloqueo", CASO, None)
    assert con_lista["canal"] == "correo"
    con_lista["_correo"] = "otro@atacante.com"                    # aunque alguien cambie el destino...
    assert avisos.enviar(con_lista)[0] == "retenida"             # ...no sale fuera de la lista
