let currentEvents = [];
let calendar = null;
let isCalendarView = true;

document.addEventListener('DOMContentLoaded', () => {
    // 인증 확인
    if (!localStorage.getItem('token')) {
        window.location.href = '/login';
        return;
    }

    // FullCalendar 초기화
    initializeCalendar();
    
    // 이벤트 폼 제출
    document.getElementById('eventForm').addEventListener('submit', handleAddEvent);
    document.getElementById('editEventForm').addEventListener('submit', handleEditEvent);
    
    // 초기 상태 설정
    toggleRepeatOptions();
});

function initializeCalendar() {
    const calendarEl = document.getElementById('calendar');
    
    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'ko',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        height: 'auto',
        selectable: true,
        selectMirror: true,
        dayMaxEvents: true,
        weekends: true,
        nowIndicator: true,
        
        // 이벤트 소스
        events: function(fetchInfo, successCallback, failureCallback) {
            loadEventsForCalendar(fetchInfo, successCallback, failureCallback);
        },
        
        // 이벤트 클릭 핸들러
        eventClick: function(info) {
            const eventId = parseInt(info.event.id);
            openEditModal(eventId);
        },
        
        // 날짜 선택 핸들러 (새 이벤트 생성)
        select: function(selectionInfo) {
            // 폼의 시작 시간을 선택된 날짜로 설정
            const startDate = selectionInfo.start.toISOString().slice(0, 16);
            document.getElementById('due_date').value = startDate;
            document.getElementById('start_time').value = startDate;
            
            // 폼으로 스크롤
            scrollToForm();
            
            // 선택 해제
            calendar.unselect();
        },
        
        // 이벤트 드래그 앤 드롭
        editable: true,
        eventDrop: function(info) {
            const eventId = parseInt(info.event.id);
            const newStart = info.event.start;
            const newEnd = info.event.end || newStart;
            
            moveEvent(eventId, newStart.toISOString(), newEnd.toISOString());
        },
        
        // 이벤트 리사이즈
        eventResize: function(info) {
            const eventId = parseInt(info.event.id);
            const newStart = info.event.start;
            const newEnd = info.event.end;
            
            moveEvent(eventId, newStart.toISOString(), newEnd.toISOString());
        },
        
        // 이벤트 렌더링 커스터마이제이션
        eventDidMount: function(info) {
            const event = info.event;
            const element = info.el;
            
            // 우선순위 색상 적용
            if (event.extendedProps.priority) {
                element.classList.add(`priority-${event.extendedProps.priority}`);
            }
            
            // 반복 이벤트 표시
            if (event.extendedProps.repeat) {
                const indicator = document.createElement('span');
                indicator.className = 'repeat-indicator-small';
                indicator.textContent = '🔄';
                element.querySelector('.fc-event-title').appendChild(indicator);
            }
            
            // 툴팁 추가
            if (event.extendedProps.description) {
                element.title = event.extendedProps.description;
            }
        }
    });
    
    calendar.render();
    loadEvents(); // 기존 이벤트 로드
}

function toggleRepeatOptions() {
    const repeatSelect = document.getElementById('repeat');
    const singleEventOptions = document.getElementById('singleEventOptions');
    const repeatEventOptions = document.getElementById('repeatEventOptions');
    const repeatRangeOptions = document.getElementById('repeatRangeOptions');
    
    const hasRepeat = repeatSelect.value !== '';
    
    if (hasRepeat) {
        // 반복 있음: 시작/종료 시간과 반복 범위 표시
        singleEventOptions.style.display = 'none';
        repeatEventOptions.style.display = 'flex';
        repeatRangeOptions.style.display = 'flex';
        
        // 필드 required 속성 변경
        document.getElementById('due_date').required = false;
        document.getElementById('start_time').required = true;
    } else {
        // 반복 없음: Due date만 표시
        singleEventOptions.style.display = 'flex';
        repeatEventOptions.style.display = 'none';
        repeatRangeOptions.style.display = 'none';
        
        // 필드 required 속성 변경
        document.getElementById('due_date').required = true;
        document.getElementById('start_time').required = false;
    }
}

