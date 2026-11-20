import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

try:  # Carga como paquete: python -m uvicorn backend.api.main:app --port 8000
    from backend.api.database import get_db, init_db, normalizar_texto
    from backend.api.estadisticas import (
        UMBRAL_DIAS_INMINENTE_POR_DEFECTO,
        UMBRAL_MARGEN_POR_DEFECTO,
        alertas_comportamientos_inusuales,
        alertas_exceso_stock,
        alertas_riesgo_agotamiento,
        calcular_kpis,
        calcular_rotacion_inventario,
        capital_inmovilizado_por_producto,
        clasificar_abc,
        detectar_estacionalidad,
        generar_recomendaciones_compra,
        predecir_demanda_media_movil,
    )
    from backend.api.importador import _generar_sku_unico, importar_archivo
    from backend.api.ordenes_compra import (
        generar_orden_compra,
        orden_a_csv,
        orden_a_html,
    )
    from backend.api.proveedores import (
        actualizar_proveedor,
        asignar_proveedor_a_producto,
        crear_proveedor,
        dar_de_baja_proveedor,
        listar_proveedores,
        validar_proveedor_asignable,
    )
    from backend.api.tendencias import (
        comparar_periodos,
        serie_ventas,
    )
except ImportError:  # Ejecución directa: python backend/api/main.py
    from database import get_db, init_db, normalizar_texto
    from estadisticas import (
        UMBRAL_DIAS_INMINENTE_POR_DEFECTO,
        UMBRAL_MARGEN_POR_DEFECTO,
        alertas_comportamientos_inusuales,
        alertas_exceso_stock,
        alertas_riesgo_agotamiento,
        calcular_kpis,
        calcular_rotacion_inventario,
        capital_inmovilizado_por_producto,
        clasificar_abc,
        detectar_estacionalidad,
        generar_recomendaciones_compra,
        predecir_demanda_media_movil,
    )
    from importador import _generar_sku_unico, importar_archivo
    from ordenes_compra import (
        generar_orden_compra,
        orden_a_csv,
        orden_a_html,
    )
    from proveedores import (
        actualizar_proveedor,
        asignar_proveedor_a_producto,
        crear_proveedor,
        dar_de_baja_proveedor,
        listar_proveedores,
        validar_proveedor_asignable,
    )
    from tendencias import (
        comparar_periodos,
        serie_ventas,
    )

# Extensiones aceptadas por el endpoint de importación
EXTENSIONES_SOPORTADAS = {".csv", ".xlsx", ".xls", ".xlsm"}


# --- RF-07: alta y edición manual de productos -----------------------------

class ProductoEntrada(BaseModel):
    """Cuerpo de alta o edición de un producto (RF-07)."""

    nombre: str = Field(min_length=1, max_length=200)
    sku: Optional[str] = None
    categoria: Optional[str] = None
    unidad: Optional[str] = None
    costo: float = Field(default=0, ge=0)
    precio_venta: float = Field(default=0, ge=0)
    stock_actual: int = Field(default=0, ge=0)
    stock_minimo: int = Field(default=0, ge=0)
    # RF-42: máximo de stock; NULL = este producto no tiene máximo.
    stock_maximo: Optional[int] = Field(default=None, ge=0)
    # RF-30: umbrales propios; NULL = hereda el de su categoría o el de fábrica.
    dias_alerta_inminente: Optional[int] = Field(default=None, ge=1)
    margen_alerta: Optional[float] = Field(default=None, gt=0)
    # RF-43: proveedor del producto. NULL = sin proveedor (lead time global).
    proveedor_id: Optional[int] = Field(default=None, ge=1)


class UmbralCategoriaEntrada(BaseModel):
    """
    Cuerpo de configuración de los umbrales de una categoría (RF-30).

    Un campo en `null` devuelve ese umbral al valor de fábrica; si los dos van
    en `null`, la categoría deja de tener configuración propia.
    """

    dias_alerta_inminente: Optional[int] = Field(default=None, ge=1)
    margen_alerta: Optional[float] = Field(default=None, gt=0)


# --- RF-43: proveedores ----------------------------------------------------

class ProveedorEntrada(BaseModel):
    """
    Cuerpo de alta o edición de un proveedor (RF-43).

    `lead_time_dias` es el plazo de entrega real: alimenta la demanda
    proyectada, el punto de reorden y la fecha de entrega de las
    recomendaciones. El máximo de 365 días evita un plazo absurdo por un cero
    de más en el formulario.
    """

    nombre: str = Field(min_length=1, max_length=200)
    lead_time_dias: int = Field(default=7, ge=1, le=365)
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    # Solo se usa en PUT: true reactiva un proveedor dado de baja.
    activo: Optional[bool] = None


class AsignacionProveedorEntrada(BaseModel):
    """Cuerpo de asignación de proveedor a un producto; `null` = sin proveedor."""

    proveedor_id: Optional[int] = Field(default=None, ge=1)


def _leer_producto(cursor, producto_id: int) -> dict:
    """Devolver un producto como diccionario; 404 si no existe."""
    cursor.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    fila = cursor.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return dict(fila)


def _extraer_archivo_multipart(body: bytes, content_type: str) -> Tuple[str, bytes]:
    """
    Extraer el archivo del campo 'file' de un cuerpo multipart/form-data.

    El parser se implementa con la biblioteca estándar porque el paquete
    'python-multipart' no está disponible en el entorno y no se pueden añadir
    dependencias nuevas. Devuelve (nombre_original, contenido).
    """
    if "multipart/form-data" not in content_type.lower():
        raise ValueError("El endpoint espera un cuerpo multipart/form-data")
    
    # Extraer el boundary del Content-Type
    limite = None
    for parte in content_type.split(";"):
        parte = parte.strip()
        if parte.lower().startswith("boundary="):
            limite = parte[len("boundary="):].strip().strip('"')
    if not limite:
        raise ValueError("El Content-Type no incluye el boundary del formulario")
    
    delimitador = b"--" + limite.encode("utf-8")
    nombre_archivo = ""
    contenido = None
    
    # El primer elemento es el preámbulo y el último el cierre ('--')
    for parte in body.split(delimitador)[1:-1]:
        if parte.startswith(b"\r\n"):
            parte = parte[2:]
        if parte.endswith(b"\r\n"):
            parte = parte[:-2]
        
        if b"\r\n\r\n" in parte:
            crudos, datos = parte.split(b"\r\n\r\n", 1)
        elif b"\n\n" in parte:
            crudos, datos = parte.split(b"\n\n", 1)
        else:
            continue
        
        disposicion = ""
        for linea in crudos.decode("utf-8", errors="replace").splitlines():
            if linea.lower().startswith("content-disposition:"):
                disposicion = linea
                break
        
        # Solo se toma el campo 'file' del formulario
        if 'name="file"' not in disposicion:
            continue
        
        nombre = ""
        marcador = 'filename="'
        if marcador in disposicion:
            inicio = disposicion.index(marcador) + len(marcador)
            fin = disposicion.find('"', inicio)
            nombre = disposicion[inicio:fin] if fin != -1 else ""
        
        nombre_archivo = nombre
        contenido = datos
    
    if contenido is None:
        raise ValueError("El formulario no incluye el campo 'file'")
    
    return nombre_archivo, contenido


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializar la base de datos al arrancar la API."""
    init_db()
    yield


app = FastAPI(
    title="Inventario-IA API",
    description="API para sistema de análisis de ventas e inventario con IA local",
    version="0.1.0",
    lifespan=lifespan
)

# CORS para desarrollo local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Inventario-IA API", "version": "0.1.0"}

@app.get("/health")
def health():
    """Verificar que la API y la BD estén disponibles"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    finally:
        if conn is not None:
            conn.close()

@app.get("/api/kpis")
def api_kpis():
    """KPIs del tablero calculados sobre los datos reales de SQLite."""
    conn = get_db()
    try:
        return calcular_kpis(conn)
    finally:
        conn.close()

@app.get("/api/alertas")
def api_alertas():
    """Alertas de riesgo de agotamiento, exceso de stock y comportamientos inusuales."""
    conn = get_db()
    try:
        return {
            "riesgo_agotamiento": alertas_riesgo_agotamiento(conn),
            "exceso_stock": alertas_exceso_stock(conn),
            "comportamiento": alertas_comportamientos_inusuales(conn)
        }
    finally:
        conn.close()


def _categoria_existente(cursor, categoria: str) -> str:
    """
    Devolver la grafía real de una categoría del catálogo (RF-30).

    Evita configuraciones fantasma: si se pide 'Herramienta' y en el catálogo
    pone 'Herramientas', se responde 404 en lugar de guardar una fila que no
    afecta a ningún producto.

    La comparación ignora mayúsculas y tildes (normalizar_texto, el mismo
    criterio que usa ADR-003 para emparejar productos y ventas): si el catálogo
    dice 'Ferretería', escribir 'Ferreteria' debe funcionar.
    """
    objetivo = normalizar_texto(categoria.strip())
    cursor.execute(
        "SELECT DISTINCT categoria FROM productos "
        "WHERE categoria IS NOT NULL AND TRIM(categoria) <> ''"
    )
    for (cat,) in cursor.fetchall():
        if normalizar_texto(cat) == objetivo:
            return cat

    raise HTTPException(
        status_code=404,
        detail=f"Ningún producto usa la categoría '{categoria.strip()}'",
    )


def _fila_umbral_categoria(cursor, categoria: str) -> Optional[tuple]:
    """Devolver la fila de umbrales_categoria que corresponde a esa categoría."""
    objetivo = normalizar_texto(categoria)
    cursor.execute(
        "SELECT categoria, dias_alerta_inminente, margen_alerta FROM umbrales_categoria"
    )
    for fila in cursor.fetchall():
        if normalizar_texto(fila[0]) == objetivo:
            return fila
    return None


def _umbral_categoria_efectivo(cursor, categoria: str) -> dict:
    """Umbrales que se aplican hoy a una categoría, resueltos con los de fábrica."""
    fila = _fila_umbral_categoria(cursor, categoria)
    dias, margen = (fila[1], fila[2]) if fila else (None, None)

    return {
        "categoria": categoria,
        "dias_inminente": dias if dias is not None else UMBRAL_DIAS_INMINENTE_POR_DEFECTO,
        "margen": margen if margen is not None else UMBRAL_MARGEN_POR_DEFECTO,
        "configurada": fila is not None,
    }


