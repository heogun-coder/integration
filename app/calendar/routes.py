from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta, date
from app.models import Event, User, EventShare, db
import calendar
import uuid

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
        
        repeat_until = None
        if data.get('repeat_until'):
            repeat_until = datetime.fromisoformat(data['repeat_until'].replace('Z', '+00:00'))
        
        # 반복 이벤트인 경우 그룹 ID 생성
        repeat_group_id = None
        if data.get('repeat') and data.get('repeat') != 'none':
            repeat_group_id = str(uuid.uuid4())
        
        event = Event(
            title=data['title'],
            description=data.get('description'),
            start_time=start_time,
            end_time=end_time,
            repeat=data.get('repeat'),
            category=data.get('category', 'general'),
            location=data.get('location'),
            is_all_day=data.get('is_all_day', False),
            user_id=user_id,
            repeat_group_id=repeat_group_id,
            is_repeat_master=bool(repeat_group_id),
            repeat_until=repeat_until,
            notification_minutes=data.get('notification_minutes', 15),
            color=data.get('color', '#3788d8'),
            priority=data.get('priority', 'normal')
        )
        db.session.add(event)
        db.session.flush()  # event.id를 얻기 위해
        
        db.session.commit()
        
        return jsonify({
            'message': '이벤트가 생성되었습니다.', 
            'event_id': event.id,
            'events_created': 1,  # 마스터 이벤트만 생성
            'repeat_group_id': repeat_group_id,
            'is_recurring': bool(repeat_group_id)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '이벤트 생성에 실패했습니다.'}), 400

@calendar_bp.route('/api/calendar/events', methods=['GET'])
@jwt_required()
def get_events():
    user_id = int(get_jwt_identity())
    
    # 날짜 범위 파라미터
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    category = request.args.get('category')
    include_shared = request.args.get('include_shared', 'true').lower() == 'true'
    
    # 본인 이벤트 쿼리
    query = Event.query.filter_by(user_id=user_id)
    
    # 공유된 이벤트도 포함하는 경우
    if include_shared:
        shared_event_ids = db.session.query(EventShare.event_id).filter_by(shared_with_user_id=user_id).subquery()
        query = Event.query.filter(
            db.or_(
                Event.user_id == user_id,
                Event.id.in_(shared_event_ids)
            )
        )
    
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
        # 공유된 이벤트인지 확인
        is_shared_with_me = event.user_id != user_id
        share_permission = None
        if is_shared_with_me:
            share = EventShare.query.filter_by(event_id=event.id, shared_with_user_id=user_id).first()
            share_permission = share.permission if share else 'view'
        
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
            'updated_at': event.updated_at.isoformat(),
            'repeat_group_id': event.repeat_group_id,
            'is_repeat_master': event.is_repeat_master,
            'repeat_until': event.repeat_until.isoformat() if event.repeat_until else None,
            'notification_minutes': event.notification_minutes,
            'color': event.color,
            'priority': event.priority,
            'is_shared_with_me': is_shared_with_me,
            'share_permission': share_permission,
            'owner_username': User.query.get(event.user_id).username if is_shared_with_me else None
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

@calendar_bp.route('/api/calendar/events/<int:event_id>/move', methods=['PUT'])
@jwt_required()
def move_event(event_id):
    """드래그앤드롭으로 이벤트 시간/날짜 변경"""
    user_id = int(get_jwt_identity())
    
    data = request.get_json()
    new_start_time = data.get('new_start_time')
    new_end_time = data.get('new_end_time')
    
    if not new_start_time:
        return jsonify({'error': '새 시작 시간이 필요합니다.'}), 400
    
    event = Event.query.filter_by(id=event_id).first()
    if not event:
        return jsonify({'error': '이벤트를 찾을 수 없습니다.'}), 404
    
    # 권한 확인 (본인 이벤트 또는 편집 권한이 있는 공유 이벤트)
    can_edit = event.user_id == user_id
    if not can_edit:
        share = EventShare.query.filter_by(event_id=event_id, shared_with_user_id=user_id).first()
        can_edit = share and share.permission == 'edit'
    
    if not can_edit:
        return jsonify({'error': '이벤트 수정 권한이 없습니다.'}), 403
    
    try:
        # 시간 변경
        old_start = event.start_time
        new_start = datetime.fromisoformat(new_start_time.replace('Z', '+00:00'))
        
        # 종료 시간 계산 (기존 이벤트 길이 유지)
        if event.end_time and new_end_time:
            new_end = datetime.fromisoformat(new_end_time.replace('Z', '+00:00'))
        elif event.end_time:
            duration = event.end_time - event.start_time
            new_end = new_start + duration
        else:
            new_end = None
        
        event.start_time = new_start
        event.end_time = new_end
        event.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': '이벤트 시간이 변경되었습니다.',
            'event': {
                'id': event.id,
                'start_time': event.start_time.isoformat(),
                'end_time': event.end_time.isoformat() if event.end_time else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '이벤트 시간 변경에 실패했습니다.'}), 500

