const DIALOGS = [
  ['inbox', 'inboxClose'], ['board', 'boardClose'], ['reports', 'reportsClose'],
  ['results', 'resultsClose'], ['perf', 'perfClose'], ['meeting', 'meetingClose'],
  ['settings', 'settingsClose'], ['card', 'cardClose'], ['custom', 'bCustom'],
  ['logDrawer', 'logClose'], ['menu', 'menuClose'],
];
const FOCUSABLE = 'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])';
let active = null;
let opener = null;

function visibleDialogs() {
  return [
    ...DIALOGS.map(([id, closeId]) => ({ root: document.getElementById(id), closeId }))
      .filter(item => item.root?.classList.contains('show')),
    ...[...document.querySelectorAll('.modal-overlay')].map(root => ({ root, closeId: null })),
  ];
}

function syncDialogs() {
  const open = visibleDialogs();
  for (const [id] of DIALOGS) {
    const root = document.getElementById(id);
    if (root) root.setAttribute('aria-hidden', String(!root.classList.contains('show')));
  }
  const top = open.at(-1) || null;
  if (top && top.root !== active?.root) {
    if (!active && !opener) {
      const focused = document.activeElement;
      if (focused instanceof HTMLElement && focused !== document.body && !top.root.contains(focused)) {
        opener = focused;
      }
    }
    active = top;
    if (top.root.id !== 'menu') {
      top.root.setAttribute('role', top.root.id === 'card' ? 'dialog' : top.root.getAttribute('role') || 'dialog');
      if (['inbox', 'board', 'reports', 'results', 'perf', 'meeting', 'settings'].includes(top.root.id)) {
        top.root.setAttribute('aria-modal', 'true');
      }
      const focusable = [...top.root.querySelectorAll(FOCUSABLE)].find(el => el.getClientRects().length);
      (focusable || top.root).focus({ preventScroll: true });
    }
  } else if (!top && active) {
    active = null;
    if (opener?.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  }
}

document.addEventListener('keydown', event => {
  if (!active) return;
  if (event.key === 'Escape') {
    const close = active.closeId
      ? document.getElementById(active.closeId)
      : active.root.querySelector('.modal-close');
    if (close) close.click();
    return;
  }
  if (event.key !== 'Tab') return;
  const modalRoot = active.root.matches('[aria-modal="true"]')
    ? active.root
    : active.root.querySelector('[aria-modal="true"]');
  if (!modalRoot) return;
  const items = [...modalRoot.querySelectorAll(FOCUSABLE)].filter(el => el.getClientRects().length);
  if (!items.length) {
    event.preventDefault();
    modalRoot.focus();
    return;
  }
  const first = items[0], last = items.at(-1);
  if (event.shiftKey && (document.activeElement === first || !modalRoot.contains(document.activeElement))) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !modalRoot.contains(document.activeElement))) {
    event.preventDefault(); first.focus();
  }
}, true);

const observer = new MutationObserver(syncDialogs);
for (const [id] of DIALOGS) {
  const root = document.getElementById(id);
  if (root) {
    if (!root.hasAttribute('tabindex')) root.tabIndex = -1;
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
  }
}
observer.observe(document.body, { childList: true, subtree: true });
syncDialogs();
