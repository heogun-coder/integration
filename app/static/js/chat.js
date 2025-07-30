let socket;
let currentRoom = null;
let currentUser = localStorage.getItem('username');
let typingTimer;
let isTyping = false;
let currentPage = 1;
let hasMoreMessages = true;

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
    
    // 주기적으로 온라인 상태 업데이트
    setInterval(() => {
        if (socket && socket.connected) {
            socket.emit('ping', { username: currentUser });
        }
    }, 60000); // 1분마다
});

function initializeSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('소켓 연결됨');
        showNotification('연결되었습니다.', 'success');
    });
    
    socket.on('disconnect', () => {
        console.log('소켓 연결 해제됨');
        showNotification('연결이 끊어졌습니다. 재연결 중...', 'error');
    });
    
    socket.on('reconnect', () => {
        console.log('소켓 재연결됨');
        showNotification('다시 연결되었습니다.', 'success');
        if (currentRoom) {
            socket.emit('join', { room: currentRoom, username: currentUser });
        }
    });
    
    socket.on('status', (data) => {
        displaySystemMessage(data.msg);
    });
    
    socket.on('message', (data) => {
        displayMessage(data);
        updateRoomLastMessage(data);
    });
    
    socket.on('user_joined', (data) => {
        displaySystemMessage(`${data.username}님이 참여했습니다.`);
        updateOnlineUsers();
    });
    
    socket.on('user_left', (data) => {
        displaySystemMessage(`${data.username}님이 나갔습니다.`);
        updateOnlineUsers();
    });
    
    socket.on('typing', (data) => {
        showTypingIndicator(data.username, data.is_typing);
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
        } else if (response.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
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
    
    roomsList.innerHTML = rooms.map(room => {
        const lastMessageTime = room.last_message_time ? 
            new Date(room.last_message_time).toLocaleString('ko-KR', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            }) : '';
        
        const unreadBadge = room.unread_count > 0 ? 
            `<span class="unread-badge">${room.unread_count}</span>` : '';
        
        const onlineIndicator = room.online_count > 0 ? 
            `<span class="online-indicator">${room.online_count}명 온라인</span>` : '';
        
        return `
            <div class="room-item" onclick="joinRoom(${room.id}, '${room.name}')">
                <div class="room-header">
                    <div style="font-weight: 600; display: flex; align-items: center; gap: 0.5rem;">
                        ${room.name}
                        ${unreadBadge}
                    </div>
                    <div style="font-size: 0.7rem; color: #999;">${lastMessageTime}</div>
                </div>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.3rem;">
                    ${room.is_group ? '그룹 채팅' : '개인 채팅'} • ${room.participant_count}명
                    ${onlineIndicator}
                </div>
                ${room.last_message ? 
                    `<div class="last-message">${room.last_message_user}: ${truncateText(room.last_message, 50)}</div>` 
                    : ''}
            </div>
        `;
    }).join('');
}

function joinRoom(roomId, roomName) {
    if (currentRoom === roomId) return;
    
    // 이전 방 나가기
    if (currentRoom) {
        socket.emit('leave', { room: currentRoom, username: currentUser });
    }
    
    currentRoom = roomId;
    currentPage = 1;
    hasMoreMessages = true;
    
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
    
    // 메시지 초기화 및 로드
    document.getElementById('messages').innerHTML = '';
    loadMessages(roomId);
    loadRoomParticipants(roomId);
}

async function loadMessages(roomId, page = 1) {
    try {
        const response = await fetch(`/api/chat/rooms/${roomId}/messages?page=${page}`, {
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            
            if (page === 1) {
                // 첫 페이지는 교체
                document.getElementById('messages').innerHTML = '';
                data.messages.forEach(message => {
                    displayMessage(message, false);
                });
            } else {
                // 추가 페이지는 위에 추가
                const messagesContainer = document.getElementById('messages');
                const scrollHeight = messagesContainer.scrollHeight;
                
                data.messages.forEach(message => {
                    displayMessage(message, false, true);
                });
                
                // 스크롤 위치 유지
                messagesContainer.scrollTop = messagesContainer.scrollHeight - scrollHeight;
            }
            
            hasMoreMessages = data.has_more;
            scrollToBottom();
        }
    } catch (error) {
        console.error('메시지 로드 실패:', error);
    }
}

async function loadRoomParticipants(roomId) {
    try {
        const response = await fetch(`/api/chat/rooms/${roomId}/participants`, {
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }
        });
        
        if (response.ok) {
            const participants = await response.json();
            displayParticipants(participants);
        }
    } catch (error) {
        console.error('참가자 로드 실패:', error);
    }
}

