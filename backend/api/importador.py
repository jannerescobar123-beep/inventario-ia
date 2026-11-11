import sqlite3
import pandas as pd
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any, Set, Tuple

try:  # Carga como parte del paquete (python -m uvicorn backend.api.main:app)
    from backend.api.database import init_db
except ImportError:  # Ejecución directa del módulo (backend/api)
    from database import init_db

BASE_DIR = Path(__file__).parent.parent  # backend/
DB_PATH = BASE_DIR / "datos" / "inventario.db"
DEMO_FILE = BASE_DIR / "datos" / "ventas_demo.xlsx"

# Extensiones de archivo soportadas por el importador
EXTENSIONES_EXCEL = {".xlsx", ".xls", ".xlsm"}
EXTENSIONES_CSV = {".csv"}


def _conectar() -> sqlite3.Connection:
    """Abrir conexión a SQLite creando la carpeta de datos si no existe."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH))


def _normalizar_fecha(valor: Any) -> str:
    """
    Normalizar una fecha a texto ISO 'YYYY-MM-DD'.

    Las estadísticas consultan la fecha con DATE(), STRFTIME('%m', ...) y
    comparaciones contra date('now', '-7 days'), por lo que el formato debe
    ser siempre ISO.
    """
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        raise ValueError("Fecha vacía")
    
    if isinstance(valor, (pd.Timestamp, datetime, date)):
        return valor.strftime("%Y-%m-%d")
    
    texto = str(valor).strip()
    if not texto:
        raise ValueError("Fecha vacía")
    
    try:
        return pd.to_datetime(texto, errors="raise").strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"Fecha inválida: {texto}") from e


def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizar los nombres de las columnas (sin espacios y en minúsculas)."""
    df = df.copy()
    df.columns = [str(columna).strip().lower() for columna in df.columns]
    return df


def normalizar_nombre(nombre: str) -> str:
    """
    Normalizar nombre de producto para comparaciones.

    Se eliminan tildes y se unifica a mayúsculas para que el emparejamiento
    entre el catálogo y las ventas sea insensible a acentos (ADR-003 §2).
    """
    import unicodedata

    texto = unicodedata.normalize("NFKD", str(nombre))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().upper()


def importar_excel(ruta_archivo: Optional[str] = None, 
                   tiene_hoja_productos: bool = True,
                   nombre_original: Optional[str] = None) -> Dict[str, Any]:
    """
    Importar archivo Excel con posible hoja 'productos' y hoja 'ventas'.
    
    Convención (ADR-003): Si existe hoja 'productos', se importa primero
    para que las ventas se emparejen con el catálogo (por SKU o nombre).
    """
    if ruta_archivo is None:
        ruta_archivo = str(DEMO_FILE) if DEMO_FILE.exists() else ruta_archivo
    
    if not ruta_archivo or not Path(ruta_archivo).exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_archivo}")
    
    # Garantizar que las tablas existan antes de escribir (idempotente)
    init_db()
    
    xl = pd.ExcelFile(ruta_archivo)
    nombres_hojas = [str(n).strip().lower() for n in xl.sheet_names]
    resultado = {
        "archivo_origen": nombre_original or str(ruta_archivo),
        "productos_creados": 0,
        "productos_actualizados": 0,
        "total_ventas": 0,
        "errores": []
    }
    
    ids_creados: Set[int] = set()
    ids_actualizados: Set[int] = set()
    
    # 1. Importar hoja 'productos' si existe (ADR-003)
    if tiene_hoja_productos and "productos" in nombres_hojas:
        df_productos = _normalizar_columnas(pd.read_excel(xl, sheet_name="productos"))
        if not df_productos.empty:
            _, _, ids_creados_cat, ids_actualizados_cat = _procesar_productos(df_productos)
            ids_creados |= ids_creados_cat
            ids_actualizados |= ids_actualizados_cat
    
    # 2. Importar hoja 'ventas'
    if "ventas" in nombres_hojas:
        df_ventas = _normalizar_columnas(pd.read_excel(xl, sheet_name="ventas"))
        if not df_ventas.empty:
            total_registros, errores, ids_creados_ventas, ids_actualizados_ventas = \
                _validar_y_guardar_ventas(df_ventas)
            ids_creados |= ids_creados_ventas
            ids_actualizados |= ids_actualizados_ventas
            resultado["total_ventas"] = total_registros
            resultado["errores"] = errores
    
    # Contadores sin duplicados: un producto creado no cuenta como actualizado
    resultado["productos_creados"] = len(ids_creados)
    resultado["productos_actualizados"] = len(ids_actualizados - ids_creados)
    
    # 3. Registrar importación en historial
    _registrar_importacion(resultado)
    
    return resultado


