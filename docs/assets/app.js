/* Read-only GitHub head freshness. Never fetch the DrivenData leaderboard. */
(() => {
  const rows = Array.from(document.querySelectorAll('tr[data-repo][data-ref]'));
  const summary = document.getElementById('feed-state');
  if (!rows.length || !summary || !window.fetch) return;
  let changed = 0, failed = 0;
  const update = async row => {
    const label = row.querySelector('.freshness');
    const repo = row.dataset.repo;
    // The markup is generated from a fixed pinned manifest, not arbitrary URLs.
    if (!/^buffedlizard55-lab\/GEMSDOE\d+$/.test(repo)) {
      label.textContent = 'Freshness unavailable'; label.dataset.state = 'failed'; failed++; return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/commits/main`, {
        headers: {'Accept': 'application/vnd.github+json'}, signal: controller.signal, credentials: 'omit'
      });
      if (!response.ok) throw new Error(`GitHub ${response.status}`);
      const data = await response.json();
      if (typeof data.sha !== 'string' || !/^[0-9a-f]{40}$/.test(data.sha)) throw new Error('Invalid response');
      const same = data.sha === row.dataset.ref;
      label.dataset.state = same ? 'same' : 'changed';
      label.textContent = same ? 'Head matches pinned audit' : 'Head changed since pinned audit';
      if (!same) changed++;
    } catch (_) {
      label.textContent = 'Head check unavailable'; label.dataset.state = 'failed'; failed++;
    } finally { clearTimeout(timer); }
  };
  Promise.all(rows.map(update)).then(() => {
    if (failed) summary.textContent = `GitHub freshness: ${failed} unavailable; ${changed} changed`;
    else summary.textContent = `GitHub freshness: ${changed} of ${rows.length} heads changed`;
  });
})();
