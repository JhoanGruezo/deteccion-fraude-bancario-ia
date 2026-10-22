"""Cliente SSE mínimo para medir al agente tal como lo ve el navegador del analista.

Por qué existe: la suite y el lote (diseno/evaluacion-entrega.md) corren contra la app
real en http://localhost:8000 y no contra funciones internas, para que la latencia
medida incluya red, base de datos y proveedor de IA, que es lo que sufre el analista.
Este módulo abre el mismo endpoint `text/event-stream` que abre el `EventSource` del
frontend, lee los eventos uno a uno apenas llegan y anota cuándo llegó cada uno.

Solo usa la biblioteca estándar (urllib): el evaluador no tiene que instalar nada para
correr `eval/`, y funciona igual en Windows, macOS y Linux (se decodifica UTF-8 a
mano y se aceptan finales de línea \\r\\n).

Tiempos que mide (en milisegundos, con reloj monotónico del cliente):
- `primer_evento_ms`: desde la petición hasta el primer evento (el `estado` que la API
  escribe antes de tocar al modelo: muestra que el stream es real, no una respuesta
  que llega toda al final).
- `ttft_ms`: desde la petición hasta el primer evento `token` (primer fragmento de
  texto del modelo). Es el TTFT que ve el analista. Es None si no hubo tokens (caché,
  plantilla o rechazo sin texto en streaming).
- `total_ms`: desde la petición hasta el evento `fin` (latencia de extremo a extremo).

Uso suelto, útil para depurar un caso:
    python eval/cliente_sse.py SPK-000001 --regenerar
    python eval/cliente_sse.py SPK-000001 --pregunta "¿Cuál fue la compra más rara?"
    python eval/cliente_sse.py SPK-000001 --regenerar --falla 429
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

URL_BASE_POR_DEFECTO = "http://localhost:8000"
# Una tarea con tres reintentos y conmutación tarda menos de un minuto; dos minutos
# separan "lento" de "colgado" sin cortar una tarea legítima.
TIMEOUT_POR_DEFECTO_S = 180.0


@dataclass
class ResultadoStream:
    """Todo lo que pasó en una conexión SSE: eventos con su instante y los tiempos clave."""

    url: str
    estado_http: int | None = None
    eventos: list[dict] = field(default_factory=list)   # {"tipo", "datos", "t_ms"}; sin el texto de los token
    n_tokens: int = 0
    texto_tokens: str = ""
    primer_evento_ms: int | None = None
    ttft_ms: int | None = None
    total_ms: int | None = None
    termino_con_fin: bool = False
    error_cliente: str | None = None

    def primero(self, tipo: str) -> dict | None:
        """Datos del primer evento de ese tipo, o None."""
        for evento in self.eventos:
            if evento["tipo"] == tipo:
                return evento["datos"]
        return None

    def todos(self, tipo: str) -> list[dict]:
        return [evento["datos"] for evento in self.eventos if evento["tipo"] == tipo]

    @property
    def fin(self) -> dict:
        return self.primero("fin") or {}

    def como_dict(self) -> dict:
        datos = asdict(self)
        datos["texto_tokens"] = datos["texto_tokens"][:4000]   # basta para revisar; el JSON final ya va en los eventos
        return datos


def url_explicacion(base: str, id_caso: str, regenerar: bool = False, falla: str | None = None) -> str:
    parametros = {"regenerar": "1" if regenerar else "0"}
    if falla:
        parametros["falla"] = falla
    return f"{base}/api/casos/{urllib.parse.quote(id_caso)}/explicacion/stream?{urllib.parse.urlencode(parametros)}"


def url_pregunta(base: str, id_caso: str, pregunta: str, falla: str | None = None) -> str:
    parametros = {"q": pregunta}
    if falla:
        parametros["falla"] = falla
    return f"{base}/api/casos/{urllib.parse.quote(id_caso)}/preguntas/stream?{urllib.parse.urlencode(parametros)}"


def obtener_json(url: str, timeout_s: float = 30.0) -> dict:
    """GET que devuelve JSON (para /api/salud, /api/casos/{id}, etc.)."""
    peticion = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=timeout_s) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _milisegundos_desde(inicio: float) -> int:
    return int(round((time.perf_counter() - inicio) * 1000))


def abrir_stream(url: str, timeout_s: float = TIMEOUT_POR_DEFECTO_S) -> ResultadoStream:
    """Consume un endpoint SSE hasta el evento `fin` (o hasta que el servidor cierre).

    El formato lo fija app/api/sse.py: bloques `id:` / `event:` / `data:` separados por
    una línea vacía, y comentarios `: ping` que se ignoran. Nunca lanza excepción: un
    error de red o HTTP queda en `error_cliente`, para que el lote lo cuente como fallo
    y siga con la siguiente tarea en vez de morir a la mitad.
    """
    resultado = ResultadoStream(url=url)
    peticion = urllib.request.Request(url, headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"})
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(peticion, timeout=timeout_s) as respuesta:
            resultado.estado_http = respuesta.status
            tipo_actual, datos_actuales = None, []
            while True:
                linea_bytes = respuesta.readline()
                if not linea_bytes:          # el servidor cerró la conexión
                    break
                linea = linea_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                if linea == "":             # fin de un bloque: se despacha el evento
                    if tipo_actual is not None or datos_actuales:
                        if _despachar(resultado, tipo_actual or "message", "\n".join(datos_actuales), inicio):
                            break
                    tipo_actual, datos_actuales = None, []
                    continue
                if linea.startswith(":"):   # comentario (ping)
                    continue
                campo, _, valor = linea.partition(":")
                valor = valor[1:] if valor.startswith(" ") else valor
                if campo == "event":
                    tipo_actual = valor
                elif campo == "data":
                    datos_actuales.append(valor)
    except urllib.error.HTTPError as error:
        resultado.estado_http = error.code
        try:
            cuerpo = error.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001 — el cuerpo del error es informativo, no esencial
            cuerpo = ""
        resultado.error_cliente = f"HTTP {error.code}: {cuerpo}"
    except Exception as error:  # noqa: BLE001 — timeout o conexión rechazada: se registra y se sigue
        resultado.error_cliente = f"{type(error).__name__}: {error}"
    resultado.total_ms = _milisegundos_desde(inicio)
    return resultado


def _despachar(resultado: ResultadoStream, tipo: str, texto_datos: str, inicio: float) -> bool:
    """Registra un evento; devuelve True si es `fin` (hay que dejar de leer)."""
    instante = _milisegundos_desde(inicio)
    try:
        datos = json.loads(texto_datos) if texto_datos else {}
    except json.JSONDecodeError:
        datos = {"crudo": texto_datos}
    if resultado.primer_evento_ms is None:
        resultado.primer_evento_ms = instante
    if tipo == "token":
        # Los fragmentos no se guardan uno por uno (serían cientos por tarea): solo
        # el conteo, el texto acumulado y el instante del primero (TTFT).
        resultado.n_tokens += 1
        resultado.texto_tokens += str(datos.get("texto", ""))
        if resultado.ttft_ms is None:
            resultado.ttft_ms = instante
        return False
    resultado.eventos.append({"tipo": tipo, "datos": datos, "t_ms": instante})
    if tipo == "fin":
        resultado.termino_con_fin = True
        resultado.total_ms = instante
        return True
    return False


def _imprimir_resumen(resultado: ResultadoStream) -> None:
    print(f"URL: {resultado.url}")
    print(f"HTTP {resultado.estado_http} · primer evento {resultado.primer_evento_ms} ms · "
          f"TTFT {resultado.ttft_ms} ms · total {resultado.total_ms} ms · {resultado.n_tokens} fragmentos")
    if resultado.error_cliente:
        print(f"Error del cliente: {resultado.error_cliente}")
    for evento in resultado.eventos:
        resumen = json.dumps(evento["datos"], ensure_ascii=False)
        print(f"  {evento['t_ms']:>6} ms  {evento['tipo']:<22} {resumen[:160]}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    analizador = argparse.ArgumentParser(description="Abre un stream SSE del agente y muestra eventos y tiempos.")
    analizador.add_argument("id_caso")
    analizador.add_argument("--pregunta", help="Si se da, usa el endpoint de preguntas en vez del de explicación.")
    analizador.add_argument("--regenerar", action="store_true", help="Ignora la explicación guardada (fuerza al agente).")
    analizador.add_argument("--falla", choices=["429", "timeout", "json", "todo"], help="Falla forzada para esta petición.")
    analizador.add_argument("--url-base", default=URL_BASE_POR_DEFECTO)
    argumentos = analizador.parse_args()

    if argumentos.pregunta:
        url = url_pregunta(argumentos.url_base, argumentos.id_caso, argumentos.pregunta, argumentos.falla)
    else:
        url = url_explicacion(argumentos.url_base, argumentos.id_caso, argumentos.regenerar, argumentos.falla)
    _imprimir_resumen(abrir_stream(url))


if __name__ == "__main__":
    main()
