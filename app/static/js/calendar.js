let currentEvents = [];

document.addEventListener('DOMContentLoaded', () => {
    // 인증 확인
    if (!localStorage.getItem('token')) {
        window.location.href = '/login';
        return;
    }

    loadEvents();
    
    // 이벤트 폼 제출
    document.getElementById('eventForm').addEventListener('submit', handleAddEvent);
    document.getElementById('editEventForm').addEventListener('submit', handleEditEvent);
});

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
            displayEvents(events);
        } else if (response.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
    } catch (error) {
        showNotification('이벤트를 불러오는데 실패했습니다.', 'error');
    }
}

function displayEvents(events) {
    const eventsGrid = document.getElementById('eventsGrid');
    
    if (events.length === 0) {
        eventsGrid.innerHTML = '<p style="text-align: center; color: #666; padding: 2rem;">등록된 일정이 없습니다.</p>';
        return;
    }
    
    eventsGrid.innerHTML = events.map(event => {
        const startDate = new Date(event.start_time);
        const endDate = event.end_time ? new Date(event.end_time) : null;
        
        return `
            <div class="event-card fade-in" onclick="openEditModal(${event.id})">
                <div class="event-title">${event.title}</div>
                <div class="event-time">
                    ${formatDateTime(startDate)}${endDate ? ' - ' + formatDateTime(endDate) : ''}
                </div>
                ${event.description ? `<div class="event-description">${event.description}</div>` : ''}
                ${event.repeat ? `<div class="event-repeat">🔄 ${getRepeatText(event.repeat)}</div>` : ''}
            </div>
        `;
    }).join('');
}

async function handleAddEvent(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const eventData = {
        title: formData.get('title'),
        description: formData.get('description'),
        start_time: formData.get('start_time'),
        end_time: formData.get('end_time') || null,
        repeat: formData.get('repeat') || null
    };
    
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
            showNotification('이벤트가 추가되었습니다!');
            e.target.reset();
            loadEvents();
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

function formatDateTime(date) {
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
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