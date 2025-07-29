const socket = io();

socket.on('connect', () => {
    socket.emit('join', { room: '1' });
});

socket.on('message', (data) => {
    const messages = document.getElementById('messages');
    messages.innerHTML += `<p>${data.user}: ${data.content}</p>`;
});

function sendMessage() {
    const input = document.getElementById('message-input');
    socket.emit('message', { room: '1', content: input.value });
    input.value = '';
}