async function loadEvents() {
    try {
        const response = await fetch('/api/calendar/events', {
            headers: { 
                'Authorization': 'Bearer ' + localStorage.getItem('token'),
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const events = await response.json();
            currentEvents = events;
            
            // 리스트 뷰 업데이트
            displayEvents(events);
            
            // FullCalendar 이벤트 새로고침
            if (calendar) {
                calendar.refetchEvents();
            }
        } else if (response.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
    } catch (error) {
        showNotification('이벤트를 불러오는데 실패했습니다.', 'error');
    }
}

async function loadEventsForCalendar(fetchInfo, successCallback, failureCallback) {
    try {
        const response = await fetch('/api/calendar/events', {
            headers: { 
                'Authorization': 'Bearer ' + localStorage.getItem('token'),
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const events = await response.json();
            
            // FullCalendar 형식으로 변환
            const calendarEvents = convertToCalendarEvents(events);
            successCallback(calendarEvents);
        } else {
            failureCallback('이벤트 로드 실패');
        }
    } catch (error) {
        failureCallback(error);
    }
}

function convertToCalendarEvents(events) {
    const calendarEvents = [];
    
    events.forEach(event => {
        if (event.repeat && event.is_repeat_master) {
            // 마스터 이벤트 추가
            calendarEvents.push({
                id: event.id,
                title: `🔄 ${event.title}`,
                start: event.start_time,
                end: event.end_time,
                allDay: event.is_all_day || false,
                backgroundColor: event.color || '#667eea',
                borderColor: event.color || '#667eea',
                extendedProps: {
                    description: event.description,
                    priority: event.priority,
                    repeat: event.repeat,
                    is_repeat_master: true
                }
            });
            
            // 반복 인스턴스들 생성 (현재 달력 뷰 범위만)
            const instances = generateRecurringInstances(event, 
                new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), // 1개월 전
                new Date(Date.now() + 60 * 24 * 60 * 60 * 1000)  // 2개월 후
            );
            
            instances.forEach(instance => {
                calendarEvents.push({
                    id: instance.id,
                    title: instance.title,
                    start: instance.start_time,
                    end: instance.end_time,
                    allDay: instance.is_all_day || false,
                    backgroundColor: event.color || '#667eea',
                    borderColor: event.color || '#667eea',
                    className: 'event-instance',
                    extendedProps: {
                        description: instance.description,
                        priority: instance.priority,
                        repeat: instance.repeat,
                        is_instance: true
                    }
                });
            });
        } else if (!event.repeat) {
            // 일반 이벤트
            calendarEvents.push({
                id: event.id,
                title: event.title,
                start: event.start_time,
                end: event.end_time,
                allDay: event.is_all_day || false,
                backgroundColor: event.color || getPriorityColor(event.priority),
                borderColor: event.color || getPriorityColor(event.priority),
                extendedProps: {
                    description: event.description,
                    priority: event.priority,
                    repeat: event.repeat
                }
            });
        }
    });
    
    return calendarEvents;
}

function getPriorityColor(priority) {
    const colors = {
        'low': '#4CAF50',
        'normal': '#2196F3', 
        'high': '#FF9800',
        'urgent': '#F44336'
    };
    return colors[priority] || '#667eea';
}

function displayEvents(events) {
    const eventsGrid = document.getElementById('eventsGrid');
    
    if (events.length === 0) {
        eventsGrid.innerHTML = '<p style="text-align: center; color: #666; padding: 2rem;">등록된 일정이 없습니다.</p>';
        return;
    }
    
    // 반복 이벤트를 현재 보기 범위에 맞게 확장
    const expandedEvents = expandRecurringEvents(events);
    
    eventsGrid.innerHTML = expandedEvents.map(event => {
        const startDate = new Date(event.start_time);
        const endDate = event.end_time ? new Date(event.end_time) : null;
        const priorityClass = event.priority ? `priority-${event.priority}` : 'priority-normal';
        const isRecurring = event.repeat && event.is_repeat_master;
        const isInstance = event.is_instance;
        
        let eventClasses = `event-card fade-in ${priorityClass}`;
        if (isRecurring) eventClasses += ' event-master';
        if (isInstance) eventClasses += ' event-instance';
        
        return `
            <div class="${eventClasses}" onclick="openEditModal(${event.id})">
                ${isRecurring ? '<div class="repeat-indicator">R</div>' : ''}
                <div class="event-title">${event.title}</div>
                <div class="event-time">
                    ${event.is_all_day ? formatDate(startDate) : 
                      formatDateTime(startDate)}${!event.is_all_day && endDate && endDate.getTime() !== startDate.getTime() ? ' - ' + formatDateTime(endDate) : ''}
                </div>
                ${event.description ? `<div class="event-description">${event.description}</div>` : ''}
                ${event.repeat ? `<div class="event-repeat">🔄 ${getRepeatText(event.repeat)}${event.repeat_until ? ' (until ' + formatDate(new Date(event.repeat_until)) + ')' : ''}</div>` : ''}
                ${event.priority && event.priority !== 'normal' ? `<div class="event-priority">우선순위: ${getPriorityText(event.priority)}</div>` : ''}
            </div>
        `;
    }).join('');
}

function expandRecurringEvents(events) {
    const expanded = [];
    const now = new Date();
    const viewStart = new Date(now.getFullYear(), now.getMonth() - 1, 1); // 1달 전부터
    const viewEnd = new Date(now.getFullYear(), now.getMonth() + 2, 0); // 2달 후까지
    
    events.forEach(event => {
        if (event.repeat && event.is_repeat_master) {
            // 마스터 이벤트는 그대로 추가
            expanded.push(event);
            
            // 반복 인스턴스들 생성
            const instances = generateRecurringInstances(event, viewStart, viewEnd);
            expanded.push(...instances);
        } else if (!event.repeat || !event.is_repeat_master) {
            // 일반 이벤트 또는 반복이 아닌 이벤트
            expanded.push(event);
        }
    });
    
    return expanded.sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
}

function generateRecurringInstances(masterEvent, viewStart, viewEnd) {
    const instances = [];
    const startDate = new Date(masterEvent.start_time);
    const endDate = masterEvent.end_time ? new Date(masterEvent.end_time) : startDate;
    const duration = endDate.getTime() - startDate.getTime();
    
    let repeatUntil = viewEnd;
    if (masterEvent.repeat_until) {
        repeatUntil = new Date(Math.min(new Date(masterEvent.repeat_until).getTime(), viewEnd.getTime()));
    }
    
    let currentDate = new Date(Math.max(startDate.getTime(), viewStart.getTime()));
    let count = 0;
    const maxCount = masterEvent.repeat_count || 50; // 최대 50개 인스턴스
    
    while (currentDate <= repeatUntil && count < maxCount) {
        if (currentDate.getTime() !== startDate.getTime()) { // 마스터 이벤트와 중복 방지
            const instanceEndDate = new Date(currentDate.getTime() + duration);
            
            instances.push({
                ...masterEvent,
                id: `${masterEvent.id}_${currentDate.toISOString().split('T')[0]}`,
                start_time: currentDate.toISOString(),
                end_time: instanceEndDate.toISOString(),
                is_instance: true,
                is_repeat_master: false
            });
        }
        
        // 다음 날짜 계산
        switch (masterEvent.repeat) {
            case 'daily':
                currentDate.setDate(currentDate.getDate() + 1);
                break;
            case 'weekly':
                currentDate.setDate(currentDate.getDate() + 7);
                break;
            case 'monthly':
                currentDate.setMonth(currentDate.getMonth() + 1);
                break;
            default:
                return instances;
        }
        count++;
    }
    
    return instances;
}

async function handleAddEvent(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const repeat = formData.get('repeat') || null;
    
    let eventData;
    
    if (repeat) {
        // 반복 이벤트
        eventData = {
            title: formData.get('title'),
            description: formData.get('description'),
            start_time: formData.get('start_time'),
            end_time: formData.get('end_time') || null,
            repeat: repeat,
            repeat_until: formData.get('repeat_until') || null,
            repeat_count: formData.get('repeat_count') ? parseInt(formData.get('repeat_count')) : null,
            priority: 'normal'
        };
    } else {
        // 단일 이벤트 (Due date 사용)
        const dueDate = formData.get('due_date');
        eventData = {
            title: formData.get('title'),
            description: formData.get('description'),
            start_time: dueDate,
            end_time: dueDate, // Due date를 시작과 끝으로 동일하게 설정
            repeat: null,
            priority: formData.get('priority') || 'normal',
            is_all_day: true // Due date는 하루 종일 이벤트로 처리
        };
    }
    
    try {
        const response = await fetch('/api/calendar/events', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify(eventData)
        });
        
        if (response.ok) {
            const result = await response.json();
            if (repeat && result.is_recurring) {
                showNotification(`반복 이벤트가 생성되었습니다! (마스터 이벤트)`);
            } else {
                showNotification('이벤트가 추가되었습니다!');
            }
            e.target.reset();
            toggleRepeatOptions(); // 폼 리셋 후 옵션 재설정
            loadEvents();
            
            // FullCalendar 새로고침
            if (calendar) {
                calendar.refetchEvents();
            }
        } else {
            const error = await response.json();
            showNotification(error.error || '이벤트 추가에 실패했습니다.', 'error');
        }
    } catch (error) {
        showNotification('네트워크 오류가 발생했습니다.', 'error');
    }
}

function openEditModal(eventId) {
    const event = currentEvents.find(e => e.id === eventId);
    if (!event) return;
    
    document.getElementById('editEventId').value = event.id;
    document.getElementById('editTitle').value = event.title;
    document.getElementById('editStartTime').value = formatForInput(event.start_time);
    document.getElementById('editEndTime').value = event.end_time ? formatForInput(event.end_time) : '';
    document.getElementById('editDescription').value = event.description || '';
    document.getElementById('editRepeat').value = event.repeat || '';
    
    document.getElementById('editModal').classList.add('active');
}

function closeModal() {
    document.getElementById('editModal').classList.remove('active');
}

async function handleEditEvent(e) {
    e.preventDefault();
    
    const eventId = document.getElementById('editEventId').value;
    const formData = new FormData(e.target);
    const eventData = {
        title: formData.get('title'),
        description: formData.get('description'),
        start_time: formData.get('start_time'),
        end_time: formData.get('end_time') || null,
        repeat: formData.get('repeat') || null
    };
    
    try {
        const response = await fetch(`/api/calendar/events/${eventId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify(eventData)
        });
        
        if (response.ok) {
            showNotification('이벤트가 수정되었습니다!');
            closeModal();
            loadEvents();
            
            // FullCalendar 새로고침
            if (calendar) {
                calendar.refetchEvents();
            }
        } else {
            const error = await response.json();
            showNotification(error.error || '이벤트 수정에 실패했습니다.', 'error');
        }
    } catch (error) {
        showNotification('네트워크 오류가 발생했습니다.', 'error');
    }
}

async function deleteEvent() {
    if (!confirm('정말로 이 이벤트를 삭제하시겠습니까?')) return;
    
    const eventId = document.getElementById('editEventId').value;
    
    try {
        const response = await fetch(`/api/calendar/events/${eventId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }
        });
        
        if (response.ok) {
            showNotification('이벤트가 삭제되었습니다!');
            closeModal();
            loadEvents();
            
            // FullCalendar 새로고침
            if (calendar) {
                calendar.refetchEvents();
            }
        } else {
            const error = await response.json();
            showNotification(error.error || '이벤트 삭제에 실패했습니다.', 'error');
        }
    } catch (error) {
        showNotification('네트워크 오류가 발생했습니다.', 'error');
    }
}

function scrollToForm() {
    document.querySelector('.event-form').scrollIntoView({ behavior: 'smooth' });
    document.getElementById('title').focus();
}

function toggleView() {
    const calendarEl = document.getElementById('calendar');
    const eventsGrid = document.getElementById('eventsGrid');  
    const toggleBtn = document.getElementById('viewToggle');
    
    if (isCalendarView) {
        // 리스트 뷰로 전환
        calendarEl.style.display = 'none';
        eventsGrid.style.display = 'block';
        toggleBtn.textContent = '달력 보기';
        isCalendarView = false;
    } else {
        // 달력 뷰로 전환
        calendarEl.style.display = 'block';
        eventsGrid.style.display = 'none';  
        toggleBtn.textContent = '리스트 보기';
        isCalendarView = true;
        
        // 달력 크기 재조정
        if (calendar) {
            calendar.updateSize();
        }
    }
}

async function moveEvent(eventId, newStartTime, newEndTime) {
    try {
        const response = await fetch(`/api/calendar/events/${eventId}/move`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify({
                start_time: newStartTime,
                end_time: newEndTime
            })
        });
        
        if (response.ok) {
            showNotification('일정이 이동되었습니다!');
            loadEvents(); // 리스트 뷰도 업데이트
        } else {
            const error = await response.json();
            showNotification(error.error || '일정 이동에 실패했습니다.', 'error');
            
            // 실패시 원래 위치로 되돌리기
            if (calendar) {
                calendar.refetchEvents();
            }
        }
    } catch (error) {
        showNotification('네트워크 오류가 발생했습니다.', 'error');
        
        // 실패시 원래 위치로 되돌리기  
        if (calendar) {
            calendar.refetchEvents();
        }
    }
}

function formatDateTime(date) {
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDate(date) {
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function formatForInput(dateString) {
    const date = new Date(dateString);
    return date.toISOString().slice(0, 16);
}

function getRepeatText(repeat) {
    const texts = {
        'daily': '매일',
        'weekly': '매주',
        'monthly': '매월'
    };
    return texts[repeat] || repeat;
}

function getPriorityText(priority) {
    const texts = {
        'low': '낮음',
        'normal': '보통',
        'high': '높음',
        'urgent': '긴급'
    };
    return texts[priority] || priority;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    showNotification('로그아웃되었습니다.');
    setTimeout(() => {
        window.location.href = '/login';
    }, 1000);
}

function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = 'notification';
    if (type === 'error') {
        notification.style.background = 'linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%)';
    }
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// 모달 외부 클릭시 닫기
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        closeModal();
    }
});