function displayParticipants(participants) {
    const onlineUsers = document.getElementById('onlineUsers');
    if (!onlineUsers) return;
    
    const onlineList = participants.filter(p => p.is_online);
    const offlineList = participants.filter(p => !p.is_online);
    
    onlineUsers.innerHTML = `
        <div style="margin-bottom: 1rem;">
            <h4 style="font-size: 0.9rem; color: #667eea; margin-bottom: 0.5rem;">
                온라인 (${onlineList.length})
            </h4>
            ${onlineList.map(user => `
                <div class="user-item online">
                    <div class="user-status"></div>
                    ${user.username}
                </div>
            `).join('')}
        </div>
        <div>
            <h4 style="font-size: 0.9rem; color: #666; margin-bottom: 0.5rem;">
                오프라인 (${offlineList.length})
            </h4>
            ${offlineList.map(user => `
                <div class="user-item offline">
                    <div class="user-status"></div>
                    ${user.username}
                </div>
            `).join('')}
        </div>
    `;
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    
    if (!content || !currentRoom) return;
    
    // 답글 기능을 위한 reply_to_id 가져오기
    const replyTo = document.getElementById('replyPreview');
    const replyToId = replyTo && !replyTo.classList.contains('hidden') ? 
        replyTo.dataset.messageId : null;
    
    socket.emit('message', {
        room: currentRoom,
        content: content,
        username: currentUser,
        reply_to_id: replyToId
    });
    
    input.value = '';
    hideReplyPreview();
    stopTyping();
}

function displayMessage(data, animate = true, prepend = false) {
    const messages = document.getElementById('messages');
    const isOwn = data.username === currentUser;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isOwn ? 'own' : ''} ${animate ? 'fade-in' : ''}`;
    messageDiv.dataset.messageId = data.id;
    
    const time = data.timestamp ? new Date(data.timestamp).toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit'
    }) : new Date().toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit'
    });
    
    let replyHtml = '';
    if (data.reply_to) {
        replyHtml = `
            <div class="reply-indicator">
                <div class="reply-line"></div>
                <div class="reply-info">
                    <strong>${data.reply_to.username}</strong>: ${data.reply_to.content}
                </div>
            </div>
        `;
    }
    
    messageDiv.innerHTML = `
        ${!isOwn ? `<div class="message-avatar">${data.username[0].toUpperCase()}</div>` : ''}
        <div class="message-content-wrapper">
            ${replyHtml}
            <div class="message-content" oncontextmenu="showMessageMenu(event, ${data.id}, ${isOwn})">
                ${!isOwn ? `<div class="message-sender">${data.username}</div>` : ''}
                <div class="message-text">${data.content}</div>
                <div class="message-time">
                    ${time}
                    ${data.is_edited ? '<span class="edited-indicator">(수정됨)</span>' : ''}
                </div>
            </div>
        </div>
    `;
    
    if (prepend) {
        messages.insertBefore(messageDiv, messages.firstChild);
    } else {
        messages.appendChild(messageDiv);
    }
    
    if (!prepend) {
        scrollToBottom();
    }
}

function displaySystemMessage(text) {
    const messages = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'system-message fade-in';
    messageDiv.innerHTML = `<div class="system-text">${text}</div>`;
    messages.appendChild(messageDiv);
    scrollToBottom();
}

function showTypingIndicator(username, isTyping) {
    const indicator = document.getElementById('typingIndicator') || createTypingIndicator();
    
    if (isTyping) {
        indicator.innerHTML = `<div class="typing-text">${username}님이 입력 중...</div>`;
        indicator.style.display = 'block';
    } else {
        indicator.style.display = 'none';
    }
}

function createTypingIndicator() {
    const messages = document.getElementById('messages');
    const indicator = document.createElement('div');
    indicator.id = 'typingIndicator';
    indicator.className = 'typing-indicator';
    indicator.style.display = 'none';
    messages.appendChild(indicator);
    return indicator;
}

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        if (event.shiftKey) {
            // Shift+Enter는 줄바꿈
            return;
        }
        event.preventDefault();
        sendMessage();
    } else {
        handleTyping();
    }
}

function handleTyping() {
    if (!isTyping) {
        isTyping = true;
        socket.emit('typing', {
            room: currentRoom,
            username: currentUser,
            is_typing: true
        });
    }
    
    clearTimeout(typingTimer);
    typingTimer = setTimeout(stopTyping, 1000);
}

function stopTyping() {
    if (isTyping) {
        isTyping = false;
        socket.emit('typing', {
            room: currentRoom,
            username: currentUser,
            is_typing: false
        });
    }
    clearTimeout(typingTimer);
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
}

// 무한 스크롤을 위한 스크롤 이벤트 리스너
document.getElementById('messagesContainer').addEventListener('scroll', (e) => {
    if (e.target.scrollTop === 0 && hasMoreMessages && currentRoom) {
        currentPage++;
        loadMessages(currentRoom, currentPage);
    }
});

// 메시지 컨텍스트 메뉴 기능
function showMessageMenu(event, messageId, isOwn) {
    event.preventDefault();
    
    const menu = document.getElementById('messageContextMenu') || createMessageContextMenu();
    menu.dataset.messageId = messageId;
    menu.style.display = 'block';
    menu.style.left = event.pageX + 'px';
    menu.style.top = event.pageY + 'px';
    
    // 메뉴 항목 표시/숨김
    menu.querySelector('.edit-message').style.display = isOwn ? 'block' : 'none';
    menu.querySelector('.delete-message').style.display = isOwn ? 'block' : 'none';
}

function createMessageContextMenu() {
    const menu = document.createElement('div');
    menu.id = 'messageContextMenu';
    menu.className = 'context-menu';
    menu.innerHTML = `
        <div class="context-menu-item reply-message" onclick="replyToMessage()">답글</div>
        <div class="context-menu-item edit-message" onclick="editMessage()">수정</div>
        <div class="context-menu-item delete-message" onclick="deleteMessage()">삭제</div>
        <div class="context-menu-item copy-message" onclick="copyMessage()">복사</div>
    `;
    document.body.appendChild(menu);
    
    // 메뉴 외부 클릭 시 숨김
    document.addEventListener('click', () => {
        menu.style.display = 'none';
    });
    
    return menu;
}

function replyToMessage() {
    const menu = document.getElementById('messageContextMenu');
    const messageId = menu.dataset.messageId;
    const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
    
    if (messageElement) {
        const username = messageElement.querySelector('.message-sender')?.textContent || 
                        messageElement.querySelector('.message-avatar')?.textContent;
        const content = messageElement.querySelector('.message-text').textContent;
        
        showReplyPreview(messageId, username, content);
    }
    
    menu.style.display = 'none';
}

function showReplyPreview(messageId, username, content) {
    let preview = document.getElementById('replyPreview');
    if (!preview) {
        preview = document.createElement('div');
        preview.id = 'replyPreview';
        preview.className = 'reply-preview';
        document.getElementById('chatInput').insertBefore(preview, document.querySelector('.input-group'));
    }
    
    preview.dataset.messageId = messageId;
    preview.innerHTML = `
        <div class="reply-content">
            <strong>${username}</strong>: ${truncateText(content, 100)}
        </div>
        <button class="reply-close" onclick="hideReplyPreview()">&times;</button>
    `;
    preview.classList.remove('hidden');
    
    document.getElementById('messageInput').focus();
}

function hideReplyPreview() {
    const preview = document.getElementById('replyPreview');
    if (preview) {
        preview.classList.add('hidden');
    }
}

async function editMessage() {
    const menu = document.getElementById('messageContextMenu');
    const messageId = menu.dataset.messageId;
    const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
    const messageText = messageElement.querySelector('.message-text');
    const originalContent = messageText.textContent;
    
    const newContent = prompt('메시지 수정:', originalContent);
    if (newContent && newContent !== originalContent) {
        try {
            const response = await fetch(`/api/chat/messages/${messageId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                },
                body: JSON.stringify({ content: newContent })
            });
            
            if (response.ok) {
                messageText.textContent = newContent;
                const timeElement = messageElement.querySelector('.message-time');
                if (!timeElement.querySelector('.edited-indicator')) {
                    timeElement.innerHTML += ' <span class="edited-indicator">(수정됨)</span>';
                }
                showNotification('메시지가 수정되었습니다.');
            } else {
                showNotification('메시지 수정에 실패했습니다.', 'error');
            }
        } catch (error) {
            showNotification('네트워크 오류가 발생했습니다.', 'error');
        }
    }
    
    menu.style.display = 'none';
}

