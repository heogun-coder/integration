from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_socketio import emit, join_room, leave_room, rooms
from app import socketio
from app.models import ChatRoom, Message, User, UserActivity, db
from datetime import datetime
from sqlalchemy import or_, and_

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat')
@jwt_required()
def chat_view():
    return render_template('chat.html')

@chat_bp.route('/api/chat/rooms', methods=['POST'])
@jwt_required()
def create_room():
    data = request.get_json()
    user_id = int(get_jwt_identity())
    
    room = ChatRoom(
        name=data['name'], 
        description=data.get('description', ''),
        is_group=data.get('is_group', False),
        is_private=data.get('is_private', False),
        created_by=user_id
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
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    rooms = []
    for room in user.chat_rooms:
        # 마지막 메시지 가져오기
        last_message = Message.query.filter_by(room_id=room.id).order_by(Message.timestamp.desc()).first()
        
        # 읽지 않은 메시지 수
        unread_count = Message.query.filter(
            Message.room_id == room.id,
            Message.user_id != user_id,
            Message.is_read == False
        ).count()
        
        # 온라인 참가자 수 계산 (실제 구현에서는 Redis 등을 사용)
        online_count = len([p for p in room.participants if p.last_seen and 
                           (datetime.utcnow() - p.last_seen).seconds < 300])  # 5분 이내
        
        rooms.append({
            'id': room.id,
            'name': room.name,
            'description': room.description,
            'is_group': room.is_group,
            'is_private': room.is_private,
            'participant_count': len(room.participants),
            'online_count': online_count,
            'last_message': last_message.content if last_message else None,
            'last_message_time': last_message.timestamp.isoformat() if last_message else None,
            'last_message_user': last_message.user.username if last_message else None,
            'unread_count': unread_count,
            'created_by': room.created_by,
            'created_at': room.created_at.isoformat()
        })
    
    # 마지막 활동 시간순으로 정렬
    rooms.sort(key=lambda x: x['last_message_time'] or '', reverse=True)
    
    return jsonify(rooms)

@chat_bp.route('/api/chat/rooms/<int:room_id>/messages', methods=['GET'])
@jwt_required()
def get_messages(room_id):
    user_id = int(get_jwt_identity())
    
    # 사용자가 이 방의 참가자인지 확인
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room or user not in room.participants:
        return jsonify({'error': '접근 권한이 없습니다.'}), 403
    
    # 페이지네이션 파라미터
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    messages_query = Message.query.filter_by(room_id=room_id).order_by(Message.timestamp.desc())
    messages = messages_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # 메시지를 읽음으로 표시
    Message.query.filter(
        Message.room_id == room_id,
        Message.user_id != user_id,
        Message.is_read == False
    ).update({'is_read': True})
    db.session.commit()
    
    message_list = []
    for message in reversed(messages.items):  # 시간순 정렬
        message_data = {
            'id': message.id,
            'content': message.content,
            'message_type': message.message_type,
            'username': User.query.get(message.user_id).username,
            'timestamp': message.timestamp.isoformat(),
            'user_id': message.user_id,
            'is_edited': message.is_edited,
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'reply_to_id': message.reply_to_id
        }
        
        # 답글인 경우 원본 메시지 정보 추가
        if message.reply_to_id:
            reply_to = Message.query.get(message.reply_to_id)
            if reply_to:
                message_data['reply_to'] = {
                    'id': reply_to.id,
                    'content': reply_to.content[:100] + '...' if len(reply_to.content) > 100 else reply_to.content,
                    'username': User.query.get(reply_to.user_id).username
                }
        
        message_list.append(message_data)
    
    return jsonify({
        'messages': message_list,
        'has_more': messages.has_next,
        'total': messages.total
    })

@chat_bp.route('/api/chat/rooms/<int:room_id>/participants', methods=['GET'])
@jwt_required()
def get_room_participants(room_id):
    user_id = int(get_jwt_identity())
    
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room or user not in room.participants:
        return jsonify({'error': '접근 권한이 없습니다.'}), 403
    
    participants = []
    for participant in room.participants:
        is_online = participant.last_seen and (datetime.utcnow() - participant.last_seen).seconds < 300
        participants.append({
            'id': participant.id,
            'username': participant.username,
            'is_online': is_online,
            'last_seen': participant.last_seen.isoformat() if participant.last_seen else None
        })
    
    return jsonify(participants)

@chat_bp.route('/api/chat/rooms/<int:room_id>/join', methods=['POST'])
@jwt_required()
def join_chat_room(room_id):
    user_id = int(get_jwt_identity())
    
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room:
        return jsonify({'error': '채팅방을 찾을 수 없습니다.'}), 404
    
    if user in room.participants:
        return jsonify({'message': '이미 참가한 채팅방입니다.'})
    
    room.participants.append(user)
    db.session.commit()
    
    return jsonify({'message': '채팅방에 참가했습니다.'})

@chat_bp.route('/api/chat/rooms/<int:room_id>/leave', methods=['POST'])
@jwt_required()
def leave_chat_room(room_id):
    user_id = int(get_jwt_identity())
    
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room:
        return jsonify({'error': '채팅방을 찾을 수 없습니다.'}), 404
    
    if user not in room.participants:
        return jsonify({'error': '참가하지 않은 채팅방입니다.'})
    
    room.participants.remove(user)
    db.session.commit()
    
    return jsonify({'message': '채팅방을 나갔습니다.'})

@chat_bp.route('/api/chat/messages/<int:message_id>', methods=['PUT'])
@jwt_required()
def edit_message(message_id):
    user_id = int(get_jwt_identity())
    
    message = Message.query.filter_by(id=message_id, user_id=user_id).first()
    if not message:
        return jsonify({'error': '메시지를 찾을 수 없습니다.'}), 404
    
    data = request.get_json()
    message.content = data['content']
    message.is_edited = True
    message.edited_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'message': '메시지가 수정되었습니다.'})

