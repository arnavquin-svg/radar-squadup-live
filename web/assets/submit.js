/* Public event request form. Validates in the browser with the same rules as the server. */
(() => {
  'use strict';

  const THEMES = [['ai', 'AI'], ['hackathon', 'Hackathons'], ['beginner', 'Beginner-friendly'], ['robotics', 'Robotics'], ['web', 'Web dev'],
                  ['data', 'Data'], ['design', 'Design'], ['science', 'Science'], ['startup', 'Startups'], ['cultural', 'Culture'],
                  ['social-impact', 'Social impact'], ['gaming', 'Gaming'], ['cybersecurity', 'Cybersecurity']];
  const INVISIBLE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏‪-‮⁠-⁤⁦-⁩﻿]/g;
  const EMAIL_RE = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;
  const PHONE_RE = /^\+?[0-9 ()-]{7,20}$/;
  const TAG_RE = /^[a-z0-9][a-z0-9 -]{0,29}$/;

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
  const cleanLine = (v) => String(v ?? '').normalize('NFC').replace(/[\r\n\t]+/g, ' ').replace(INVISIBLE, '').replace(/ {2,}/g, ' ').trim();
  const cleanBlock = (v) => String(v ?? '').normalize('NFC').replace(/\r\n?/g, '\n').replace(/\t/g, ' ').replace(INVISIBLE, '')
    .split('\n').map(l => l.trimEnd()).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  const hasLetter = (v) => /\p{L}/u.test(v);
  const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

  function checkLine(value, min, max, letter = true) {
    const v = cleanLine(value);
    if (v.length < min) return min <= 1 ? 'This is required.' : `Use at least ${min} characters.`;
    if (v.length > max) return `Use at most ${max} characters.`;
    if (/[<>]/.test(v)) return 'Remove the < and > characters.';
    if (v && letter && !hasLetter(v)) return 'Include at least one letter.';
    return '';
  }

  const form = $('#request-form');
  const dateInput = $('#start_date');
  const today = new Date();
  const later = new Date(); later.setFullYear(today.getFullYear() + 3);
  dateInput.min = isoDate(today);
  dateInput.max = isoDate(later);

  $('#tag-picker').innerHTML = THEMES.map(([id, label]) =>
    `<label class="check-chip"><input type="checkbox" name="tag" value="${id}" /><span>${label}</span></label>`).join('');

  function showErrors(errors) {
    $$('[data-error-for]', form).forEach(el => { el.textContent = ''; });
    $$('[aria-invalid]', form).forEach(el => el.removeAttribute('aria-invalid'));
    const box = $('.form-error', form);
    box.classList.add('hidden');
    let first = null;
    Object.entries(errors).forEach(([field, msg]) => {
      const slot = $(`[data-error-for="${field}"]`, form);
      const input = $(`[name="${field}"]`, form);
      if (slot) slot.textContent = msg; else { box.textContent = msg; box.classList.remove('hidden'); }
      if (input) { input.setAttribute('aria-invalid', 'true'); first = first || input; }
    });
    first?.focus();
    return !Object.keys(errors).length;
  }

  function collect() {
    const f = new FormData(form);
    const errors = {};
    const body = {
      contact_name: cleanLine(f.get('contact_name')),
      organisation: cleanLine(f.get('organisation')),
      contact_email: cleanLine(f.get('contact_email')).toLowerCase(),
      contact_phone: cleanLine(f.get('contact_phone')),
      event_name: cleanLine(f.get('event_name')),
      city: cleanLine(f.get('city')),
      start_date: String(f.get('start_date') || ''),
      venue: cleanLine(f.get('venue')),
      description: cleanBlock(f.get('description')),
      tags: [...new Set([...f.getAll('tag'), ...cleanLine(f.get('extra_tags')).split(',').map(t => t.trim().toLowerCase()).filter(Boolean)])],
      expected_participants: f.get('expected_participants') ? Number(f.get('expected_participants')) : null,
      consent: f.get('consent') === 'on',
      website: String(f.get('website') || ''),
    };
    const e1 = checkLine(body.contact_name, 2, 80); if (e1) errors.contact_name = e1;
    const e2 = checkLine(body.organisation, 2, 120); if (e2) errors.organisation = e2;
    if (!EMAIL_RE.test(body.contact_email) || body.contact_email.length > 254 || body.contact_email.includes('..')) errors.contact_email = 'Enter a valid email address.';
    if (body.contact_phone) {
      const digits = body.contact_phone.replace(/\D/g, '');
      if (!PHONE_RE.test(body.contact_phone) || digits.length < 7 || digits.length > 15) errors.contact_phone = 'Enter a valid phone number, or leave it empty.';
    }
    const e3 = checkLine(body.event_name, 3, 120); if (e3) errors.event_name = e3;
    const e4 = checkLine(body.city, 2, 60); if (e4) errors.city = e4;
    if (!body.start_date) errors.start_date = 'Pick the event date.';
    else if (body.start_date < dateInput.min) errors.start_date = 'Pick today or a later date.';
    else if (body.start_date > dateInput.max) errors.start_date = 'Pick a date within the next three years.';
    const e5 = checkLine(body.venue, 0, 160, false); if (e5) errors.venue = e5;
    if (body.expected_participants !== null && (!Number.isInteger(body.expected_participants) || body.expected_participants < 10 || body.expected_participants > 100000)) {
      errors.expected_participants = 'Enter a whole number between 10 and 100,000, or leave it empty.';
    }
    if (body.description.length < 20) errors.description = 'Describe the event in at least a sentence (20 characters).';
    else if (body.description.length > 2000) errors.description = 'Use at most 2,000 characters.';
    if (body.tags.length > 15) errors.tags = 'Pick at most 15 topics.';
    else if (body.tags.some(t => !TAG_RE.test(t))) errors.tags = 'Topics can use lowercase letters, numbers, spaces and hyphens.';
    if (!body.consent) errors.consent = 'Please tick this box so we can contact you about the event.';
    return { body, errors };
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const { body, errors } = collect();
    if (!showErrors(errors)) return;
    const btn = $('button[type="submit"]', form);
    btn.disabled = true;
    const label = btn.innerHTML;
    btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>Sending…';
    try {
      const res = await fetch('/api/requests', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body), credentials: 'same-origin', cache: 'no-store',
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 422 && Array.isArray(data.errors)) {
        const map = {};
        data.errors.forEach(er => { map[String(er.field).split('.')[0]] = er.message.charAt(0).toUpperCase() + er.message.slice(1) + '.'; });
        showErrors(map);
        return;
      }
      if (!res.ok) { showErrors({ form: data.detail || 'Something went wrong. Please try again.' }); return; }
      const link = `${location.origin}/track/#t=${data.token}`;
      $('#done-ref').textContent = data.reference;
      $('#done-link').textContent = link;
      $('#open-link').href = `/track/#t=${data.token}`;
      form.classList.add('hidden');
      const done = $('#request-done');
      done.classList.remove('hidden');
      done.focus();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      $('#copy-link').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(link); $('#copy-link').textContent = 'Copied'; }
        catch { $('#copy-link').textContent = 'Select and copy it'; }
      });
    } catch {
      showErrors({ form: "Can't reach the server. Check your connection and try again." });
    } finally {
      btn.disabled = false;
      btn.innerHTML = label;
    }
  });
})();
