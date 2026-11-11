"""
Genera los datos de prueba del prototipo: datos/ventas_demo.xlsx

Produce un Excel con dos hojas (ADR-003):
  - productos: sku, producto, categoria, costo, precio_venta, stock_inicial, stock_minimo
  - ventas:    fecha, producto, cantidad, precio

Uso:
  python scripts/generar_datos_prueba.py
"""

import random
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CARPETA_DATOS = BASE_DIR / "datos"
ARCHIVO_SALIDA = CARPETA_DATOS / "ventas_demo.xlsx"

# Catálogo de una ferretería pequeña (con stock varied para activar alertas)
CATALOGO = [
    # sku, producto, categoria, costo, precio_venta, stock_inicial, stock_minimo
    ("MART-PRO", "Martillo profesional", "Herramientas de mano", 28.00, 45.00, 4, 6),
    ("CIN-ACERO", "Cincel de acero", "Herramientas de mano", 16.50, 28.50, 3, 4),
    ("ALIC-12", "Alicate 12 pulgadas", "Herramientas de mano", 11.00, 19.90, 9, 5),
    ("TORN-840", "Tornillos 8x40 (caja 100)", "Fijaciones", 22.00, 34.90, 2, 3),
    ("TARJ-12", "TornilloMetrico 12mm", "Fijaciones", 0.25, 0.45, 180, 60),
    ("CBL-5M", "Cable eléctrico 5m", "Materiales eléctricos", 7.40, 12.90, 5, 8),
    ("LAMP-LED", "Bombilla LED 9W", "Materiales eléctricos", 3.20, 6.50, 14, 10),
    ("CINTA-50", "Cinta aislante 50m", "Materiales eléctricos", 4.10, 7.90, 8, 6),
    ("PINT-BL", "Pintura blanca 4L", "Pinturas", 19.00, 29.90, 3, 5),
    ("BROCHA-3", "Brocha 3 pulgadas", "Pinturas", 2.80, 5.90, 11, 8),
]

# Producto que no debe tener ventas: sirve para ver "productos muertos" (RF-12)
PRODUCTO_SIN_VENTAS = ("EXT-2M", "Extensor 2 metros", "Accesorios", 9.90, 15.90, 2, 4)


def _fecha_aleatoria(dias_atras: int) -> date:
    """Fecha aleatoria dentro de los últimos N días."""
    return date.today() - timedelta(days=random.randint(0, dias_atras))


def _generar_ventas(cantidad_filas: int) -> list:
    """Genera ventas con algo de estacionalidad: algunos productos venden más."""
    ventas = []
    # Peso de rotación por producto: los primeros Selling más (RF-11)
    pesos = [30, 20, 12, 18, 40, 15, 10, 8, 6, 5]
    nombres = [c[1] for c in CATALOGO]
    chances = list(range(len(nombres)))

    for _ in range(cantidad_filas):
        indice = random.choices(chances, weights=pesos, k=1)[0]
        nombre = nombres[indice]
        _, _, _, costo, precio_venta, _, _ = CATALOGO[indice]
        cantidad = random.randint(1, 8)
        precio = round(precio_venta * random.uniform(0.95, 1.0), 2)
        ventas.append((_fecha_aleatoria(60), nombre, cantidad, precio))
    return ventas


def main() -> None:
    """Genera el archivo Excel de datos de prueba."""
    import pandas as pd

    random.seed(42)  # datos reproducibles

    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

    productos = [
        {
            "sku": sku,
            "producto": nombre,
            "categoria": categoria,
            "costo": costo,
            "precio_venta": precio,
            "stock_inicial": stock,
            "stock_minimo": minimo,
        }
        for sku, nombre, categoria, costo, precio, stock, minimo in CATALOGO + [PRODUCTO_SIN_VENTAS]
    ]

    ventas = _generar_ventas(600)
    df_ventas = pd.DataFrame(ventas, columns=["fecha", "producto", "cantidad", "precio"])
    df_ventas["fecha"] = pd.to_datetime(df_ventas["fecha"]).dt.strftime("%Y-%m-%d")
    df_ventas = df_ventas.sort_values("fecha").reset_index(drop=True)

    df_productos = pd.DataFrame(productos)

    with pd.ExcelWriter(ARCHIVO_SALIDA, engine="openpyxl") as writer:
        df_productos.to_excel(writer, sheet_name="productos", index=False)
        df_ventas.to_excel(writer, sheet_name="ventas", index=False)

    print(f"Archivo generado: {ARCHIVO_SALIDA}")
    print(f"  Hoja 'productos': {len(df_productos)} filas")
    print(f"  Hoja 'ventas':    {len(df_ventas)} filas")
    print(f"  Rango de fechas:  {df_ventas['fecha'].min()} a {df_ventas['fecha'].max()}")


if __name__ == "__main__":
    main()