@chat_bp.route('/api/chat/messages/<int:message_id>', methods=['DELETE'])
@jwt_required()
def delete_message(message_id):
    user_id = int(get_jwt_identity())
    
    message = Message.query.filter_by(id=message_id, user_id=user_id).first()
    if not message:
        return jsonify({'error': '메시지를 찾을 수 없습니다.'}), 404
    
    db.session.delete(message)
    db.session.commit()
    
    return jsonify({'message': '메시지가 삭제되었습니다.'})

# SocketIO 이벤트들
@socketio.on('join')
def on_join(data):
    room = data['room']
    username = data.get('username', 'Anonymous')
    join_room(room)
    
    # 사용자 활동 기록
    user = User.query.filter_by(username=username).first()
    if user:
        user.last_seen = datetime.utcnow()
        activity = UserActivity(user_id=user.id, activity_type='join_room', 
                              details=f'Joined room {room}')
        db.session.add(activity)
        db.session.commit()
    
    emit('status', {'msg': f'{username}님이 채팅방에 참여했습니다.'}, room=room, include_self=False)
    emit('user_joined', {'username': username}, room=room, include_self=False)

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    username = data.get('username', 'Anonymous')
    leave_room(room)
    
    # 사용자 활동 기록
    user = User.query.filter_by(username=username).first()
    if user:
        activity = UserActivity(user_id=user.id, activity_type='leave_room', 
                              details=f'Left room {room}')
        db.session.add(activity)
        db.session.commit()
    
    emit('user_left', {'username': username}, room=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    content = data['content']
    username = data['username']
    reply_to_id = data.get('reply_to_id')
    
    # 사용자 ID 가져오기
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    
    # 데이터베이스에 메시지 저장
    message = Message(
        content=content, 
        room_id=room, 
        user_id=user.id,
        timestamp=datetime.utcnow(),
        reply_to_id=reply_to_id
    )
    db.session.add(message)
    
    # 채팅방 마지막 활동 시간 업데이트
    chat_room = ChatRoom.query.get(room)
    if chat_room:
        chat_room.last_activity = datetime.utcnow()
    
    # 사용자 마지막 접속 시간 업데이트
    user.last_seen = datetime.utcnow()
    
    db.session.commit()
    
    # 답글 정보 추가
    reply_info = None
    if reply_to_id:
        reply_to = Message.query.get(reply_to_id)
        if reply_to:
            reply_info = {
                'id': reply_to.id,
                'content': reply_to.content[:100] + '...' if len(reply_to.content) > 100 else reply_to.content,
                'username': User.query.get(reply_to.user_id).username
            }
    
    # 모든 방 참가자에게 메시지 전송
    emit('message', {
        'id': message.id,
        'content': content, 
        'username': username,
        'timestamp': message.timestamp.isoformat(),
        'user_id': user.id,
        'reply_to': reply_info
    }, room=room)

@socketio.on('typing')
def handle_typing(data):
    room = data['room']
    username = data['username']
    is_typing = data['is_typing']
    
    emit('typing', {
        'username': username,
        'is_typing': is_typing
    }, room=room, include_self=False)

@socketio.on('disconnect')
def on_disconnect():
    print('User disconnected')

# 온라인 사용자 상태 업데이트를 위한 주기적 핑
@socketio.on('ping')
def handle_ping(data):
    username = data.get('username')
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            user.last_seen = datetime.utcnow()
            db.session.commit()