@app.get("/api/umbrales")
def api_umbrales():
    """
    Configuración efectiva de los umbrales de alerta (RF-30).

    Devuelve los valores de fábrica y, por categoría, lo que hay configurado.
    Los productos que tienen umbral propio lo muestran en /api/productos.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT categoria, dias_alerta_inminente, margen_alerta
            FROM umbrales_categoria
            ORDER BY categoria COLLATE NOCASE ASC
        """)
        categorias = [
            {
                "categoria": fila[0],
                "dias_inminente": (
                    fila[1] if fila[1] is not None
                    else UMBRAL_DIAS_INMINENTE_POR_DEFECTO
                ),
                "margen": (
                    fila[2] if fila[2] is not None
                    else UMBRAL_MARGEN_POR_DEFECTO
                ),
                "propio_dias_inminente": fila[1],
                "propio_margen": fila[2],
            }
            for fila in cursor.fetchall()
        ]

        return {
            "por_defecto": {
                "dias_inminente": UMBRAL_DIAS_INMINENTE_POR_DEFECTO,
                "margen": UMBRAL_MARGEN_POR_DEFECTO,
            },
            "categorias": categorias,
        }
    finally:
        conn.close()


@app.put("/api/umbrales/{categoria}")
def api_configurar_umbrales(categoria: str, datos: UmbralCategoriaEntrada):
    """
    Configurar los umbrales de alerta de una categoría (RF-30).

    - Un campo en null devuelve ese umbral al valor de fábrica.
    - Si los dos van en null, la categoría deja de tener configuración propia.
    - 404 si ningún producto usa esa categoría (evita configuraciones fantasma).
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        nombre_categoria = _categoria_existente(cursor, categoria)

        # Reutilizar la fila existente aunque se haya escrito con otra grafía.
        fila = _fila_umbral_categoria(cursor, nombre_categoria)
        if fila is not None:
            nombre_categoria = fila[0]

        if datos.dias_alerta_inminente is None and datos.margen_alerta is None:
            if fila is not None:
                cursor.execute(
                    "DELETE FROM umbrales_categoria WHERE categoria = ?",
                    (fila[0],),
                )
            resultado = _umbral_categoria_efectivo(cursor, nombre_categoria)
            resultado["configurada"] = False
        else:
            cursor.execute("""
                INSERT INTO umbrales_categoria
                    (categoria, dias_alerta_inminente, margen_alerta, actualizado)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(categoria) DO UPDATE SET
                    dias_alerta_inminente = excluded.dias_alerta_inminente,
                    margen_alerta = excluded.margen_alerta,
                    actualizado = CURRENT_TIMESTAMP
            """, (
                nombre_categoria,
                datos.dias_alerta_inminente,
                datos.margen_alerta,
            ))
            resultado = _umbral_categoria_efectivo(cursor, nombre_categoria)

        conn.commit()
        return resultado
    finally:
        conn.close()

@app.get("/api/productos")
def api_productos():
    """Listar el catálogo de productos ordenado por nombre."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        # RF-43: se expone el proveedor y su lead time para que el catálogo no
        # obligue a una segunda llamada. `lead_time_proveedor` es el plazo del
        # proveedor asignado; el lead time aplicado en las recomendaciones es
        # el de la ficha de cada producto (NULL = el global de 7 días).
        cursor.execute("""
            SELECT p.id, p.sku, p.nombre, p.categoria, p.costo, p.precio_venta,
                   p.stock_actual, p.stock_minimo,
                   p.stock_maximo, p.dias_alerta_inminente, p.margen_alerta,
                   p.proveedor_id, pr.nombre AS proveedor, pr.lead_time_dias
            FROM productos p
            LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
            ORDER BY p.nombre ASC
        """)
        filas = cursor.fetchall()
        return [{
            "id": f[0],
            "sku": f[1],
            "nombre": f[2],
            "categoria": f[3],
            "costo": f[4],
            "precio_venta": f[5],
            "stock_actual": f[6],
            "stock_minimo": f[7],
            "stock_maximo": f[8],
            "dias_alerta_inminente": f[9],
            "margen_alerta": f[10],
            "proveedor_id": f[11],
            "proveedor": f[12],
            "lead_time_proveedor": f[13],
        } for f in filas]
    finally:
        conn.close()

@app.post("/api/productos", status_code=201)
def api_crear_producto(datos: ProductoEntrada):
    """
    Alta manual de un producto (RF-07).

    Si no se envía SKU se genera uno único a partir del nombre. Un SKU
    repetido devuelve 409 en lugar de sobrescribir el producto existente.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        nombre = datos.nombre.strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

        sku = (datos.sku or "").strip()
        if sku:
            cursor.execute("SELECT 1 FROM productos WHERE sku = ?", (sku,))
            if cursor.fetchone() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ya existe un producto con el SKU {sku}",
                )
        else:
            sku = _generar_sku_unico(cursor, nombre)

        # RF-43: si se asigna proveedor en el alta, tiene que estar activo.
        validar_proveedor_asignable(cursor, datos.proveedor_id)

        cursor.execute("""
            INSERT INTO productos (sku, nombre, nombre_norm, categoria, unidad,
                                   costo, precio_venta, stock_actual, stock_minimo,
                                   stock_maximo, dias_alerta_inminente, margen_alerta,
                                   proveedor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sku, nombre, normalizar_texto(nombre), datos.categoria, datos.unidad,
            datos.costo, datos.precio_venta, datos.stock_actual, datos.stock_minimo,
            datos.stock_maximo, datos.dias_alerta_inminente, datos.margen_alerta,
            datos.proveedor_id,
        ))
        conn.commit()
        return _leer_producto(cursor, cursor.lastrowid)
    finally:
        conn.close()

