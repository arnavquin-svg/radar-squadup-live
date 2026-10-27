/* RadiUp.ai — shared interaction layer for every page.
   Adds: hover lift + cursor glow on boxes, scroll reveals with stagger, scroll-linked fact cards,
   count-up numbers, a reading-progress line and a nav that firms up on scroll.
   Pure progressive enhancement: no content depends on it, and it stays still for reduced-motion users. */
(() => {
  'use strict';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // ------------------------------------------------------------------ splash: once per browser session
  const splash = document.getElementById('splash');
  let splashDelay = 0;
  if (splash) {
    let seen = false;
    try { seen = sessionStorage.getItem('radiup.splash') === '1'; sessionStorage.setItem('radiup.splash', '1'); } catch { /* storage off */ }
    if (seen || reduceMotion) {
      splash.classList.add('skip');
    } else {
      splashDelay = 1700;  // let the hero animate in as the splash lifts
      const done = () => splash.classList.add('skip');
      splash.addEventListener('animationend', (e) => { if (e.animationName === 'splash-out') done(); });
      splash.addEventListener('click', done);
      document.addEventListener('keydown', done, { once: true });
    }
  }

  const LIFT = '.fact, .step, .panel, .stat, .team, .request, .form-card, .numbers > div, .signin .card, .phone';
  const REVEAL = [
    '.hero .kicker', '.hero h1', '.hero .lede', '.hero .hero-actions', '.fact',
    '.where .platform', '.section-head', '.section .display', '.section .lede', '.step',
    '.promises li', '.phone .bubble', '.phone .mini-buttons', '.cta .display', '.cta .lede', '.cta .hero-actions',
    '.page .kicker', '.page .display', '.page .lede', '.next-steps li', '.page .form-card',
  ].join(', ');

  // ------------------------------------------------------------------ lift + glow (works on content added later too)
  function enhanceBoxes(root = document) {
    $$(LIFT, root).forEach(el => {
      if (el.dataset.enhanced) return;
      el.dataset.enhanced = '1';
      el.classList.add('lift');
      if (!finePointer) return;
      el.classList.add('spot');
      el.addEventListener('pointermove', (e) => {
        const r = el.getBoundingClientRect();
        el.style.setProperty('--mx', `${e.clientX - r.left}px`);
        el.style.setProperty('--my', `${e.clientY - r.top}px`);
      });
      el.addEventListener('pointerleave', () => {
        el.style.setProperty('--mx', '-999px');
        el.style.setProperty('--my', '-999px');
      });
    });
  }
  enhanceBoxes();
  // The desk renders cards after loading data; enhance them as they appear.
  new MutationObserver(() => enhanceBoxes()).observe(document.body, { childList: true, subtree: true });

  // ------------------------------------------------------------------ nav + progress line
  const nav = document.querySelector('.nav');
  const line = document.createElement('div');
  line.className = 'progress-line';
  line.setAttribute('aria-hidden', 'true');
  document.body.appendChild(line);

  const factRow = document.querySelector('.fact-row');
  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      nav?.classList.toggle('scrolled', doc.scrollTop > 24);
      line.style.transform = `scaleX(${max > 0 ? Math.min(1, doc.scrollTop / max) : 0})`;
      if (factRow && !reduceMotion) {
        // 0 when the cards first come into view, 1 when they reach the upper third of the screen.
        const r = factRow.getBoundingClientRect();
        const vh = window.innerHeight;
        const s = Math.max(0, Math.min(1, (vh - r.top) / (vh * 0.75)));
        factRow.style.setProperty('--s', s.toFixed(3));
      }
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  onScroll();

  if (reduceMotion) return;
  document.documentElement.classList.add('motion');

  // ------------------------------------------------------------------ count-up numbers
  function countUp(el) {
    const match = el.textContent.match(/^(\D*)(\d[\d,]*)(.*)$/s);
    if (!match) return;
    const [, before, digits, after] = match;
    const target = Number(digits.replace(/,/g, ''));
    if (!Number.isFinite(target) || target === 0) return;
    const start = performance.now();
    const duration = Math.min(1400, 500 + target * 40);
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = `${before}${Math.round(target * eased).toLocaleString('en-IN')}${after}`;
      if (t < 1) requestAnimationFrame(step);
    };
    el.textContent = `${before}0${after}`;
    requestAnimationFrame(step);
  }

  // ------------------------------------------------------------------ scroll reveals with sibling stagger
  const targets = $$(REVEAL);
  const seen = new Map();
  targets.forEach(el => {
    const parent = el.parentElement;
    const index = seen.get(parent) || 0;
    seen.set(parent, index + 1);
    const extra = el.closest('.hero') ? splashDelay : 0;
    el.style.setProperty('--d', `${extra + Math.min(index, 6) * 90}ms`);
    el.classList.add('reveal');
  });
  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      el.classList.add('in');
      io.unobserve(el);
      const big = el.matches('.fact') ? el.querySelector('.big') : null;
      if (big) setTimeout(() => countUp(big), 150);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
  targets.forEach(el => io.observe(el));
})();
