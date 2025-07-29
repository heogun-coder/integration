from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_jwt_extended import create_access_token, jwt_required
from werkzeug.security import generate_password_hash
from app.models import User, db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login_page():
    return render_template('login.html')

@auth_bp.route('/register')
def register_page():
    return render_template('register.html')

@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '사용자명과 비밀번호를 입력해주세요.'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '이미 존재하는 사용자명입니다.'}), 400
    
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': '회원가입이 완료되었습니다.'}), 201

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '사용자명과 비밀번호를 입력해주세요.'}), 400
    
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        access_token = create_access_token(identity=user.id)
        return jsonify({'access_token': access_token, 'username': user.username})
    return jsonify({'error': '잘못된 사용자명 또는 비밀번호입니다.'}), 401