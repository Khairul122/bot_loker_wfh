(() => {
  const loading = document.getElementById('loading');
  let settled = false;
  window.officeLoadingDone = () => {
    settled = true;
    loading.style.opacity = 0;
    setTimeout(() => loading.remove(), 700);
  };
  window.addEventListener('error', event => {
    if (settled) return;
    loading.textContent = `Gagal memuat kantor: ${event.message || 'JavaScript error'}`;
    loading.style.color = '#8b2635';
  });
  window.addEventListener('unhandledrejection', event => {
    if (settled) return;
    const reason = event.reason?.message || String(event.reason || 'Promise error');
    loading.textContent = `Gagal memuat kantor: ${reason}`;
    loading.style.color = '#8b2635';
  });
  setTimeout(() => {
    if (!settled && loading.isConnected && loading.textContent === 'Menyiapkan kantor…') {
      loading.textContent = 'Kantor terlalu lama memuat. Buka Console (F12) untuk detail.';
      loading.style.color = '#8b2635';
    }
  }, 15000);
})();
