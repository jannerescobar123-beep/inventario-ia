"""CRUD básico de productos."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Producto
from app.schemas import ProductoNuevo, ProductoOut

router = APIRouter(prefix="/api/productos", tags=["Productos"])


@router.get("", response_model=list[ProductoOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Producto).order_by(Producto.nombre).all()


@router.post("", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def crear(payload: ProductoNuevo, db: Session = Depends(get_db)):
    producto = Producto(**payload.model_dump())
    db.add(producto)
    db.commit()
    db.refresh(producto)
    return producto


@router.get("/{producto_id}", response_model=ProductoOut)
def obtener(producto_id: int, db: Session = Depends(get_db)):
    producto = db.get(Producto, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto
