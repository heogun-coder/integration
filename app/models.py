from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

# db 인스턴스는 __init__.py에서 초기화되지만 여기서는 참조만 함
# 실제 초기화는 create_app()에서 발생
db = SQLAlchemy()

room_participants = db.Table('room_participants',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('chat_room_id', db.Integer, db.ForeignKey('chat_room.id'), primary_key=True)
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    profile_picture = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 종단간 암호화를 위한 RSA 키 쌍
    public_key = db.Column(db.Text)  # PEM 형식의 공개키
    private_key = db.Column(db.Text)  # PEM 형식의 개인키 (클라이언트에서 관리)
    key_fingerprint = db.Column(db.String(128))  # 키 지문
    
    # 관계 설정
    events = db.relationship('Event', backref='user', lazy=True)
    messages = db.relationship('Message', backref='user', lazy=True)
    chat_rooms = db.relationship('ChatRoom', secondary=room_participants, 
                               back_populates='participants', lazy='dynamic')


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    repeat = db.Column(db.String(20))
    category = db.Column(db.String(50), default='general')  # general, meeting, deadline, personal
    location = db.Column(db.String(200))
    is_all_day = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 향상된 기능을 위한 추가 필드들
    repeat_group_id = db.Column(db.String(36))  # 반복 이벤트 그룹 ID (UUID)
    is_repeat_master = db.Column(db.Boolean, default=False)  # 반복 이벤트의 마스터인지
    repeat_until = db.Column(db.DateTime)  # 반복 종료 날짜
    notification_minutes = db.Column(db.Integer, default=15)  # 알림 시간 (분 단위)
    is_shared = db.Column(db.Boolean, default=False)  # 공유 여부
    color = db.Column(db.String(7), default='#3788d8')  # 이벤트 색상 (HEX)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent

class EventShare(db.Model):
    """이벤트 공유를 위한 모델"""
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    shared_with_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shared_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    permission = db.Column(db.String(20), default='view')  # view, edit
    shared_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    event = db.relationship('Event', backref='shares')
    shared_with = db.relationship('User', foreign_keys=[shared_with_user_id], backref='received_event_shares')  
    shared_by = db.relationship('User', foreign_keys=[shared_by_user_id], backref='sent_event_shares')
    
    # 복합 유니크 제약조건
    __table_args__ = (db.UniqueConstraint('event_id', 'shared_with_user_id', name='unique_event_share'),)

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_group = db.Column(db.Boolean, default=False)
    is_private = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 그룹 채팅 암호화를 위한 키
    encryption_key = db.Column(db.Text)  # AES 그룹 키 (참가자들에게 RSA로 암호화되어 전달)
    is_encrypted = db.Column(db.Boolean, default=True)  # 암호화 여부
    
    # 관계 설정
    participants = db.relationship('User', secondary=room_participants, 
                                 back_populates='chat_rooms')
    messages = db.relationship('Message', backref='room', lazy=True, 
                             cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_rooms')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)  # 암호화된 경우 암호화된 텍스트, 아닌 경우 평문
    message_type = db.Column(db.String(20), default='text')  # text, image, file, system
    file_url = db.Column(db.String(200))
    file_name = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    
    # 암호화 관련 필드
    is_encrypted = db.Column(db.Boolean, default=True)  # 메시지가 암호화되었는지 여부
    
    # 자기 참조 관계 (답글)
    reply_to = db.relationship('Message', remote_side=[id], backref='replies')

class UserGroupKey(db.Model):
    """각 사용자별로 그룹 채팅방의 암호화 키를 저장하는 테이블"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    encrypted_group_key = db.Column(db.Text, nullable=False)  # 사용자의 공개키로 암호화된 그룹 키
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    user = db.relationship('User', backref='group_keys')
    room = db.relationship('ChatRoom', backref='user_keys')
    
    # 복합 유니크 제약조건
    __table_args__ = (db.UniqueConstraint('user_id', 'room_id', name='unique_user_room_key'),)



class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    author = db.relationship('User', backref='announcements')

# 온라인 사용자 추적을 위한 모델
class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # login, logout, message, etc.
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)
    
    user = db.relationship('User', backref='activities')