def importar_csv(ruta_archivo: Optional[str] = None,
                 nombre_original: Optional[str] = None) -> Dict[str, Any]:
    """
    Importar un archivo CSV de ventas (columnas: fecha, producto, cantidad, precio).
    
    Según ADR-003 el CSV es solo de ventas: los productos que no existan en el
    catálogo se crean automáticamente a partir de las ventas (RF-07).
    """
    if not ruta_archivo:
        raise FileNotFoundError("Se requiere la ruta de un archivo CSV")
    
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta}")
    
    # Garantizar que las tablas existan antes de escribir (idempotente)
    init_db()
    
    resultado = {
        "archivo_origen": nombre_original or str(ruta),
        "productos_creados": 0,
        "productos_actualizados": 0,
        "total_ventas": 0,
        "errores": []
    }
    
    df_ventas = _normalizar_columnas(pd.read_csv(ruta))
    if not df_ventas.empty:
        total_registros, errores, ids_creados, ids_actualizados = \
            _validar_y_guardar_ventas(df_ventas)
        resultado["total_ventas"] = total_registros
        resultado["errores"] = errores
        resultado["productos_creados"] = len(ids_creados)
        resultado["productos_actualizados"] = len(ids_actualizados - ids_creados)
    
    # Registrar importación en historial
    _registrar_importacion(resultado)
    
    return resultado


def importar_archivo(ruta_archivo: str,
                     nombre_original: Optional[str] = None) -> Dict[str, Any]:
    """
    Importar un archivo detectando el formato por extensión (.csv o Excel).

    Devuelve el resumen de importación (contrato ADR-003 §4).
    """
    ruta = Path(ruta_archivo)
    extension = ruta.suffix.lower()
    
    if extension in EXTENSIONES_CSV:
        return importar_csv(str(ruta), nombre_original=nombre_original)
    
    if extension in EXTENSIONES_EXCEL:
        return importar_excel(str(ruta), nombre_original=nombre_original)
    
    soportadas = ", ".join(sorted(EXTENSIONES_CSV | EXTENSIONES_EXCEL))
    raise ValueError(f"Formato de archivo no soportado: {extension or '(sin extensión)'}. Use: {soportadas}")