@app.put("/api/productos/{producto_id}")
def api_editar_producto(producto_id: int, datos: ProductoEntrada):
    """
    Editar un producto existente (RF-07).

    Sustituye los campos editables. Si no se envía SKU se conserva el actual.
    Devuelve 404 si el producto no existe y 409 si el SKU pertenece a otro.

    Los umbrales de RF-30/RF-42 (`stock_maximo`, `dias_alerta_inminente`,
    `margen_alerta`) solo se sobrescriben si llegan en el cuerpo: el formulario
    actual no los envía y borrarlos en cada edición sería perder configuración
    sin que nadie lo pidiera. Para quitarlos, se envían explícitamente en null.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        _leer_producto(cursor, producto_id)

        nombre = datos.nombre.strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

        sku = (datos.sku or "").strip() or None
        if sku:
            cursor.execute(
                "SELECT 1 FROM productos WHERE sku = ? AND id <> ?",
                (sku, producto_id),
            )
            if cursor.fetchone() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ya existe otro producto con el SKU {sku}",
                )

        enviados = datos.model_fields_set

        # RF-43: solo se valida si el cuerpo trae el campo (null = quitarlo).
        if "proveedor_id" in enviados:
            validar_proveedor_asignable(cursor, datos.proveedor_id)

        cursor.execute("""
            UPDATE productos SET
                sku = COALESCE(?, sku),
                nombre = ?, nombre_norm = ?,
                categoria = ?, unidad = ?,
                costo = ?, precio_venta = ?,
                stock_actual = ?, stock_minimo = ?,
                stock_maximo = CASE WHEN ? THEN ? ELSE stock_maximo END,
                dias_alerta_inminente = CASE WHEN ? THEN ? ELSE dias_alerta_inminente END,
                margen_alerta = CASE WHEN ? THEN ? ELSE margen_alerta END,
                proveedor_id = CASE WHEN ? THEN ? ELSE proveedor_id END
            WHERE id = ?
        """, (
            sku, nombre, normalizar_texto(nombre), datos.categoria, datos.unidad,
            datos.costo, datos.precio_venta, datos.stock_actual, datos.stock_minimo,
            "stock_maximo" in enviados, datos.stock_maximo,
            "dias_alerta_inminente" in enviados, datos.dias_alerta_inminente,
            "margen_alerta" in enviados, datos.margen_alerta,
            "proveedor_id" in enviados, datos.proveedor_id,
            producto_id,
        ))
        conn.commit()
        return _leer_producto(cursor, producto_id)
    finally:
        conn.close()


# --- RF-43: proveedores ----------------------------------------------------

@app.get("/api/proveedores")
def api_proveedores(solo_activos: bool = False):
    """
    Listar proveedores ordenados por nombre.

    `solo_activos=true` devuelve únicamente los que se pueden asignar: es lo
    que consumen los selectores del catálogo.
    """
    conn = get_db()
    try:
        return listar_proveedores(conn, solo_activos=solo_activos)
    finally:
        conn.close()


@app.post("/api/proveedores", status_code=201)
def api_crear_proveedor(datos: ProveedorEntrada):
    """
    Alta de un proveedor (RF-43).

    El nombre es único sin distinguir tildes ni mayúsculas: «Ferretería Paz» y
    «Ferreteria paz» son el mismo proveedor. Un duplicado devuelve 409.
    """
    conn = get_db()
    try:
        return crear_proveedor(
            conn,
            nombre=datos.nombre,
            lead_time_dias=datos.lead_time_dias,
            contacto=datos.contacto,
            telefono=datos.telefono,
        )
    finally:
        conn.close()


@app.put("/api/proveedores/{proveedor_id}")
def api_editar_proveedor(proveedor_id: int, datos: ProveedorEntrada):
    """
    Editar un proveedor. `activo: true` lo reactiva tras una baja lógica.
    """
    conn = get_db()
    try:
        return actualizar_proveedor(
            conn,
            proveedor_id=proveedor_id,
            nombre=datos.nombre,
            lead_time_dias=datos.lead_time_dias,
            contacto=datos.contacto,
            telefono=datos.telefono,
            activo=datos.activo,
        )
    finally:
        conn.close()


@app.delete("/api/proveedores/{proveedor_id}")
def api_dar_de_baja_proveedor(proveedor_id: int):
    """
    Baja lógica de un proveedor (`activo = 0`).

    No se borra la fila ni se limpia la asignación de sus productos: los
    productos vuelven al lead time global y el proveedor se puede reactivar.
    """
    conn = get_db()
    try:
        return dar_de_baja_proveedor(conn, proveedor_id)
    finally:
        conn.close()


@app.put("/api/productos/{producto_id}/proveedor")
def api_asignar_proveedor(producto_id: int, datos: AsignacionProveedorEntrada):
    """
    Asignar o quitar el proveedor de un producto (RF-43).

    Existe aparte de `PUT /api/productos/{id}` para que el selector del
    catálogo no tenga que reenviar el producto entero (y arriesgarse a perder
    campos que no envía).
    """
    conn = get_db()
    try:
        return asignar_proveedor_a_producto(conn, producto_id, datos.proveedor_id)
    finally:
        conn.close()


@app.get("/api/rotacion")
def api_rotacion():
    """Rotación de inventario, baja rotación y productos sin ventas."""
    conn = get_db()
    try:
        return calcular_rotacion_inventario(conn)
    finally:
        conn.close()

@app.get("/api/recomendaciones")
def api_recomendaciones(lead_time: int = 7):
    """
    Lista semanal de productos sugeridos para comprar (RF-22 a RF-26).

    Query params:
      - lead_time: días de entrega del proveedor (por defecto 7).
    """
    conn = get_db()
    try:
        return generar_recomendaciones_compra(conn, lead_time_dias=max(1, int(lead_time)))
    finally:
        conn.close()

@app.get("/api/ordenes-compra")
def api_orden_compra(lead_time: int = 7):
    """
    Orden de compra en JSON (RF-27).

    Mismos datos que /api/recomendaciones, pero con forma de pedido: cabecera
    fechada, líneas numeradas y totales.
    """
    conn = get_db()
    try:
        return generar_orden_compra(conn, lead_time_dias=max(1, int(lead_time)))
    finally:
        conn.close()

@app.get("/api/ordenes-compra.csv")
def api_orden_compra_csv(lead_time: int = 7):
    """
    Orden de compra en CSV (RF-27), lista para Excel.

    UTF-8 con BOM y separador ';': Excel en español abre el archivo con las
    columnas separadas y las tildes correctas.
    """
    conn = get_db()
    try:
        orden = generar_orden_compra(conn, lead_time_dias=max(1, int(lead_time)))
    finally:
        conn.close()

    return Response(
        content=orden_a_csv(orden),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="orden-compra-{orden["fecha_emision"]}.csv"'
        },
    )

@app.get("/api/ordenes-compra.html")
def api_orden_compra_html(lead_time: int = 7):
    """
    Orden de compra como documento imprimible (RF-27).

    El navegador la muestra con su CSS de impresión: «Imprimir» produce el PDF
    sin dependencias ni conexión.
    """
    conn = get_db()
    try:
        orden = generar_orden_compra(conn, lead_time_dias=max(1, int(lead_time)))
    finally:
        conn.close()

    return Response(
        content=orden_a_html(orden),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="orden-compra-{orden["fecha_emision"]}.html"'
        },
    )

@app.get("/api/predicciones/{producto_id}")
def api_predicciones(producto_id: int):
    """
    Predicción de demanda de un producto para 7, 14 y 30 días (RF-18 a RF-20).

    Usa media móvil simple sobre el histórico de ventas del producto.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM productos WHERE id = ?", (producto_id,))
        producto = cursor.fetchone()
        if producto is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        resultado = predecir_demanda_media_movil(conn, producto[1])
        if "error" in resultado:
            raise HTTPException(status_code=400, detail=f"Insuficiente historial para {producto[1]}")
        return {"producto_id": producto_id, "producto": producto[1], **resultado}
    finally:
        conn.close()

