from flask import Blueprint, render_template
from flask_jwt_extended import jwt_required

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/profile')
@jwt_required()
def profile_view():
    return render_template('profile.html')