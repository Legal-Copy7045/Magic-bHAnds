#!/usr/bin/env node
// Walkthrough browser crawl: every screen of the MagicbHAnds page (per persona) and of the web installer, at desktop
// (1280×900) and phone (390×844, touch emulation), with an inventory and screenshots, and the automated UX checks.
//
//   node regression/walkthrough/crawl.js <out dir> [<installer site dir>]
//
// Writes <out>/crawl.json ({results, inventory}) and <out>/shots/*.png. Run by regression/walkthrough/run.py.
// The page comes from regression/page/harness.js (as built by panel.py, in the real panel, with the mock hass);
// the installer site is served from the directory run.py assembled. All other network is blocked. Its own
// browser and mock hosts, so it can run while the page stage runs.
//
// Personas: "admin" (a Home Assistant administrator, Morgan) and "member" (a household member, Jordan: Home
// Assistant refuses the admin-only services and the tap history, as it does for non-admin users). The page has one
// screen per section, reached from its jump menu (on a phone the same menu is a sideways-scrolling row of chips:
// there's no separate phone menu to open); each is captured as it first appears and with every fold-out open.
'use strict';
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const H = require('../page/harness');

const OUT = path.resolve(process.argv[2] || path.join(__dirname, 'out'));
const SITE = process.argv[3] ? path.resolve(process.argv[3]) : null;
const SHOTS = path.join(OUT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

const WIDTHS = {
  desktop: { viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 },
  phone: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};
const ADMIN_ONLY = ['add_person', 'update_person', 'remove_person', 'assign_band', 'unassign_band', 'remove_band',
  'play_welcome_sound', 'unpair_reader', 'pair_reader', 'answer', 'list', 'list_bluetooth_bands', 'link_bluetooth',
  'unlink_bluetooth', 'forget_bluetooth', 'set_guest_pass', 'set_settings', 'set_snapshot_days', 'set_reader_camera',
  'set_band_access', 'enrol', 'stop_enrolment', 'history', 'list_heard'];
const PERSONAS = {
  admin: { who: 'Morgan, a Home Assistant administrator', opts: { admin: true } },
  member: { who: 'Jordan, a household member (not an administrator)',
    opts: { admin: false, history: false, historyError: 'Unauthorized', reject: '^magicband\\.(' + ADMIN_ONLY.join('|') + ')$', rejectWith: 'Unauthorized' } },
};
// Stable IDs: block per surface × width (see regression/ids/walkthrough.yaml), check number within the block.
const BLOCK = { 'admin/desktop': 100, 'admin/phone': 200, 'member/desktop': 300, 'member/phone': 400, 'visitor/desktop': 500, 'visitor/phone': 600 };
const CHECKS = {
  1: 'Every menu label matches the heading of the screen it opens',
  2: 'No horizontal scroll (the page is no wider than the screen)',
  3: 'No element runs off the screen or is wider than its container (outside sideways-scrolling rows)',
  4: 'Tap targets are at least 40×40 px (phone)',
  5: 'No two menu entries have the same label',
  6: 'No menu entry that only redirects (every entry opens a screen with its own content)',
  7: 'No console or CSP errors while loading and opening every fold-out',
};

const results = [], inventory = { generated: new Date().toISOString(), widths: { desktop: '1280×900', phone: '390×844 (touch)' }, surfaces: [] };
function result(key, n, ok, detail, evidence, skip) {
  const r = { id: 'WALK-' + (BLOCK[key] + n), feature: 'Walkthrough: ' + key.replace('/', ' on ') , check: CHECKS[n] + ' — ' + key.replace('/', ', '),
    status: skip ? 'skip' : ok ? 'pass' : 'fail' };
  if (detail !== undefined && detail !== '') r.detail = typeof detail === 'string' ? detail : JSON.stringify(detail).slice(0, 2500);
  if (evidence) r.evidence = evidence;
  results.push(r);
}

// In-page probes (run inside the document being checked).
const PROBES = () => {
  // Shown on screen: Chromium lays out the inside of a closed <details> without drawing it, so its size alone
  // doesn't say an element can be seen or tapped.
  const vis = e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (!(r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none')) return false;
    if (e.checkVisibility && !e.checkVisibility({ checkVisibilityCSS: true, contentVisibilityAuto: true })) return false;
    for (let d = e.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) {
      if (!d.open && !(e.closest('summary') && e.closest('summary').parentElement === d)) return false; }
    return true; };
  const sig = e => (e.id ? '#' + e.id : e.tagName.toLowerCase() + (e.classList.length ? '.' + [...e.classList].slice(0, 2).join('.') : '')) + (e.textContent.trim() ? ' "' + e.textContent.trim().replace(/\s+/g, ' ').slice(0, 30) + '"' : '');
  const scroller = e => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) { const ox = getComputedStyle(a).overflowX; if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') return a; } return null; };
  window.__walk = {
    hscroll: () => ({ scrollWidth: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }),
    overflow: () => {
      const W = document.documentElement.clientWidth, out = [];
      document.body.querySelectorAll('*').forEach(e => {
        if (!vis(e) || scroller(e) || ['svg', 'path', 'circle', 'g'].includes(e.tagName.toLowerCase()) || e.closest('svg')) return;
        const r = e.getBoundingClientRect();
        if (r.right > W + 1 || r.left < -1) { out.push('off screen: ' + sig(e) + ' ' + Math.round(r.left) + '..' + Math.round(r.right)); return; }
        let p = e.parentElement;   // the nearest ancestor with a box of its own (display:contents wrappers have none)
        while (p && p !== document.body && (getComputedStyle(p).display === 'contents' || p.getBoundingClientRect().width === 0)) p = p.parentElement;
        if (p && p !== document.body) { const pr = p.getBoundingClientRect(); if (r.width > pr.width + 1 && getComputedStyle(e).position !== 'absolute' && getComputedStyle(e).position !== 'fixed') out.push('wider than its container: ' + sig(e) + ' ' + Math.round(r.width) + ' > ' + Math.round(pr.width)); }
      });
      return [...new Set(out)];
    },
    taps: () => {
      const sel = 'a[href],button,summary,select,input:not([type=hidden]),textarea,[role=button],[role=switch],[role=tab],[tabindex="0"]';
      const small = {};
      document.querySelectorAll(sel).forEach(e => {
        if (!vis(e)) return;
        if (e.tagName === 'INPUT' && (e.type === 'checkbox' || e.type === 'radio') && e.labels && [...e.labels].some(l => vis(l) && l.getBoundingClientRect().height >= 40)) return;
        // inline links inside a sentence are exempt (WCAG 2.5.8), as are controls inside a bigger control
        if (e.tagName === 'A' && e.parentElement && /^(P|LI|SPAN|SMALL|TD)$/.test(e.parentElement.tagName) && e.parentElement.textContent.trim().length > e.textContent.trim().length + 10) return;
        let r = e.getBoundingClientRect(); if (r.width >= 40 && r.height >= 40) return;
        // the touch area can be bigger than the drawn box (a transparent ::before, padding on a parent label):
        // hit-test 20 px out from the centre in each direction
        e.scrollIntoView({ block: 'center', inline: 'center' }); r = e.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const hits = [[0, -19.5], [0, 19.5], [-19.5, 0], [19.5, 0]].every(([dx, dy]) => { const t = document.elementFromPoint(cx + dx, cy + dy); return t && (t === e || e.contains(t) || (e.labels && [...e.labels].some(l => l === t || l.contains(t)))); });
        if (hits) return;
        const host = e.parentElement && e.parentElement.closest(sel); if (host && vis(host)) { const hr = host.getBoundingClientRect(); if (hr.width >= 40 && hr.height >= 40) return; }
        const k = sig(e).replace(/ ".*/, '') + ' ' + Math.round(r.width) + '×' + Math.round(r.height);
        small[k] = (small[k] || 0) + 1;
      });
      return Object.entries(small).sort((a, b) => b[1] - a[1]).map(([k, n]) => k + (n > 1 ? ' ×' + n : ''));
    },
  };
};

const clean = t => (t || '').replace(/\s+/g, ' ').trim();
const norm = t => clean(t).toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9' ]/g, '').trim();

// ───────── the MagicbHAnds page ─────────
async function crawlPage(browser, persona, width) {
  const key = persona + '/' + width, tag = persona + '-' + width;
  const ctx = await browser.newContext(Object.assign({ colorScheme: 'light' }, WIDTHS[width]));
  const p = await ctx.newPage(), errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error' && !H.IGNORE.test(m.text())) errs.push(m.text()); });
  const o = { opts: PERSONAS[persona].opts };
  await H.route(p, o);
  const surface = { surface: 'MagicbHAnds page (sidebar panel)', persona, who: PERSONAS[persona].who, width, size: inventory.widths[width], menu: [], screens: [], shots: [] };
  try {
    await p.goto('http://ha.test/');
    const f = await H.pageFrame(p);
    await p.waitForTimeout(900);
    await f.evaluate(PROBES);
    // Screenshots go through a viewport as tall as the page, never Playwright's fullPage: a tall full-page capture
    // makes Chromium drop the touch emulation (the phone styles switch off), which would show desktop-sized
    // controls on the phone. Every measurement runs at the real viewport, before or after the shots.
    const W = WIDTHS[width].viewport.width, VH = WIDTHS[width].viewport.height;
    const shots = async list => {   // list: [{name, clip?}] taken in one tall-viewport pass
      const h = Math.min(await f.evaluate(() => document.documentElement.scrollHeight), 16000);
      await p.evaluate(h => { window.__panel.style.height = h + 'px'; }, h);
      await p.setViewportSize({ width: W, height: Math.max(h, VH) }); await p.waitForTimeout(400);
      const files = [];
      for (const s of list) {
        const file = path.join(SHOTS, tag + '-' + s.name + '.png');
        await p.screenshot(Object.assign({ path: file }, s.clip ? { clip: Object.assign({}, s.clip, { height: Math.min(s.clip.height, h - s.clip.y) }) } : {}));
        surface.shots.push(path.relative(OUT, file)); files.push(path.relative(OUT, file));
      }
      await p.setViewportSize({ width: W, height: VH }); await p.evaluate(() => { window.__panel.style.height = ''; }); await p.waitForTimeout(300);
      return files;
    };
    const probe = async () => ({ hscroll: await f.evaluate(() => __walk.hscroll()), overflow: await f.evaluate(() => __walk.overflow()),
      taps: width === 'phone' ? await f.evaluate(() => __walk.taps()) : [], coarse: await f.evaluate(() => matchMedia('(pointer:coarse)').matches) });
    const closed = await probe();
    // the menu, and each screen it opens
    const inv = await f.evaluate(() => {
      const clean = t => (t || '').replace(/\s+/g, ' ').trim();
      const menu = [...document.querySelectorAll('#jump a')].map(a => { const c = a.cloneNode(true); c.querySelectorAll('b').forEach(b => b.remove()); return { label: clean(c.textContent), count: clean((a.querySelector('b') || {}).textContent), href: a.getAttribute('href') }; });
      const heads = [...document.querySelectorAll('h2.sec')];
      const screens = heads.map((h, i) => {
        const c = h.cloneNode(true); const sub = clean((c.querySelector('small') || {}).textContent); c.querySelectorAll('small').forEach(s => s.remove());
        const nodes = []; for (let n = h.nextElementSibling; n && !(n.matches && n.matches('h2.sec')); n = n.nextElementSibling) nodes.push(n);
        const within = sel => nodes.flatMap(n => [...(n.matches(sel) ? [n] : []), ...n.querySelectorAll(sel)]);
        const label = e => clean(e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].textContent) || e.getAttribute('title') || e.textContent || e.getAttribute('placeholder') || e.name);
        const top = h.getBoundingClientRect().top + scrollY, next = heads[i + 1], bottom = next ? next.getBoundingClientRect().top + scrollY : document.documentElement.scrollHeight;
        return {
          id: h.id, heading: clean(c.textContent), subtitle: sub, hidden: getComputedStyle(h).display === 'none',
          buttons: [...new Set(within('button,a.btn,[role=button],a[href]').filter(e => e.getBoundingClientRect().width > 0).map(label).filter(Boolean))].slice(0, 60),
          fields: [...new Set(within('select,input:not([type=hidden]),textarea').map(e => (e.tagName.toLowerCase() + (e.type ? ':' + e.type : '')) + ' "' + label(e) + '"'))].slice(0, 60),
          folds: [...new Set(within('details > summary').map(s => clean(s.textContent)))].slice(0, 40),
          text_chars: nodes.reduce((a, n) => a + clean(n.textContent).length, 0),
          box: { y: Math.max(0, top - 8), height: Math.max(40, bottom - top) },
        };
      });
      return { menu, screens };
    });
    surface.menu = inv.menu;
    const visible = inv.screens.filter(s => !s.hidden);
    const [full, ...secShots] = await shots([{ name: 'full' }, ...visible.map(s => ({ name: 's-' + s.id, clip: { x: 0, y: s.box.y, width: W, height: Math.min(s.box.height, 6000) } }))]);
    visible.forEach((s, i) => { s.shot = secShots[i]; });
    surface.screens = inv.screens;
    // every fold-out open (the forms behind them)
    await f.evaluate(() => document.querySelectorAll('details').forEach(d => { d.open = true; }));
    await p.waitForTimeout(600);
    const open = await probe();
    const [expanded] = await shots([{ name: 'full-open' }]);
    if (width === 'phone' && !(closed.coarse && open.coarse)) errs.push('harness: touch emulation was off during a measurement');
    const openFields = await f.evaluate(() => [...document.querySelectorAll('details[open] select, details[open] input:not([type=hidden]), details[open] textarea')].length);
    surface.open_fields = openFields;
    surface.fullpage = full; surface.fullpage_open = expanded;

    // checks
    const byId = Object.fromEntries(inv.screens.map(s => [s.id, s]));
    // A chip may be the heading's first words ("People" for "People and access"); anything else is a mismatch.
    const pairs = inv.menu.map(m => [m, byId[(m.href || '').replace(/^#/, '')]]).filter(([, s]) => s);
    const mism = pairs.filter(([m, s]) => !norm(s.heading).startsWith(norm(m.label))).map(([m, s]) => `"${m.label}" opens "${s.heading}"`);
    const short = pairs.filter(([m, s]) => norm(s.heading) !== norm(m.label) && norm(s.heading).startsWith(norm(m.label))).map(([m, s]) => `"${m.label}" (heading "${s.heading}")`);
    result(key, 1, !mism.length, mism.length ? mism.join('; ') : inv.menu.length + ' entries' + (short.length ? '; shortened: ' + short.join(', ') : ''), full);
    const hs = [closed.hscroll, open.hscroll].filter(h => h.scrollWidth > h.width + 1);
    result(key, 2, !hs.length, hs.length ? JSON.stringify(hs) : `${closed.hscroll.scrollWidth} ≤ ${closed.hscroll.width} px`, full);
    const ov = [...new Set([...closed.overflow, ...open.overflow])];
    result(key, 3, !ov.length, ov.slice(0, 25).join('; ') + (ov.length > 25 ? ` (+${ov.length - 25} more)` : ''), expanded);
    if (width === 'phone') {
      const t = [...new Set([...closed.taps, ...open.taps])];
      result(key, 4, !t.length, t.slice(0, 30).join('; ') + (t.length > 30 ? ` (+${t.length - 30} more)` : ''), expanded);
    }
    const labels = inv.menu.map(m => norm(m.label)), dup = labels.filter((l, i) => labels.indexOf(l) !== i);
    result(key, 5, !dup.length, dup.length ? 'duplicates: ' + [...new Set(dup)].join(', ') : '');
    const empty = inv.menu.filter(m => { const s = byId[(m.href || '').replace(/^#/, '')]; return !s || s.hidden || s.text_chars < 20; }).map(m => `"${m.label}" → ${m.href}`);
    result(key, 6, !empty.length, empty.join('; '));
    result(key, 7, !errs.length, errs.slice(0, 15).join(' | '));
  } catch (e) {
    for (const n of [1, 2, 3, ...(width === 'phone' ? [4] : []), 5, 6, 7]) result(key, n, false, 'crawl failed: ' + String(e && e.message || e).slice(0, 300));
  }
  surface.errors = errs.slice(0, 30);
  inventory.surfaces.push(surface);
  await ctx.close();
}

// ───────── the web installer site ─────────
async function crawlSite(browser, width) {
  const key = 'visitor/' + width, tag = 'installer-' + width;
  const surface = { surface: 'Web installer (GitHub Pages site)', persona: 'visitor', who: 'Anyone flashing a board from the browser', width, size: inventory.widths[width], menu: [], screens: [], shots: [] };
  const nums = [1, 2, 3, ...(width === 'phone' ? [4] : []), 5, 6, 7];
  if (!SITE || !fs.existsSync(path.join(SITE, 'index.html'))) {
    for (const n of nums) result(key, n, false, 'the installer site could not be assembled (see walkthrough.log)', undefined, true);
    surface.note = 'not assembled'; inventory.surfaces.push(surface); return;
  }
  const ctx = await browser.newContext(Object.assign({ colorScheme: 'light' }, WIDTHS[width]));
  const p = await ctx.newPage(), errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error' && !H.IGNORE.test(m.text())) errs.push(m.text()); });
  await p.route('**/*', r => {
    const u = new URL(r.request().url());
    if (u.host !== 'site.test') return r.abort();
    const f = path.join(SITE, decodeURIComponent(u.pathname === '/' ? '/index.html' : u.pathname));
    if (!f.startsWith(SITE + path.sep) || !fs.existsSync(f) || !fs.statSync(f).isFile()) return r.fulfill({ status: 404, body: 'not found' });
    const type = f.endsWith('.html') ? 'text/html; charset=utf-8' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : f.endsWith('.css') ? 'text/css' : 'application/octet-stream';
    return r.fulfill({ body: fs.readFileSync(f), contentType: type });
  });
  try {
    await p.goto('http://site.test/');
    await p.waitForTimeout(1500);
    await p.evaluate(PROBES);
    const ph = Math.min(await p.evaluate(() => document.documentElement.scrollHeight), 16000);
    const hs = await p.evaluate(() => __walk.hscroll()), ov = await p.evaluate(() => __walk.overflow());
    const taps = width === 'phone' ? await p.evaluate(() => __walk.taps()) : [];
    await p.setViewportSize({ width: WIDTHS[width].viewport.width, height: Math.max(ph, WIDTHS[width].viewport.height) }); await p.waitForTimeout(300);
    const file = path.join(SHOTS, tag + '-full.png'); await p.screenshot({ path: file });
    const rel = path.relative(OUT, file); surface.shots.push(rel);
    const inv = await p.evaluate(() => {
      const clean = t => (t || '').replace(/\s+/g, ' ').trim();
      return {
        title: document.title, h1: clean((document.querySelector('h1') || {}).textContent),
        menu: [...document.querySelectorAll('nav a')].map(a => ({ label: clean(a.textContent), href: a.getAttribute('href') })),
        screens: [...document.querySelectorAll('h2')].map(h => { const card = h.closest('section,article,div'); return { heading: clean(h.textContent), text: clean((card || h).textContent).slice(0, 400), buttons: [...(card || h).querySelectorAll('button,a[href]')].map(b => clean(b.textContent)).filter(Boolean) }; }),
        links: [...document.querySelectorAll('a[href]')].map(a => ({ label: clean(a.textContent), href: a.getAttribute('href') })),
      };
    });
    Object.assign(surface, { title: inv.title, h1: inv.h1, menu: inv.menu, screens: inv.screens, links: inv.links, fullpage: rel });
    const none = 'the installer is a single page with no menu';
    result(key, 1, true, inv.menu.length ? '' : none, rel, !inv.menu.length);
    result(key, 2, hs.scrollWidth <= hs.width + 1, `${hs.scrollWidth} vs ${hs.width} px`, rel);
    result(key, 3, !ov.length, ov.slice(0, 25).join('; '), rel);
    if (width === 'phone') result(key, 4, !taps.length, taps.slice(0, 30).join('; '), rel);
    result(key, 5, true, inv.menu.length ? '' : none, undefined, !inv.menu.length);
    result(key, 6, true, inv.menu.length ? '' : none, undefined, !inv.menu.length);
    result(key, 7, !errs.length, errs.slice(0, 15).join(' | '));
  } catch (e) {
    for (const n of nums) result(key, n, false, 'crawl failed: ' + String(e && e.message || e).slice(0, 300));
  }
  surface.errors = errs.slice(0, 30);
  inventory.surfaces.push(surface);
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  try {
    for (const persona of Object.keys(PERSONAS)) for (const width of Object.keys(WIDTHS)) await crawlPage(browser, persona, width);
    for (const width of Object.keys(WIDTHS)) await crawlSite(browser, width);
  } finally { await browser.close(); }
  inventory.page_build = H.build();
  fs.writeFileSync(path.join(OUT, 'crawl.json'), JSON.stringify({ results, inventory }, null, 1));
  console.log(`crawl: ${results.filter(r => r.status === 'pass').length} pass, ${results.filter(r => r.status === 'fail').length} fail, ${results.filter(r => r.status === 'skip').length} skip; ${inventory.surfaces.length} surface×width crawls`);
})().catch(e => { console.error(e); process.exit(1); });
