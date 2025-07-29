from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
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
    user_id = get_jwt_identity()
    event = Event(
        title=data['title'],
        description=data.get('description'),
        start_time=data['start_time'],
        end_time=data.get('end_time'),
        repeat=data.get('repeat'),
        user_id=user_id
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({'message': 'Event created successfully'}), 201

@calendar_bp.route('/api/calendar/events', methods=['GET'])
@jwt_required()
def get_events():
    user_id = get_jwt_identity()
    events = Event.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'id': event.id,
        'title': event.title,
        'start_time': event.start_time.isoformat(),
        'end_time': event.end_time.isoformat() if event.end_time else None,
        'repeat': event.repeat
    } for event in events])