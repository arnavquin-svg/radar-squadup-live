/* RadiUp.ai organiser desk.
   No frameworks, no inline handlers, no inline styles: compatible with a strict Content-Security-Policy.
   Everything rendered from data goes through esc(). */
(() => {
  'use strict';

  const KEY_STORE = 'radar.desk.key';
  const POLL_MS = 6000;
  const ROLES = [
    { id: 'developer', label: 'Developer' },
    { id: 'designer', label: 'Designer' },
    { id: 'domain_expert', label: 'Domain expert' },
    { id: 'presenter', label: 'Presenter' },
  ];
  const ROLE = Object.fromEntries(ROLES.map(r => [r.id, r]));
  const THEMES = [['ai', 'AI'], ['hackathon', 'Hackathons'], ['beginner', 'Beginner-friendly'], ['robotics', 'Robotics'], ['web', 'Web dev'],
                  ['data', 'Data'], ['design', 'Design'], ['science', 'Science'], ['startup', 'Startups'], ['cultural', 'Culture'],
                  ['social-impact', 'Social impact'], ['gaming', 'Gaming'], ['cybersecurity', 'Cybersecurity']];
  const PLATFORM = { whatsapp: 'WhatsApp', telegram: 'Telegram', instagram: 'Instagram', discord: 'Discord', other: 'Other' };
  const LANG = { en: 'English', hi: 'Hindi', mr: 'Marathi' };
  const VIEWS = ['requests', 'overview', 'radar', 'outreach', 'squads'];
  const EVENT_VIEWS = ['overview', 'radar', 'outreach', 'squads'];

  const state = {
    config: null, events: [], eventId: null, event: null, ranking: null, outreach: [], filter: 'pending', selected: null,
    stats: null, teams: [], highlight: null, sigs: {}, pollTimer: null,
    requests: [], rfilter: 'new', declining: null,
  };

  // ------------------------------------------------------------------ helpers
  const $ = (s, el = document) => el.querySelector(s);
  // Clear a field's error as soon as the person edits it.
  document.addEventListener('input', (e) => {
    const name = e.target?.name; const form = e.target?.form;
    if (!name || !form) return;
    e.target.removeAttribute('aria-invalid');
    const slot = form.querySelector(`[data-error-for="${name === 'tag' || name === 'extra_tags' ? 'tags' : name === 'lang' ? 'languages' : name}"]`);
    if (slot) slot.textContent = '';
  });

  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (n) => Number(n || 0).toLocaleString('en-IN');
  const fmtDate = (iso) => {
    if (!iso) return '';
    const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  };
  const ago = (ts) => {
    const d = new Date(`${String(ts).replace(' ', 'T')}Z`);
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (!Number.isFinite(s)) return '';
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
    return `${Math.floor(s / 86400)} d ago`;
  };
  const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const clicks = (n) => `${fmt(n)} ${Number(n) === 1 ? 'click' : 'clicks'}`;
  const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

  const session = {
    get() { try { return sessionStorage.getItem(KEY_STORE); } catch { return null; } },
    set(v) { try { sessionStorage.setItem(KEY_STORE, v); } catch { /* private mode: key lives in memory only */ } memoryKey = v; },
    clear() { try { sessionStorage.removeItem(KEY_STORE); } catch { /* ignore */ } memoryKey = null; },
  };
  let memoryKey = null;
  const currentKey = () => session.get() || memoryKey;

  class ApiError extends Error {
    constructor(status, message, errors = []) { super(message); this.status = status; this.errors = errors; }
  }

  async function api(path, { method = 'GET', body } = {}) {
    const headers = { Accept: 'application/json' };
    const key = currentKey();
    if (key) headers.Authorization = `Bearer ${key}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res;
    try {
      res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin', cache: 'no-store' });
    } catch {
      throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
    }
    if (res.status === 204) return null;
    let data = {};
    try { data = await res.json(); } catch { /* non-JSON error page */ }
    if (res.status === 401) {
      signOut('That access key was not accepted. Sign in again.');
      throw new ApiError(401, 'Signed out');
    }
    if (res.status === 429) throw new ApiError(429, data.detail || 'Too many requests. Wait a moment and try again.');
    if (!res.ok) throw new ApiError(res.status, data.detail || `Request failed (${res.status}).`, data.errors || []);
    return data;
  }

  function toast(message, kind = 'ok') {
    const el = document.createElement('div');
    el.className = 'toast';
    el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    el.innerHTML = `<i class="${kind === 'error' ? 'bg-tomato' : kind === 'info' ? 'bg-marigold' : 'bg-leaf'}"></i><span>${esc(message)}</span>`;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), kind === 'error' ? 7000 : 3500);
  }
  const fail = (e) => { if (!(e instanceof ApiError && e.status === 401)) toast(e.message || 'Something went wrong.', 'error'); };

  function busy(btn, on, label) {
    if (!btn) return;
    if (on) {
      btn.dataset.label = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner" aria-hidden="true"></span>${esc(label || 'Working…')}`;
    } else {
      btn.disabled = false;
      if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
    }
  }

  async function copyText(text, what) {
    try { await navigator.clipboard.writeText(text); toast(`${what} copied`); }
    catch { toast(`Couldn't copy automatically. Select the ${what.toLowerCase()} and copy it by hand.`, 'error'); }
  }

  /** Bars are sized after render through the CSSOM (allowed by CSP, unlike style="" attributes). */
  function applyBars(root = document) {
    $$('[data-w]', root).forEach(el => { el.style.width = `${Math.max(0, Math.min(100, Number(el.dataset.w) || 0))}%`; });
  }

  // ------------------------------------------------------------------ validation (mirrors the server)
  const INVISIBLE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏‪-‮⁠-⁤⁦-⁩﻿]/g;
  const cleanLine = (v) => String(v ?? '').normalize('NFC').replace(/[\r\n\t]+/g, ' ').replace(INVISIBLE, '').replace(/ {2,}/g, ' ').trim();
  const cleanBlock = (v) => String(v ?? '').normalize('NFC').replace(/\r\n?/g, '\n').replace(/\t/g, ' ').replace(INVISIBLE, '')
    .split('\n').map(l => l.trimEnd()).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  const hasLetter = (v) => /\p{L}/u.test(v);
  const TAG_RE = /^[a-z0-9][a-z0-9 -]{0,29}$/;

  function checkLine(value, min, max, letter = true) {
    const v = cleanLine(value);
    if (v.length < min) return min <= 1 ? 'This is required.' : `Use at least ${min} characters.`;
    if (v.length > max) return `Use at most ${max} characters.`;
    if (/[<>]/.test(v)) return 'Remove the < and > characters.';
    if (v && letter && !hasLetter(v)) return 'Include at least one letter.';
    return '';
  }

  function parseTags(raw) {
    return cleanLine(raw).split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
  }

  function setErrors(form, errors) {
    $$('[data-error-for]', form).forEach(el => { el.textContent = ''; });
    $$('[aria-invalid]', form).forEach(el => el.removeAttribute('aria-invalid'));
    const box = $('.form-error', form);
    box?.classList.add('hidden');
    let first = null;
    Object.entries(errors).forEach(([field, msg]) => {
      const slot = $(`[data-error-for="${field}"]`, form);
      const input = $(`[name="${field}"]`, form);
      if (slot) slot.textContent = msg;
      if (input) { input.setAttribute('aria-invalid', 'true'); first = first || input; }
      if (!slot && box) { box.textContent = msg; box.classList.remove('hidden'); }
    });
    first?.focus();
    return Object.keys(errors).length === 0;
  }

  function serverErrors(form, err) {
    if (err instanceof ApiError && err.status === 422 && err.errors.length) {
      const map = {};
      err.errors.forEach(e => { map[String(e.field).split('.')[0]] = e.message; });
      setErrors(form, map);
    } else {
      const box = $('.form-error', form);
      if (box) { box.textContent = err.message; box.classList.remove('hidden'); } else fail(err);
    }
  }

  // ------------------------------------------------------------------ sign in / out
  function showSignin(message = '') {
    stopPolling();
    $('#desk').classList.add('hidden');
    $('#signin').classList.remove('hidden');
    $('#signin-error').textContent = message;
    $('#access-key').value = '';
    $('#access-key').focus();
  }

  function signOut(message = '') {
    session.clear();
    $$('dialog[open]').forEach(d => d.close());
    showSignin(message);
  }

  $('#signin-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#access-key');
    const key = input.value.trim();
    if (key.length < 8 || key.length > 256) {
      $('#signin-error').textContent = 'Enter the full access key.';
      input.setAttribute('aria-invalid', 'true');
      return;
    }
    input.removeAttribute('aria-invalid');
    const btn = $('#signin-btn');
    busy(btn, true, 'Checking…');
    try {
      const res = await fetch('/api/config', { headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' }, cache: 'no-store' });
      if (res.status === 401) { $('#signin-error').textContent = "That key didn't work. Check it and try again."; return; }
      if (res.status === 429) { $('#signin-error').textContent = 'Too many attempts from this network. Try again in 15 minutes.'; return; }
      if (!res.ok) { $('#signin-error').textContent = 'The server had a problem. Try again shortly.'; return; }
      session.set(key);
      state.config = await res.json();
      enterDesk();
    } catch {
      $('#signin-error').textContent = "Can't reach the server. Check your connection.";
    } finally {
      busy(btn, false);
    }
  });

  $('#signout').addEventListener('click', () => signOut());

  async function enterDesk() {
    $('#signin').classList.add('hidden');
    $('#desk').classList.remove('hidden');
    $('#btn-simulate').classList.toggle('hidden', !state.config?.simulator_enabled);
    updateNewCount();
    await loadEvents();
    startPolling();
  }

  // ------------------------------------------------------------------ navigation
  function currentView() {
    const v = location.hash.replace('#', '');
    return VIEWS.includes(v) ? v : 'overview';
  }

  function show(view = currentView()) {
    const needsEvent = EVENT_VIEWS.includes(view);
    const target = needsEvent && !state.eventId ? 'empty' : view;
    $$('.view').forEach(s => s.classList.toggle('hidden', s.id !== `view-${target}`));
    $$('.nav-links [data-view]').forEach(b => {
      const on = b.dataset.view === target;
      b.setAttribute('aria-selected', String(on));
      b.setAttribute('aria-current', on ? 'page' : 'false');
      b.disabled = EVENT_VIEWS.includes(b.dataset.view) && !state.eventId;
    });
    $('#event-bar').classList.toggle('hidden', !state.events.length || target === 'requests');
    if (target === 'requests') loadRequests().catch(fail);
    else if (state.eventId) refresh(view);
  }

  function refresh(view) {
    const jobs = {
      overview: () => loadStats(),
      radar: () => (state.ranking ? Promise.resolve(renderRadar(false)) : loadRanking()),
      outreach: () => loadOutreach(),
      squads: () => Promise.all([loadTeams(), loadStats()]),
    };
    (jobs[view] || jobs.overview)().catch(fail);
  }

  $$('.nav-links [data-view]').forEach(b => b.addEventListener('click', () => {
    if (location.hash === `#${b.dataset.view}`) show(b.dataset.view);
    else location.hash = b.dataset.view;
  }));
  addEventListener('hashchange', () => { if (!$('#desk').classList.contains('hidden')) show(); });

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      if (document.hidden) return;
      const view = currentView();
      updateNewCount();
      if (view === 'requests') loadRequests().catch(() => {});
      if (!state.eventId) return;
      if (view === 'overview') loadStats().catch(() => {});
      if (view === 'squads') Promise.all([loadTeams(), loadStats()]).catch(() => {});
    }, POLL_MS);
  }
  function stopPolling() { if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; }

  // ------------------------------------------------------------------ events
  async function loadEvents(selectId) {
    state.events = await api('/api/events');
    const sel = $('#event-select');
    if (!state.events.length) {
      state.eventId = null; state.event = null;
      sel.innerHTML = '';
      show();
      return;
    }
    sel.innerHTML = state.events.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join('');
    let saved = null;
    try { saved = Number(sessionStorage.getItem('radar.desk.event')); } catch { /* ignore */ }
    const id = selectId || (state.events.some(e => e.id === saved) ? saved : state.events[0].id);
    await selectEvent(id);
  }

  async function selectEvent(id) {
    state.eventId = Number(id);
    try { sessionStorage.setItem('radar.desk.event', String(id)); } catch { /* ignore */ }
    $('#event-select').value = String(id);
    state.event = await api(`/api/events/${state.eventId}`);
    Object.assign(state, { ranking: null, outreach: [], selected: null, stats: null, teams: [], highlight: null, sigs: {} });
    const e = state.event;
    $('#event-meta').textContent = [e.city, fmtDate(e.start_date), e.venue].filter(Boolean).join(', ');
    updatePendingCount();
    show();
  }

  $('#event-select').addEventListener('change', e => selectEvent(e.target.value).catch(fail));

  async function updatePendingCount() {
    try {
      const list = await api(`/api/events/${state.eventId}/outreach?status=pending`);
      $('#pending-count').textContent = list.length ? list.length : '';
    } catch { /* best effort */ }
  }

  // ------------------------------------------------------------------ overview
  async function loadStats() {
    const stats = await api(`/api/events/${state.eventId}/stats`);
    state.stats = stats;
    const sig = JSON.stringify(stats);
    if (state.sigs.stats === sig) return;
    state.sigs.stats = sig;
    renderOverview();
    renderSquadSummary();
  }

  function ledgerRow(label, value, width, colorClass, note = '') {
    return `<li><span class="truncate">${label}</span><span class="bar"><span class="${colorClass}" data-w="${width}"></span></span>
      <span class="value num">${fmt(value)}${note ? `<small>${esc(note)}</small>` : ''}</span></li>`;
  }

  function renderOverview() {
    const s = state.stats; if (!s) return;
    const k = s.kpis;
    $('#stats').innerHTML = `
      <article class="stat"><div class="big num">${fmt(k.registrations)}</div><div class="label">Registered</div>
        <div class="note">${k.withdrawn ? `${fmt(k.withdrawn)} gave up their seat` : 'Nobody has dropped out'}</div></article>
      <article class="stat"><div class="big num">${fmt(k.confirmed)}</div><div class="label">Confirmed they're coming</div>
        <div class="note">${pct(k.confirmed, k.registrations)}% of registrations</div></article>
      <article class="stat"><div class="big num">${fmt(k.full_teams)}<span class="muted"> / ${fmt(k.teams)}</span></div><div class="label">Full squads</div>
        <div class="note">${fmt(k.open_seats)} open seats</div></article>`;

    const [drafts, approved, clicks, regs, conf] = s.funnel.map(f => f.value);
    const notes = ['', drafts ? `${pct(approved, drafts)}% of drafts` : '', approved ? `${(clicks / approved).toFixed(1)} per link` : '',
                   clicks ? `${pct(regs, clicks)}% of clicks` : '', regs ? `${pct(conf, regs)}% of registered` : ''];
    const colors = ['bg-muted', 'bg-marigold', 'bg-tomato', 'bg-sky', 'bg-leaf'];
    const max = Math.max(1, ...s.funnel.map(f => f.value));
    $('#funnel').innerHTML = s.funnel.map((f, i) => ledgerRow(esc(f.stage), f.value, (f.value / max) * 100, colors[i], notes[i])).join('');
    $('#funnel-note').textContent = k.synthetic
      ? `Includes ${fmt(k.synthetic)} sample sign-ups, marked as synthetic in the data.`
      : 'From written drafts to confirmed attendance.';

    const srcMax = Math.max(1, ...s.by_source.map(x => x.registrations));
    $('#sources').innerHTML = s.by_source.length
      ? s.by_source.slice(0, 8).map(x => ledgerRow(esc(x.label), x.registrations, (x.registrations / srcMax) * 100,
          x.platform === 'referral' ? 'bg-marigold' : x.platform === 'direct' ? 'bg-muted' : 'bg-sky',
          x.clicks != null ? clicks(x.clicks) : '')).join('')
      : '<li class="empty">No approved messages yet. Approve one in Outreach and send it to the admin; sign-ups through it appear here.</li>';

    const total = Object.values(s.roles).reduce((a, b) => a + b, 0);
    $('#roles').innerHTML = ROLES.map(r => ledgerRow(esc(r.label), s.roles[r.id] || 0, total ? ((s.roles[r.id] || 0) / total) * 100 : 0, `dot-${r.id}`)).join('');

    $('#recent').innerHTML = s.recent.length ? s.recent.map(p => {
      const source = p.via_referral ? 'invited by a teammate' : p.source ? `via ${esc(p.source)}` : 'direct';
      const tag = p.status === 'confirmed' ? '<span class="tag ok">Confirmed</span>'
        : p.status === 'withdrawn' ? '<span class="tag off">Left</span>' : '<span class="tag wait">Registered</span>';
      return `<li class="row"><span class="avatar role-${esc(p.role)}">${esc(p.first_name.slice(0, 1).toUpperCase())}</span>
        <span class="grow"><span class="truncate">${esc(p.name)} <span class="muted">${esc(ROLE[p.role]?.label || '')}${p.team_number ? `, Team ${p.team_number}` : ''}</span></span>
        <span class="muted truncate">${source}, ${esc(ago(p.created_at))}</span></span>${tag}</li>`;
    }).join('') : '<li class="empty">Nobody yet. Once an approved link is shared, people register in Telegram and show up here.</li>';
    applyBars($('#view-overview'));
  }

  // ------------------------------------------------------------------ radar
  async function loadRanking() {
    state.ranking = await api(`/api/events/${state.eventId}/radar`);
    renderRadar(false);
  }

  $('#btn-run-radar').addEventListener('click', runRadar);
  async function runRadar() {
    const btn = $('#btn-run-radar');
    busy(btn, true, 'Scanning…');
    try {
      const data = await api(`/api/events/${state.eventId}/radar/run`, { method: 'POST', body: { limit: 12 } });
      state.ranking = data;
      renderRadar(true);
      toast(`${data.drafts_created} new messages drafted for review${data.drafts_refreshed ? `, ${data.drafts_refreshed} refreshed` : ''}.`);
      updatePendingCount();
    } catch (e) { fail(e); } finally { busy(btn, false); }
  }

  function renderRadar() {
    const d = state.ranking; if (!d) return;
    const p = d.profile;
    $('#profile').innerHTML = `
      <div><dt>Topics</dt><dd>${p.theme_labels.map(t => `<span class="chip">${esc(t)}</span>`).join('') || '<span class="muted">None found. Add topics to the event.</span>'}</dd></div>
      <div><dt>Level</dt><dd>${esc(p.skill_level.charAt(0).toUpperCase() + p.skill_level.slice(1))}</dd></div>
      <div><dt>City</dt><dd>${esc(p.city)}</dd></div>
      <div><dt>Drafts in</dt><dd>${p.languages.map(l => esc(LANG[l] || l)).join(', ')}</dd></div>`;
    $('#scanned').textContent = `${d.ranking.length} of ${d.scanned} groups in the directory qualify.`;
    $('#formula').textContent = d.formula || 'Score = 22 × topic overlaps + 25 (if local) + size factor (up to 15)';
    renderScope(d.ranking);
    $('#ranking').innerHTML = d.ranking.length ? d.ranking.map(r => {
      const c = r.community;
      return `<li data-cid="${c.id}" tabindex="0">
        <span class="rank">${r.rank}</span>
        <div><div class="name">${esc(c.name)}</div>
          <div class="meta">${esc(PLATFORM[c.platform] || c.platform)}, ${fmt(c.size)} members${r.is_local ? '' : `, ${esc(c.city)}`}</div>
          <div class="why">${esc(r.rationale)}</div>
          ${c.discovered_via === 'squadup_referral' ? '<span class="chip found"><span class="swatch leaf"></span>Found through SquadUp</span>' : ''}</div>
        <div class="score num">${Math.round(r.score)}<small>fit score</small></div></li>`;
    }).join('') : `<li class="empty">No group shares a topic with this event or is based in ${esc(state.event.city)}. Add topics to the event, or add the groups you know.</li>`;
    $$('#ranking li[data-cid]').forEach(li => {
      const pick = () => highlight(Number(li.dataset.cid));
      li.addEventListener('click', pick);
      li.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    });
  }

  function renderScope(ranking) {
    const C = 180, R = 160;
    const scores = ranking.map(r => r.score);
    const hi = scores.length ? Math.max(...scores) : 1;
    const lo = scores.length ? Math.min(...scores) : 0;
    const rings = [R, R * 0.66, R * 0.33].map((r, i) => `<circle cx="${C}" cy="${C}" r="${r}" fill="${i ? 'none' : '#FFFFFF'}" stroke="${i ? '#E2D9C7' : '#221C14'}" stroke-width="${i ? 1 : 1.5}" />`).join('');
    const blips = ranking.map((r, i) => {
      const rel = hi === lo ? 1 : (r.score - lo) / (hi - lo);
      const dist = 24 + (1 - rel) * (R - 44);
      const ang = ((i * 137.508) + 20) * Math.PI / 180;
      const x = (C + dist * Math.cos(ang)).toFixed(1);
      const y = (C + dist * Math.sin(ang)).toFixed(1);
      const size = (4.5 + (r.size_factor / 15) * 5).toFixed(1);
      return `<g class="blip" data-cid="${r.community.id}" tabindex="0" role="button" aria-label="${esc(r.community.name)}, fit score ${Math.round(r.score)}">
        <title>${esc(r.community.name)}: ${Math.round(r.score)}</title>
        <circle cx="${x}" cy="${y}" r="${size}" fill="${r.is_local ? '#F2542D' : '#2F9BFF'}" />
        ${i < 3 ? `<text x="${x}" y="${(Number(y) - Number(size) - 5).toFixed(1)}" text-anchor="middle" font-size="12" font-family="Instrument Serif, serif" font-style="italic" fill="#221C14">${i + 1}</text>` : ''}</g>`;
    }).join('');
    $('#scope').innerHTML = `${rings}
      <line x1="${C - R}" y1="${C}" x2="${C + R}" y2="${C}" stroke="#E2D9C7" />
      <line x1="${C}" y1="${C - R}" x2="${C}" y2="${C + R}" stroke="#E2D9C7" />
      <path d="M${C} ${C} L${C} ${C - R} A${R} ${R} 0 0 1 ${(C + R * Math.sin(0.9)).toFixed(1)} ${(C - R * Math.cos(0.9)).toFixed(1)} Z" fill="#FFB627" opacity=".28" />
      <circle cx="${C}" cy="${C}" r="4" fill="#221C14" />
      ${ranking.length ? blips : `<text x="${C}" y="${C + 34}" text-anchor="middle" font-size="14" fill="#6F6556">No matching groups yet</text>`}`;
    $$('#scope .blip').forEach(g => {
      const pick = () => { highlight(Number(g.dataset.cid)); $(`#ranking li[data-cid="${g.dataset.cid}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); };
      g.addEventListener('click', pick);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    });
  }

  function highlight(cid) {
    state.highlight = state.highlight === cid ? null : cid;
    $$('#scope .blip').forEach(g => g.classList.toggle('dim', state.highlight !== null && Number(g.dataset.cid) !== state.highlight));
    $$('#ranking li[data-cid]').forEach(li => li.classList.toggle('hl', Number(li.dataset.cid) === state.highlight));
  }

  // ------------------------------------------------------------------ outreach
  async function loadOutreach() {
    state.outreach = await api(`/api/events/${state.eventId}/outreach`);
    renderOutreach();
  }

  $$('#outreach-filter [data-filter]').forEach(b => b.addEventListener('click', () => {
    state.filter = b.dataset.filter; state.selected = null; renderOutreach();
  }));

  function renderOutreach() {
    const counts = { pending: 0, approved: 0, rejected: 0 };
    state.outreach.forEach(o => { counts[o.status] += 1; });
    $$('[data-count]').forEach(el => { el.textContent = counts[el.dataset.count] || ''; });
    $('#pending-count').textContent = counts.pending || '';
    $$('#outreach-filter [data-filter]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.filter === state.filter)));

    const list = state.filter === 'all' ? state.outreach : state.outreach.filter(o => o.status === state.filter);
    if (!list.some(o => o.id === state.selected)) state.selected = list[0]?.id ?? null;
    const dot = { pending: 'bg-marigold', approved: 'bg-leaf', rejected: 'bg-muted' };
    $('#letters').innerHTML = list.length ? list.map(o => `
      <li><button data-oid="${o.id}" aria-current="${o.id === state.selected}">
        <span class="status-dot ${dot[o.status]}" aria-hidden="true"></span>
        <span><span class="name">${esc(o.community_name)}</span><br /><span class="meta">${esc(o.language_name)}, ${esc(PLATFORM[o.platform] || o.platform)}${o.status === 'approved' ? `, ${clicks(o.clicks)}` : ''}</span></span>
        <span class="score-sm num">${Math.round(o.score)}</span></button></li>`).join('')
      : `<li class="empty">${state.outreach.length ? 'Nothing in this list.' : 'No messages yet. Run Radar to draft one for each matching group.'}</li>`;
    $$('#letters [data-oid]').forEach(b => b.addEventListener('click', () => { state.selected = Number(b.dataset.oid); renderOutreach(); }));
    renderEditor();
  }

  function renderEditor() {
    const box = $('#editor');
    const o = state.outreach.find(x => x.id === state.selected);
    if (!o) {
      box.innerHTML = state.outreach.length
        ? '<p class="empty">Choose a message on the left to review it.</p>'
        : '<h3>No drafts yet</h3><p class="empty">Radar writes one message per matching group, in the language its admin reads.</p><button class="btn btn-primary" id="ed-run">Run Radar</button>';
      $('#ed-run')?.addEventListener('click', () => { location.hash = 'radar'; runRadar(); });
      return;
    }
    const approved = o.status === 'approved';
    const tag = { pending: '<span class="tag wait">Waiting for your review</span>', approved: '<span class="tag ok">Approved, link is live</span>', rejected: '<span class="tag off">Skipped</span>' }[o.status];
    box.innerHTML = `
      ${tag}
      <h3>${esc(o.community_name)}</h3>
      <p class="muted">${o.admin_name ? `For ${esc(o.admin_name)}, the admin. ` : 'For the group admin. '}${esc(o.rationale)}</p>
      <div class="lang-row" role="group" aria-label="Message language">
        ${Object.entries(LANG).map(([code, name]) => `<button type="button" data-lang="${code}" aria-pressed="${code === o.language}" ${approved ? 'disabled' : ''}>${name}</button>`).join('')}
        ${o.edited ? '<span class="muted">Edited by you</span>' : ''}
      </div>
      <label class="sr-only" for="ed-draft">Message</label>
      <textarea class="field" id="ed-draft" rows="13" maxlength="4000" ${approved ? 'readonly' : ''}>${esc(o.draft)}</textarea>
      <span class="field-error" id="ed-error" role="alert"></span>
      <div class="link-box ${approved ? 'live' : ''}">
        <div class="grow"><div class="sub">Tracked link for this group</div><code>${esc(o.link)}</code></div>
        ${approved ? '<button class="btn btn-paper btn-sm" id="ed-copy-link">Copy link</button><button class="btn btn-primary btn-sm" id="ed-copy-msg">Copy message</button>'
                   : '<span class="muted">Unlocks after approval</span>'}
      </div>
      <div class="editor-actions">
        ${approved
          ? `<span class="left">${clicks(o.clicks)} so far</span><button class="btn btn-quiet" id="ed-reset">Move back to review</button>`
          : `${o.status === 'rejected' ? '<button class="btn btn-quiet" id="ed-reset">Move back to review</button>' : '<button class="btn btn-danger" id="ed-reject">Skip this group</button>'}
             <button class="btn btn-paper" id="ed-save" disabled>Save edits</button>
             <button class="btn btn-primary" id="ed-approve">Approve message</button>`}
      </div>`;

    const ta = $('#ed-draft');
    ta.addEventListener('input', () => { const s = $('#ed-save'); if (s) s.disabled = cleanBlock(ta.value) === o.draft; $('#ed-error').textContent = ''; });
    $$('#editor [data-lang]').forEach(b => b.addEventListener('click', async () => {
      if (b.dataset.lang === o.language) return;
      if ((o.edited || cleanBlock(ta.value) !== o.draft) && !window.confirm('Switching language rewrites the message and discards your edits. Continue?')) return;
      try { replaceOutreach(await api(`/api/outreach/${o.id}`, { method: 'PATCH', body: { language: b.dataset.lang } })); toast(`Rewritten in ${LANG[b.dataset.lang]}`); }
      catch (err) { fail(err); }
    }));
    $('#ed-save')?.addEventListener('click', () => saveDraft(o).then(() => toast('Edits saved')).catch(() => {}));
    $('#ed-approve')?.addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      const text = cleanBlock(ta.value);
      if (!text.includes(o.link)) { $('#ed-error').textContent = 'Keep the tracked link in the message, or sign-ups from this group won’t be counted.'; ta.focus(); return; }
      busy(btn, true, 'Approving…');
      try {
        if (text !== o.draft) await saveDraft(o);
        replaceOutreach(await api(`/api/outreach/${o.id}/approve`, { method: 'POST' }));
        toast('Approved. Copy the message and send it to the admin yourself.');
      } catch (err) { if (!(err instanceof ApiError && err.status === 422)) fail(err); busy(btn, false); }
    });
    $('#ed-reject')?.addEventListener('click', async () => { try { replaceOutreach(await api(`/api/outreach/${o.id}/reject`, { method: 'POST' })); toast('Skipped', 'info'); } catch (err) { fail(err); } });
    $('#ed-reset')?.addEventListener('click', async () => { try { replaceOutreach(await api(`/api/outreach/${o.id}/reset`, { method: 'POST' })); toast('Moved back to review', 'info'); } catch (err) { fail(err); } });
    $('#ed-copy-link')?.addEventListener('click', () => copyText(o.link, 'Link'));
    $('#ed-copy-msg')?.addEventListener('click', () => copyText(o.draft, 'Message'));
  }

  async function saveDraft(o) {
    const text = cleanBlock($('#ed-draft').value);
    const err = text.length < 10 ? 'The message needs at least a sentence.' : text.length > 4000 ? 'Keep the message under 4,000 characters.' : '';
    if (err) { $('#ed-error').textContent = err; throw new Error(err); }
    try {
      const updated = await api(`/api/outreach/${o.id}`, { method: 'PATCH', body: { draft: text } });
      replaceOutreach(updated, true);
      return updated;
    } catch (e) {
      $('#ed-error').textContent = e.message;
      throw e;
    }
  }

  function replaceOutreach(updated, keepFilter) {
    state.outreach = state.outreach.map(o => (o.id === updated.id ? updated : o));
    if (!keepFilter && state.filter !== 'all' && updated.status !== state.filter) state.filter = updated.status;
    state.selected = updated.id;
    renderOutreach();
  }

  // ------------------------------------------------------------------ squads
  async function loadTeams() {
    const teams = await api(`/api/events/${state.eventId}/teams`);
    const sig = JSON.stringify(teams);
    state.teams = teams;
    if (state.sigs.teams === sig) return;
    state.sigs.teams = sig;
    renderTeams();
  }

  function renderSquadSummary() {
    const k = state.stats?.kpis; if (!k) return;
    $('#squad-summary').innerHTML = `
      <div><b class="num">${fmt(k.teams)}</b>squads</div>
      <div><b class="num">${fmt(k.full_teams)}</b>complete</div>
      <div><b class="num">${fmt(k.open_seats)}</b>open seats</div>
      <div><b class="num">${fmt(k.via_referral)}</b>brought by a teammate</div>`;
  }

  function teamText(t) {
    const lines = [`Team ${t.number}: ${t.filled}/${t.size} filled`];
    ROLES.forEach(r => {
      const ms = t.members.filter(m => m.role === r.id);
      if (ms.length) ms.forEach(m => lines.push(`${r.label}: ${m.first_name}`));
      else if (!t.is_full) lines.push(`${r.label}: open seat`);
    });
    lines.push('', t.is_full ? 'Squad complete' : `Looking for: ${t.missing_role_labels.join(', ')}`, `Event: ${t.event_name}`);
    return lines.join('\n');
  }

  function renderTeams() {
    const box = $('#teams');
    if (!state.teams.length) {
      box.innerHTML = '<p class="empty">No squads yet. They form as people register through the Telegram bot or as walk-ins.</p>';
      return;
    }
    box.innerHTML = state.teams.map(t => {
      const byRole = {};
      t.members.forEach(m => { (byRole[m.role] ||= []).push(m); });
      const seats = [];
      ROLES.forEach(r => (byRole[r.id] || []).forEach(m => seats.push({ r, m })));
      ROLES.forEach(r => { if (!byRole[r.id] && seats.length < t.size) seats.push({ r, m: null }); });
      while (seats.length < t.size) seats.push({ r: null, m: null });
      return `<article class="team ${t.is_full ? 'full' : ''}">
        <header><h3>Team ${t.number}</h3><span class="fill num">${t.filled}/${t.size}</span></header>
        <p class="needs ${t.is_full ? 'full-note' : ''}">${t.is_full ? 'Complete' : `Looking for ${esc(t.missing_role_labels.map(x => x.toLowerCase()).join(', '))}`}</p>
        <ul class="seats">${seats.map(({ r, m }) => (m
          ? `<li class="role-${r.id}"><div class="role">${esc(r.label)}</div><div class="who">${esc(m.first_name)}${m.confirmed ? ' <span class="muted">✓</span>' : ''}</div></li>`
          : `<li class="open"><div class="role">${r ? esc(r.label) : 'Any role'}</div><div class="who">Open seat</div></li>`)).join('')}</ul>
        <footer><span>${t.confirmed} of ${t.filled} confirmed</span><button class="btn btn-quiet btn-sm" data-copy-team="${t.team_id}">Copy card</button></footer>
      </article>`;
    }).join('');
    $$('[data-copy-team]', box).forEach(b => b.addEventListener('click', () => {
      const t = state.teams.find(x => x.team_id === Number(b.dataset.copyTeam));
      if (t) copyText(teamText(t), 'Team card');
    }));
  }

  $('#btn-simulate').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true, 'Adding…');
    try {
      const r = await api(`/api/events/${state.eventId}/simulate`, { method: 'POST', body: { count: 12 } });
      toast(`${r.created} sample sign-ups added. They're marked as synthetic in the data.`, 'info');
      await Promise.all([loadTeams(), loadStats()]);
    } catch (err) { fail(err); } finally { busy(btn, false); }
  });

  // ------------------------------------------------------------------ requests from hosts
  async function updateNewCount() {
    try {
      const fresh = await api('/api/requests?status=new');
      $('#new-count').textContent = fresh.length || '';
    } catch { /* best effort */ }
  }

  async function loadRequests() {
    const list = await api('/api/requests');
    const sig = JSON.stringify(list);
    state.requests = list;
    if (state.sigs.requests === sig) return;
    state.sigs.requests = sig;
    renderRequests();
  }

  $$('#request-filter [data-rfilter]').forEach(b => b.addEventListener('click', () => { state.rfilter = b.dataset.rfilter; renderRequests(); }));

  function renderRequests() {
    const counts = { new: 0, accepted: 0, declined: 0 };
    state.requests.forEach(r => { counts[r.status] += 1; });
    $$('[data-rcount]').forEach(el => { el.textContent = counts[el.dataset.rcount] || ''; });
    $('#new-count').textContent = counts.new || '';
    $$('#request-filter [data-rfilter]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.rfilter === state.rfilter)));
    const list = state.rfilter === 'all' ? state.requests : state.requests.filter(r => r.status === state.rfilter);
    const box = $('#requests');
    if (!list.length) {
      box.innerHTML = `<p class="empty">${state.requests.length ? 'Nothing in this list.' : 'No requests yet. Share your website’s “Submit your event” page with event hosts; their requests land here.'}</p>`;
      return;
    }
    const tagFor = { new: '<span class="tag wait">New</span>', accepted: '<span class="tag ok">Accepted</span>', declined: '<span class="tag off">Declined</span>' };
    box.innerHTML = list.map(r => `
      <article class="request ${r.status === 'new' ? 'is-new' : ''}">
        <div>
          ${tagFor[r.status]} <span class="muted">${esc(r.reference)}, sent ${esc(ago(r.created_at))}</span>
          <h3>${esc(r.event_name)}</h3>
          <div class="facts">${esc([r.organisation, r.city, fmtDate(r.start_date), r.venue].filter(Boolean).join(', '))}${r.expected_participants ? `, about ${fmt(r.expected_participants)} people` : ''}</div>
          <p class="desc">${esc(r.description)}</p>
          ${r.tags?.length ? `<div class="chips">${r.tags.map(t => `<span class="chip">${esc(t)}</span>`).join('')}</div>` : ''}
          ${r.status === 'declined' && r.decision_note ? `<p class="muted">Note sent: ${esc(r.decision_note)}</p>` : ''}
        </div>
        <div>
          <div class="contact">
            <strong>${esc(r.contact_name)}</strong>
            <a href="mailto:${esc(r.contact_email)}">${esc(r.contact_email)}</a>
            ${r.contact_phone ? `<a href="tel:${esc(r.contact_phone.replace(/[^0-9+]/g, ''))}">${esc(r.contact_phone)}</a>` : ''}
          </div>
          <div class="actions">
            ${r.status === 'new' ? `<button class="btn btn-primary btn-sm" data-accept="${r.id}">Accept and create event</button>
                                    <button class="btn btn-danger btn-sm" data-decline="${r.id}">Decline</button>` : ''}
            ${r.status === 'accepted' && r.event_id ? `<button class="btn btn-paper btn-sm" data-open-event="${r.event_id}">Open event</button>` : ''}
          </div>
        </div>
      </article>`).join('');
    $$('[data-accept]', box).forEach(b => b.addEventListener('click', () => acceptRequest(Number(b.dataset.accept), b)));
    $$('[data-decline]', box).forEach(b => b.addEventListener('click', () => { state.declining = Number(b.dataset.decline); openDialog('#dlg-decline'); }));
    $$('[data-open-event]', box).forEach(b => b.addEventListener('click', async () => {
      location.hash = 'radar';
      await loadEvents(Number(b.dataset.openEvent)).catch(fail);
    }));
  }

  async function acceptRequest(id, btn) {
    busy(btn, true, 'Creating event…');
    try {
      const res = await api(`/api/requests/${id}/accept`, { method: 'POST' });
      toast(`Accepted ${res.request.reference}. Running Radar on it now.`);
      state.sigs.requests = null;
      updateNewCount();
      location.hash = 'radar';
      await loadEvents(res.event_id);
      await runRadar();
    } catch (e) { fail(e); busy(btn, false); }
  }

  $('#form-decline').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const note = cleanLine($('#decline-note').value);
    const err = checkLine(note, 0, 500, false);
    if (!setErrors(form, err ? { note: err } : {})) return;
    const btn = $('button[type="submit"]', form);
    busy(btn, true, 'Declining…');
    try {
      await api(`/api/requests/${state.declining}/decline`, { method: 'POST', body: { note } });
      $('#dlg-decline').close();
      toast('Request declined. The host will see your note on their tracking page.', 'info');
      state.sigs.requests = null;
      await loadRequests();
      updateNewCount();
    } catch (err2) { serverErrors(form, err2); } finally { busy(btn, false); }
  });

  // ------------------------------------------------------------------ dialogs
  function openDialog(id) {
    const d = $(id);
    const form = $('form', d);
    form.reset();
    setErrors(form, {});
    d.showModal();
    $('input, select, textarea', d)?.focus();
  }
  $$('dialog [data-close]').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
  $$('dialog').forEach(d => d.addEventListener('click', e => { if (e.target === d) d.close(); }));

  $('#tag-picker').innerHTML = THEMES.map(([id, label]) => `<label class="check-chip"><input type="checkbox" name="tag" value="${id}" /><span>${label}</span></label>`).join('');
  $('#walkin-roles').innerHTML = ROLES.map((r, i) => `<label class="check-chip"><input type="radio" name="role" value="${r.id}" ${i === 0 ? 'checked' : ''} /><span>${r.label}</span></label>`).join('');

  $('#btn-new-event').addEventListener('click', () => {
    const today = new Date();
    const later = new Date(); later.setFullYear(today.getFullYear() + 3);
    $('#ev-date').min = isoDate(today);
    $('#ev-date').max = isoDate(later);
    openDialog('#dlg-event');
  });
  document.addEventListener('click', e => { if (e.target.closest('[data-action="new-event"]')) $('#btn-new-event').click(); });
  $('#btn-add-community').addEventListener('click', () => openDialog('#dlg-community'));
  $('#btn-walkin').addEventListener('click', () => openDialog('#dlg-walkin'));

  $('#form-event').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const errors = {};
    const name = checkLine(f.get('name'), 3, 120); if (name) errors.name = name;
    const city = checkLine(f.get('city'), 2, 60); if (city) errors.city = city;
    const venue = checkLine(f.get('venue'), 0, 160, false); if (venue) errors.venue = venue;
    const description = cleanBlock(f.get('description'));
    if (description.length > 2000) errors.description = 'Use at most 2,000 characters.';
    const date = String(f.get('start_date') || '');
    if (date) {
      if (date < $('#ev-date').min) errors.start_date = 'Pick today or a later date.';
      else if (date > $('#ev-date').max) errors.start_date = 'Pick a date within the next three years.';
    }
    const tags = [...new Set([...f.getAll('tag'), ...parseTags(f.get('extra_tags'))])];
    if (tags.length > 15) errors.tags = 'Pick at most 15 topics.';
    else if (tags.some(t => !TAG_RE.test(t))) errors.tags = 'Topics can use lowercase letters, numbers, spaces and hyphens (30 characters max).';
    if (!setErrors(form, errors)) return;

    const btn = $('button[type="submit"]', form);
    busy(btn, true, 'Creating…');
    try {
      const ev = await api('/api/events', { method: 'POST', body: {
        name: cleanLine(f.get('name')), city: cleanLine(f.get('city')), venue: cleanLine(f.get('venue')), description, tags, start_date: date || null,
      } });
      $('#dlg-event').close();
      location.hash = 'radar';
      await loadEvents(ev.id);
      await runRadar();
    } catch (err) { serverErrors(form, err); } finally { busy(btn, false); }
  });

  $('#form-community').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const errors = {};
    const name = checkLine(f.get('name'), 3, 120); if (name) errors.name = name;
    const city = checkLine(f.get('city'), 2, 60); if (city) errors.city = city;
    const admin = checkLine(f.get('admin_name'), 0, 60); if (admin) errors.admin_name = admin;
    const size = Number(f.get('size'));
    if (!Number.isInteger(size) || size < 1 || size > 10_000_000) errors.size = 'Enter a whole number between 1 and 10,000,000.';
    const tags = [...new Set(parseTags(f.get('tags')))];
    if (tags.length > 12) errors.tags = 'Use at most 12 topics.';
    else if (tags.some(t => !TAG_RE.test(t))) errors.tags = 'Topics can use lowercase letters, numbers, spaces and hyphens.';
    const languages = f.getAll('lang');
    if (!languages.length) errors.languages = 'Pick at least one language.';
    if (!setErrors(form, errors)) return;

    const btn = $('button[type="submit"]', form);
    busy(btn, true, 'Adding…');
    try {
      const body = { name: cleanLine(f.get('name')), city: cleanLine(f.get('city')), platform: f.get('platform'), size,
                     admin_name: cleanLine(f.get('admin_name')), tags, languages };
      await api('/api/communities', { method: 'POST', body });
      $('#dlg-community').close();
      toast(`${body.name} added to the directory. Run Radar again to include it.`);
      await loadRanking();
    } catch (err) { serverErrors(form, err); } finally { busy(btn, false); }
  });

  $('#form-walkin').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const errors = {};
    const name = checkLine(f.get('name'), 1, 80); if (name) errors.name = name;
    if (!ROLE[f.get('role')]) errors.role = 'Pick a role.';
    if (!setErrors(form, errors)) return;
    const btn = $('button[type="submit"]', form);
    busy(btn, true, 'Seating…');
    try {
      const p = await api('/api/register', { method: 'POST', body: { event_id: state.eventId, name: cleanLine(f.get('name')), role: f.get('role'), experience: f.get('experience') } });
      $('#dlg-walkin').close();
      toast(`${p.name} is in Team ${p.team_number}.`);
      state.sigs = {};
      await Promise.all([loadTeams(), loadStats()]);
    } catch (err) { serverErrors(form, err); } finally { busy(btn, false); }
  });

  // ------------------------------------------------------------------ boot
  async function boot() {
    const key = currentKey();
    if (!key) { showSignin(); return; }
    try {
      state.config = await api('/api/config');
      await enterDesk();
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) showSignin(e.message);
    }
  }
  boot();
})();
