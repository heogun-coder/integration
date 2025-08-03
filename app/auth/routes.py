from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_jwt_extended import create_access_token, unset_jwt_cookies, jwt_required, get_jwt_identity
from app.models import User, db
from app.crypto import MessageCrypto

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
    email = data.get('email')
    
    if not username or not password:
        return jsonify({'error': '사용자명과 비밀번호를 입력해주세요.'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '이미 존재하는 사용자명입니다.'}), 400
    
    if email and User.query.filter_by(email=email).first():
        return jsonify({'error': '이미 사용중인 이메일입니다.'}), 400
    
    # RSA 키 쌍 생성
    try:
        private_key_pem, public_key_pem = MessageCrypto.generate_key_pair()
        key_fingerprint = MessageCrypto.generate_fingerprint(public_key_pem)
        
        user = User(
            username=username,
            email=email,
            public_key=public_key_pem,
            key_fingerprint=key_fingerprint
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'message': '회원가입이 완료되었습니다.',
            'private_key': private_key_pem,  # 클라이언트에서 안전하게 저장해야 함
            'public_key': public_key_pem,
            'key_fingerprint': key_fingerprint
        }), 201
        
    except Exception as e:
        return jsonify({'error': '회원가입 중 오류가 발생했습니다.'}), 500

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '사용자명과 비밀번호를 입력해주세요.'}), 400
    
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        # user.id를 문자열로 변환
        access_token = create_access_token(identity=str(user.id))
        response = jsonify({'access_token': access_token, 'username': user.username})
        
        # 쿠키에도 토큰 설정
        from flask_jwt_extended import set_access_cookies
        set_access_cookies(response, access_token)
        
        return response
    return jsonify({'error': '잘못된 사용자명 또는 비밀번호입니다.'}), 401

@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    response = jsonify({'message': '로그아웃되었습니다.'})
    unset_jwt_cookies(response)
    return response

@auth_bp.route('/api/auth/users/<username>/public-key', methods=['GET'])
@jwt_required()
def get_user_public_key(username):
    """다른 사용자의 공개키를 가져오는 API"""
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    if not user.public_key:
        return jsonify({'error': '사용자의 공개키가 설정되지 않았습니다.'}), 404
    
    return jsonify({
        'username': username,
        'public_key': user.public_key,
        'key_fingerprint': user.key_fingerprint
    })

@auth_bp.route('/api/auth/verify-fingerprint', methods=['POST'])
@jwt_required()
def verify_key_fingerprint():
    """키 지문을 확인하는 API"""
    data = request.get_json()
    username = data.get('username')
    fingerprint = data.get('fingerprint')
    
    if not username or not fingerprint:
        return jsonify({'error': '사용자명과 지문이 필요합니다.'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    is_valid = user.key_fingerprint == fingerprint
    return jsonify({
        'is_valid': is_valid,
        'username': username,
        'expected_fingerprint': user.key_fingerprint
    })

@auth_bp.route('/api/auth/my-keys', methods=['GET'])
@jwt_required()
def get_my_keys():
    """현재 사용자의 키 정보를 가져오는 API"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    return jsonify({
        'username': user.username,
        'public_key': user.public_key,
        'key_fingerprint': user.key_fingerprint,
        'has_keys': bool(user.public_key)
    })

@auth_bp.route('/api/auth/regenerate-keys', methods=['POST'])
@jwt_required()
def regenerate_keys():
    """사용자의 키 쌍을 재생성하는 API"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    try:
        # 새로운 키 쌍 생성
        private_key_pem, public_key_pem = MessageCrypto.generate_key_pair()
        key_fingerprint = MessageCrypto.generate_fingerprint(public_key_pem)
        
        # 데이터베이스 업데이트
        user.public_key = public_key_pem
        user.key_fingerprint = key_fingerprint
        db.session.commit()
        
        return jsonify({
            'message': '키가 재생성되었습니다.',
            'private_key': private_key_pem,  # 클라이언트에서 안전하게 저장해야 함
            'public_key': public_key_pem,
            'key_fingerprint': key_fingerprint
        })
        
    except Exception as e:
        return jsonify({'error': '키 재생성 중 오류가 발생했습니다.'}), 500

@auth_bp.route('/api/auth/online-users', methods=['GET'])
@jwt_required()
def get_online_users():
    """온라인 사용자 목록을 가져오는 API"""
    from datetime import datetime, timedelta
    
    # 5분 이내에 활동한 사용자를 온라인으로 간주
    cutoff_time = datetime.utcnow() - timedelta(minutes=5)
    
    users = User.query.all()
    
    online_users = []
    for user in users:
        is_online = user.last_seen and user.last_seen > cutoff_time
        online_users.append({
            'username': user.username,
            'is_online': is_online,
            'last_seen': user.last_seen.isoformat() if user.last_seen else None
        })
    
    return jsonify(online_users)