async function deleteMessage() {
    const menu = document.getElementById('messageContextMenu');
    const messageId = menu.dataset.messageId;
    
    if (confirm('정말로 이 메시지를 삭제하시겠습니까?')) {
        try {
            const response = await fetch(`/api/chat/messages/${messageId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                }
            });
            
            if (response.ok) {
                const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
                messageElement.remove();
                showNotification('메시지가 삭제되었습니다.');
            } else {
                showNotification('메시지 삭제에 실패했습니다.', 'error');
            }
        } catch (error) {
            showNotification('네트워크 오류가 발생했습니다.', 'error');
        }
    }
    
    menu.style.display = 'none';
}

function copyMessage() {
    const menu = document.getElementById('messageContextMenu');
    const messageId = menu.dataset.messageId;
    const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
    const content = messageElement.querySelector('.message-text').textContent;
    
    navigator.clipboard.writeText(content).then(() => {
        showNotification('메시지가 복사되었습니다.');
    });
    
    menu.style.display = 'none';
}

async function handleCreateRoom(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const roomData = {
        name: formData.get('name'),
        description: formData.get('description') || '',
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

function updateRoomLastMessage(messageData) {
    const roomItems = document.querySelectorAll('.room-item');
    roomItems.forEach(item => {
        if (item.onclick.toString().includes(currentRoom)) {
            const lastMessage = item.querySelector('.last-message');
            if (lastMessage) {
                lastMessage.textContent = `${messageData.username}: ${truncateText(messageData.content, 50)}`;
            }
        }
    });
}

function updateOnlineUsers() {
    if (currentRoom) {
        loadRoomParticipants(currentRoom);
    }
}

function truncateText(text, length) {
    return text.length > length ? text.substring(0, length) + '...' : text;
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