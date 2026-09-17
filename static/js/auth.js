(() => {
  const userId = document.body.dataset.userId;
  if (!userId) return;
  document.querySelectorAll('[data-logout-form]').forEach((form) => {
    form.addEventListener('submit', () => {
      try { sessionStorage.removeItem(`formusense_tryon_photo_v1_${userId}`); }
      catch (error) { /* Storage may be disabled. */ }
    });
  });
})();