@app.get("/api/abc")
def api_abc():
    """Clasificación ABC del inventario (RF-15): A 80%, B 15%, C 5% del valor."""
    conn = get_db()
    try:
        return clasificar_abc(conn)
    finally:
        conn.close()

@app.get("/api/capital")
def api_capital():
    """Capital inmovilizado en inventario por producto (RF-17)."""
    conn = get_db()
    try:
        return capital_inmovilizado_por_producto(conn)
    finally:
        conn.close()

@app.get("/api/estacionalidad")
def api_estacionalidad(producto: str = None):
    """
    Detectar patrones estacionales de ventas (RF-14).

    Query params:
      - producto: nombre opcional para analizar un solo producto.
    """
    conn = get_db()
    try:
        return detectar_estacionalidad(conn, producto_nombre=producto.upper() if producto else None)
    finally:
        conn.close()

@app.get("/api/tendencias")
def api_tendencias(granularidad: str = "mes", desde: str = None, hasta: str = None):
    """
    Serie de ventas por día, semana o mes (RF-10).

    Query params:
      - granularidad: `dia`, `semana` o `mes` (por defecto `mes`).
      - desde / hasta: fechas `AAAA-MM-DD` opcionales. Sin ellas se usan los
        últimos 90 días (día), 26 semanas o 12 meses, anclados en la última
        venta registrada.

    Los periodos sin ventas aparecen con cero: un día que no se vendió es
    información, no un hueco.
    """
    conn = get_db()
    try:
        return serie_ventas(conn, granularidad=granularidad, desde=desde, hasta=hasta)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    finally:
        conn.close()

@app.get("/api/comparacion")
def api_comparacion(tipo: str = "semana", contra: str = "anterior"):
    """
    Comparar el periodo actual con otro (RF-16).

    Query params:
      - tipo: `semana` o `mes`.
      - contra: `anterior` (periodo inmediatamente anterior) o `anio_anterior`
        (el mismo mes del año pasado; solo para `tipo=mes`).

    Si el periodo de referencia no tiene ventas, devuelve `disponible: false`
    con el motivo, en lugar de un 0 % que parecería una caída real.
    """
    conn = get_db()
    try:
        return comparar_periodos(conn, tipo=tipo, contra=contra)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    finally:
        conn.close()

@app.post("/api/importar")
async def api_importar(request: Request):
    """
    Importar un archivo de ventas (Excel o CSV) enviado como multipart/form-data.

    Campo esperado: 'file'. Devuelve el resumen de importación (ADR-003 §4).
    """
    content_type = request.headers.get("content-type", "")
    body = await request.body()
    
    if "multipart/form-data" in content_type.lower():
        try:
            nombre_original, contenido = _extraer_archivo_multipart(body, content_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        # Carga directa del binario; el nombre se puede indicar con ?filename=
        nombre_original = request.query_params.get("filename", "")
        contenido = body
    
    nombre_original = nombre_original or "subida"
    extension = Path(nombre_original).suffix.lower()
    
    if extension not in EXTENSIONES_SOPORTADAS:
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Usa un archivo .csv, .xlsx o .xls"
        )
    
    # Guardar el archivo temporalmente para procesarlo con el importador
    ruta_temporal = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temporal:
            temporal.write(contenido)
            ruta_temporal = temporal.name
        
        resultado = importar_archivo(ruta_temporal, nombre_original=nombre_original)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error importando el archivo: {e}")
    finally:
        # Limpiar el archivo temporal (no es dato del usuario)
        if ruta_temporal and os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except OSError:
                pass
    
    return resultado


