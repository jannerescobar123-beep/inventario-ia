import sqlite3
import os
import unicodedata
from pathlib import Path

# Ruta de la base de datos (archivo único, cero configuración como en ADR-001)
BASE_DIR = Path(__file__).parent.parent  # backend/
DB_PATH = BASE_DIR / "datos" / "inventario.db"


def normalizar_texto(valor) -> str:
    """
    Normalizar texto para comparaciones: sin tildes y en mayúsculas.

    SQLite UPPER() solo afecta al alfabeto ASCII, por eso la comparación
    entre catálogo y ventas se hace contra estas columnas auxiliares
    (productos.nombre_norm y ventas.producto_norm).
    """
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().upper()


def get_db():
    """Obtener conexión a la base de datos SQLite."""
    # La carpeta de datos se crea si no existe (instalación limpia)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializar las tablas de la base de datos si no existen."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabla: productos (stock, costo, precio, categoría)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE,
            nombre TEXT NOT NULL,
            categoria TEXT,
            costo REAL DEFAULT 0,
            precio_venta REAL DEFAULT 0,
            stock_actual INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 0,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Columna auxiliar: nombre sin tildes y en mayúsculas.
    # SQLite UPPER() no elimina acentos, así que el emparejamiento entre el
    # catálogo y las ventas se hace contra este valor calculado en Python.
    cursor.execute("PRAGMA table_info(productos)")
    columnas = [c[1] for c in cursor.fetchall()]
    if "nombre_norm" not in columnas:
        cursor.execute("ALTER TABLE productos ADD COLUMN nombre_norm TEXT")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_nombre_norm ON productos(nombre_norm)")
    
    # Tabla: ventas (historial de ventas importadas)
    # La fecha se guarda como TEXT en formato ISO YYYY-MM-DD porque las
    # estadísticas usan DATE(v.fecha), STRFTIME('%m', v.fecha) y
    # v.fecha >= date('now', '-7 days')
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            producto TEXT NOT NULL,
            producto_norm TEXT,
            cantidad INTEGER NOT NULL,
            precio REAL NOT NULL,
            fecha_importacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Misma idea para la tabla de ventas: nombre sin tildes para los JOIN.
    # Se hace después del CREATE para no fallar con bases nuevas.
    cursor.execute("PRAGMA table_info(ventas)")
    columnas_ventas = [c[1] for c in cursor.fetchall()]
    if "producto_norm" not in columnas_ventas:
        cursor.execute("ALTER TABLE ventas ADD COLUMN producto_norm TEXT")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_producto_norm ON ventas(producto_norm)")
    
    # Índices para las consultas por producto y por fecha (estadísticas y alertas)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_producto ON ventas(producto)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha)")
    
    # Backfill: filas guardadas antes de existir las columnas normalizadas
    cursor.execute("SELECT id, nombre FROM productos WHERE nombre_norm IS NULL OR nombre_norm = ''")
    for prod_id, nombre in cursor.fetchall():
        cursor.execute(
            "UPDATE productos SET nombre_norm = ? WHERE id = ?",
            (normalizar_texto(nombre), prod_id),
        )
    cursor.execute("SELECT id, producto FROM ventas WHERE producto_norm IS NULL OR producto_norm = ''")
    for venta_id, producto in cursor.fetchall():
        cursor.execute(
            "UPDATE ventas SET producto_norm = ? WHERE id = ?",
            (normalizar_texto(producto), venta_id),
        )
    
    # Tabla: importaciones (historial de cargas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS importaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo_origen TEXT,
            total_filas INTEGER,
            productos_creados INTEGER DEFAULT 0,
            productos_actualizados INTEGER DEFAULT 0,
            fecha_importacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabla: kpis (puntos de cálculo frecuentemente consultados)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kpis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_calculo TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ventas_totales REAL DEFAULT 0,
            ticket_promedio REAL DEFAULT 0,
            unidades_vendidas INTEGER DEFAULT 0,
            margen_total REAL DEFAULT 0,
            top_productos TEXT DEFAULT '[]'
        )
    """)
    
    conn.commit()
    conn.close()

# Ejecutar inicialización al importar (solo primera vez)
init_db()