@calendar_bp.route('/api/calendar/events/<int:event_id>/share', methods=['POST'])
@jwt_required()
def share_event(event_id):
    """이벤트 공유"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    share_with_username = data.get('username')
    permission = data.get('permission', 'view')  # view 또는 edit
    
    if not share_with_username:
        return jsonify({'error': '공유할 사용자명이 필요합니다.'}), 400
    
    # 이벤트 소유자 확인
    event = Event.query.filter_by(id=event_id, user_id=user_id).first()
    if not event:
        return jsonify({'error': '이벤트를 찾을 수 없거나 권한이 없습니다.'}), 404
    
    # 공유할 사용자 확인
    share_with_user = User.query.filter_by(username=share_with_username).first()
    if not share_with_user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    # 자신과 공유 방지
    if share_with_user.id == user_id:
        return jsonify({'error': '자신과는 공유할 수 없습니다.'}), 400
    
    # 이미 공유된 경우 권한 업데이트
    existing_share = EventShare.query.filter_by(
        event_id=event_id, 
        shared_with_user_id=share_with_user.id
    ).first()
    
    try:
        if existing_share:
            existing_share.permission = permission
        else:
            event_share = EventShare(
                event_id=event_id,
                shared_with_user_id=share_with_user.id,
                shared_by_user_id=user_id,
                permission=permission
            )
            db.session.add(event_share)
            
        # 이벤트를 공유됨으로 표시
        event.is_shared = True
        db.session.commit()
        
        return jsonify({
            'message': f'이벤트가 {share_with_username}님과 공유되었습니다.',
            'permission': permission
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '이벤트 공유에 실패했습니다.'}), 500

@calendar_bp.route('/api/calendar/events/<int:event_id>/unshare', methods=['DELETE'])
@jwt_required()
def unshare_event(event_id):
    """이벤트 공유 해제"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    unshare_with_username = data.get('username')
    
    if not unshare_with_username:
        return jsonify({'error': '공유 해제할 사용자명이 필요합니다.'}), 400
    
    # 이벤트 소유자 확인
    event = Event.query.filter_by(id=event_id, user_id=user_id).first()
    if not event:
        return jsonify({'error': '이벤트를 찾을 수 없거나 권한이 없습니다.'}), 404
    
    # 공유 해제할 사용자 확인
    unshare_with_user = User.query.filter_by(username=unshare_with_username).first()
    if not unshare_with_user:
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    # 공유 레코드 삭제
    event_share = EventShare.query.filter_by(
        event_id=event_id,
        shared_with_user_id=unshare_with_user.id
    ).first()
    
    if not event_share:
        return jsonify({'error': '공유되지 않은 이벤트입니다.'}), 404
    
    try:
        db.session.delete(event_share)
        
        # 다른 공유가 없으면 is_shared를 False로 변경
        remaining_shares = EventShare.query.filter_by(event_id=event_id).count()
        if remaining_shares == 1:  # 삭제할 것 포함해서 1개
            event.is_shared = False
            
        db.session.commit()
        
        return jsonify({
            'message': f'{unshare_with_username}님과의 이벤트 공유가 해제되었습니다.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '이벤트 공유 해제에 실패했습니다.'}), 500

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
        
        # 새 이벤트 생성 (모든 필드 복사)
        new_event = Event(
            title=base_event.title,
            description=base_event.description,
            start_time=current_date,
            end_time=current_date + (base_event.end_time - base_event.start_time) if base_event.end_time else None,
            repeat=base_event.repeat,
            category=base_event.category,
            location=base_event.location,
            is_all_day=base_event.is_all_day,
            user_id=base_event.user_id,
            repeat_group_id=base_event.repeat_group_id,
            is_repeat_master=False,  # 반복 생성된 이벤트는 마스터가 아님
            repeat_until=base_event.repeat_until,
            notification_minutes=base_event.notification_minutes,
            color=base_event.color,
            priority=base_event.priority
        )
        
        db.session.add(new_event)
        created_events.append(new_event)
        
        # 너무 많은 이벤트 생성 방지
        if len(created_events) >= 100:
            break
    
    return created_events

@calendar_bp.route('/api/calendar/events/repeat-group/<repeat_group_id>', methods=['DELETE'])
@jwt_required()
def delete_repeat_group(repeat_group_id):
    """반복 이벤트 그룹 전체 삭제"""
    user_id = int(get_jwt_identity())
    
    # 해당 그룹의 모든 이벤트 조회
    events = Event.query.filter_by(repeat_group_id=repeat_group_id, user_id=user_id).all()
    
    if not events:
        return jsonify({'error': '반복 이벤트 그룹을 찾을 수 없습니다.'}), 404
    
    try:
        # 모든 이벤트 삭제
        for event in events:
            db.session.delete(event)
        
        db.session.commit()
        
        return jsonify({
            'message': f'{len(events)}개의 반복 이벤트가 삭제되었습니다.',
            'deleted_count': len(events)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '반복 이벤트 삭제에 실패했습니다.'}), 500

@calendar_bp.route('/api/calendar/events/<int:event_id>/notifications', methods=['GET'])
@jwt_required()
def get_event_notifications():
    """다가오는 이벤트 알림 조회"""
    user_id = int(get_jwt_identity())
    
    # 현재 시간부터 24시간 이내의 이벤트들
    now = datetime.utcnow()
    tomorrow = now + timedelta(hours=24)
    
    events = Event.query.filter(
        Event.user_id == user_id,
        Event.start_time >= now,
        Event.start_time <= tomorrow
    ).order_by(Event.start_time).all()
    
    notifications = []
    for event in events:
        # 알림 시간 계산
        notification_time = event.start_time - timedelta(minutes=event.notification_minutes)
        
        # 알림 시간이 현재 시간 이후라면 포함
        if notification_time <= now:
            time_until_event = event.start_time - now
            hours_until = int(time_until_event.total_seconds() // 3600)
            minutes_until = int((time_until_event.total_seconds() % 3600) // 60)
            
            notifications.append({
                'event_id': event.id,
                'title': event.title,
                'start_time': event.start_time.isoformat(),
                'location': event.location,
                'category': event.category,
                'priority': event.priority,
                'hours_until': hours_until,
                'minutes_until': minutes_until,
                'time_until_text': f'{hours_until}시간 {minutes_until}분 후' if hours_until > 0 else f'{minutes_until}분 후'
            })
    
    return jsonify({
        'notifications': notifications,
        'count': len(notifications)
    })