from flask import Flask
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from config import Config

jwt = JWTManager()
socketio = SocketIO()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # models에서 db import
    from app.models import db
    
    db.init_app(app)
    jwt.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")

    # 블루프린트 등록
    from app.auth.routes import auth_bp
    from app.calendar.routes import calendar_bp
    from app.chat.routes import chat_bp
    from app.profile.routes import profile_bp
    from app.messages.routes import messages_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(messages_bp)

    with app.app_context():
        db.create_all()
        
        # 기본 관리자 계정 생성
        from app.models import User
        from app.crypto import MessageCrypto
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            try:
                # 관리자용 키 쌍 생성
                private_key_pem, public_key_pem = MessageCrypto.generate_key_pair()
                key_fingerprint = MessageCrypto.generate_fingerprint(public_key_pem)
                
                admin = User(
                    username='admin', 
                    email='admin@myapp.com', 
                    is_admin=True,
                    public_key=public_key_pem,
                    key_fingerprint=key_fingerprint
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Admin user created: username=admin, password=admin123")
                print(f"Admin key fingerprint: {key_fingerprint}")
            except Exception as e:
                print(f"Error creating admin user: {e}")
                # 키 생성 실패시 기본 관리자만 생성
                admin = User(username='admin', email='admin@myapp.com', is_admin=True)
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Admin user created without encryption keys: username=admin, password=admin123")

    return app