# --- Asistente conversacional con IA local (ADR-002: function calling) ---

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:1.7b")

# Herramientas que el LLM puede invocar. Cada una consulta SQLite de forma
# determinista: el modelo nunca adivina cifras, solo las explica (ADR-002 §3).
HERRAMIENTAS = {
    "obtener_kpis": {
        "descripcion": "KPIs del negocio: ventas totales, ticket promedio, unidades vendidas y margen",
        "funcion": lambda conn: calcular_kpis(conn),
    },
    "productos_baja_rotacion": {
        "descripcion": "Productos con baja rotación o sin ventas, con su stock actual",
        "funcion": lambda conn: calcular_rotacion_inventario(conn)["baja_rotacion"],
    },
    "riesgo_agotamiento": {
        "descripcion": "Productos con riesgo de agotarse pronto",
        "funcion": lambda conn: alertas_riesgo_agotamiento(conn),
    },
    "comportamiento_ventas": {
        "descripcion": "Detección de picos o caídas anómalas en las ventas",
        "funcion": lambda conn: alertas_comportamientos_inusuales(conn),
    },
    "recomendaciones_compra": {
        "descripcion": "Lista de productos sugeridos para comprar con cantidades y urgencia",
        "funcion": lambda conn: generar_recomendaciones_compra(conn)["recomendaciones"],
    },
}


def _detectar_intencion(mensaje: str) -> list:
    """Detectar qué herramientas aplican a la pregunta (enrutado simple por palabras clave)."""
    texto = mensaje.lower()
    herramientas = []

    if any(p in texto for p in ["comprar", "compra", "pedido", "orden", "reabastec", "suger"]):
        herramientas.append("recomendaciones_compra")
    if any(p in texto for p in ["agot", "quedan", "queda", "stock bajo", "terminan", "faltan"]):
        herramientas.append("riesgo_agotamiento")
    if any(p in texto for p in ["rotaci", "muerto", "no se vende", "baja venta", "inmoviliz"]):
        herramientas.append("productos_baja_rotacion")
    if any(p in texto for p in ["pico", "caída", "caida", "inusual", "anómal", "anomal", "irregular"]):
        herramientas.append("comportamiento_ventas")
    if any(p in texto for p in ["kpi", "venta", "facturación", "facturacion", "total", "ticket", "margen", "promedio"]):
        herramientas.append("obtener_kpis")

    if not herramientas:
        herramientas.append("obtener_kpis")

    return list(dict.fromkeys(herramientas))


def _construir_contexto(nombres: list) -> dict:
    """Ejecutar las herramientas deterministas sobre SQLite y reunir sus resultados."""
    conn = get_db()
    contexto = {}
    try:
        for nombre in nombres:
            try:
                contexto[nombre] = HERRAMIENTAS[nombre]["funcion"](conn)
            except Exception as e:  # una herramienta rota no debe tumbar la respuesta
                contexto[nombre] = {"error": str(e)}
    finally:
        conn.close()
    return contexto


def _compactar_contexto(contexto: dict) -> dict:
    """
    Reducir el contexto a las cifras que el LLM necesita para responder.

    El JSON completo (con el detalle de cada producto) se devuelve igual en
    la respuesta de la API, pero enviarlo entero al modelo lo vuelve lento y
    puede truncar la lista a mitad, dejando datos incoherentes.
    """
    compacto = {}
    for nombre, datos in (contexto or {}).items():
        if nombre == "recomendaciones_compra" and isinstance(datos, list):
            criticos = sum(1 for r in datos if r.get("urgencia") == "crítico")
            orden = {"crítico": 0, "medio": 1, "bajo": 2}
            top = sorted(
                datos,
                key=lambda r: (orden.get(r.get("urgencia"), 9), -r.get("cantidad_sugerida", 0)),
            )[:6]
            compacto[nombre] = {
                "total_productos_a_comprar": len(datos),
                "urgencia_critica": criticos,
                "productos": [
                    {
                        "producto": r.get("producto"),
                        "cantidad_sugerida": r.get("cantidad_sugerida"),
                        "urgencia": r.get("urgencia"),
                        "pedir_el": r.get("fecha_sugerida"),
                        "llega_el": r.get("fecha_entrega_estimada"),
                    }
                    for r in top
                ],
            }
        elif nombre == "riesgo_agotamiento" and isinstance(datos, list):
            top = sorted(
                datos,
                key=lambda a: (a.get("dias_estimados") if a.get("dias_estimados") is not None else 999),
            )[:6]
            compacto[nombre] = {
                "total_productos_en_riesgo": len(datos),
                "productos": [
                    {
                        "producto": a.get("producto"),
                        "stock_actual": a.get("stock_actual"),
                        "stock_minimo": a.get("stock_minimo"),
                        "dias_estimados": a.get("dias_estimados"),
                        "riesgo": a.get("riesgo"),
                    }
                    for a in top
                ],
            }
        else:
            compacto[nombre] = datos
    return compacto


