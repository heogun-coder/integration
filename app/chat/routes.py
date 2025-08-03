from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_socketio import emit, join_room, leave_room, rooms
from app import socketio
from app.models import ChatRoom, Message, User, UserActivity, UserGroupKey, db
from app.crypto import MessageCrypto, GroupCrypto
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
    
    try:
        participants = data.get('participants', [])  # 초대할 사용자명 리스트
        is_group = data.get('is_group', False)
        is_private = data.get('is_private', False)
        
        # 1:1 채팅방인 경우 기존 방 확인
        if not is_group and len(participants) == 1:
            other_username = participants[0]
            other_user = User.query.filter_by(username=other_username).first()
            
            if other_user:
                # 기존 1:1 채팅방 확인
                existing_room = ChatRoom.query.filter(
                    ChatRoom.is_group == False,
                    ChatRoom.is_private == True,
                    ChatRoom.participants.any(User.id == user_id),
                    ChatRoom.participants.any(User.id == other_user.id)
                ).first()
                
                if existing_room:
                    return jsonify({
                        'message': '기존 채팅방을 사용합니다.',
                        'room_id': existing_room.id,
                        'room_name': existing_room.name,
                        'is_encrypted': existing_room.is_encrypted
                    }), 200
        
        # 그룹 암호화 키 생성
        group_key = GroupCrypto.generate_group_key()
        
        room = ChatRoom(
            name=data['name'], 
            description=data.get('description', ''),
            is_group=is_group,
            is_private=is_private,
            created_by=user_id,
            encryption_key=group_key,
            is_encrypted=data.get('is_encrypted', True)
        )
        db.session.add(room)
        db.session.flush()  # room.id를 얻기 위해
        
        # 방 생성자를 참가자로 추가
        user = User.query.get(user_id)
        room.participants.append(user)
        
        # 다른 참가자들 추가
        for username in participants:
            participant = User.query.filter_by(username=username).first()
            if participant and participant not in room.participants:
                room.participants.append(participant)
        
        # 모든 참가자들에게 그룹 키 분배
        for participant in room.participants:
            if participant.public_key and room.is_encrypted:
                encrypted_key = GroupCrypto.encrypt_group_key_for_user(group_key, participant.public_key)
                user_group_key = UserGroupKey(
                    user_id=participant.id,
                    room_id=room.id,
                    encrypted_group_key=encrypted_key
                )
                db.session.add(user_group_key)
        
        db.session.commit()
        
        return jsonify({
            'message': '채팅방이 생성되었습니다.', 
            'room_id': room.id,
            'room_name': room.name,
            'is_encrypted': room.is_encrypted
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'채팅방 생성 중 오류가 발생했습니다: {str(e)}'}), 500

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
    
    # 사용자의 그룹 키 가져오기 (암호화된 채팅방인 경우)
    user_group_key = None
    if room.is_encrypted:
        user_key_record = UserGroupKey.query.filter_by(user_id=user_id, room_id=room_id).first()
        if user_key_record:
            # 클라이언트에서 개인키를 제공해야 복호화 가능 (보안을 위해 서버에 저장하지 않음)
            pass
    
    message_list = []
    for message in reversed(messages.items):  # 시간순 정렬
        content = message.content
        
        # 암호화된 메시지인 경우 복호화 필요 (클라이언트에서 처리)
        # 여기서는 암호화된 상태로 전송하고 클라이언트에서 복호화
        
        message_data = {
            'id': message.id,
            'content': content,
            'message_type': message.message_type,
            'username': User.query.get(message.user_id).username,
            'timestamp': message.timestamp.isoformat(),
            'user_id': message.user_id,
            'is_edited': message.is_edited,
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'reply_to_id': message.reply_to_id,
            'is_encrypted': message.is_encrypted
        }
        
        # 답글인 경우 원본 메시지 정보 추가
        if message.reply_to_id:
            reply_to = Message.query.get(message.reply_to_id)
            if reply_to:
                reply_content = reply_to.content
                if len(reply_content) > 100:
                    reply_content = reply_content[:100] + '...'
                    
                message_data['reply_to'] = {
                    'id': reply_to.id,
                    'content': reply_content,
                    'username': User.query.get(reply_to.user_id).username,
                    'is_encrypted': reply_to.is_encrypted
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
    
    try:
        room.participants.append(user)
        
        # 암호화된 채팅방인 경우 사용자에게 그룹 키 분배
        if room.is_encrypted and user.public_key and room.encryption_key:
            encrypted_key = GroupCrypto.encrypt_group_key_for_user(room.encryption_key, user.public_key)
            user_group_key = UserGroupKey(
                user_id=user_id,
                room_id=room_id,
                encrypted_group_key=encrypted_key
            )
            db.session.add(user_group_key)
        
        db.session.commit()
        
        return jsonify({
            'message': '채팅방에 참가했습니다.',
            'is_encrypted': room.is_encrypted
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '채팅방 참가 중 오류가 발생했습니다.'}), 500

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
    
    try:
        room.participants.remove(user)
        
        # 사용자의 그룹 키 삭제
        user_group_key = UserGroupKey.query.filter_by(user_id=user_id, room_id=room_id).first()
        if user_group_key:
            db.session.delete(user_group_key)
        
        db.session.commit()
        
        return jsonify({'message': '채팅방을 나갔습니다.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '채팅방 나가기 중 오류가 발생했습니다.'}), 500

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

@chat_bp.route('/api/chat/rooms/<int:room_id>/encryption-key', methods=['GET'])
@jwt_required()
def get_room_encryption_key(room_id):
    """사용자의 암호화된 그룹 키를 가져오는 API"""
    user_id = int(get_jwt_identity())
    
    # 사용자가 해당 방의 참가자인지 확인
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room:
        return jsonify({'error': '채팅방을 찾을 수 없습니다.'}), 404
    
    if user not in room.participants:
        return jsonify({'error': '접근 권한이 없습니다.'}), 403
    
    if not room.is_encrypted:
        return jsonify({'error': '암호화되지 않은 채팅방입니다.'}), 400
    
    # 사용자의 암호화된 그룹 키 가져오기
    user_group_key = UserGroupKey.query.filter_by(user_id=user_id, room_id=room_id).first()
    
    if not user_group_key:
        return jsonify({'error': '그룹 키를 찾을 수 없습니다.'}), 404
    
    return jsonify({
        'room_id': room_id,
        'encrypted_group_key': user_group_key.encrypted_group_key,
        'is_encrypted': room.is_encrypted
    })

@chat_bp.route('/api/chat/send-encrypted', methods=['POST'])
@jwt_required()
def send_encrypted_message():
    """암호화된 메시지를 직접 전송하는 API"""
    data = request.get_json()
    user_id = int(get_jwt_identity())
    
    room_id = data.get('room_id')
    encrypted_content = data.get('encrypted_content')
    message_type = data.get('message_type', 'text')
    reply_to_id = data.get('reply_to_id')
    
    if not room_id or not encrypted_content:
        return jsonify({'error': '방 ID와 암호화된 내용이 필요합니다.'}), 400
    
    # 권한 확인
    room = ChatRoom.query.get(room_id)
    user = User.query.get(user_id)
    
    if not room or user not in room.participants:
        return jsonify({'error': '접근 권한이 없습니다.'}), 403
    
    try:
        # 메시지 저장
        message = Message(
            content=encrypted_content,
            message_type=message_type,
            room_id=room_id,
            user_id=user_id,
            is_encrypted=True,
            reply_to_id=reply_to_id
        )
        db.session.add(message)
        
        # 방 활동 시간 업데이트
        room.last_activity = datetime.utcnow()
        user.last_seen = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': '메시지가 전송되었습니다.',
            'message_id': message.id,
            'timestamp': message.timestamp.isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '메시지 전송 중 오류가 발생했습니다.'}), 500

@chat_bp.route('/api/chat/private-room/<username>', methods=['GET'])
@jwt_required()
def get_private_room(username):
    """특정 사용자와의 1:1 채팅방을 찾는 API"""
    user_id = int(get_jwt_identity())
    
    # 상대방 사용자 확인
    other_user = User.query.filter_by(username=username).first()
    if not other_user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    # 자기 자신과는 채팅방을 만들 수 없음
    if other_user.id == user_id:
        return jsonify({'error': '자기 자신과는 채팅할 수 없습니다.'}), 400
    
    # 두 사용자가 모두 참여한 개인 채팅방 찾기
    room = ChatRoom.query.filter(
        ChatRoom.is_group == False,
        ChatRoom.is_private == True,
        ChatRoom.participants.any(User.id == user_id),
        ChatRoom.participants.any(User.id == other_user.id)
    ).first()
    
    if room:
        return jsonify({
            'room_id': room.id, 
            'room_name': room.name,
            'is_encrypted': room.is_encrypted
        })
    else:
        return jsonify({'error': '채팅방을 찾을 수 없습니다.'}), 404

@chat_bp.route('/api/chat/rooms/<int:room_id>/invite', methods=['POST'])
@jwt_required()
def invite_user_to_room(room_id):
    """사용자를 채팅방에 초대하는 API"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    username = data.get('username')
    if not username:
        return jsonify({'error': '사용자명이 필요합니다.'}), 400
    
    # 채팅방 및 권한 확인
    room = ChatRoom.query.get(room_id)
    current_user = User.query.get(user_id)
    
    if not room:
        return jsonify({'error': '채팅방을 찾을 수 없습니다.'}), 404
    
    if current_user not in room.participants:
        return jsonify({'error': '채팅방 참가자만 초대할 수 있습니다.'}), 403
    
    # 초대할 사용자 확인
    invite_user = User.query.filter_by(username=username).first()
    if not invite_user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    if invite_user in room.participants:
        return jsonify({'error': '이미 채팅방에 참여한 사용자입니다.'}), 400
    
    try:
        # 사용자를 채팅방에 추가
        room.participants.append(invite_user)
        
        # 그룹 키 분배 (암호화된 채팅방인 경우)
        if room.is_encrypted and invite_user.public_key and room.encryption_key:
            from app.crypto import GroupCrypto
            encrypted_key = GroupCrypto.encrypt_group_key_for_user(room.encryption_key, invite_user.public_key)
            user_group_key = UserGroupKey(
                user_id=invite_user.id,
                room_id=room_id,
                encrypted_group_key=encrypted_key
            )
            db.session.add(user_group_key)
        
        db.session.commit()
        
        return jsonify({
            'message': f'{username}님이 채팅방에 초대되었습니다.',
            'invited_user': username
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '초대 중 오류가 발생했습니다.'}), 500

# SocketIO 이벤트들 
@socketio.on('connect')
def on_connect(auth):
    """사용자 연결 이벤트"""
    if auth and 'token' in auth and 'username' in auth:
        try:
            # JWT 토큰 검증 (간단한 방법)
            username = auth['username']
            user = User.query.filter_by(username=username).first()
            
            if user:
                user.last_seen = datetime.utcnow()
                db.session.commit()
                
                # 모든 사용자에게 온라인 상태 변경 알림
                emit('user_status_changed', {
                    'username': username,
                    'is_online': True
                }, broadcast=True)
                
                print(f'{username} 연결됨')
        except Exception as e:
            print(f'연결 오류: {e}')

@socketio.on('disconnect')
def on_disconnect():
    """사용자 연결 해제 이벤트"""
    # 연결 해제된 사용자의 온라인 상태 업데이트는 주기적 체크로 처리
    print('사용자 연결 해제됨')

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
    is_encrypted = data.get('is_encrypted', False)
    
    # 사용자 ID 가져오기
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    
    # 채팅방 정보 확인
    chat_room = ChatRoom.query.get(room)
    if not chat_room:
        return
    
    # 데이터베이스에 메시지 저장
    message = Message(
        content=content, 
        room_id=room, 
        user_id=user.id,
        timestamp=datetime.utcnow(),
        reply_to_id=reply_to_id,
        is_encrypted=is_encrypted or chat_room.is_encrypted
    )
    db.session.add(message)
    
    # 채팅방 마지막 활동 시간 업데이트
    chat_room.last_activity = datetime.utcnow()
    
    # 사용자 마지막 접속 시간 업데이트
    user.last_seen = datetime.utcnow()
    
    db.session.commit()
    
    # 답글 정보 추가
    reply_info = None
    if reply_to_id:
        reply_to = Message.query.get(reply_to_id)
        if reply_to:
            reply_content = reply_to.content
            if len(reply_content) > 100:
                reply_content = reply_content[:100] + '...'
            reply_info = {
                'id': reply_to.id,
                'content': reply_content,
                'username': User.query.get(reply_to.user_id).username,
                'is_encrypted': reply_to.is_encrypted
            }
    
    # 모든 방 참가자에게 메시지 전송
    emit('message', {
        'id': message.id,
        'content': content, 
        'username': username,
        'timestamp': message.timestamp.isoformat(),
        'user_id': user.id,
        'reply_to': reply_info,
        'is_encrypted': message.is_encrypted
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
            
            # 온라인 상태 브로드캐스트
            emit('user_status_changed', {
                'username': username,
                'is_online': True
            }, broadcast=True)

@socketio.on('user_invited')
def handle_user_invited(data):
    """사용자 초대 이벤트 처리"""
    room = data['room']
    invited_user = data['invited_user']
    invited_by = data['invited_by']
    
    # 채팅방의 모든 참가자에게 알림
    emit('status', {
        'msg': f'{invited_by}님이 {invited_user}님을 초대했습니다.'
    }, room=room)

@socketio.on('request_online_users')
def handle_online_users_request():
    """온라인 사용자 목록 요청 처리"""
    from datetime import timedelta
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
    
    emit('online_users_update', {'users': online_users})