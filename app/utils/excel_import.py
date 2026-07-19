"""
excel_import.py  —  Importa productos desde el Excel 'Caroai Cafe control ventas'.

Uso:  python -m app.utils.excel_import

Lee la hoja 'Precios' del Excel y extrae:
- Bebidas: nombre + precio en COP (columna 2)
- Comidas: nombre + precio en COP (columna 7)

Luego inserta o actualiza los productos en la base de datos.
"""

import os, sys
import openpyxl
from app.models import db, Producto
from app import create_app

# ── Ruta del Excel dentro del proyecto ──
EXCEL_FILENAME = 'Caroai Cafe control ventas (1).xlsx'


def find_excel():
    """Busca el Excel en el directorio del proyecto o sus padres."""
    start = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        candidate = os.path.join(start, EXCEL_FILENAME)
        if os.path.exists(candidate):
            return candidate
        start = os.path.dirname(start)
    return None


def parse_excel(excel_path):
    """
    Lee la hoja 'Precios' y extrae productos con nombre, categoría y precio.
    
    Estructura esperada:
      - Filas 1-2: encabezados / parámetros
      - Fila 3: 'Bebidas' en col A, 'Comida' en col F (o cerca)
      - Filas 4+: productos, con nombre en col A/F, precio COP en col B/G
    
    Retorna lista de dicts: {nombre, categoria, precio_venta_cop}
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    
    productos = []
    
    # Intentar hoja 'Precios' primero
    sheet_name = 'Precios' if 'Precios' in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]
    
    # Detectar dónde empiezan las secciones Bebidas y Comida
    # Buscar palabras clave en las primeras 10 filas
    bebidas_row = None
    comida_row = None
    bebidas_col = 1      # col A: nombres de bebidas
    comida_col = 5       # col E: nombres de comida
    precio_bebidas_col = 2   # col B: precio COP para bebidas
    precio_comida_col = 6    # col F: precio COP para comida
    
    for row_idx in range(1, min(ws.max_row + 1, 20)):
        row_vals = [ws.cell(row=row_idx, column=c).value for c in range(1, ws.max_column + 1)]
        for c, v in enumerate(row_vals, 1):
            if v is not None:
                sv = str(v).strip().lower()
                if 'bebida' in sv:
                    bebidas_row = row_idx
                    bebidas_col = c
                if 'comida' in sv or sv == 'comida':
                    comida_row = row_idx
                    comida_col = c
    
    # Si no encontramos por palabras clave, asumir estructura por defecto
    if bebidas_row is None:
        bebidas_row = 4  # asumir que los datos empiezan en fila 4
    if comida_row is None:
        comida_row = 4
    
    # Leer bebidas: desde bebidas_row hasta encontrar fila vacía o 'Comida'
    for row_idx in range(bebidas_row, ws.max_row + 1):
        nombre = ws.cell(row=row_idx, column=bebidas_col).value
        precio = ws.cell(row=row_idx, column=precio_bebidas_col).value
        
        if nombre is None and precio is None:
            continue  # fila vacía
        
        nombre_str = str(nombre).strip() if nombre else ''
        
        # Detectar fin de sección
        if not nombre_str or 'comida' in nombre_str.lower():
            continue
        
        # Saltar encabezados/parametros
        if any(kw in nombre_str.lower() for kw in ['tasa', 'cambio', 'dolar', 'precio', 'bebidas', 'producto']):
            continue
        if len(nombre_str) < 2:
            continue
            
        precio_val = None
        if precio is not None:
            try:
                precio_val = int(float(str(precio).replace(',', '').replace('$', '').strip()))
            except (ValueError, TypeError):
                pass
        
        if precio_val and precio_val > 0:
            productos.append({
                'nombre': nombre_str,
                'categoria': 'bebida',
                'precio_venta_cop': precio_val,
            })
    
    # Leer comidas desde comida_col
    for row_idx in range(comida_row, ws.max_row + 1):
        nombre = ws.cell(row=row_idx, column=comida_col).value
        precio = ws.cell(row=row_idx, column=precio_comida_col).value
        
        if nombre is None and precio is None:
            continue
        
        nombre_str = str(nombre).strip() if nombre else ''
        
        if not nombre_str or len(nombre_str) < 2:
            continue
        if any(kw in nombre_str.lower() for kw in ['tasa', 'cambio', 'dolar', 'comida', 'producto']):
            continue
            
        precio_val = None
        if precio is not None:
            try:
                precio_val = int(float(str(precio).replace(',', '').replace('$', '').strip()))
            except (ValueError, TypeError):
                pass
        
        if precio_val and precio_val > 0:
            productos.append({
                'nombre': nombre_str,
                'categoria': 'comida',
                'precio_venta_cop': precio_val,
            })
    
    return productos


def import_productos(excel_path=None):
    """
    Importa productos desde el Excel a la base de datos.
    Retorna (insertados, actualizados).
    """
    if excel_path is None:
        excel_path = find_excel()
    
    if not excel_path:
        print(f'❌ Excel "{EXCEL_FILENAME}" no encontrado en el proyecto.')
        return 0, 0
    
    print(f'📄 Leyendo: {excel_path}')
    productos_data = parse_excel(excel_path)
    print(f'   → {len(productos_data)} productos encontrados')
    
    insertados = 0
    actualizados = 0
    
    for data in productos_data:
        nombre = data['nombre']
        existente = Producto.query.filter_by(nombre=nombre).first()
        if existente:
            # Actualizar precio y categoría si cambió
            changed = False
            if existente.precio_venta_cop != data['precio_venta_cop']:
                existente.precio_venta_cop = data['precio_venta_cop']
                changed = True
            if existente.categoria != data['categoria']:
                existente.categoria = data['categoria']
                changed = True
            if changed:
                actualizados += 1
        else:
            prod = Producto(
                nombre=nombre,
                categoria=data['categoria'],
                precio_venta_cop=data['precio_venta_cop'],
                descuenta_inventario=False,
            )
            db.session.add(prod)
            insertados += 1
    
    db.session.commit()
    
    # Mostrar resumen
    total = Producto.query.count()
    print(f'\n📊 Resumen:')
    print(f'   Insertados: {insertados}')
    print(f'   Actualizados: {actualizados}')
    print(f'   Total en BD: {total}')
    
    return insertados, actualizados


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        import_productos()