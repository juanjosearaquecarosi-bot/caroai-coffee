from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Receta, Producto, Insumo
from ..utils.decorators import role_required

recetas_bp = Blueprint('recetas', __name__)


# ──────────────────────────────────────────────
#  LISTAR RECETAS (admin only)
# ──────────────────────────────────────────────
@recetas_bp.route('/')
@login_required
@role_required('admin')
def index():
    recetas = Receta.query.options(
        db.joinedload(Receta.producto),
        db.joinedload(Receta.insumo),
    ).order_by(Receta.id).all()
    return render_template('recetas/index.html', recetas=recetas)


# ──────────────────────────────────────────────
#  CREAR RECETA (admin only)
# ──────────────────────────────────────────────
@recetas_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create():
    productos = Producto.query.order_by(Producto.nombre).all()
    insumos = Insumo.query.order_by(Insumo.nombre).all()

    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        insumo_id = request.form.get('insumo_id', type=int)
        cantidad_gramos = request.form.get('cantidad_gramos', type=float)
        descripcion = request.form.get('descripcion', '').strip()

        if not producto_id or not insumo_id or not cantidad_gramos or cantidad_gramos <= 0:
            flash('Completa todos los campos obligatorios.', 'warning')
            return redirect(url_for('recetas.create'))

        receta = Receta(
            producto_id=producto_id,
            insumo_id=insumo_id,
            cantidad_gramos=cantidad_gramos,
            descripcion=descripcion if descripcion else None,
        )
        db.session.add(receta)
        db.session.commit()
        flash(f'Receta creada: {receta}', 'success')
        return redirect(url_for('recetas.index'))

    return render_template('recetas/form.html', action='Crear', receta=None,
                           productos=productos, insumos=insumos)


# ──────────────────────────────────────────────
#  EDITAR RECETA (admin only)
# ──────────────────────────────────────────────
@recetas_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit(id):
    receta = Receta.query.get_or_404(id)
    productos = Producto.query.order_by(Producto.nombre).all()
    insumos = Insumo.query.order_by(Insumo.nombre).all()

    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        insumo_id = request.form.get('insumo_id', type=int)
        cantidad_gramos = request.form.get('cantidad_gramos', type=float)
        descripcion = request.form.get('descripcion', '').strip()

        if not producto_id or not insumo_id or not cantidad_gramos or cantidad_gramos <= 0:
            flash('Completa todos los campos obligatorios.', 'warning')
            return redirect(url_for('recetas.edit', id=id))

        receta.producto_id = producto_id
        receta.insumo_id = insumo_id
        receta.cantidad_gramos = cantidad_gramos
        receta.descripcion = descripcion if descripcion else None
        db.session.commit()
        flash('Receta actualizada.', 'success')
        return redirect(url_for('recetas.index'))

    return render_template('recetas/form.html', action='Editar', receta=receta,
                           productos=productos, insumos=insumos)


# ──────────────────────────────────────────────
#  ELIMINAR RECETA (admin only)
# ──────────────────────────────────────────────
@recetas_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    receta = Receta.query.get_or_404(id)
    db.session.delete(receta)
    db.session.commit()
    flash('Receta eliminada.', 'info')
    return redirect(url_for('recetas.index'))
