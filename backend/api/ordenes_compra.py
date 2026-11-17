"""
Órdenes de compra exportables e imprimibles (RF-27).

Este módulo no calcula nada nuevo: parte de las recomendaciones que ya
produce `estadisticas.generar_recomendaciones_compra` (RF-22 a RF-26) y les
da forma de pedido: cabecera, líneas numeradas, totales y totales en dinero.

Tres salidas:
  - `generar_orden_compra()`: la orden como diccionario (JSON, tests, app).
  - `orden_a_csv()`: archivo CSV para Excel (UTF-8 con BOM y `;`).
  - `orden_a_html()`: documento A4 con CSS de impresión.

Sin dependencias externas y sin CDN: el PDF, si se quiere, lo genera el
navegador al imprimir el HTML (RNF-45: nada sale del equipo).
"""
from __future__ import annotations

import html
from datetime import date
from typing import Any, Dict, List

try:  # Carga como paquete: python -m uvicorn backend.api.main:app
    from backend.api.database import normalizar_texto
    from backend.api.estadisticas import generar_recomendaciones_compra
except ImportError:  # Ejecución directa del módulo (backend/api)
    from database import normalizar_texto
    from estadisticas import generar_recomendaciones_compra


# Columnas del CSV, en el mismo orden que las líneas del HTML.
COLUMNAS_CSV = [
    "num",
    "producto",
    "cantidad",
    "urgencia",
    "fecha_sugerida",
    "fecha_entrega_estimada",
    "stock_actual",
    "punto_reorden",
    "costo_unitario",
    "costo_total_estimado",
]

# De qué campo de la recomendación sale cada columna de la orden.
# almost todas tienen el mismo nombre; la cantidad es la excepción.
ORIGEN_CAMPO = {
    "cantidad": "cantidad_sugerida",
}

ETIQUETAS_CSV = {
    "num": "Nº",
    "producto": "Producto",
    "cantidad": "Cantidad",
    "urgencia": "Urgencia",
    "fecha_sugerida": "Fecha sugerida",
    "fecha_entrega_estimada": "Fecha entrega estimada",
    "stock_actual": "Stock actual",
    "punto_reorden": "Punto de reorden",
    "costo_unitario": "Coste unitario",
    "costo_total_estimado": "Coste total",
}


def generar_orden_compra(conn, lead_time_dias: int = 7) -> Dict[str, Any]:
    """
    Construir la orden de compra a partir de las recomendaciones actuales.

    La cabecera lleva la fecha de emisión, el lead time usado y la fecha de
    referencia de la demanda; las líneas son las recomendaciones ordenadas por
    urgencia (ya lo están) y los totales son la suma de unidades y de coste.
    """
    datos = generar_recomendaciones_compra(conn, lead_time_dias=lead_time_dias)
    recomendaciones: List[Dict[str, Any]] = datos.get("recomendaciones", [])

    lineas: List[Dict[str, Any]] = []
    for numero, recomendacion in enumerate(recomendaciones, start=1):
        linea: Dict[str, Any] = {"num": numero}
        for columna in COLUMNAS_CSV:
            if columna == "num":
                continue
            origen = ORIGEN_CAMPO.get(columna, columna)
            linea[columna] = recomendacion.get(origen)
        lineas.append(linea)

    unidades = sum(int(linea.get("cantidad") or 0) for linea in lineas)
    coste_total = round(
        sum(float(linea.get("costo_total_estimado") or 0) for linea in lineas), 2
    )

    return {
        "titulo": "Orden de compra",
        "fecha_emision": date.today().isoformat(),
        "lead_time_dias": datos.get("lead_time_asumido", lead_time_dias),
        "fecha_referencia_demanda": datos.get("fecha_referencia_demanda"),
        "lineas": lineas,
        "totales": {
            "productos": len(lineas),
            "unidades": unidades,
            "costo_total_estimado": coste_total,
        },
    }


def _valor_csv(valor: Any) -> str:
    """Formatear un valor para CSV: texto plano, coma y salto de línea escapados."""
    if valor is None:
        return ""
    texto = str(valor)
    if '"' in texto:
        texto = '"' + texto.replace('"', '""') + '"'
    return texto.replace("\r", " ").replace("\n", " ")


