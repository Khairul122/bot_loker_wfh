const drawer = document.querySelector('#logDrawer');
const list = document.querySelector('#logList');
const toggle = document.querySelector('#bLogs');
const close = document.querySelector('#logClose');
function show(open) { drawer.classList.toggle('show', open); drawer.setAttribute('aria-hidden', String(!open)); }
toggle?.addEventListener('click', () => show(!drawer.classList.contains('show')));
close?.addEventListener('click', () => show(false));
if (window.EventSource) {
  const stream = new EventSource('/events');
  stream.onmessage = ({ data }) => {
    try {
      const event = JSON.parse(data);
      const item = document.createElement('li');
      item.textContent = `${event.employee || '-'} · ${event.task || '-'} · ${event.status || ''}${event.error_code ? ` · ${event.error_code}` : ''}`;
      list.append(item);
      while (list.children.length > 100) list.firstChild.remove();
    } catch (_) { /* malformed event ignored */ }
  };
}
