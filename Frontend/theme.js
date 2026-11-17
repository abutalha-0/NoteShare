(() => {
  const key = 'fieldnotes-theme';
  const root = document.documentElement;
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');
  let saved = null;
  try { saved = localStorage.getItem(key); } catch {}

  function apply(theme) {
    const dark = theme === 'dark';
    root.dataset.theme = dark ? 'dark' : 'light';
    root.style.colorScheme = dark ? 'dark' : 'light';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#142129' : '#e7edf0');
    const toggle = document.getElementById('themeToggle');
    if (toggle) {
      const label = `Switch to ${dark ? 'light' : 'dark'} mode`;
      toggle.setAttribute('aria-label', label);
      toggle.setAttribute('aria-pressed', String(dark));
      toggle.title = label;
    }
  }

  apply(saved === 'dark' || saved === 'light' ? saved : media?.matches ? 'dark' : 'light');

  document.addEventListener('DOMContentLoaded', () => {
    apply(root.dataset.theme);
    document.getElementById('themeToggle')?.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      apply(next);
      try { localStorage.setItem(key, next); } catch {}
    });
  });

  media?.addEventListener?.('change', event => {
    let preference = null;
    try { preference = localStorage.getItem(key); } catch {}
    if (preference !== 'dark' && preference !== 'light') apply(event.matches ? 'dark' : 'light');
  });
})();
