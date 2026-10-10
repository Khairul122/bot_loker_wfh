// ---------- single realtime socket: live log events + stats over one WebSocket ----------
import { applyStats } from './sync.js';
import { addLogItem } from '../ui/logs.js';
import { meetingEvent } from '../ui/meeting.js';

function handle({ data }) {
  let msg;
  try { msg = JSON.parse(data); } catch { return; }
  if (msg && msg.type === 'stats') applyStats(msg.data);
  else if (msg && msg.type === 'meeting') meetingEvent(msg);
  else addLogItem(msg);
}

function sse() {
  if (!window.EventSource) return;
  const stream = new EventSource('/events');
  stream.onmessage = handle;
}

function connect() {
  let ws;
  try { ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/logs'); }
  catch { return sse(); }
  ws.onmessage = handle;
  ws.onclose = () => setTimeout(connect, 3000); // quiet reconnect, no console noise
}

connect();