def _procesar_productos(df: pd.DataFrame) -> Tuple[int, int, Set[int], Set[int]]:
    """
    Procesar datos de la hoja productos.

    Retorna (creados, actualizados, ids_creados, ids_actualizados).
    """
    conn = _conectar()
    cursor = conn.cursor()
    
    creado = 0
    actualizado = 0
    ids_creados: Set[int] = set()
    ids_actualizados: Set[int] = set()
    
    for _, row in df.iterrows():
        # Buscar por SKU primero, luego por nombre
        sku = str(row.get("sku", "")).strip() if pd.notna(row.get("sku")) else ""
        nombre = str(row.get("producto", "")).strip() if pd.notna(row.get("producto")) else ""
        categoria = str(row.get("categoria", "")).strip() if pd.notna(row.get("categoria")) else ""
        costo = float(row.get("costo", 0)) if pd.notna(row.get("costo")) else 0
        precio_venta = float(row.get("precio_venta", 0)) if pd.notna(row.get("precio_venta")) else 0
        stock_inicial = int(row.get("stock_inicial", 0)) if pd.notna(row.get("stock_inicial")) else 0
        stock_minimo = int(row.get("stock_minimo", 0)) if pd.notna(row.get("stock_minimo")) else 0
        
        if not sku and not nombre:
            continue
        
        # Normalizar nombre para búsqueda
        nombre_norm = normalizar_nombre(nombre)
        
        # Buscar si existe
        if sku:
            cursor.execute("SELECT id, sku FROM productos WHERE sku = ?", (sku,))
        else:
            # Buscar producto por nombre normalizado
            nombre_norm = normalizar_nombre(nombre)
            cursor.execute(
                "SELECT id, nombre FROM productos WHERE nombre_norm = ?",
                (nombre_norm,),
            )
        
        fila_existente = cursor.fetchone()
        
        if fila_existente:
            # Actualizar producto existente
            cursor.execute("""
                UPDATE productos SET 
                    nombre = ?, nombre_norm = ?, categoria = ?, costo = ?, precio_venta = ?,
                    stock_actual = ?, stock_minimo = ?
                WHERE id = ?
            """, (nombre, nombre_norm, categoria, costo, precio_venta, stock_inicial, stock_minimo, fila_existente[0]))
            actualizado += 1
            ids_actualizados.add(fila_existente[0])
        else:
            # Crear nuevo producto
            if not sku:
                # Generar SKU a partir del nombre, garantizando que sea único
                sku = _generar_sku_unico(cursor, nombre) if nombre else "PROD"
            
            cursor.execute("""
                INSERT INTO productos (sku, nombre, nombre_norm, categoria, costo, precio_venta, 
                                       stock_actual, stock_minimo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sku, nombre, nombre_norm, categoria, costo, precio_venta, stock_inicial, stock_minimo))
            creado += 1
            ids_creados.add(cursor.lastrowid)
    
    conn.commit()
    conn.close()
    return creado, actualizado, ids_creados, ids_actualizados


def _validar_y_guardar_ventas(df: pd.DataFrame) -> Tuple[int, list, Set[int], Set[int]]:
    """
    Validar datos de ventas y guardarlos en la BD.

    Cada fila válida se persiste en la tabla 'ventas' con la fecha normalizada
    a ISO 'YYYY-MM-DD'. Retorna (ventas guardadas, errores, ids_creados,
    ids_actualizados) de los productos afectados.
    """
    conn = _conectar()
    cursor = conn.cursor()
    
    requeridas = {"fecha", "producto", "cantidad", "precio"}
    errores = []
    total_registros = 0
    ids_creados: Set[int] = set()
    ids_actualizados: Set[int] = set()
    
    for _, row in df.iterrows():
        # Validar columnas requeridas
        fila_errores = []
        for col in requeridas:
            if col not in df.columns or pd.isna(row.get(col)):
                fila_errores.append(f"Falta columna '{col}'")
        
        if fila_errores:
            errores.append({
                "fila": _numero_fila_df(df, _),
                "motivos": fila_errores
            })
            continue
        
        try:
            fecha = _normalizar_fecha(row["fecha"])
            producto_nombre = str(row["producto"]).strip()
            cantidad = int(row["cantidad"])
            precio = float(row["precio"])
            
            if not producto_nombre:
                raise ValueError("Nombre de producto vacío")
            if cantidad <= 0:
                raise ValueError("Cantidad debe ser positiva")
            if precio < 0:
                raise ValueError("Precio no puede ser negativo")
            
            # Buscar producto por nombre normalizado (columna nombre_norm:
            # sin tildes y en mayúsculas, calculado en Python)
            nombre_norm = normalizar_nombre(producto_nombre)
            cursor.execute(
                "SELECT id, nombre, stock_actual, precio_venta FROM productos WHERE nombre_norm = ?",
                (nombre_norm,),
            )
            prod = cursor.fetchone()
            
            if prod:
                prod_id, nombre_catalogo, stock_actual, precio_venta_base = prod
                # El stock del producto es el conteo físico actual
                # (ADR-003: NO se descuentan ventas históricas en esta fase)
                
                # Actualizar precio si es diferente
                if precio != precio_venta_base:
                    cursor.execute("UPDATE productos SET precio_venta = ? WHERE id = ?", (precio, prod_id))
                    ids_actualizados.add(prod_id)
                
                nombre_venta = nombre_catalogo
            else:
                # Crear producto nuevo automáticamente (RF-07)
                sku = _generar_sku_unico(cursor, producto_nombre)
                cursor.execute("""
                    INSERT INTO productos (sku, nombre, nombre_norm, costo, precio_venta, stock_actual)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sku, producto_nombre, nombre_norm, precio * 0.8, precio, 0))  # costo = 80% del precio
                nombre_venta = producto_nombre
                ids_creados.add(cursor.lastrowid)
            
            # Persistir la venta (las ventas no se pierden: se guardan en la tabla 'ventas')
            cursor.execute("""
                INSERT INTO ventas (fecha, producto, producto_norm, cantidad, precio)
                VALUES (?, ?, ?, ?, ?)
            """, (fecha, nombre_venta, nombre_norm, cantidad, precio))
            
            total_registros += 1
        except (ValueError, TypeError) as e:
            errores.append({
                "fila": _numero_fila_df(df, _),
                "motivo": str(e)
            })
    
    # Actualizar KPIs simplificados
    if total_registros > 0:
        _actualizar_kpis(cursor, total_registros)
    
    conn.commit()
    conn.close()
    
    return total_registros, errores, ids_creados, ids_actualizados


