from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_socketio import emit, join_room
from app import socketio
from app.models import ChatRoom, Message, db

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat')
@jwt_required()
def chat_view():
    return render_template('chat.html')

@chat_bp.route('/api/chat/rooms', methods=['POST'])
@jwt_required()
def create_room():
    data = request.get_json()
    room = ChatRoom(name=data['name'], is_group=data.get('is_group', False))
    db.session.add(room)
    db.session.commit()
    return jsonify({'message': 'Room created successfully'}), 201

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('status', {'msg': 'Joined room'}, room=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    content = data['content']
    user_id = get_jwt_identity()
    message = Message(content=content, room_id=room, user_id=user_id)
    db.session.add(message)
    db.session.commit()
    emit('message', {'content': content, 'user': user_id}, room=room)