"""Perfil de cada tarjeta mantenido transacción a transacción (un "feature store" mínimo).

Por qué existe: el modelo compara cada compra contra TODO lo que la tarjeta hizo antes
(cuántas compras, su promedio y su dispersión, a qué horas y en qué categorías suele
comprar, a qué distancia de su casa, su ritmo diario y lo que movió en las últimas
24 h). Fuera de línea, `src/perfil_cuenta.agregar_features` lo calcula con sumas
acumuladas sobre el dataset completo. En vivo no se puede releer el historial entero de
la tarjeta en cada compra, así que se guarda el **estado acumulado** y se actualiza con
cada transacción, que es lo que hacen los sistemas de fraude de los bancos para responder
en milisegundos.

La regla que no se negocia: este módulo debe dar **exactamente** las mismas features
que `agregar_features` para la misma secuencia de transacciones. Lo verifica
`app/pruebas/test_perfil_incremental.py` contra la función original, feature por
feature, y `scripts/validar_paridad_en_vivo.py` sobre Sparkov con el modelo real.

Las fórmulas, una por una, son las de `src/perfil_cuenta.py`:

- `n_previas`: compras anteriores; `sin_historial` si son menos de 10.
- promedio y desviación con suma y suma de cuadrados (varianza = E[x²] − E[x]², con
  piso de 1,0 para la desviación); `z_monto` y `razon_monto` (promedio con piso de 1,0).
- `frecuencia_hora_previa` y `frecuencia_categoria_previa`: fracción de las compras
  previas con la misma hora o la misma categoría.
- `conteo_24h_previo` y `monto_24h_previo`: compras en [t − 24 h, t), incluido el borde
  izquierdo, como el `searchsorted(..., side="left")` original.
- `tasa_diaria_previa`: compras previas / días desde la primera compra (piso de 1 día).
- distancia domicilio-comercio (Haversine) y su diferencia contra el promedio previo.
- Con `sin_historial`, las features relativas toman el valor neutro del original.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from perfil_cuenta import MINIMO_HISTORIAL, PISO_DESVIACION_MONTO, distancia_km_vectorizada

from detectar_viaje_imposible import VELOCIDAD_MAXIMA_PLAUSIBLE_KMH, distancia_km

VENTANA_24H = timedelta(hours=24)
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"
NEUTROS = {"z_monto": 0.0, "razon_monto": 1.0, "frecuencia_hora_previa": 0.5,
           "frecuencia_categoria_previa": 0.5, "distancia_vs_habitual_km": 0.0}


def _fecha(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    return datetime.strptime(str(valor)[:19], FORMATO_FECHA)


@dataclass
class EstadoTarjeta:
    """Lo que el banco sabe de una tarjeta ANTES de la próxima compra."""
    id_cuenta: str
    latitud_domicilio: float
    longitud_domicilio: float
    n: int = 0
    suma: float = 0.0
    suma_cuadrados: float = 0.0
    suma_distancia: float = 0.0
    primera_fecha: datetime | None = None
    conteo_hora: list[int] = field(default_factory=lambda: [0] * 24)
    conteo_categoria: dict[str, int] = field(default_factory=dict)
    # Compras de las últimas 24 h (fecha, monto), en orden; se recorta al actualizar.
    ventana_24h: list[tuple[datetime, float]] = field(default_factory=list)
    # Última compra, para el detector de viaje imposible.
    ultima_fecha: datetime | None = None
    ultima_latitud: float | None = None
    ultima_longitud: float | None = None

    # --- Persistencia (jsonb) -------------------------------------------------------
    def a_dict(self) -> dict:
        return {
            "id_cuenta": self.id_cuenta,
            "latitud_domicilio": self.latitud_domicilio, "longitud_domicilio": self.longitud_domicilio,
            "n": self.n, "suma": self.suma, "suma_cuadrados": self.suma_cuadrados,
            "suma_distancia": self.suma_distancia,
            "primera_fecha": self.primera_fecha.strftime(FORMATO_FECHA) if self.primera_fecha else None,
            "conteo_hora": self.conteo_hora, "conteo_categoria": self.conteo_categoria,
            "ventana_24h": [[f.strftime(FORMATO_FECHA), m] for f, m in self.ventana_24h],
            "ultima_fecha": self.ultima_fecha.strftime(FORMATO_FECHA) if self.ultima_fecha else None,
            "ultima_latitud": self.ultima_latitud, "ultima_longitud": self.ultima_longitud,
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> "EstadoTarjeta":
        return cls(
            id_cuenta=str(datos["id_cuenta"]),
            latitud_domicilio=float(datos["latitud_domicilio"]),
            longitud_domicilio=float(datos["longitud_domicilio"]),
            n=int(datos["n"]), suma=float(datos["suma"]), suma_cuadrados=float(datos["suma_cuadrados"]),
            suma_distancia=float(datos["suma_distancia"]),
            primera_fecha=_fecha(datos["primera_fecha"]) if datos.get("primera_fecha") else None,
            conteo_hora=[int(x) for x in datos["conteo_hora"]],
            conteo_categoria={str(k): int(v) for k, v in datos["conteo_categoria"].items()},
            ventana_24h=[(_fecha(f), float(m)) for f, m in datos["ventana_24h"]],
            ultima_fecha=_fecha(datos["ultima_fecha"]) if datos.get("ultima_fecha") else None,
            ultima_latitud=datos.get("ultima_latitud"), ultima_longitud=datos.get("ultima_longitud"),
        )


def _distancia_domicilio(estado: EstadoTarjeta, latitud: float, longitud: float) -> float:
    # La misma función vectorizada del motor, con escalares: mismo resultado bit a bit.
    return float(distancia_km_vectorizada(estado.latitud_domicilio, estado.longitud_domicilio, latitud, longitud))


def features_de(estado: EstadoTarjeta, transaccion: dict) -> dict:
    """Features de la transacción contra el estado previo (no modifica el estado).

    `transaccion`: fecha_hora, monto, categoria, latitud, longitud (las del comercio).
    Devuelve las features del modelo y las columnas auxiliares que usan las señales.
    """
    fecha = _fecha(transaccion["fecha_hora"])
    monto = float(transaccion["monto"])
    hora = fecha.hour
    categoria = str(transaccion["categoria"])
    n = estado.n
    sin_historial = n < MINIMO_HISTORIAL

    if n > 0:
        promedio = estado.suma / n
        varianza = max(estado.suma_cuadrados / n - promedio ** 2, 0.0)
        frecuencia_hora = estado.conteo_hora[hora] / n
        frecuencia_categoria = estado.conteo_categoria.get(categoria, 0) / n
        distancia_previa = estado.suma_distancia / n
    else:
        promedio = varianza = frecuencia_hora = frecuencia_categoria = distancia_previa = math.nan
    desviacion = max(math.sqrt(varianza), PISO_DESVIACION_MONTO) if n > 0 else math.nan
    z_monto = (monto - promedio) / desviacion if n > 0 else math.nan
    razon_monto = monto / max(promedio, PISO_DESVIACION_MONTO) if n > 0 else math.nan

    desde = fecha - VENTANA_24H
    en_ventana = [m for f, m in estado.ventana_24h if f >= desde]
    primera = estado.primera_fecha or fecha
    dias = max((fecha - primera).total_seconds() / 86400, 1.0)
    distancia = _distancia_domicilio(estado, float(transaccion["latitud"]), float(transaccion["longitud"]))

    valores = {
        "monto": monto,
        "hora": hora,
        "z_monto": z_monto,
        "razon_monto": razon_monto,
        "frecuencia_hora_previa": frecuencia_hora,
        "conteo_24h_previo": len(en_ventana),
        "monto_24h_previo": float(sum(en_ventana)),
        "tasa_diaria_previa": n / dias,
        "sin_historial": int(sin_historial),
        "frecuencia_categoria_previa": frecuencia_categoria,
        "distancia_domicilio_km": distancia,
        "distancia_vs_habitual_km": distancia - distancia_previa if n > 0 else math.nan,
        # Auxiliares para las señales en palabras (src/motor_riesgo._senales_de).
        "n_previas": n,
        "monto_promedio_previo": promedio,
        "monto_desv_previa": desviacion,
        "distancia_promedio_previa_km": distancia_previa,
        "categoria": categoria,
    }
    for columna, neutro in NEUTROS.items():
        if sin_historial or math.isnan(valores[columna]):
            valores[columna] = neutro
    return valores


def es_viaje_imposible(estado: EstadoTarjeta, transaccion: dict) -> bool:
    """Misma regla que src/detectar_viaje_imposible.py en modo "coordenadas": velocidad > 900 km/h."""
    if estado.ultima_fecha is None:
        return False
    horas = (_fecha(transaccion["fecha_hora"]) - estado.ultima_fecha).total_seconds() / 3600
    if horas <= 0:
        return False
    distancia = distancia_km(estado.ultima_latitud, estado.ultima_longitud,
                             float(transaccion["latitud"]), float(transaccion["longitud"]))
    return distancia / horas > VELOCIDAD_MAXIMA_PLAUSIBLE_KMH


def actualizar(estado: EstadoTarjeta, transaccion: dict) -> None:
    """Suma la transacción al estado: desde ahora cuenta como "compra previa"."""
    fecha = _fecha(transaccion["fecha_hora"])
    monto = float(transaccion["monto"])
    latitud, longitud = float(transaccion["latitud"]), float(transaccion["longitud"])
    categoria = str(transaccion["categoria"])
    estado.n += 1
    estado.suma += monto
    estado.suma_cuadrados += monto ** 2
    estado.suma_distancia += _distancia_domicilio(estado, latitud, longitud)
    if estado.primera_fecha is None:
        estado.primera_fecha = fecha
    estado.conteo_hora[fecha.hour] += 1
    estado.conteo_categoria[categoria] = estado.conteo_categoria.get(categoria, 0) + 1
    # Las próximas compras son posteriores: lo que ya salió de la ventana de esta, sale de todas.
    estado.ventana_24h = [(f, m) for f, m in estado.ventana_24h if f >= fecha - VENTANA_24H] + [(fecha, monto)]
    estado.ultima_fecha, estado.ultima_latitud, estado.ultima_longitud = fecha, latitud, longitud


def perfil_resumido(estado: EstadoTarjeta, fecha, cuantos: int = 3) -> dict:
    """El perfil previo en el formato de `src/perfil_cuenta.perfil_al_momento` (va a casos.perfil_previo).

    Es lo que el agente lee con `obtener_perfil_cuenta`, así que un caso en vivo se ve
    igual que uno de la semilla.
    """
    n = estado.n
    perfil = {"n_transacciones_previas": n, "sin_historial": n < MINIMO_HISTORIAL}
    if n == 0:
        return perfil
    fecha = _fecha(fecha)
    promedio = estado.suma / n
    dias = max((fecha - (estado.primera_fecha or fecha)).total_seconds() / 86400, 1)
    perfil["monto_promedio"] = round(promedio, 2)
    perfil["monto_desviacion"] = round(math.sqrt(max(estado.suma_cuadrados / n - promedio ** 2, 0.0)), 2)
    perfil["transacciones_por_dia"] = round(n / dias, 2)
    horas = sorted(range(24), key=lambda h: (-estado.conteo_hora[h], h))[:cuantos]
    perfil["horas_habituales"] = [{"hora": h, "porcentaje": round(100 * estado.conteo_hora[h] / n, 1)}
                                  for h in horas if estado.conteo_hora[h]]
    categorias = sorted(estado.conteo_categoria.items(), key=lambda par: (-par[1], par[0]))[:cuantos]
    perfil["categorias_habituales"] = [{"categoria": c, "porcentaje": round(100 * v / n, 1)} for c, v in categorias]
    return perfil
