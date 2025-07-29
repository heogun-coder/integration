from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from config import Config

db = SQLAlchemy()
jwt = JWTManager()
socketio = SocketIO()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    jwt.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")

    from app.auth.routes import auth_bp
    from app.calendar.routes import calendar_bp
    from app.chat.routes import chat_bp
    from app.profile.routes import profile_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(profile_bp)

    with app.app_context():
        db.create_all()

    return app