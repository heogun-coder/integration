from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import PrivateMessage, User, db
from app.crypto import MessageCrypto
from datetime import datetime
from sqlalchemy import or_, and_

messages_bp = Blueprint('messages', __name__)

@messages_bp.route('/messages')
@jwt_required()
def messages_view():
    return render_template('messages.html')

@messages_bp.route('/api/messages/conversations', methods=['GET'])
@jwt_required()
def get_conversations():
    user_id = int(get_jwt_identity())
    
    # 사용자가 참여한 모든 대화 상대 찾기
    # 서브쿼리로 대화한 모든 사용자 ID 가져오기
    conversation_users = db.session.query(
        db.case(
            (PrivateMessage.sender_id == user_id, PrivateMessage.receiver_id),
            else_=PrivateMessage.sender_id
        ).label('other_user_id')
    ).filter(
        or_(PrivateMessage.sender_id == user_id, PrivateMessage.receiver_id == user_id)
    ).distinct().subquery()
    
    # 대화 상대 정보와 함께 가져오기
    conversations_query = db.session.query(User).filter(
        User.id.in_(db.session.query(conversation_users.c.other_user_id))
    )
    
    conversations = conversations_query.all()
    
    # 모든 사용자 목록도 포함 (새로운 대화 시작용)
    all_users = User.query.filter(User.id != user_id).all()
    
    conversation_list = []
    for user in conversations:
        # 마지막 메시지 가져오기
        last_message = PrivateMessage.query.filter(
            or_(
                and_(PrivateMessage.sender_id == user_id, PrivateMessage.receiver_id == user.id),
                and_(PrivateMessage.sender_id == user.id, PrivateMessage.receiver_id == user_id)
            )
        ).order_by(PrivateMessage.timestamp.desc()).first()
        
        # 읽지 않은 메시지 수
        unread_count = PrivateMessage.query.filter_by(
            sender_id=user.id,
            receiver_id=user_id,
            is_read=False,
            is_deleted_by_receiver=False
        ).count()
        
        # 온라인 상태 확인 (5분 이내 활동)
        is_online = user.last_seen and (datetime.utcnow() - user.last_seen).seconds < 300
        
        conversation_list.append({
            'user_id': user.id,
            'username': user.username,
            'is_online': is_online,
            'last_seen': user.last_seen.isoformat() if user.last_seen else None,
            'last_message': last_message.content if last_message else None,
            'last_message_time': last_message.timestamp.isoformat() if last_message else None,
            'last_message_sender': last_message.sender_id if last_message else None,
            'unread_count': unread_count
        })
    
    # 마지막 메시지 시간순으로 정렬
    conversation_list.sort(key=lambda x: x['last_message_time'] or '', reverse=True)
    
    return jsonify({
        'conversations': conversation_list,
        'all_users': [{
            'id': user.id,
            'username': user.username,
            'is_online': user.last_seen and (datetime.utcnow() - user.last_seen).seconds < 300
        } for user in all_users]
    })

