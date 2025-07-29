from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_socketio import emit, join_room, leave_room
from app import socketio
from app.models import ChatRoom, Message, User, db
from datetime import datetime

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat')
@jwt_required()
def chat_view():
    return render_template('chat.html')

@chat_bp.route('/api/chat/rooms', methods=['POST'])
@jwt_required()
def create_room():
    data = request.get_json()
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    
    room = ChatRoom(
        name=data['name'], 
        is_group=data.get('is_group', False)
    )
    db.session.add(room)
    db.session.commit()
    
    # 방 생성자를 참가자로 추가
    user = User.query.get(user_id)
    room.participants.append(user)
    db.session.commit()
    
    return jsonify({'message': '채팅방이 생성되었습니다.', 'room_id': room.id}), 201

@chat_bp.route('/api/chat/rooms', methods=['GET'])
@jwt_required()
def get_rooms():
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    user = User.query.get(user_id)
    
    rooms = []
    for room in user.chat_rooms:
        rooms.append({
            'id': room.id,
            'name': room.name,
            'is_group': room.is_group,
            'participant_count': len(room.participants)
        })
    
    return jsonify(rooms)

@chat_bp.route('/api/chat/rooms/<int:room_id>/messages', methods=['GET'])
@jwt_required()
def get_messages(room_id):
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    
    # 사용자가 이 방의 참가자인지 확인
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room or user not in room.participants:
        return jsonify({'error': '접근 권한이 없습니다.'}), 403
    
    messages = Message.query.filter_by(room_id=room_id).order_by(Message.timestamp).all()
    
    return jsonify([{
        'id': message.id,
        'content': message.content,
        'username': User.query.get(message.user_id).username,
        'timestamp': message.timestamp.isoformat(),
        'user_id': message.user_id
    } for message in messages])

@socketio.on('join')
def on_join(data):
    room = data['room']
    username = data.get('username', 'Anonymous')
    join_room(room)
    emit('status', {'msg': f'{username}님이 채팅방에 참여했습니다.'}, room=room)
    emit('user_joined', {'username': username}, room=room, include_self=False)

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    username = data.get('username', 'Anonymous')
    leave_room(room)
    emit('user_left', {'username': username}, room=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    content = data['content']
    username = data['username']
    
    # 사용자 ID 가져오기
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    
    # 데이터베이스에 메시지 저장
    message = Message(
        content=content, 
        room_id=room, 
        user_id=user.id,
        timestamp=datetime.utcnow()
    )
    db.session.add(message)
    db.session.commit()
    
    # 모든 방 참가자에게 메시지 전송
    emit('message', {
        'content': content, 
        'username': username,
        'timestamp': message.timestamp.isoformat(),
        'user_id': user.id
    }, room=room)