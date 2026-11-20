"""
Configuración común de las pruebas del backend.

`backend/api/database.py` ejecuta `init_db()` al importarse, y los módulos de
prueba importan ese módulo a nivel de archivo. Sin esta red de seguridad, la
primera ejecución de `pytest` tras añadir una migración (por ejemplo la tabla
`proveedores` de RF-43) aplicaría los cambios sobre `backend/datos/inventario.db`,
la base de datos real del usuario.

Aquí se apunta `INVENTARIO_DB` a un archivo temporal **antes** de que pytest
importe cualquier módulo de prueba. Cada test sigue parcheando `DB_PATH` a su
propio `tmp_path`, así que este archivo solo absorbe el `init_db()` implícito
del import.
"""
import os
import tempfile
from pathlib import Path

# Se mantiene la referencia viva: si el objeto se recolecta, el directorio
# temporal se borra al instante y el import de `database` fallaría.
_DIRECTORIO_TEMPORAL = tempfile.TemporaryDirectory(prefix="inventario-ia-tests-")

# `setdefault`: si alguien define INVENTARIO_DB a propósito, se respeta.
os.environ.setdefault(
    "INVENTARIO_DB", str(Path(_DIRECTORIO_TEMPORAL.name) / "conftest.db")
)