def orden_a_csv(orden: Dict[str, Any]) -> str:
    """
    Convertir la orden en CSV.

    Separador `;` y BOM UTF-8 al final: así Excel en español abre el archivo
    con las columnas separadas y las tildes intactas. Sin BOM, Excel
    interpreta el archivo como ANSI y destroza 'Ferretería'.
    """
    filas: List[str] = []
    cabecera = ";".join(ETIQUETAS_CSV[columna] for columna in COLUMNAS_CSV)
    filas.append(cabecera)

    for linea in orden.get("lineas", []):
        filas.append(";".join(
            _valor_csv(linea.get(columna)) for columna in COLUMNAS_CSV
        ))

    totales = orden.get("totales", {})
    filas.append("")  # línea en blanco antes de los totales
    filas.append(f"Productos;{totales.get('productos', 0)}")
    filas.append(f"Unidades;{totales.get('unidades', 0)}")
    filas.append(f"Coste total estimado;{totales.get('costo_total_estimado', 0)}")

    return "\ufeff" + "\r\n".join(filas) + "\r\n"


def _clase_urgencia(urgencia: str) -> str:
    """
    Clase CSS de la urgencia, solo con letras ASCII.

    El valor real es 'crítico', con tilde: una clase CSS con acentos funciona
    en los navegadores, pero es frágil (depende de la codificación del
    documento y de las herramientas que lo preprocesan). Aquí se traduce.
    """
    texto = normalizar_texto(urgencia)
    if texto.startswith("CRIT"):
        return "u-critico"
    if texto.startswith("MED"):
        return "u-medio"
    if texto.startswith("BAJ") or texto.startswith("ALT"):
        return "u-bajo"
    return "u-bajo"


def _fila_html(linea: Dict[str, Any]) -> str:
    """Una línea de la tabla del HTML, con todos los textos escapados."""
    celdas = [
        f"<td class='num'>{html.escape(str(linea.get('num', '')))}</td>",
        f"<td class='producto'>{html.escape(str(linea.get('producto', '')))}</td>",
        f"<td class='cantidad'>{html.escape(str(linea.get('cantidad', '')))}</td>",
        f"<td class='urgencia {_clase_urgencia(str(linea.get('urgencia', '')))}'>"
        f"{html.escape(str(linea.get('urgencia', '')))}</td>",
        f"<td>{html.escape(str(linea.get('fecha_sugerida', '')))}</td>",
        f"<td>{html.escape(str(linea.get('fecha_entrega_estimada', '')))}</td>",
        f"<td>{html.escape(str(linea.get('stock_actual', '')))}</td>",
        f"<td>{html.escape(str(linea.get('punto_reorden', '')))}</td>",
        f"<td class='num'>{html.escape(str(linea.get('costo_unitario', '')))}</td>",
        f"<td class='num'>{html.escape(str(linea.get('costo_total_estimado', '')))}</td>",
    ]
    return "      <tr>" + "".join(celdas) + "</tr>"


CSS_IMPRESION = """
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      color: #1b1f24; background: #f4f5f7; margin: 0; padding: 24px;
      font-size: 13px;
    }
    .hoja {
      max-width: 210mm; margin: 0 auto; background: #fff; padding: 18mm 14mm;
      box-shadow: 0 8px 28px rgba(0,0,0,.12);
    }
    header { border-bottom: 3px solid #1b1f24; padding-bottom: 10px; margin-bottom: 16px; }
    h1 { font-size: 22px; margin: 0 0 6px; letter-spacing: .3px; }
    .sub { color: #555; font-size: 12px; }
    .datos { display: flex; flex-wrap: wrap; gap: 6px 28px; margin: 12px 0 18px; }
    .datos div { min-width: 150px; }
    .datos strong { display: block; font-size: 11px; text-transform: uppercase;
                    letter-spacing: .6px; color: #666; }
    table { width: 100%; border-collapse: collapse; margin-top: 6px; }
    th, td { border: 1px solid #d7dbe0; padding: 6px 8px; text-align: left; }
    th { background: #eef0f3; font-size: 11px; text-transform: uppercase;
         letter-spacing: .4px; color: #444; }
    td.num, th.num { text-align: right; }
    td.cantidad { text-align: right; font-weight: 600; }
    td.producto { font-weight: 600; }
    tfoot td { background: #f7f8fa; font-weight: 600; }
    .u-critico { color: #b42318; font-weight: 700; }
    .u-medio { color: #b54708; font-weight: 700; }
    .u-bajo { color: #475467; }
    .proveedor { margin-top: 22px; padding-top: 12px; border-top: 1px dashed #b9bec6; }
    .proveedor span { display: inline-block; min-width: 260px;
                      border-bottom: 1px solid #555; }
    .firma { display: flex; gap: 40px; margin-top: 34px; }
    .firma div { flex: 1; border-top: 1px solid #555; padding-top: 4px;
                 font-size: 11px; color: #555; text-align: center; }
    .acciones { max-width: 210mm; margin: 14px auto 0; text-align: right; }
    .acciones button {
      font: inherit; padding: 9px 18px; border: 1px solid #1b1f24; border-radius: 6px;
      background: #1b1f24; color: #fff; cursor: pointer;
    }
    .acciones button:hover { background: #333; }
    .vacio { padding: 26px 0; color: #555; text-align: center; }
    .nota { color: #777; font-size: 11px; margin-top: 10px; }
    @media print {
      @page { size: A4 portrait; margin: 12mm; }
      body { background: #fff; padding: 0; font-size: 11px; }
      .hoja { box-shadow: none; max-width: none; padding: 0; }
      .acciones { display: none; }
      thead { display: table-header-group; }
      tr { break-inside: avoid; }
    }
""".strip()


