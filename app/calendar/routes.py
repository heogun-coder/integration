from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta, date
from app.models import Event, User, db
import calendar

calendar_bp = Blueprint('calendar', __name__)

@calendar_bp.route('/calendar')
@jwt_required()
def calendar_view():
    return render_template('calendar.html')

@calendar_bp.route('/api/calendar/events', methods=['POST'])
@jwt_required()
def create_event():
    data = request.get_json()
    user_id = int(get_jwt_identity())
    
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
            category=data.get('category', 'general'),
            location=data.get('location'),
            is_all_day=data.get('is_all_day', False),
            user_id=user_id
        )
        db.session.add(event)
        db.session.commit()
        
        # 반복 이벤트 생성
        created_events = [event]
        if data.get('repeat') and data.get('repeat') != 'none':
            created_events.extend(create_recurring_events(event, data.get('repeat_until')))
        
        return jsonify({
            'message': '이벤트가 생성되었습니다.', 
            'event_id': event.id,
            'events_created': len(created_events)
        }), 201
    except Exception as e:
        return jsonify({'error': '이벤트 생성에 실패했습니다.'}), 400

@calendar_bp.route('/api/calendar/events', methods=['GET'])
@jwt_required()
def get_events():
    user_id = int(get_jwt_identity())
    
    # 날짜 범위 파라미터
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    category = request.args.get('category')
    
    query = Event.query.filter_by(user_id=user_id)
    
    # 날짜 범위 필터링
    if start_date:
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        query = query.filter(Event.start_time >= start_dt)
    
    if end_date:
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        query = query.filter(Event.start_time <= end_dt)
    
    # 카테고리 필터링
    if category and category != 'all':
        query = query.filter(Event.category == category)
    
    events = query.order_by(Event.start_time).all()
    
    event_list = []
    for event in events:
        event_data = {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'start_time': event.start_time.isoformat(),
            'end_time': event.end_time.isoformat() if event.end_time else None,
            'repeat': event.repeat,
            'category': event.category,
            'location': event.location,
            'is_all_day': event.is_all_day,
            'created_at': event.created_at.isoformat(),
            'updated_at': event.updated_at.isoformat()
        }
        event_list.append(event_data)
    
    return jsonify(event_list)

@calendar_bp.route('/api/calendar/events/<int:event_id>', methods=['PUT'])
@jwt_required()
def update_event(event_id):
    user_id = int(get_jwt_identity())
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
        event.category = data.get('category', event.category)
        event.location = data.get('location')
        event.is_all_day = data.get('is_all_day', False)
        event.updated_at = datetime.utcnow()
        
        db.session.commit()
        return jsonify({'message': '이벤트가 수정되었습니다.'})
    except Exception as e:
        return jsonify({'error': '이벤트 수정에 실패했습니다.'}), 400

@calendar_bp.route('/api/calendar/events/<int:event_id>', methods=['DELETE'])
@jwt_required()
def delete_event(event_id):
    user_id = int(get_jwt_identity())
    event = Event.query.filter_by(id=event_id, user_id=user_id).first()
    
    if not event:
        return jsonify({'error': '이벤트를 찾을 수 없습니다.'}), 404
    
    db.session.delete(event)
    db.session.commit()
    return jsonify({'message': '이벤트가 삭제되었습니다.'})

@calendar_bp.route('/api/calendar/events/today', methods=['GET'])
@jwt_required()
def get_today_events():
    user_id = int(get_jwt_identity())
    
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    events = Event.query.filter(
        Event.user_id == user_id,
        Event.start_time >= start_of_day,
        Event.start_time <= end_of_day
    ).order_by(Event.start_time).all()
    
    return jsonify([{
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'start_time': event.start_time.isoformat(),
        'end_time': event.end_time.isoformat() if event.end_time else None,
        'category': event.category,
        'location': event.location,
        'is_all_day': event.is_all_day
    } for event in events])

@calendar_bp.route('/api/calendar/events/upcoming', methods=['GET'])
@jwt_required()
def get_upcoming_events():
    user_id = int(get_jwt_identity())
    
    # 다음 7일간의 이벤트
    now = datetime.utcnow()
    week_later = now + timedelta(days=7)
    
    events = Event.query.filter(
        Event.user_id == user_id,
        Event.start_time >= now,
        Event.start_time <= week_later
    ).order_by(Event.start_time).limit(10).all()
    
    return jsonify([{
        'id': event.id,
        'title': event.title,
        'start_time': event.start_time.isoformat(),
        'category': event.category,
        'location': event.location
    } for event in events])

@calendar_bp.route('/api/calendar/stats', methods=['GET'])
@jwt_required()
def get_calendar_stats():
    user_id = int(get_jwt_identity())
    
    # 이번 달 이벤트 수
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    if now.month == 12:
        end_of_month = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end_of_month = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)
    
    month_events = Event.query.filter(
        Event.user_id == user_id,
        Event.start_time >= start_of_month,
        Event.start_time <= end_of_month
    ).count()
    
    # 카테고리별 이벤트 수
    category_stats = db.session.query(
        Event.category, 
        db.func.count(Event.id)
    ).filter(
        Event.user_id == user_id,
        Event.start_time >= start_of_month,
        Event.start_time <= end_of_month
    ).group_by(Event.category).all()
    
    # 오늘의 이벤트 수
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    today_events = Event.query.filter(
        Event.user_id == user_id,
        Event.start_time >= start_of_day,
        Event.start_time <= end_of_day
    ).count()
    
    return jsonify({
        'month_events': month_events,
        'today_events': today_events,
        'category_stats': dict(category_stats),
        'month': now.strftime('%B %Y')
    })

def create_recurring_events(base_event, repeat_until=None):
    """반복 이벤트 생성 함수"""
    created_events = []
    
    if not repeat_until:
        # 기본적으로 6개월 후까지
        repeat_until = base_event.start_time + timedelta(days=180)
    else:
        repeat_until = datetime.fromisoformat(repeat_until.replace('Z', '+00:00'))
    
    current_date = base_event.start_time
    
    while current_date <= repeat_until:
        if base_event.repeat == 'daily':
            current_date += timedelta(days=1)
        elif base_event.repeat == 'weekly':
            current_date += timedelta(weeks=1)
        elif base_event.repeat == 'monthly':
            # 월 단위 증가
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        else:
            break
        
        if current_date > repeat_until:
            break
        
        # 새 이벤트 생성
        new_event = Event(
            title=base_event.title,
            description=base_event.description,
            start_time=current_date,
            end_time=current_date + (base_event.end_time - base_event.start_time) if base_event.end_time else None,
            repeat=base_event.repeat,
            category=base_event.category,
            location=base_event.location,
            is_all_day=base_event.is_all_day,
            user_id=base_event.user_id
        )
        
        db.session.add(new_event)
        created_events.append(new_event)
        
        # 너무 많은 이벤트 생성 방지
        if len(created_events) >= 100:
            break
    
    db.session.commit()
    return created_events