def _recortar_linea_incompleta(texto: str, truncado: bool = False) -> str:
    """
    Quitar la última línea si quedó cortada por el límite de tokens.

    El modelo puede agotar 'num_predict' a mitad de una viñeta; en ese caso
    la respuesta se vería truncada ("... llega el 2026-11-"). Solo se recorta
    cuando Ollama confirma que la generación terminó por longitud, para no
    perder respuestas cortas de una sola línea.
    """
    if not truncado:
        return (texto or "").strip()
    lineas = [linea.rstrip() for linea in (texto or "").splitlines() if linea.strip()]
    if not lineas:
        return ""
    ultima = lineas[-1].strip()
    # Una fecha a medias ("2026-11" o "llega el 20") no es una línea terminada.
    fecha_incompleta = bool(
        re.search(r"\d{4}-\d{1,2}$", ultima) or re.search(r"\bel \d{1,2}$", ultima)
    )
    terminada = (
        ultima.endswith((".", "!", "?"))
        or (ultima[-1].isdigit() and len(ultima) > 3 and not fecha_incompleta)
    )
    if not terminada:
        lineas = lineas[:-1]
    return "\n".join(lineas)


PLACEHOLDERS_PLANTILLA = {
    "<producto>": ("producto",),
    "<cantidad_sugerida>": ("cantidad_sugerida",),
    "<urgencia>": ("urgencia",),
    "<llega_el>": ("fecha_entrega_estimada", "llega_el"),
    "<pedir_el>": ("fecha_sugerida", "pedir_el"),
    # El modelo pequeño también copia el nombre del campo entre paréntesis.
    "(urgencia)": ("urgencia",),
}


def _reparar_resumen_compra(texto: str, contexto: dict) -> str:
    """
    Completar la primera línea del resumen de compra con cifras reales.

    El modelo de 1.7B a veces escribe 'Hay 9 productos para comprar,
    críticos.' sin el número de críticos. Como el total y los críticos ya
    están calculados en el contexto, se rellenan de forma determinista.
    """
    compras = contexto.get("recomendaciones_compra")
    if not texto or not isinstance(compras, dict):
        return texto
    total = compras.get("total_productos_a_comprar")
    criticos = compras.get("urgencia_critica")
    if total is None or criticos is None:
        return texto
    # 'Hay 9 productos para comprar, críticos.' -> número ausente
    texto = re.sub(
        r"(Hay\s+)\d+(\s+productos para comprar,\s*)(\d+\s+)?críticos",
        rf"\g<1>{total}\g<2>{criticos} críticos",
        texto,
        count=1,
        flags=re.IGNORECASE,
    )
    return texto


def _reparar_placeholders(texto: str, contexto: dict) -> str:
    """
    Sustituir placeholders de plantilla que el modelo local copia literalmente.

    Un modelo de 1.7B a veces reproduce '<producto>: comprar 75 unidades' en vez
    de rellenar el nombre. Los números son correctos, pero la respuesta queda
    inservible. Aquí se rellenan con los datos reales del contexto, en el mismo
    orden en que aparece cada viñeta. Es una red de seguridad determinista: no
    depende de que el modelo obedezca.
    """
    if not texto:
        return texto
    if not any(token in texto.lower() for token in PLACEHOLDERS_PLANTILLA):
        return texto

    filas = contexto.get("recomendaciones_compra")
    if isinstance(filas, list) and filas:
        orden = {"crítico": 0, "medio": 1, "bajo": 2}
        filas = sorted(
            filas,
            key=lambda r: (
                orden.get(str(r.get("urgencia") or "").lower(), 9),
                -(r.get("cantidad_sugerida") or 0),
            ),
        )
    elif isinstance(contexto.get("riesgo_agotamiento"), list) and contexto["riesgo_agotamiento"]:
        filas = sorted(
            contexto["riesgo_agotamiento"],
            key=lambda r: r.get("dias_estimados") if r.get("dias_estimados") is not None else 999,
        )
    else:
        return texto

    indice = 0
    salida = []
    for linea in texto.splitlines():
        minuscula = linea.lower()
        if any(token in minuscula for token in PLACEHOLDERS_PLANTILLA) and indice < len(filas):
            fila = filas[indice]
            indice += 1
            for token, claves in PLACEHOLDERS_PLANTILLA.items():
                valor = next((fila[c] for c in claves if fila.get(c) not in (None, "")), "")
                if token.startswith("("):
                    valor = f"({valor})"
                linea = re.sub(
                    re.escape(token),
                    lambda _m, v=str(valor): v,
                    linea,
                    flags=re.IGNORECASE,
                )
        salida.append(linea)
    return "\n".join(salida)


def _limitar_vinetas(texto: str, maximo: int = 3) -> str:
    """
    Dejar como máximo 'maximo' viñetas, como exige el formato de respuesta.

    El modelo local a veces devuelve 5 o 6 viñetas aunque se le pidan 3. No es un
    dato inventado (todas salen de SQLite), pero alarga la respuesta y con ella
    el tiempo de espera. Si no se detecta ninguna viñeta, el texto se devuelve
    tal cual: no se recorta una respuesta en párrafos.
    """
    lineas = [linea.rstrip() for linea in (texto or "").splitlines() if linea.strip()]
    if len(lineas) <= 1:
        return (texto or "").strip()

    vinetas = [
        linea
        for linea in lineas[1:]
        if re.match(r"^\s*[-•*]\s", linea) or ": comprar " in linea
    ]
    if len(vinetas) <= maximo:
        return (texto or "").strip()
    return "\n".join([lineas[0]] + vinetas[:maximo])