def _generar_sku_unico(cursor, nombre: str) -> str:
    """
    Generar un SKU único a partir del nombre del producto.

    Los primeros 8 caracteres pueden coincidir entre productos distintos
    (p. ej. 'Tornillos 8x40' y 'TornilloMétrico'), por lo que se añade un
    sufijo numérico cuando el SKU ya existe.
    """
    base = "".join(nombre.upper().split())[:8] or "PROD"
    sku = base
    sufijo = 2
    while True:
        cursor.execute("SELECT 1 FROM productos WHERE sku = ?", (sku,))
        if cursor.fetchone() is None:
            return sku
        sku = f"{base[:6]}-{sufijo}"
        sufijo += 1


def _numero_fila_df(df: pd.DataFrame, row) -> int:
    """Obtener el número de fila original del DataFrame."""
    try:
        return int(row.name) + 2  # +1 por header, +1 por index base 0
    except:
        return 0


def _actualizar_kpis(cursor, total_ventas: int):
    """Actualizar tabla de KPIs con cálculos simples."""
    # KPIs básicos: ventas totales, ticket promedio
    cursor.execute("""
        INSERT INTO kpis (ventas_totales, ticket_promedio, unidades_vendidas)
        VALUES (?, ?, ?)
    """, (total_ventas * 100,  # precio promedio estimado
          100,  # ticket estimado
          total_ventas))  # unidades
    
    # En un caso real calcularíamos los verdaderos KPIs aquí
    # Por ahora dejamos valores placeholder que se actualizarán con análisis real


def _registrar_importacion(resultado: Dict[str, Any]):
    """Registrar la importación en el historial."""
    conn = _conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO importaciones (archivo_origen, total_filas, productos_creados, productos_actualizados)
        VALUES (?, ?, ?, ?)
    """, (
        resultado.get("archivo_origen", "desconocido"),
        resultado.get("total_ventas", 0),
        resultado.get("productos_creados", 0),
        resultado.get("productos_actualizados", 0)
    ))
    
    conn.commit()
    conn.close()