"""Arma el ZIP de la entrega del Momento 2 y se niega a cerrarlo si lleva una llave.

Por qué existe: la página de la entrega dice que un ZIP que no arranca es nota cero y
que jamás puede llevar llaves reales; además prohíbe carpetas pesadas (.venv/, .git/,
node_modules/). Armarlo a mano desde el explorador de archivos es justo como se cuela
un `.env` con llaves o 500 MB de CSV de Kaggle. Este script lo arma siempre igual:

1. Lista blanca: solo entra lo que la app, la evaluación y la sustentación necesitan
   (diseno/evaluacion-entrega.md). Todo lo demás queda fuera por defecto.
2. Exclusiones dentro de la lista blanca: `__pycache__/`, `.pytest_cache/`, `*.pyc`,
   `*.joblib`, `*.csv` sueltos, `.env` y cualquier `.env.*` que no sea `.env.example`.
3. Comprobaciones que abortan sin escribir el ZIP:
   - patrones de llave (`AIza…` de Google, `AQ.Ab…` de Google OAuth/Vertex,
     `sk-ant-…` de Anthropic, `gsk_…` de Groq) en el contenido de TODOS los archivos,
     incluidos los .gz descomprimidos;
   - `.env.example` con algún valor en una variable de llave;
   - scripts `.sh` con finales de línea de Windows (\\r\\n), que en Linux/macOS
     fallan con "bad interpreter".
4. `run.sh` entra con permiso de ejecución (0755) dentro del ZIP, para que
   `./run.sh` funcione al descomprimir en Linux/macOS.
5. Todo va dentro de una carpeta raíz (`fraude-bancario/`), para que descomprimir no
   desparrame archivos en la carpeta del evaluador.

Uso (desde la raíz del proyecto):
    python scripts/empaquetar_entrega.py                    # deja el ZIP en la carpeta padre del proyecto
    python scripts/empaquetar_entrega.py --salida C:/tmp    # o donde se indique
"""

import argparse
import gzip
import os
import re
import sys
import zipfile
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA_EN_ZIP = "fraude-bancario"

CARPETAS_PERMITIDAS = ["app", "src", "scripts", "semilla", "eval", "docs", "requisitos", "diseno", "validacion"]
ARCHIVOS_PERMITIDOS = ["README.md", "docker-compose.yml", "run.sh", ".env.example", ".dockerignore",
                       "decisiones.md", "CLAUDE.md"]
# Lo que es obligatorio según la página de la entrega: si falta, el ZIP no se arma.
OBLIGATORIOS = ["README.md", "docker-compose.yml", "run.sh", ".env.example", "docs/decisiones.md",
                "eval/casos_dorados.json", "app/Dockerfile", "semilla/casos_sparkov.json"]

CARPETAS_EXCLUIDAS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".git", "node_modules", "datos", ".claude"}
EXTENSIONES_EXCLUIDAS = {".pyc", ".pyo", ".joblib", ".csv"}
EJECUTABLES = {"run.sh"}

# Los cuantificadores mínimos evitan que este mismo archivo o el README (que nombran
# los prefijos) disparen la alarma: una llave real siempre trae decenas de caracteres.
PATRONES_LLAVE = {
    "Google (AIza…)": re.compile(rb"AIza[0-9A-Za-z_\-]{30,}"),
    "Google OAuth/Vertex (AQ.Ab…)": re.compile(rb"AQ\.Ab[0-9A-Za-z_\-]{20,}"),
    "Anthropic (sk-ant-…)": re.compile(rb"sk-ant-[0-9A-Za-z_\-]{20,}"),
    "Groq (gsk_…)": re.compile(rb"gsk_[0-9A-Za-z]{20,}"),
}
# Variables cuyo nombre termina en API_KEY, _SECRET o _TOKEN (no MAX_TOKENS_RESPUESTA).
VARIABLES_DE_LLAVE = re.compile(r"^\s*([A-Z0-9_]*(API_KEY|_SECRET|_TOKEN))\s*=\s*(.*)$")


def archivos_a_empaquetar() -> list[str]:
    """Rutas relativas (con /) de todo lo que entra, en orden estable."""
    rutas = []
    for nombre in ARCHIVOS_PERMITIDOS:
        if os.path.isfile(os.path.join(RAIZ, nombre)):
            rutas.append(nombre)
    for carpeta in CARPETAS_PERMITIDAS:
        base = os.path.join(RAIZ, carpeta)
        if not os.path.isdir(base):
            continue
        for actual, subcarpetas, archivos in os.walk(base):
            subcarpetas[:] = sorted(s for s in subcarpetas if s not in CARPETAS_EXCLUIDAS)
            for archivo in sorted(archivos):
                if os.path.splitext(archivo)[1].lower() in EXTENSIONES_EXCLUIDAS:
                    continue
                if archivo == ".env" or (archivo.startswith(".env.") and archivo != ".env.example"):
                    continue
                rutas.append(os.path.relpath(os.path.join(actual, archivo), RAIZ).replace(os.sep, "/"))
    return rutas