def _consultar_ollama(mensaje: str, contexto: dict, historial: list) -> str:
    """Enviar la pregunta + cifras ya calculadas al LLM local para que las explique."""
    import json
    import urllib.request

    compacto = _compactar_contexto(contexto)
    contexto_texto = json.dumps(compacto, ensure_ascii=False, default=str)[:4000]
    historial_texto = "\n".join(
        f"{'Usuario' if m.get('rol') == 'usuario' else 'Asistente'}: {m.get('contenido', '')}"
        for m in (historial or [])[-6:]
    )

    # Un modelo pequeño imita mejor un ejemplo con datos reales que una plantilla
    # abstracta: se le muestra la forma exacta con el primer producto del negocio.
    # El formato de compra SOLO se inyecta si el contexto incluye compras: si no,
    # el modelo aplicaría la plantilla a preguntas ajenas (p. ej. stock muerto)
    # y escribiría marcadores sin sustituir.
    ejemplo = ""
    compras = compacto.get("recomendaciones_compra")
    if isinstance(compras, dict) and compras.get("productos"):
        primero = compras["productos"][0]
        ejemplo = (
            " EJEMPLO con datos reales de este negocio: "
            f"{primero.get('producto')}: comprar {primero.get('cantidad_sugerida')} unidades "
            f"({primero.get('urgencia')}), llega el {primero.get('llega_el')}."
        )
        formato_compra = (
            "FORMATO: primera línea con el total ('Hay N productos para comprar, M críticos.'); "
            "después máximo 3 viñetas, una línea cada una, sin explicar cálculos. "
            "Cada viñeta de compra se escribe así: NOMBRE DEL PRODUCTO: comprar N unidades (crítico), "
            "llega el AAAA-MM-DD. Sustituye el nombre por el valor real del campo 'producto', la N por la "
            "cantidad real, la palabra entre paréntesis por el valor real de 'urgencia' (crítico, medio o "
            "bajo) y la fecha por la del campo 'llega_el'. "
            "Nunca escribas los nombres de campo 'producto', 'cantidad_sugerida' ni 'urgencia' en la "
            "respuesta, y nunca uses corchetes angulares: son etiquetas, no datos." + ejemplo
        )
    else:
        formato_compra = (
            "FORMATO: responde en máximo 3 viñetas cortas con los datos del contexto, "
            "sin explicar cálculos ni usar corchetes angulares."
        )

    instruccion = (
        "Eres el asistente de Inventario-IA. Respondes SIEMPRE en español, en lenguaje sencillo, "
        "para un dueño de tienda o ferretería sin formación técnica.\n"
        "REGLA ESTRICTA: usa ÚNICAMENTE los datos del CONTEXTO DE DATOS que se te entrega. "
        "No inventes números, no completes lo que falte, no uses conocimiento externo del negocio. "
        "Si el contexto no contiene el dato que te piden, dilo con claridad.\n"
        + formato_compra +
        " Responde directo, sin análisis previo."
    )

    cuerpo = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "think": False,  # respuesta directa: sin bloque de razonamiento
        # Mantener el modelo en memoria entre preguntas: por defecto Ollama lo
        # descarga a los 5 minutos y la siguiente respuesta tardaría ~20 s.
        "keep_alive": "30m",
        "options": {"temperature": 0.2, "num_predict": 140},
        "messages": [
            {"role": "system", "content": instruccion},
            {"role": "system", "content": f"CONTEXTO DE DATOS (JSON):\n{contexto_texto}"},
            *(
                [{"role": "user", "content": historial_texto}]
                if historial_texto
                else []
            ),
            {"role": "user", "content": mensaje},
        ],
    }

    peticion = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(peticion, timeout=60) as respuesta:
        datos = json.loads(respuesta.read().decode("utf-8"))
    truncado = datos.get("done_reason") == "length"
    respuesta = _recortar_linea_incompleta(
        datos.get("message", {}).get("content", "").strip(), truncado
    )
    respuesta = _reparar_resumen_compra(respuesta, compacto)
    respuesta = _reparar_placeholders(respuesta, contexto)
    return _limitar_vinetas(respuesta)


@app.post("/api/chat")
async def api_chat(request: Request):
    """
    Asistente conversacional con IA local (ADR-002).

    El LLM no calcula nada: el backend ejecuta herramientas deterministas sobre
    SQLite y el modelo solo explica esas cifras en lenguaje sencillo.
    """
    try:
        cuerpo = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Se esperaba un cuerpo JSON")

    mensaje = str(cuerpo.get("mensaje", "")).strip()
    historial = cuerpo.get("historial", []) or []
    if not mensaje:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    herramientas = _detectar_intencion(mensaje)
    contexto = _construir_contexto(herramientas)

    try:
        respuesta = _consultar_ollama(mensaje, contexto, historial)
    except Exception as e:
        # Si Ollama no está disponible, se responde con las cifras calculadas
        return {
            "respuesta": (
                f"No pude contactar con el modelo de IA local ({e}). "
                f"Estos son los datos reales del negocio: {json_dumps(contexto)}"
            ),
            "herramientas": herramientas,
            "contexto": contexto,
            "modelo": None,
        }

    return {
        "respuesta": respuesta,
        "herramientas": herramientas,
        "contexto": contexto,
        "modelo": OLLAMA_MODEL,
    }


def json_dumps(objeto) -> str:
    """Serialización segura para las respuestas de respaldo."""
    import json
    return json.dumps(objeto, ensure_ascii=False, default=str)[:2000]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)