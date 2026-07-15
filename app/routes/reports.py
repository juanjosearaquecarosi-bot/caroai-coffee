from flask import Blueprint, render_template
from flask_login import login_required

reports_bp = Blueprint('reports', __name__)

@login_required
@reports_bp.route('/')
def index():
    return render_template('reports/index.html')