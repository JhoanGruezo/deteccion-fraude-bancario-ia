"""Configuración central de la app: todo lo que cambia entre máquinas viene del entorno.

Un solo lugar para los límites del agente, los modelos, las tarifas y las fallas
forzadas, para que la interfaz pueda mostrarlos y el README pueda documentarlos sin
adivinar. Las llaves de API NUNCA se escriben aquí ni en ningún archivo del proyecto:
llegan por variable de entorno (ver .env.example).
"""

import os


def _texto(nombre, por_defecto=""):
    # Una variable definida pero vacía en .env (DATABASE_URL=) cuenta como ausente.
    return os.environ.get(nombre, "").strip() or por_defecto


def _entero(nombre, por_defecto):
    return int(os.environ.get(nombre, por_defecto))


def _decimal(nombre, por_defecto):
    return float(os.environ.get(nombre, por_defecto))


def _booleano(nombre, por_defecto):
    return os.environ.get(nombre, str(por_defecto)).strip().lower() in {"1", "true", "si", "sí", "yes"}


# --- Base de datos -----------------------------------------------------------------
DATABASE_URL = _texto("DATABASE_URL", "postgresql://fraude:fraude_dev@localhost:5432/fraude")
CARPETA_SEMILLA = _texto("CARPETA_SEMILLA", os.path.join(os.path.dirname(os.path.dirname(__file__)), "semilla"))

# --- Proveedores de IA ---------------------------------------------------------------
GEMINI_API_KEY = _texto("GEMINI_API_KEY")
# Respaldo: Flash-Lite. El 2026-10-21 gemini-3.8-flash respondía 503 o tardaba 25-40 s
# por saturación, mientras 3.1 Flash-Lite atendía tool calling en 4-17 s.
GEMINI_MODELO = _texto("GEMINI_MODELO", "gemini-3.1-flash-lite")
ANTHROPIC_API_KEY = _texto("ANTHROPIC_API_KEY")
CLAUDE_MODELO = _texto("CLAUDE_MODELO", "claude-haiku-5-5")
# Razonamiento extendido de Claude: apagado (ver proveedores/claude.py, por qué).
CLAUDE_RAZONAMIENTO = _booleano("CLAUDE_RAZONAMIENTO", False)
# Orden de la cascada: el primero es el principal, el resto son respaldos.
ORDEN_PROVEEDORES = [p.strip() for p in _texto("ORDEN_PROVEEDORES", "claude,gemini").split(",") if p.strip()]

# Tarifas de lista en USD por millón de tokens (entrada, salida), consultadas el
# 2026-10-21 en agregadores de precios (OpenRouter, Apidog para Gemini; Sentra,
# aipricing.guru para Claude), no en la página oficial: verificar antes de citarlas.
# Gemini 3.8 Flash: tarifa introductoria hasta el 2026-12-31 (sube a 1,50 / 7,50).
# Claude Haiku 5.5: tramo de prompts de hasta 100 000 tokens.
TARIFAS_USD_POR_MILLON = {
    "gemini-3.8-flash": (_decimal("TARIFA_GEMINI_ENTRADA", 0.75), _decimal("TARIFA_GEMINI_SALIDA", 3.75)),
    # Gemini 3.1 Flash-Lite: 0,25 / 1,50 (anotherwrapper.com y morphllm.com, citando ai.google.dev).
    "gemini-3.1-flash-lite": (_decimal("TARIFA_GEMINI_LITE_ENTRADA", 0.25), _decimal("TARIFA_GEMINI_LITE_SALIDA", 1.50)),
    "claude-haiku-5-5": (_decimal("TARIFA_CLAUDE_ENTRADA", 0.10), _decimal("TARIFA_CLAUDE_SALIDA", 0.50)),
}

# --- Los cuatro límites del agente ---------------------------------------------------
# Dimensionados con la tarea más larga esperada (explicar un caso: 3-4 herramientas,
# 2-3 iteraciones con llamadas + 1 final). Ver diseno/agente.md. Medición real del
# 2026-10-21: una explicación con reintento de contrato consumió ~28 000 tokens de
# entrada (cada iteración reenvía la conversación), por eso el presupuesto es 40 000;
# el presupuesto se revisa antes de cada llamada, así que una llamada puede pasarlo
# como máximo en su propio tamaño.
MAX_ITERACIONES = _entero("MAX_ITERACIONES", 6)
PRESUPUESTO_TOKENS = _entero("PRESUPUESTO_TOKENS", 40_000)
TIMEOUT_MODELO_S = _decimal("TIMEOUT_MODELO_S", 25.0)
TIMEOUT_HERRAMIENTA_S = _decimal("TIMEOUT_HERRAMIENTA_S", 5.0)
MAX_TOKENS_RESPUESTA = _entero("MAX_TOKENS_RESPUESTA", 2_500)
# El cuarto límite (confirmación humana) no es un número: toda herramienta que
# escribe solo crea una propuesta pendiente (ver agente/herramientas.py).

# Esperas del backoff ante 429/5xx/timeout, en segundos, antes de conmutar.
ESPERAS_REINTENTO_S = tuple(float(x) for x in _texto("ESPERAS_REINTENTO_S", "1,2,4").split(","))

# --- Fallas forzadas para la demo (reto de la semana 9) -----------------------------
# FALLA_FORZADA: "" | "429" | "timeout" | "json" | "todo"
FALLA_FORZADA = _texto("FALLA_FORZADA")
FALLAS_VALIDAS = {"", "429", "timeout", "json", "todo"}
PERMITIR_FALLAS_DESDE_UI = _booleano("PERMITIR_FALLAS_DESDE_UI", True)

# --- Servidor -----------------------------------------------------------------------
PUERTO = _entero("PUERTO", 8000)
