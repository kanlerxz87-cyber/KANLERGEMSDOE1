(() => {
  const list = document.getElementById('source-feed-list');
  const summary = document.getElementById('source-feed-summary');
  const updated = document.getElementById('source-feed-updated');
  if (!list || !summary || !updated) return;

  const labelFor = (status) => {
    if (status === 'ok') return 'PAGE RESPONDS';
    if (status === 'login_required') return 'LOGIN REQUIRED';
    if (status === 'http_error') return 'HTTP ERROR';
    if (status === 'network_error') return 'NETWORK ERROR';
    return 'CHECK FAILED';
  };

  fetch('data/live-source-status.json', { cache: 'no-store' })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((feed) => {
      if (feed.generated_at_utc) {
        updated.textContent = `Last automated page check: ${feed.generated_at_utc} · scores are not scraped`;
      } else {
        updated.textContent = 'No automated check has been published yet; live source links remain available below.';
      }
      if (!Array.isArray(feed.sources) || feed.sources.length === 0) {
        summary.textContent = feed.status || 'No status records are available yet.';
        return;
      }
      summary.textContent = feed.purpose || 'Public source availability only.';
      for (const source of feed.sources) {
        const item = document.createElement('li');
        const link = document.createElement('a');
        link.href = source.url;
        link.textContent = source.label;
        link.rel = 'noopener noreferrer';
        const status = document.createElement('span');
        status.className = `source-status feed-${source.status || 'unknown'}`;
        status.textContent = labelFor(source.status);
        item.append(link, status);
        if (source.note) {
          const note = document.createElement('p');
          note.className = 'small';
          note.textContent = source.note;
          item.append(note);
        }
        list.append(item);
      }
    })
    .catch((error) => {
      updated.textContent = 'Automated feed unavailable; use the direct source links on this page.';
      summary.textContent = `Feed could not be loaded (${error.message}).`;
    });
})();