@messages_bp.route('/api/messages/<int:other_user_id>', methods=['GET'])
@jwt_required()
def get_messages_with_user(other_user_id):
    user_id = int(get_jwt_identity())
    
    # 페이지네이션 파라미터
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # 두 사용자 간의 모든 메시지 가져오기 (삭제되지 않은 메시지만)
    messages_query = PrivateMessage.query.filter(
        or_(
            and_(
                PrivateMessage.sender_id == user_id, 
                PrivateMessage.receiver_id == other_user_id,
                PrivateMessage.is_deleted_by_sender == False
            ),
            and_(
                PrivateMessage.sender_id == other_user_id, 
                PrivateMessage.receiver_id == user_id,
                PrivateMessage.is_deleted_by_receiver == False
            )
        )
    ).order_by(PrivateMessage.timestamp.desc())
    
    messages = messages_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # 받은 메시지를 읽음으로 표시
    PrivateMessage.query.filter_by(
        sender_id=other_user_id,
        receiver_id=user_id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    
    # 상대방 정보
    other_user = User.query.get(other_user_id)
    if not other_user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    # 온라인 상태 확인
    is_online = other_user.last_seen and (datetime.utcnow() - other_user.last_seen).seconds < 300
    
    message_list = []
    for msg in reversed(messages.items):  # 시간순 정렬
        message_list.append({
            'id': msg.id,
            'content': msg.content,  # 암호화된 상태로 전송, 클라이언트에서 복호화
            'message_type': msg.message_type,
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'timestamp': msg.timestamp.isoformat(),
            'is_read': msg.is_read,
            'is_own': msg.sender_id == user_id,
            'is_encrypted': msg.is_encrypted
        })
    
    return jsonify({
        'other_user': {
            'id': other_user.id,
            'username': other_user.username,
            'is_online': is_online,
            'last_seen': other_user.last_seen.isoformat() if other_user.last_seen else None
        },
        'messages': message_list,
        'has_more': messages.has_next,
        'total': messages.total
    })

@messages_bp.route('/api/messages', methods=['POST'])
@jwt_required()
def send_message():
    data = request.get_json()
    user_id = int(get_jwt_identity())
    
    try:
        # 받는 사람이 존재하는지 확인
        receiver = User.query.get(data['receiver_id'])
        if not receiver:
            return jsonify({'error': '받는 사람을 찾을 수 없습니다.'}), 404
        
        # 자기 자신에게 메시지 보내기 방지
        if user_id == data['receiver_id']:
            return jsonify({'error': '자기 자신에게는 메시지를 보낼 수 없습니다.'}), 400
        
        content = data['content']
        is_encrypted = data.get('is_encrypted', True)
        
        # 암호화된 메시지인 경우 클라이언트에서 이미 암호화된 상태로 전송됨
        # 서버에서는 그대로 저장만 함
        message = PrivateMessage(
            sender_id=user_id,
            receiver_id=data['receiver_id'],
            content=content,
            message_type=data.get('message_type', 'text'),
            is_encrypted=is_encrypted
        )
        
        db.session.add(message)
        db.session.commit()
        
        return jsonify({
            'message': '메시지가 전송되었습니다.',
            'message_data': {
                'id': message.id,
                'content': message.content,
                'message_type': message.message_type,
                'sender_id': message.sender_id,
                'receiver_id': message.receiver_id,
                'timestamp': message.timestamp.isoformat(),
                'is_read': message.is_read,
                'is_own': True,
                'is_encrypted': message.is_encrypted
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': '메시지 전송에 실패했습니다.'}), 400

@messages_bp.route('/api/messages/send-encrypted', methods=['POST'])
@jwt_required()
def send_encrypted_private_message():
    """암호화된 프라이빗 메시지를 직접 전송하는 API"""
    data = request.get_json()
    user_id = int(get_jwt_identity())
    
    receiver_id = data.get('receiver_id')
    encrypted_content = data.get('encrypted_content')
    message_type = data.get('message_type', 'text')
    
    if not receiver_id or not encrypted_content:
        return jsonify({'error': '받는 사람 ID와 암호화된 내용이 필요합니다.'}), 400
    
    try:
        # 받는 사람이 존재하는지 확인
        receiver = User.query.get(receiver_id)
        if not receiver:
            return jsonify({'error': '받는 사람을 찾을 수 없습니다.'}), 404
        
        # 자기 자신에게 메시지 보내기 방지
        if user_id == receiver_id:
            return jsonify({'error': '자기 자신에게는 메시지를 보낼 수 없습니다.'}), 400
        
        message = PrivateMessage(
            sender_id=user_id,
            receiver_id=receiver_id,
            content=encrypted_content,
            message_type=message_type,
            is_encrypted=True
        )
        
        db.session.add(message)
        db.session.commit()
        
        return jsonify({
            'message': '암호화된 메시지가 전송되었습니다.',
            'message_id': message.id,
            'timestamp': message.timestamp.isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': '메시지 전송 중 오류가 발생했습니다.'}), 500

@messages_bp.route('/api/messages/<int:message_id>', methods=['DELETE'])
@jwt_required()
def delete_message(message_id):
    user_id = int(get_jwt_identity())
    
    message = PrivateMessage.query.get(message_id)
    if not message:
        return jsonify({'error': '메시지를 찾을 수 없습니다.'}), 404
    
    # 발신자 또는 수신자만 삭제 가능
    if message.sender_id == user_id:
        message.is_deleted_by_sender = True
    elif message.receiver_id == user_id:
        message.is_deleted_by_receiver = True
    else:
        return jsonify({'error': '권한이 없습니다.'}), 403
    
    # 양쪽 모두 삭제했으면 실제로 삭제
    if message.is_deleted_by_sender and message.is_deleted_by_receiver:
        db.session.delete(message)
    
    db.session.commit()
    
    return jsonify({'message': '메시지가 삭제되었습니다.'})

@messages_bp.route('/api/messages/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    user_id = int(get_jwt_identity())
    
    unread_count = PrivateMessage.query.filter_by(
        receiver_id=user_id,
        is_read=False,
        is_deleted_by_receiver=False
    ).count()
    
    return jsonify({'unread_count': unread_count})

@messages_bp.route('/api/messages/mark-read', methods=['PUT'])
@jwt_required()
def mark_messages_read():
    data = request.get_json()
    user_id = int(get_jwt_identity())
    sender_id = data.get('sender_id')
    
    if not sender_id:
        return jsonify({'error': '발신자 ID가 필요합니다.'}), 400
    
    # 특정 발신자의 모든 메시지를 읽음으로 표시
    PrivateMessage.query.filter_by(
        sender_id=sender_id,
        receiver_id=user_id,
        is_read=False
    ).update({'is_read': True})
    
    db.session.commit()
    
    return jsonify({'message': '메시지가 읽음으로 표시되었습니다.'})

@messages_bp.route('/api/messages/search', methods=['GET'])
@jwt_required()
def search_messages():
    user_id = int(get_jwt_identity())
    query = request.args.get('q', '').strip()
    other_user_id = request.args.get('user_id', type=int)
    
    if not query:
        return jsonify({'messages': []})
    
    # 검색 쿼리 구성
    search_query = PrivateMessage.query.filter(
        or_(
            and_(PrivateMessage.sender_id == user_id, PrivateMessage.is_deleted_by_sender == False),
            and_(PrivateMessage.receiver_id == user_id, PrivateMessage.is_deleted_by_receiver == False)
        ),
        PrivateMessage.content.ilike(f'%{query}%')
    )
    
    # 특정 사용자와의 대화에서만 검색
    if other_user_id:
        search_query = search_query.filter(
            or_(
                and_(PrivateMessage.sender_id == user_id, PrivateMessage.receiver_id == other_user_id),
                and_(PrivateMessage.sender_id == other_user_id, PrivateMessage.receiver_id == user_id)
            )
        )
    
    messages = search_query.order_by(PrivateMessage.timestamp.desc()).limit(50).all()
    
    return jsonify({
        'messages': [{
            'id': msg.id,
            'content': msg.content,
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'timestamp': msg.timestamp.isoformat(),
            'sender_username': User.query.get(msg.sender_id).username,
            'receiver_username': User.query.get(msg.receiver_id).username,
            'is_own': msg.sender_id == user_id
        } for msg in messages]
    })