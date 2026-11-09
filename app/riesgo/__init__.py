"""Motor de riesgo en vivo: puntúa cada transacción al llegar (SPEC, RF1).

Reutiliza el código del motor fuera de línea (`src/`) en lugar de copiarlo, para que el
score de la app y el de la evaluación salgan de las mismas fórmulas y el mismo modelo.
`src/` usa importaciones planas (`from perfil_cuenta import ...`) porque sus scripts se
corren desde esa carpeta; por eso aquí se agrega `src/` a la ruta de búsqueda una sola
vez, en lugar de reescribir los scripts del motor.
"""

import os
import sys

CARPETA_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
if CARPETA_SRC not in sys.path:
    sys.path.insert(0, CARPETA_SRC)
