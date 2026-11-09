"""Configuración común de las pruebas.

El triaje automático y la red de seguridad corren en hilos de fondo al arrancar la app. En las
pruebas se apagan: cada prueba que los necesita los llama a mano, con dobles y sin carreras.
"""

from app import config

config.FLUJO_AUTOMATICO = False
