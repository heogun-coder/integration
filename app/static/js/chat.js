let socket;
let currentRoom = null;
let currentUser = localStorage.getItem('username');

document.addEventListener('DOMContentLoaded', () => {
    // 인증 확인
    if (!localStorage.getItem('token')) {
        window.location.href = '/login';
        return;
    }

    initializeSocket();
    loadChatRooms();
    
    // 채팅방 생성 폼 제출
    document.getElementById('createRoomForm').addEventListener('submit', handleCreateRoom);
});

function initializeSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('소켓 연결됨');
    });
    
    socket.on('disconnect', () => {
        console.log('소켓 연결 해제됨');
    });
    
    socket.on('status', (data) => {
        console.log('상태:', data.msg);
    });
    
    socket.on('message', (data) => {
        displayMessage(data);
    });
    
    socket.on('user_joined', (data) => {
        showNotification(`${data.username}님이 채팅방에 참여했습니다.`);
    });
    
    socket.on('user_left', (data) => {
        showNotification(`${data.username}님이 채팅방을 나갔습니다.`);
    });
}

async function loadChatRooms() {
    try {
        const response = await fetch('/api/chat/rooms', {
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }
        });
        
        if (response.ok) {
            const rooms = await response.json();
            displayChatRooms(rooms);
        }
    } catch (error) {
        showNotification('채팅방 목록을 불러오는데 실패했습니다.', 'error');
    }
}

function displayChatRooms(rooms) {
    const roomsList = document.getElementById('roomsList');
    
    if (rooms.length === 0) {
        roomsList.innerHTML = '<p style="color: #666; text-align: center; padding: 1rem;">채팅방이 없습니다.</p>';
        return;
    }
    
    roomsList.innerHTML = rooms.map(room => `
        <div class="room-item" onclick="joinRoom(${room.id}, '${room.name}')">
            <div style="font-weight: 600;">${room.name}</div>
            <div style="font-size: 0.8rem; color: #666;">
                ${room.is_group ? '그룹 채팅' : '개인 채팅'}
            </div>
        </div>
    `).join('');
}

function joinRoom(roomId, roomName) {
    if (currentRoom === roomId) return;
    
    // 이전 방 나가기
    if (currentRoom) {
        socket.emit('leave', { room: currentRoom });
    }
    
    currentRoom = roomId;
    
    // 새 방 참여
    socket.emit('join', { room: roomId, username: currentUser });
    
    // UI 업데이트
    document.getElementById('currentRoomName').textContent = roomName;
    document.getElementById('chatInput').style.display = 'block';
    
    // 활성 방 표시
    document.querySelectorAll('.room-item').forEach(item => {
        item.classList.remove('active');
    });
    event.target.closest('.room-item').classList.add('active');
    
    // 메시지 초기화
    document.getElementById('messages').innerHTML = '';
    
    // 기존 메시지 로드
    loadMessages(roomId);
}

async function loadMessages(roomId) {
    try {
        const response = await fetch(`/api/chat/rooms/${roomId}/messages`, {
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }
        });
        
        if (response.ok) {
            const messages = await response.json();
            messages.forEach(message => {
                displayMessage(message, false);
            });
            scrollToBottom();
        }
    } catch (error) {
        console.error('메시지 로드 실패:', error);
    }
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    
    if (!content || !currentRoom) return;
    
    socket.emit('message', {
        room: currentRoom,
        content: content,
        username: currentUser
    });
    
    input.value = '';
}

function displayMessage(data, animate = true) {
    const messages = document.getElementById('messages');
    const isOwn = data.username === currentUser;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isOwn ? 'own' : ''} ${animate ? 'fade-in' : ''}`;
    
    const time = data.timestamp ? new Date(data.timestamp).toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit'
    }) : new Date().toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit'
    });
    
    messageDiv.innerHTML = `
        ${!isOwn ? `<div class="message-avatar">${data.username[0].toUpperCase()}</div>` : ''}
        <div>
            <div class="message-content">
                ${!isOwn ? `<div style="font-size: 0.8rem; color: #666; margin-bottom: 0.3rem;">${data.username}</div>` : ''}
                <div>${data.content}</div>
                <div class="message-time">${time}</div>
            </div>
        </div>
    `;
    
    messages.appendChild(messageDiv);
    scrollToBottom();
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
}

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

async function handleCreateRoom(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const roomData = {
        name: formData.get('name'),
        is_group: formData.get('is_group') === 'on'
    };
    
    try {
        const response = await fetch('/api/chat/rooms', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify(roomData)
        });
        
        if (response.ok) {
            showNotification('채팅방이 생성되었습니다!');
            closeCreateRoomModal();
            e.target.reset();
            loadChatRooms();
        } else {
            const error = await response.json();
            showNotification(error.error || '채팅방 생성에 실패했습니다.', 'error');
        }
    } catch (error) {
        showNotification('네트워크 오류가 발생했습니다.', 'error');
    }
}

function openCreateRoomModal() {
    document.getElementById('createRoomModal').classList.add('active');
    document.getElementById('roomName').focus();
}

function closeCreateRoomModal() {
    document.getElementById('createRoomModal').classList.remove('active');
}

function logout() {
    if (socket) {
        socket.disconnect();
    }
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
        closeCreateRoomModal();
    }
});