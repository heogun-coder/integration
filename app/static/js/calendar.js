document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/calendar/events', {
        headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
    })
    .then(response => response.json())
    .then(events => {
        const calendar = document.getElementById('calendar');
        calendar.innerHTML = '<h2>Events</h2>' + events.map(e => `<p>${e.title} - ${e.start_time}</p>`).join('');
    });
});

function addEvent() {
    const event = { title: 'New Event', start_time: new Date().toISOString() };
    fetch('/api/calendar/events', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + localStorage.getItem('token')
        },
        body: JSON.stringify(event)
    });
}