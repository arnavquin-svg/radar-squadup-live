/* Private progress page for event hosts. The token lives in the URL fragment (#t=...),
   which browsers never send to servers or in Referer headers. */
(() => {
  'use strict';

  const TOKEN_RE = /^[A-Za-z0-9_-]{32,64}$/;
  const REFRESH_MS = 30000;
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (n) => Number(n || 0).toLocaleString('en-IN');
  const fmtDate = (iso) => {
    if (!iso) return '';
    const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  };

  function tokenFrom(text) {
    const m = String(text || '').match(/(?:#|[?&])t=([A-Za-z0-9_-]{32,64})/);
    if (m) return m[1];
    const raw = String(text || '').trim();
    return TOKEN_RE.test(raw) ? raw : null;
  }

  let timer = null;

  function ask(message = '') {
    $('#progress').classList.add('hidden');
    $('#ask').classList.remove('hidden');
    $('#ask-error').textContent = message;
  }

  async function load(token) {
    let res;
    try {
      res = await fetch('/api/requests/status', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ token }), cache: 'no-store', credentials: 'same-origin',
      });
    } catch {
      ask("Can't reach the server. Check your connection and try again.");
      return;
    }
    if (res.status === 404 || res.status === 422) { ask("That link doesn't match any request. Check you copied all of it."); return; }
    if (res.status === 429) { ask('Too many checks from this network. Try again in a while.'); return; }
    if (!res.ok) { ask('Something went wrong. Please try again shortly.'); return; }
    render(await res.json());
    clearTimeout(timer);
    if (!document.hidden) timer = setTimeout(() => load(token), REFRESH_MS);
  }

  function render(d) {
    $('#ask').classList.add('hidden');
    $('#progress').classList.remove('hidden');
    $('#p-ref').textContent = `Reference ${d.reference}`;
    $('#p-title').innerHTML = `${esc(d.event.event_name)}`;
    $('#p-meta').textContent = [d.event.organisation, d.event.city, fmtDate(d.event.start_date), d.event.venue].filter(Boolean).join(', ');

    const p = d.progress;
    const stages = [
      ['Received', true],
      [d.status === 'declined' ? 'Not taken on' : 'Accepted', d.status !== 'new'],
      ['Groups contacted', !!(p && p.groups_contacted)],
      ['Sign-ups arriving', !!(p && p.registrations)],
    ];
    const currentIndex = stages.findIndex(([, done]) => !done);
    $('#p-timeline').innerHTML = stages.map(([label, done], i) => {
      const cls = d.status === 'declined' && i === 1 ? 'stop' : done ? 'done' : i === currentIndex ? 'now' : '';
      return `<li class="${cls}">${esc(label)}</li>`;
    }).join('');

    const body = $('#p-body');
    if (d.status === 'new') {
      body.innerHTML = `<h2 class="display display-md">We're <em>reviewing</em> your event.</h2>
        <p class="muted">We'll email you if we need anything. Once we take it on, this page shows the groups we contact and the people signing up.</p>`;
    } else if (d.status === 'declined') {
      body.innerHTML = `<h2 class="display display-md">We can't take this one on.</h2>
        ${d.decision_note ? `<p>${esc(d.decision_note)}</p>` : ''}
        <p class="muted">You're welcome to submit another event at any time.</p>
        <div class="hero-actions"><a class="btn btn-primary" href="/submit/">Submit another event</a></div>`;
    } else {
      const n = p || {};
      body.innerHTML = `<h2 class="display display-md">Reach is <em>underway.</em></h2>
        <p class="muted">Numbers update on their own every 30 seconds.</p>
        <div class="numbers">
          <div><b class="num">${fmt(n.groups_found)}</b><span>Groups that fit your event</span></div>
          <div><b class="num">${fmt(n.groups_contacted)}</b><span>Group admins contacted</span></div>
          <div><b class="num">${fmt(n.link_clicks)}</b><span>Link clicks</span></div>
          <div><b class="num">${fmt(n.registrations)}</b><span>People registered</span></div>
          <div><b class="num">${fmt(n.confirmed)}</b><span>Confirmed they're coming</span></div>
          <div><b class="num">${fmt(n.full_teams)}<span class="muted"> / ${fmt(n.teams)}</span></b><span>Full teams of four</span></div>
        </div>`;
    }
  }

  $('#ask-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const token = tokenFrom($('#ask-link').value);
    if (!token) { $('#ask-error').textContent = 'Paste the whole link, including the part after #t='; return; }
    history.replaceState(null, '', `/track/#t=${token}`);
    load(token);
  });

  document.addEventListener('visibilitychange', () => {
    const token = tokenFrom(location.hash);
    if (!document.hidden && token && !$('#progress').classList.contains('hidden')) load(token);
  });

  const initial = tokenFrom(location.hash);
  if (initial) load(initial); else ask();
})();