def orden_a_html(orden: Dict[str, Any]) -> str:
    """
    Convertir la orden en un documento HTML listo para imprimir.

    El CSS de impresión usa A4 vertical, una página por bloque y
    `break-inside: avoid` en las filas: al imprimir no se parte ninguna línea
    de la tabla a la mitad. El botón "Imprimir" solo existe en pantalla: en
    el papel desaparece.
    """
    totales = orden.get("totales", {})
    lineas = orden.get("lineas", [])

    if lineas:
        cuerpo = (
            "    <table>\n"
            "      <thead>\n"
            "        <tr>"
            "<th class='num'>Nº</th><th>Producto</th><th class='num'>Cantidad</th>"
            "<th>Urgencia</th><th>Fecha sugerida</th><th>Fecha entrega estimada</th>"
            "<th class='num'>Stock actual</th><th class='num'>Punto de reorden</th>"
            "<th class='num'>Coste unitario</th><th class='num'>Coste total</th>"
            "</tr>\n"
            "      </thead>\n"
            "      <tbody>\n"
            + "\n".join(_fila_html(linea) for linea in lineas)
            + "\n      </tbody>\n"
            "      <tfoot>\n"
            "        <tr>"
            f"<td colspan='2'>Total ({totales.get('productos', 0)} productos)</td>"
            f"<td class='cantidad'>{totales.get('unidades', 0)}</td>"
            "<td colspan='5'></td>"
            f"<td class='num'>{totales.get('costo_total_estimado', 0)}</td>"
            "</tr>\n"
            "      </tfoot>\n"
            "    </table>\n"
        )
    else:
        cuerpo = "    <p class='vacio'>No hay productos que comprar esta semana.</p>\n"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(orden.get('titulo', 'Orden de compra'))} — {html.escape(str(orden.get('fecha_emision', '')))}</title>
  <style>
{CSS_IMPRESION}
  </style>
</head>
<body>
  <div class="acciones">
    <button type="button" onclick="window.print()">Imprimir / Guardar como PDF</button>
  </div>
  <main class="hoja">
    <header>
      <h1>{html.escape(orden.get('titulo', 'Orden de compra'))}</h1>
      <div class="sub">Emitida el {html.escape(str(orden.get('fecha_emision', '')))}</div>
    </header>
    <section class="datos">
      <div><strong>Fecha de emisión</strong>{html.escape(str(orden.get('fecha_emision', '')))}</div>
      <div><strong>Lead time asumido</strong>{html.escape(str(orden.get('lead_time_dias', '')))} días</div>
      <div><strong>Referencia de demanda</strong>{html.escape(str(orden.get('fecha_referencia_demanda') or ''))}</div>
      <div><strong>Productos</strong>{html.escape(str(totales.get('productos', 0)))}</div>
      <div><strong>Unidades</strong>{html.escape(str(totales.get('unidades', 0)))}</div>
      <div><strong>Coste estimado</strong>{html.escape(str(totales.get('costo_total_estimado', 0)))}</div>
    </section>
{cuerpo}    <section class="proveedor">
      <strong>Proveedor</strong> <span>&nbsp;</span>
      <div class="nota">Pendiente de RF-43 (tabla de proveedores): esta orden no guarda proveedor.</div>
    </section>
    <section class="firma">
      <div>Fecha y firma del solicitante</div>
      <div>Recibido por</div>
    </section>
  </main>
</body>
</html>
"""
