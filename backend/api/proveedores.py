"""
Proveedores y su tiempo de entrega (RF-43).

El lead time pertenece al **proveedor**, no al producto: corregir el plazo de
un proveedor no obliga a tocar su catálogo. Cada producto apunta a un
proveedor con `productos.proveedor_id` (NULL = sin proveedor asignado).

La baja es **lógica** (`activo = 0`):
  - el proveedor deja de usarse al resolver el lead time, así que sus
    productos vuelven al plazo por defecto (7 días);
  - el historial y las asignaciones se conservan;
  - se puede reactivar con `PUT` enviando `activo: true`.

Este módulo no calcula estadísticas: expone el CRUD y la asignación a
productos. La resolución del lead time en las recomendaciones está en
`estadisticas.generar_recomendaciones_compra`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

try:  # Carga como paquete: python -m uvicorn backend.api.main:app
    from backend.api.database import normalizar_texto
except ImportError:  # Ejecución directa del módulo (backend/api)
    from database import normalizar_texto


# Columnas de salida comunes a listado, detalle y mutaciones.
_SELECT_PROVEEDOR = """
    SELECT pr.id, pr.nombre, pr.lead_time_dias, pr.contacto, pr.telefono,
           pr.activo, pr.fecha_creacion,
           (SELECT COUNT(*) FROM productos p WHERE p.proveedor_id = pr.id)
               AS productos_asignados
    FROM proveedores pr
"""


def _fila_a_dict(fila) -> Dict[str, Any]:
    """Convertir una fila de proveedor en el diccionario que devuelve la API."""
    return {
        "id": fila[0],
        "nombre": fila[1],
        "lead_time_dias": fila[2],
        "contacto": fila[3],
        "telefono": fila[4],
        # SQLite guarda 0/1; la API habla en booleanos.
        "activo": bool(fila[5]),
        "fecha_creacion": fila[6],
        "productos_asignados": fila[7] or 0,
    }


def _leer_proveedor(cursor, proveedor_id: int) -> Dict[str, Any]:
    """Devolver un proveedor; 404 si no existe."""
    cursor.execute(_SELECT_PROVEEDOR + " WHERE pr.id = ?", (proveedor_id,))
    fila = cursor.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return _fila_a_dict(fila)


def listar_proveedores(conn, solo_activos: bool = False) -> List[Dict[str, Any]]:
    """
    Listar proveedores ordenados por nombre.

    `solo_activos=True` sirve para los selectores: un proveedor dado de baja no
    se puede asignar a un producto nuevo.
    """
    cursor = conn.cursor()
    consulta = _SELECT_PROVEEDOR
    if solo_activos:
        consulta += " WHERE pr.activo = 1"
    consulta += " ORDER BY pr.nombre_norm ASC, pr.id ASC"
    cursor.execute(consulta)
    return [_fila_a_dict(fila) for fila in cursor.fetchall()]


def _validar_nombre_disponible(cursor, nombre_norm: str, excluir_id: Optional[int] = None) -> None:
    """409 si otro proveedor ya usa ese nombre (comparado sin tildes)."""
    if excluir_id is None:
        cursor.execute(
            "SELECT id FROM proveedores WHERE nombre_norm = ?", (nombre_norm,)
        )
    else:
        cursor.execute(
            "SELECT id FROM proveedores WHERE nombre_norm = ? AND id <> ?",
            (nombre_norm, excluir_id),
        )
    if cursor.fetchone() is not None:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un proveedor con ese nombre",
        )


def crear_proveedor(conn, nombre: str, lead_time_dias: int = 7,
                    contacto: Optional[str] = None,
                    telefono: Optional[str] = None) -> Dict[str, Any]:
    """Alta de un proveedor activo. 409 si el nombre ya existe."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    cursor = conn.cursor()
    nombre_norm = normalizar_texto(nombre)
    _validar_nombre_disponible(cursor, nombre_norm)

    cursor.execute(
        """INSERT INTO proveedores
               (nombre, nombre_norm, lead_time_dias, contacto, telefono, activo)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (nombre, nombre_norm, lead_time_dias, contacto, telefono),
    )
    conn.commit()
    return _leer_proveedor(cursor, cursor.lastrowid)


def actualizar_proveedor(conn, proveedor_id: int, nombre: str,
                         lead_time_dias: int,
                         contacto: Optional[str] = None,
                         telefono: Optional[str] = None,
                         activo: Optional[bool] = None) -> Dict[str, Any]:
    """
    Editar un proveedor. 404 si no existe y 409 si el nombre es de otro.

    `activo` solo se toca si llega en el cuerpo: así un formulario que no lo
    envía no reactiva sin querer un proveedor dado de baja.
    """
    cursor = conn.cursor()
    _leer_proveedor(cursor, proveedor_id)

    nombre = (nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    nombre_norm = normalizar_texto(nombre)
    _validar_nombre_disponible(cursor, nombre_norm, excluir_id=proveedor_id)

    cursor.execute(
        """UPDATE proveedores
              SET nombre = ?, nombre_norm = ?, lead_time_dias = ?,
                  contacto = ?, telefono = ?,
                  activo = COALESCE(?, activo)
            WHERE id = ?""",
        (
            nombre, nombre_norm, lead_time_dias, contacto, telefono,
            None if activo is None else int(bool(activo)),
            proveedor_id,
        ),
    )
    conn.commit()
    return _leer_proveedor(cursor, proveedor_id)


def dar_de_baja_proveedor(conn, proveedor_id: int) -> Dict[str, Any]:
    """
    Baja lógica: `activo = 0`.

    No se borra la fila ni se limpia `productos.proveedor_id`: los productos
    vuelven al lead time por defecto porque la resolución solo mira proveedores
    activos, y la asignación sigue ahí para poder reactivar el proveedor.
    """
    cursor = conn.cursor()
    _leer_proveedor(cursor, proveedor_id)
    cursor.execute(
        "UPDATE proveedores SET activo = 0 WHERE id = ?", (proveedor_id,)
    )
    conn.commit()
    return _leer_proveedor(cursor, proveedor_id)


def validar_proveedor_asignable(cursor, proveedor_id: Optional[int]) -> None:
    """
    Comprobar que un proveedor se puede asignar a un producto.

    `None` es válido (quitar el proveedor). 404 si no existe y 409 si está
    dado de baja: asignar un proveedor inactivo dejaría el lead time real sin
    efecto y el usuario no sabría por qué.
    """
    if proveedor_id is None:
        return
    cursor.execute("SELECT activo FROM proveedores WHERE id = ?", (proveedor_id,))
    fila = cursor.fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    if not fila[0]:
        raise HTTPException(
            status_code=409,
            detail="El proveedor está dado de baja y no puede asignarse",
        )


def asignar_proveedor_a_producto(conn, producto_id: int,
                                 proveedor_id: Optional[int]) -> Dict[str, Any]:
    """
    Asignar (o quitar, con `proveedor_id=None`) el proveedor de un producto.

    404 si el producto no existe, 404 si el proveedor no existe y 409 si se
    intenta asignar uno dado de baja.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM productos WHERE id = ?", (producto_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    validar_proveedor_asignable(cursor, proveedor_id)

    cursor.execute(
        "UPDATE productos SET proveedor_id = ? WHERE id = ?",
        (proveedor_id, producto_id),
    )
    conn.commit()

    cursor.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    return dict(cursor.fetchone())