def contenido_para_revisar(ruta: str) -> bytes:
    with open(os.path.join(RAIZ, ruta), "rb") as archivo:
        datos = archivo.read()
    if ruta.endswith(".gz"):
        try:
            datos += gzip.decompress(datos)
        except OSError:
            pass
    return datos


def buscar_llaves(rutas: list[str]) -> list[str]:
    hallazgos = []
    for ruta in rutas:
        datos = contenido_para_revisar(ruta)
        for nombre, patron in PATRONES_LLAVE.items():
            for coincidencia in patron.finditer(datos):
                # Nunca se imprime la llave: solo el prefijo, para poder encontrarla.
                hallazgos.append(f"{ruta}: posible llave {nombre} que empieza por {coincidencia.group()[:8].decode()}…")
    return hallazgos


def revisar_env_example() -> list[str]:
    problemas = []
    with open(os.path.join(RAIZ, ".env.example"), encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, 1):
            coincidencia = VARIABLES_DE_LLAVE.match(linea)
            if coincidencia and coincidencia.group(3).strip().strip("\"'"):
                problemas.append(f".env.example línea {numero}: {coincidencia.group(1)} tiene un valor; debe quedar vacía")
    return problemas


def revisar_finales_de_linea(rutas: list[str]) -> list[str]:
    return [f"{ruta}: tiene finales de línea de Windows (\\r\\n); conviértalo a LF"
            for ruta in rutas if ruta.endswith(".sh") and b"\r" in contenido_para_revisar(ruta)]


def escribir_zip(rutas: list[str], destino: str) -> None:
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_salida:
        for ruta in rutas:
            info = zipfile.ZipInfo.from_file(os.path.join(RAIZ, ruta), arcname=f"{CARPETA_EN_ZIP}/{ruta}")
            info.compress_type = zipfile.ZIP_DEFLATED
            permisos = 0o755 if os.path.basename(ruta) in EJECUTABLES else 0o644
            info.external_attr = (0o100000 | permisos) << 16
            info.create_system = 3   # Unix: así unzip respeta los permisos de arriba
            with open(os.path.join(RAIZ, ruta), "rb") as archivo:
                zip_salida.writestr(info, archivo.read())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    analizador = argparse.ArgumentParser(description="Arma el ZIP de la entrega sin llaves ni carpetas pesadas.")
    analizador.add_argument("--salida", default=os.path.dirname(RAIZ),
                            help="Carpeta donde se escribe el ZIP (por defecto, la carpeta padre del proyecto).")
    argumentos = analizador.parse_args()

    faltan = [o for o in OBLIGATORIOS if not os.path.isfile(os.path.join(RAIZ, o))]
    if faltan:
        raise SystemExit(f"ABORTADO: faltan archivos obligatorios de la entrega: {', '.join(faltan)}")

    rutas = archivos_a_empaquetar()
    problemas = buscar_llaves(rutas) + revisar_env_example() + revisar_finales_de_linea(rutas)
    if problemas:
        print("ABORTADO: el ZIP no se escribió.", file=sys.stderr)
        for problema in problemas:
            print(f"  - {problema}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Búsqueda de llaves: 0 coincidencias en {len(rutas)} archivos "
          f"(patrones: {', '.join(PATRONES_LLAVE)}). .env.example sin valores de llave.")

    os.makedirs(argumentos.salida, exist_ok=True)
    destino = os.path.join(argumentos.salida, f"entrega_momento2_{date.today().isoformat()}.zip")
    escribir_zip(rutas, destino)

    tamano_mb = os.path.getsize(destino) / 1_000_000
    por_carpeta: dict[str, int] = {}
    for ruta in rutas:
        clave = ruta.split("/")[0] if "/" in ruta else "(raíz)"
        por_carpeta[clave] = por_carpeta.get(clave, 0) + os.path.getsize(os.path.join(RAIZ, ruta))
    print("Contenido (sin comprimir): " + ", ".join(f"{c} {b / 1_000_000:.2f} MB" for c, b in sorted(por_carpeta.items())))
    print(f"ZIP escrito: {destino}")
    print(f"Tamaño final: {tamano_mb:.2f} MB · {len(rutas)} archivos · run.sh con permiso 0755.")


if __name__ == "__main__":
    main()
