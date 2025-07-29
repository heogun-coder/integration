from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.models import Event, db

calendar_bp = Blueprint('calendar', __name__)

@calendar_bp.route('/calendar')
@jwt_required()
def calendar_view():
    return render_template('calendar.html')

@calendar_bp.route('/api/calendar/events', methods=['POST'])
@jwt_required()
def create_event():
    data = request.get_json()
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    
    try:
        # 날짜 문자열을 datetime 객체로 변환
        start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        end_time = None
        if data.get('end_time'):
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        
        event = Event(
            title=data['title'],
            description=data.get('description'),
            start_time=start_time,
            end_time=end_time,
            repeat=data.get('repeat'),
            user_id=user_id
        )
        db.session.add(event)
        db.session.commit()
        return jsonify({'message': '이벤트가 생성되었습니다.', 'event_id': event.id}), 201
    except Exception as e:
        return jsonify({'error': '이벤트 생성에 실패했습니다.'}), 400

@calendar_bp.route('/api/calendar/events', methods=['GET'])
@jwt_required()
def get_events():
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    events = Event.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'start_time': event.start_time.isoformat(),
        'end_time': event.end_time.isoformat() if event.end_time else None,
        'repeat': event.repeat
    } for event in events])

@calendar_bp.route('/api/calendar/events/<int:event_id>', methods=['PUT'])
@jwt_required()
def update_event(event_id):
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    event = Event.query.filter_by(id=event_id, user_id=user_id).first()
    
    if not event:
        return jsonify({'error': '이벤트를 찾을 수 없습니다.'}), 404
    
    data = request.get_json()
    
    try:
        event.title = data['title']
        event.description = data.get('description')
        event.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        if data.get('end_time'):
            event.end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        else:
            event.end_time = None
        event.repeat = data.get('repeat')
        
        db.session.commit()
        return jsonify({'message': '이벤트가 수정되었습니다.'})
    except Exception as e:
        return jsonify({'error': '이벤트 수정에 실패했습니다.'}), 400

@calendar_bp.route('/api/calendar/events/<int:event_id>', methods=['DELETE'])
@jwt_required()
def delete_event(event_id):
    user_id = int(get_jwt_identity())  # 문자열을 정수로 변환
    event = Event.query.filter_by(id=event_id, user_id=user_id).first()
    
    if not event:
        return jsonify({'error': '이벤트를 찾을 수 없습니다.'}), 404
    
    db.session.delete(event)
    db.session.commit()
    return jsonify({'message': '이벤트가 삭제되었습니다.'})