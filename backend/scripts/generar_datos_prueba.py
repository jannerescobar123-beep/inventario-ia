"""Generador de datos de prueba — Inventario-IA.

Crea `datos/ventas_demo.xlsx` con ~6 meses de ventas de un negocio tipo
ferretería + tienda de barrio: ~200 productos, estacionalidad, más ventas
los fines de semana, productos estrella, de baja rotación y "muertos".

Uso (desde backend/ con el venv activo):
    python scripts/generar_datos_prueba.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO_SALIDA = REPO_RAIZ / "datos" / "ventas_demo.xlsx"

N_PRODUCTOS = 200
DIAS = 180
SEMILLA = 42

# Catálogo base por categoría (nombres realistas de ferretería/tienda)
CATEGORIAS = {
    "Herramientas": ["Martillo", "Destornillador Phillips", "Llave inglesa", "Alicate",
                     "Sierra manual", "Taladro", "Cinta métrica", "Nivel"],
    "Fijaciones": ["Clavo 2 pulgadas", "Tornillo 1/4", "Tarugo", "Silicona",
                   "Pegamento universal", "Alambre galvanizado"],
    "Pinturas": ["Pintura látex blanca", "Esmalte", "Brocha 2 pulgadas", "Rodillo",
                 "Thinner", "Masilla"],
    "Electricidad": ["Cable eléctrico", "Bombillo LED", "Interruptor", "Toma corriente",
                     "Cinta aislante", "Fusible"],
    "Plomería": ["Tubo PVC", "Codo PVC", "Llave de paso", "Cinta teflón",
                 "Grifería lavamanos", "Flexible inodoro"],
    "Abarrotes": ["Arroz 1kg", "Azúcar 1kg", "Aceite 1L", "Harina 1kg", "Sal 500g",
                  "Fideos 500g", "Atún lata", "Café 250g"],
    "Bebidas": ["Gaseosa 2L", "Agua 600ml", "Jugo 1L", "Cerveza 650ml"],
    "Limpieza": ["Detergente 1kg", "Jabón de barra", "Cloro 1L", "Lavaplatos 900ml",
                 "Escoba", "Trapeador"],
}
VARIANTES = ["", " estándar", " premium", " económica", " x6", " x12", " jumbo"]


def generar() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEMILLA)

    # 1) Catálogo de productos
    nombres: list[str] = []
    categorias: list[str] = []
    while len(nombres) < N_PRODUCTOS:
        for categoria, base_nombres in CATEGORIAS.items():
            for nombre_base in base_nombres:
                for variante in VARIANTES:
                    if len(nombres) >= N_PRODUCTOS:
                        break
                    nombres.append(f"{nombre_base}{variante}")
                    categorias.append(categoria)

    # 2) Perfil de demanda por producto
    #    55% normal · 20% estrella · 15% baja rotación · 10% muerto (sin ventas)
    base_diaria = rng.choice(
        [3.0, 12.0, 0.15, 0.0],
        size=N_PRODUCTOS,
        p=[0.55, 0.20, 0.15, 0.10],
    )
    amplitud_estacional = rng.uniform(0.0, 0.4, N_PRODUCTOS)   # ×(0.6–1.4) según época
    fase_estacional = rng.uniform(0, 2 * np.pi, N_PRODUCTOS)
    precio_unitario = np.round(rng.uniform(0.5, 60, N_PRODUCTOS), 2)
    costo = np.round(precio_unitario * rng.uniform(0.55, 0.8, N_PRODUCTOS), 2)
    stock_inicial = np.round(rng.uniform(0, 120, N_PRODUCTOS)).astype(int)
    stock_minimo = np.round(rng.uniform(3, 15, N_PRODUCTOS)).astype(int)

    # 3) Demanda diaria (vectorizada): 200 productos × 180 días
    dias_idx = np.arange(DIAS)
    dia_semana = pd.Timestamp.today().normalize().to_period("D").start_time  # placeholder
    fechas = pd.date_range(end=pd.Timestamp.today().normalize(), periods=DIAS, freq="D")
    es_fin_de_semana = (fechas.dayofweek >= 5).astype(float)  # sáb=5, dom=6

    lam = base_diaria[:, None] * (
        1
        + amplitud_estacional[:, None] * np.sin(2 * np.pi * dias_idx[None, :] / 30 + fase_estacional[:, None])
        + 0.25 * es_fin_de_semana.to_numpy()[None, :]
    )
    ventas = rng.poisson(np.clip(lam, 0, None))  # (N_PRODUCTOS, DIAS)

    # 4) Aplanar solo las celdas con ventas > 0
    producto_idx, dia_idx = np.nonzero(ventas)
    cantidades = ventas[producto_idx, dia_idx]

    df_ventas = pd.DataFrame(
        {
            "fecha": fechas[dia_idx].strftime("%Y-%m-%d"),
            "sku": [f"SKU-{i + 1:04d}" for i in producto_idx],
            "producto": [nombres[i] for i in producto_idx],
            "categoria": [categorias[i] for i in producto_idx],
            "cantidad": cantidades.astype(int),
            "precio_unitario": precio_unitario[producto_idx],
        }
    )
    df_ventas["importe"] = (df_ventas["cantidad"] * df_ventas["precio_unitario"]).round(2)

    df_productos = pd.DataFrame(
        {
            "sku": [f"SKU-{i + 1:04d}" for i in range(N_PRODUCTOS)],
            "producto": nombres,
            "categoria": categorias,
            "costo": costo,
            "precio_venta": precio_unitario,
            "stock_inicial": stock_inicial,
            "stock_minimo": stock_minimo,
        }
    )

    _ = dia_semana  # reservado para análisis futuros
    return df_ventas, df_productos


def main() -> None:
    df_ventas, df_productos = generar()
    ARCHIVO_SALIDA.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(ARCHIVO_SALIDA, engine="openpyxl") as escritor:
        df_ventas.to_excel(escritor, sheet_name="ventas", index=False)
        df_productos.to_excel(escritor, sheet_name="productos", index=False)

    muertos = int((df_productos["producto"].isin(df_ventas["producto"]) == False).sum())
    print(f"✅ Archivo generado: {ARCHIVO_SALIDA}")
    print(f"   Hoja 'ventas':    {len(df_ventas):,} filas ({df_ventas['fecha'].min()} → {df_ventas['fecha'].max()})")
    print(f"   Hoja 'productos': {len(df_productos)} productos ({muertos} sin ventas: baja rotación/muertos)")
    print("\nPróximo paso: súbelo desde la app (pestaña 'Importar') o pruébalo con:")
    print("  curl -F 'archivo=@datos/ventas_demo.xlsx' http://localhost:8000/api/importar")


if __name__ == "__main__":
    try:
        main()
    except ImportError as exc:
        print(f"Falta una dependencia: {exc}")
        print("Activa el venv e instala requisitos:  pip install -r requirements.txt")
        sys.exit(1)
