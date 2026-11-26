#!/usr/bin/env node
// Regression stage "page": the MagicbHAnds management page in headless Chromium with mock Home Assistant data.
//
//   node regression/page/run.js            (writes regression/out/page.json and screenshots in regression/out/page/)
//
// The page is built exactly as custom_components/magicband/panel.py build_page() builds it (that function is run with
// python3; a JavaScript copy is the fallback), served at /api/magicband/page, and loaded by the real sidebar panel
// (frontend/panel.js) with a mock `hass` (regression/page/mock.js, knobs in __MOCK_OPTS). Every request outside the
// mock host is blocked (the page needs no three.js or echarts; Google Fonts are blocked, so the system fonts are used).
// Exit code 0 even when checks fail; non-zero only when the harness itself breaks.
'use strict';
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const MB = path.join(ROOT, 'custom_components', 'magicband'), FE = path.join(MB, 'frontend');
const OUT = path.join(ROOT, 'regression', 'out'), SHOTS = path.join(OUT, 'page');
const ONLY = process.argv.slice(2).filter(a => !a.startsWith('-'));   // optional: scenario names to run (debugging)
const started = new Date();

// ───────── the page, as panel.py builds it (shared with the walkthrough: harness.js) ─────────
const H = require('./harness');

// ───────── results ─────────
const results = [], seen = new Set();
// known page bugs, by check id: why the failure is the page's, not the harness's (added after checking each failure by hand)
const BUGS = {};
const clip = (x, n) => { let s = typeof x === 'string' ? x : JSON.stringify(x); if (s === undefined) s = String(x); return s.length > (n || 900) ? s.slice(0, n || 900) + '…' : s; };
async function chk(id, feature, check, fn, evidence) {
  if (seen.has(id)) throw new Error('duplicate check id ' + id);
  seen.add(id);
  let status, detail;
  try { const r = await fn(); const [ok, info] = Array.isArray(r) ? r : [r, undefined]; status = ok ? 'pass' : 'fail'; detail = info === undefined ? undefined : clip(info); }
  catch (e) { status = 'fail'; detail = 'harness exception: ' + clip(String((e && e.stack) || e).split('\n').slice(0, 3).join(' | ')); }
  if (status === 'fail' && BUGS[id]) detail = 'PAGE BUG: ' + BUGS[id] + (detail ? ' | seen: ' + detail : '');
  const r = { id, feature, check, status }; if (detail) r.detail = detail; if (evidence) r.evidence = evidence;
  results.push(r); console.log((status === 'pass' ? 'PASS ' : 'FAIL ') + id + ' ' + check + (status !== 'pass' && detail ? '  ' + detail.slice(0, 300) : ''));
}

// ───────── browser helpers ─────────
const IGNORE = H.IGNORE;
async function open(browser, o) {
  o = o || {};
  const ctx = await browser.newContext(Object.assign({ viewport: { width: o.width || 1400, height: o.height || 900 }, colorScheme: o.dark ? 'dark' : 'light', deviceScaleFactor: 1 },
    o.tz ? { timezoneId: o.tz } : {},
    o.touch ? { hasTouch: true, isMobile: true, deviceScaleFactor: 2 } : {}));
  const p = await ctx.newPage(), errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error' && !IGNORE.test(m.text())) errs.push(m.text()); });
  await H.route(p, o);
  await p.goto('http://ha.test/');
  const f = await H.pageFrame(p);
  await p.waitForTimeout(900);
  await f.evaluate(() => {
    window.__w = ms => new Promise(r => setTimeout(r, ms));
    window.__C = () => window.parent.__calls.length;
    window.__since = n => window.parent.__calls.slice(n);
    window.__push = () => window.parent.__push();
    window.__cr = (fg, bg) => { const L = c => { const m = c.match(/[\d.]+/g).slice(0, 3).map(x => +x / 255).map(x => x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4)); return .2126 * m[0] + .7152 * m[1] + .0722 * m[2]; }; const a = L(fg), b = L(bg); return Math.round((Math.max(a, b) + .05) / (Math.min(a, b) + .05) * 100) / 100; };
    window.__openAll = () => { document.querySelectorAll('details').forEach(d => d.open = true); };
    // elements wider than the viewport, outside the intentionally scrolling jump chips
    window.__over = root => { const W = document.documentElement.clientWidth, o = []; (root || document.body).querySelectorAll('*').forEach(e => { if (e.closest('#jump')) return; const r = e.getBoundingClientRect(); if (r.width && (r.right > W + 0.5 || r.left < -0.5)) o.push((e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].join('.')) + ' ' + Math.round(r.left) + '..' + Math.round(r.right)); }); return o.slice(0, 12); };
    window.__unlabelled = () => { const u = []; document.querySelectorAll('select,input,button,textarea').forEach(e => { if (e.type === 'hidden' || (e.hidden && e.type === 'file')) return; const lab = (e.getAttribute('aria-label') || '').trim() || (e.labels && [...e.labels].some(l => l.textContent.trim())) || e.getAttribute('aria-labelledby') || (e.tagName === 'BUTTON' && e.textContent.trim()); if (!lab) u.push(e.tagName + ' ' + (e.id || [...e.attributes].map(a => a.name + (a.name.startsWith('data-') ? '=' + a.value : '')).filter(n => n.startsWith('data-')).join(','))); }); return u; };
    window.__card = re => [...document.querySelectorAll('#readers > section')].find(s => re.test(s.querySelector('h3').textContent));
    window.__band = n => [...document.querySelectorAll('#bands section.band')].find(s => s.querySelector('.nh h3').textContent === n);
    window.__bridge = re => [...document.querySelectorAll('#bridges > section')].find(s => re.test(s.querySelector('h3').textContent));
    // lit LEDs of a twin: [{i, fill, op}]
    window.__lit = tw => [...tw.querySelectorAll('.tw-leds circle,.tw-leds path')].map((d, i) => { const P = d.tagName === 'path' ? 'stroke' : 'fill'; return { i, fill: d.getAttribute(P), op: +(d.getAttribute(P + '-opacity') || 0) }; }).filter(x => x.fill && x.fill !== 'var(--tw-off)');
  });
  return { ctx, p, f, errs };
}
async function fullShot(p, f, name) {
  const h = await f.evaluate(() => document.documentElement.scrollHeight);
  await p.evaluate(h => { window.__panel.style.height = h + 'px'; }, h); await p.waitForTimeout(300);
  const file = path.join(SHOTS, name + '.png'); await p.screenshot({ path: file, fullPage: true });
  await p.evaluate(() => { window.__panel.style.height = ''; }); await p.waitForTimeout(150);
  return path.relative(OUT, file);
}
async function elShot(p, f, sel, name) {
  const h = await f.evaluate(() => document.documentElement.scrollHeight);
  await p.evaluate(h => { window.__panel.style.height = h + 'px'; }, h); await p.waitForTimeout(300);
  const box = await f.evaluate(s => { const e = typeof s === 'string' ? document.querySelector(s) : null; if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.max(0, r.left), y: r.top + scrollY, width: r.width, height: r.height }; }, sel);
  const file = path.join(SHOTS, name + '.png');
  if (box && box.width && box.height) await p.screenshot({ path: file, fullPage: true, clip: { x: box.x, y: box.y, width: Math.min(box.width, 1400), height: Math.min(box.height, 3000) } });
  await p.evaluate(() => { window.__panel.style.height = ''; }); await p.waitForTimeout(150);
  return path.relative(OUT, file);
}

// ───────── scenarios ─────────
const SCEN = [];
const scenario = (name, o, fn) => SCEN.push({ name, o, fn });
// a context that throws on every use, so a scenario whose page never loaded still records each of its checks as failing
const broken = msg => { const t = () => { throw new Error('page did not load: ' + msg); }; const px = new Proxy({}, { get: (_, k) => k === 'then' ? undefined : t }); return { ctx: null, p: px, f: px, errs: ['page did not load: ' + msg], broken: true }; };

const F = {   // feature names (the catalogue maps these to IDs)
  render: 'Page renders (all sections)', member: 'Household members (not administrators)', layout: 'Layout and overflow', a11y: 'Accessibility: labels, switches, headings, focus', touch: 'Touch targets on phones',
  dark: 'Dark mode', nav: 'Jump chips and KPIs', status: 'Status strip and Needs attention', taps: 'Recent taps', people: 'People and access',
  guest: 'Guest passes and band hours', lockdown: 'Lockdown', welcome: 'Welcome colour and welcome sound', bands: 'Bands list',
  btonly: 'Bluetooth-only bands and linking', unknown: 'Unknown band discovery and assignment', readers: 'Reader cards', settings: 'Reader ring and tap settings',
  idle: 'Idle circle', night: 'Night mode and Sound at night', lockout: 'Refused-tap lockout', every: 'Welcome every band', hw: 'Hardware settings confirm',
  pair: 'Paired with MagicbHAnds', lightup: 'Band light-up power', autoupd: 'Automatic updates and Time zone', health: 'Device health tiles',
  twin: 'Live ring twin', bridges: 'Bridge cards', send: 'Send to bands', celeb: 'Celebrations', passport: 'Tap passport', msgs: 'Per-card messages and revert on error',
  numbers: 'Number range validation', redraw: 'Redraw guard', arm: 'Second tap for removals and loosening access', fw: 'Older firmware hides settings gracefully',
  rgbw: 'RGBW rings', ago: 'Relative times (ago)', camera: 'Tap pictures and cameras', battery: 'Battery history', enrol: 'Enrolment', offline: 'Offline devices',
  security: 'Page controls reach only MagicbHAnds devices',
};

// ── 1. desktop, default mock: structure, wording, navigation (from probe4) ──
scenario('desk-structure', { width: 1400 }, async ({ p, f, errs }) => {
  await chk('PAGE-001', F.render, 'Every section draws at 1400 px: 6 KPIs, 10 taps, 4 people, 7 bands, 2 readers, 2 bridges, 12 send buttons, 3 passports, lockdown and celebrations', async () => {
    const r = await f.evaluate(() => ({ kpis: document.querySelectorAll('#kpis .kpi').length, taps: document.querySelectorAll('#hist table tr').length - 1, people: document.querySelectorAll('#people .pc').length, bands: document.querySelectorAll('#bands section.band').length,
      readers: document.querySelectorAll('#readers > section').length, bridges: document.querySelectorAll('#bridges > section').length, send: document.querySelectorAll('#send button').length, pass: document.querySelectorAll('#passport .tc').length,
      rules: !!document.querySelector('#rules [data-stg="lockdown"]'), celeb: !!document.querySelector('#celeb [data-stg="holiday_shows"]'), live: $('lstatus').textContent }));
    return [r.kpis === 6 && r.taps === 10 && r.people === 4 && r.bands === 7 && r.readers === 2 && r.bridges === 2 && r.send === 12 && r.pass === 3 && r.rules && r.celeb && /Live from Home Assistant/.test(r.live), r];
  }, await fullShot(p, f, 'desk-closed'));
  await chk('PAGE-002', F.nav, 'Sections in order: Needs attention, Recent taps, People, Bands, Readers, Bridges, Celebrations', async () => {
    const r = await f.evaluate(() => [...document.querySelectorAll('h2.sec')].map(h => h.id));
    return [JSON.stringify(r) === JSON.stringify(['s-attn', 's-taps', 's-people', 's-bands', 's-readers', 's-bridges', 's-celeb']), r]; });
  await chk('PAGE-003', F.nav, 'Seven jump chips (Needs attention first, with its count), sticky', async () => {
    const j = await f.evaluate(() => [...document.querySelectorAll('#jump a')].map(a => a.textContent + '>' + a.dataset.go)); const st = await f.evaluate(() => getComputedStyle($('jump')).position);
    return [j.length === 7 && /Needs attention \d+/.test(j[0]) && st === 'sticky', { j, st }]; });
  await chk('PAGE-004', F.nav, 'A jump chip scrolls to its section in place (the srcdoc frame does not navigate)', async () => {
    const y = await f.evaluate(async () => { document.querySelector('#jump a[data-go="s-readers"]').click(); await __w(900); return [Math.round($('s-readers').getBoundingClientRect().top), location.href]; });
    return [y[0] >= 0 && y[0] < 120 && /srcdoc/.test(y[1]), y]; });
  await chk('PAGE-005', F.nav, 'The People KPI jumps to People and access', async () => {
    const k = await f.evaluate(async () => { window.scrollTo(0, 0); document.querySelector('#kpis a.kpi[data-go="s-people"]').click(); await __w(900); return Math.round($('s-people').getBoundingClientRect().top); });
    return [k >= 0 && k < 120, k]; });
  const st = await f.evaluate(() => ({ st: [...document.querySelectorAll('#status .pchip')].map(x => x.textContent.trim()), pr: $('probs').textContent, hidden: $('attn-wrap').hidden,
    cols: [...document.querySelectorAll('.stack>.job:not([hidden])')].map(x => Math.round(x.getBoundingClientRect().width)), W: document.querySelector('.stack').getBoundingClientRect().width,
    near: [...document.querySelectorAll('#kpis .kpi')][1].textContent }));
  await chk('PAGE-184', F.pair, 'Not paired: the attention hint says to tap only while MagicbHAnds’ Repairs notice asks (the ring also breathes blue for someone else’s request), not “tap any band while its ring breathes blue”', async () => {
    const t = await f.evaluate(() => $('probs').textContent);
    return [/isn’t paired/.test(t) && /only while MagicbHAnds’ notice in Settings → Repairs asks you to/.test(t) && /someone else asks to pair it/.test(t) && !/Tap any band on it while its ring breathes blue/.test(t), t.slice(0, 600)]; });
  await chk('PAGE-185', F.pair, 'Not paired: the reader card’s tag tooltip says to tap only while MagicbHAnds’ Repairs notice asks, not “while its ring breathes blue” (SEC-021)', async () => {
    const t = await f.evaluate(() => [...document.querySelectorAll('.tag.no')].filter(x => /Not paired/.test(x.textContent)).map(x => x.title));
    return [t.length > 0 && t.every(x => /only while MagicbHAnds’ notice in Settings → Repairs asks you to/.test(x) && !/tapped on this reader while its ring breathes blue/.test(x)), t]; });
  await chk('PAGE-006', F.status, 'Status strip: problems first (list not applied, locked out, not paired, battery 15%)', async () => [/list not applied/.test(st.st[0]) && st.st.some(t => /locked out/.test(t)) && st.st.some(t => /paired/.test(t)) && st.st.some(t => /battery 15%/.test(t)), st.st]);
  await chk('PAGE-007', F.status, 'Needs attention shows reader problems (with End lockout now) and the low battery', async () => [!st.hidden && /End lockout now/.test(st.pr) && /battery 15%/.test(st.pr), st.pr.slice(0, 200)]);
  await chk('PAGE-008', F.status, 'Attention cards fill the row (no empty grid column)', async () => [st.cols.length >= 3 && Math.abs(st.cols.slice(0, 3).reduce((a, c) => a + c, 0) + 28 - st.W) < 4, { cols: st.cols, W: st.W }]);
  await chk('PAGE-009', F.nav, 'Nearby now KPI says the integration’s away window (35 min)', async () => [/last 35 min/.test(st.near), st.near]);
  await chk('PAGE-010', F.nav, 'KPI “Readers OK 1 / 2” counts 3 problems and jumps to the problem list', async () => {
    const r = await f.evaluate(() => { const k = [...document.querySelectorAll('#kpis .kpi')].find(x => /Readers OK/.test(x.textContent)); return k ? { v: k.querySelector('b').textContent, i: k.querySelector('i').textContent, c: k.className, go: k.dataset.go } : null; });
    return [r && r.v === '1 / 2' && /^3 problems/.test(r.i) && /\bb\b/.test(r.c) && r.go === 'j-probs', r]; });
  // recent taps
  await chk('PAGE-011', F.taps, 'Taps say “let in” / “turned away” / “enrolled” and show badge tags', async () => {
    const r = await f.evaluate(() => [...new Set([...document.querySelectorAll('#hist .tag')].map(t => t.textContent))]);
    return [r.includes('let in') && r.includes('turned away') && r.includes('enrolled') && r.includes('Super fan') && !r.includes('denied') && !r.includes('welcomed'), r]; });
  await chk('PAGE-012', F.taps, 'A tap’s time has the full date as a tooltip', async () => { const t = await f.evaluate(() => (document.querySelector('#hist td[title]') || {}).title); return [/\d{4}/.test(t || ''), t]; });
  await chk('PAGE-013', F.taps, 'Pager: 27 taps, 10 a page; Older goes to 11–20, Newer is off on page 1', async () => {
    const r = await f.evaluate(async () => { const a = document.querySelector('#hist .pager').textContent, nd = document.querySelector('#hist [data-hp="-1"]').disabled; document.querySelector('#hist [data-hp="1"]').click(); await __w(100);
      const b = document.querySelector('#hist .pager').textContent; document.querySelector('#hist [data-hp="-1"]').click(); await __w(100); return { a, nd, b }; });
    return [/1–10 of 27 · page 1 of 3/.test(r.a) && r.nd && /11–20 of 27 · page 2 of 3/.test(r.b), r]; });
  await chk('PAGE-014', F.taps, 'Recent taps: “Assign…” on an unknown band’s tap scrolls to its New bands card and focuses its picker', async () => {
    const r = await f.evaluate(async () => { const a = document.querySelector('#hist [data-go^="unk-"]'); if (!a) return { none: true }; window.scrollTo(0, 99999); a.click(); await __w(2000); const el = $(a.dataset.go);
      return { top: Math.round(el.getBoundingClientRect().top), focus: !!(document.activeElement && document.activeElement.dataset.uPerson != null) }; });
    await f.evaluate(() => document.activeElement && document.activeElement.blur());
    return [r.top >= 0 && r.top < 200 && r.focus, r]; });
  // people
  const pr = await f.evaluate(() => { const sums = [...document.querySelectorAll('#people details.more summary')].map(s => s.textContent); const rows = [...document.querySelectorAll('#people .pc .pr')].map(t => t.querySelector('.pc-n').textContent);
    const sam = [...document.querySelectorAll('#people .pc .pm')][3]; return { sums: [...new Set(sums)], rows, wcIn: !!document.querySelector('#people .pc .pm [data-wc]'), wcRow: !!document.querySelector('#people .pc .pr [data-wc]'),
      allowIn: !!document.querySelector('#people .pc .pm details [data-allow]'), samPass: /Sam’s guest pass \(all their bands\)/.test(sam.textContent), samOwn: /own hours also apply: Dog walker 07:00–19:00/.test(sam.textContent) }; });
  await chk('PAGE-015', F.people, 'Each person has two fold-outs: Access, Welcome and birthday', async () => [JSON.stringify(pr.sums) === '["Access","Welcome and birthday"]', pr.sums]);
  await chk('PAGE-016', F.people, 'Welcome colour and Allowed live in the fold-outs, not the row', async () => [pr.wcIn && !pr.wcRow && pr.allowIn, pr]);
  await chk('PAGE-017', F.guest, 'Access summary: “Guest · Mo We Fr 11:00–14:00 · 12 uses left · until … · not now”', async () => [pr.rows.some(t => /Guest · Mo We Fr 11:00–14:00 · 12 uses left · until .* · not now/.test(t)), pr.rows]);
  await chk('PAGE-018', F.guest, 'A guest pass names the band’s own hours that also apply', async () => [pr.samPass && pr.samOwn, pr]);
  await chk('PAGE-019', F.guest, 'A band’s own hours name the owner’s guest pass that also applies', async () => {
    const b = await f.evaluate(() => __band('Dog walker').textContent); return [/This band’s own hours/.test(b) && /Sam’s guest pass also applies: Mo We Fr 11:00–14:00/.test(b), (b.match(/guest pass also applies[^.]*/) || [])[0]]; });
  await chk('PAGE-020', F.arm, 'Remove person arms to “Tap again to remove <Name>” and sends nothing on the first tap', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('[data-rmp]').click(); await __w(80); return { t: document.querySelector('[data-rmp]').textContent, sent: __since(n0).some(c => c[3] === 'remove_person') }; });
    await p.waitForTimeout(4300); return [r.t === 'Tap again to remove Alex' && !r.sent, r]; });
  // bands
  const bd = await f.evaluate(() => { const blue = __band('Blue'), dt = [...blue.querySelectorAll('dl dt')].map(x => x.textContent), old = __band('Old band'), m = __band("Morgan's MagicBand+");
    return { dt, oldType: !!old.querySelector('dl [data-sel]'), mType: !!m.querySelector('dl [data-sel]'), mManage: !!m.querySelector('details [data-sel]'), cap: $('bands-cap').textContent, ph: $('b-find').placeholder }; });
  await chk('PAGE-021', F.bands, 'A standard (classic) band shows no Battery, Closest or Bluetooth', async () => [!bd.dt.includes('Battery') && !bd.dt.includes('Closest') && !bd.dt.includes('Bluetooth'), bd.dt]);
  await chk('PAGE-022', F.bands, 'Band type in the body only while unknown, else under Manage', async () => [bd.oldType && !bd.mType && bd.mManage, bd]);
  await chk('PAGE-023', F.bands, 'Caption “7 bands” and the “Search bands” box', async () => [bd.cap === '7 bands' && bd.ph === 'Search bands', bd]);
  await chk('PAGE-024', F.bands, 'Owner, then name: bands nobody owns sort last', async () => {
    const r = await f.evaluate(() => { $('b-sort').value = 'person'; $('b-sort').onchange(); return [...document.querySelectorAll('#bands section.band dl dd:first-of-type')].map(d => d.textContent.split(' ·')[0]); });
    return [r[r.length - 1].startsWith('nobody') && !r[0].startsWith('nobody'), r]; });
  await chk('PAGE-025', F.bands, 'Group by Battery: Low, Good, No battery reading, in that order', async () => {
    const r = await f.evaluate(() => { $('b-group').value = 'battery'; $('b-group').onchange(); const g = [...document.querySelectorAll('#bands h3.grp')].map(h => h.firstChild.textContent.trim()); $('b-group').value = 'none'; $('b-group').onchange(); return g; });
    return [JSON.stringify(r) === JSON.stringify(['Low (20% or less)', 'Good (over 50%)', 'No battery reading']), r]; });
  await chk('PAGE-026', F.bands, 'Search “casey” keeps Casey’s 2 bands (caption “2 of 7 bands”)', async () => {
    const r = await f.evaluate(() => { const s = $('b-find'); s.value = 'casey'; s.oninput(); const a = { cap: $('bands-cap').textContent, n: document.querySelectorAll('#bands section.band').length }; s.value = ''; s.oninput(); return a; });
    return [r.cap === '2 of 7 bands' && r.n === 2, r]; });
  // reader cards and settings (probe4)
  const rc = await f.evaluate(() => { document.querySelectorAll('#readers details').forEach(d => d.open = true); const s = __card(/Garage/);
    const kids = [...s.children].map(c => c.tagName.toLowerCase() + (c.className ? '.' + c.className.split(' ')[0] : '') + (c.querySelector && c.querySelector('summary') ? ':' + c.querySelector('summary').firstChild.textContent.trim() : ''));
    return { kids, g: [...s.querySelectorAll('.sg h4')].map(h => h.firstChild.textContent.trim()), labs: [...document.querySelectorAll('#readers .sg .lab')].map(x => x.textContent), labsG: [...s.querySelectorAll('.sg .lab')].map(x => x.textContent),
      hsum: s.querySelector('details.hp summary').textContent, tags: s.querySelector('h3').textContent, prev: $('readers-bar').textContent, seg: s.querySelectorAll('[data-twstyle]').length }; });
  await chk('PAGE-027', F.readers, 'Reader card order: title, twin, status line, controls, buttons, Health, then Ring and tap settings', async () => [/div\.twin/.test(rc.kids[1]) && /p\.stl/.test(rc.kids[2]) && rc.kids.indexOf('details.more:Health') >= 0 && rc.kids.indexOf('details.more:Health') < rc.kids.indexOf('details.more:Ring and tap settings'), rc.kids]);
  await chk('PAGE-028', F.readers, 'Garage reader title tags: Online, Locked out, Not paired', async () => [/Online/.test(rc.tags) && /Locked out/.test(rc.tags) && /Not paired/.test(rc.tags), rc.tags]);
  await chk('PAGE-029', F.health, 'Health summary while closed: “Wi-Fi weak · up 50 min (after a power dip)”', async () => [/Wi-Fi weak · up 50 min \(after a power dip\)/.test(rc.hsum), rc.hsum]);
  await chk('PAGE-030', F.twin, 'One page-level “Ring preview” switch (LEDs / Diffused), none per card', async () => [/Ring preview/.test(rc.prev) && rc.seg === 0, rc.prev]);
  await chk('PAGE-031', F.settings, 'Settings groups in order: Waiting, Night, Reading, Welcome, Denied, Refused-tap lockout, Shows, Hardware', async () => [JSON.stringify(rc.g) === JSON.stringify(['Waiting for a band', 'Night', 'Reading a band', 'Welcome', 'Denied', 'Refused-tap lockout', 'Shows', 'Hardware']), rc.g]);
  await chk('PAGE-032', F.settings, 'Setting labels use the page’s words (Quieter volume, One lap takes, Tail fades to, Max brightness, Band light-up power…) not the entity names', async () => {
    const want = ['Quieter volume', 'Night from', 'Night until', 'One lap takes', 'Tail fades to', 'Pulses', 'Show for “Play show”', 'Night runs', 'LED count', 'Max brightness', 'Light up MagicBand+', 'Band light-up power', 'Heads', 'Direction', 'Style at night', 'Sound at night'];
    const miss = want.filter(l => !rc.labs.includes(l)), old = rc.labs.filter(l => /^(LEDs|Brightness|Repeat|Each circle|Tail ends at|Night is|Volume \(Quieter\))$/.test(l)); return [!miss.length && !old.length, { miss, old }]; });
  await chk('PAGE-033', F.idle, 'Circle rows (Heads, lap, tail, fade, direction) hidden while Style and Style at night are Static (Garage)', async () => [!rc.labsG.includes('Heads') && !rc.labsG.includes('Direction') && rc.labsG.includes('Style'), rc.labsG.slice(0, 8)]);
  await chk('PAGE-034', F.idle, 'Circle rows appear once Style is set to Circle', async () => {
    const r = await f.evaluate(async () => { const sel = [...__card(/Garage/).querySelectorAll('select[data-sel]')].find(x => /idle_style$/.test(x.dataset.sel)); sel.value = 'Circle'; sel.dispatchEvent(new Event('change')); await __w(1300);
      return [...__card(/Garage/).querySelectorAll('.sg .lab')].map(x => x.textContent); });
    return [['Heads', 'One lap takes', 'Tail (0 = auto)', 'Tail fades to', 'Direction'].every(l => r.includes(l)), r.slice(0, 9)]; });
  await chk('PAGE-035', F.night, 'Quieter volume hidden once Sound at night is not Quieter', async () => {
    const r = await f.evaluate(async () => { const before = [...__card(/Front/).querySelectorAll('.sg .lab')].map(x => x.textContent).includes('Quieter volume');
      const sel = [...__card(/Front/).querySelectorAll('select[data-sel]')].find(x => /sound_at_night$/.test(x.dataset.sel)); sel.value = 'Off'; sel.dispatchEvent(new Event('change')); await __w(1300);
      return { before, after: [...__card(/Front/).querySelectorAll('.sg .lab')].map(x => x.textContent).includes('Quieter volume') }; });
    return [r.before && !r.after, r]; });
  await chk('PAGE-036', F.hw, 'Hardware settings (Ring type, LED count) need the same pick / entry twice; the first goes back with a “restarts” note', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); const pick = () => [...__card(/Front/).querySelectorAll('select[data-sel]')].find(x => /ring_type$/.test(x.dataset.sel));
      let s = pick(); s.value = 'RGBW warm white'; s.dispatchEvent(new Event('change')); await __w(150); const a = { first: __since(n0).some(c => c[2] === 'select_option'), back: pick().value, msg: pick().closest('.sg').querySelector('.msg').textContent };
      s = pick(); s.value = 'RGBW warm white'; s.dispatchEvent(new Event('change')); await __w(300); a.second = __since(n0).some(c => c[2] === 'select_option' && c[3].option === 'RGBW warm white');
      const led = () => [...__card(/Front/).querySelectorAll('[data-num]')].find(x => /led_count$/.test(x.dataset.num)); const n1 = __C();
      let l = led(); l.value = '30'; l.dispatchEvent(new Event('change')); await __w(150); a.ledFirst = __since(n1).some(c => c[2] === 'set_value'); l = led(); l.value = '30'; l.dispatchEvent(new Event('change')); await __w(300);
      a.ledSecond = __since(n1).some(c => c[2] === 'set_value' && c[3].value === 30); a.hwBox = !!pick().closest('.sg.hw') && /restarts the reader/.test(pick().closest('.sg').textContent); return a; });
    return [!r.first && r.back === 'RGB' && /restarts/.test(r.msg) && r.second && !r.ledFirst && r.ledSecond && r.hwBox, r]; });
  await chk('PAGE-037', F.lockout, 'End lockout now (in the lockout group) turns the reader’s Refused-tap lockout switch off', async () => {
    const r = await f.evaluate(async () => { const x = __card(/Garage/).querySelector('.sg [data-endlock]'); if (!x) return null; const n0 = __C(); x.click(); await __w(200); return __since(n0).find(c => c[2] === 'turn_off'); });
    return [r && /garage_reader_refused_tap_lockout/.test(r[3].entity_id), r]; });
  await chk('PAGE-038', F.lockout, 'End lockout now shows only on the locked-out reader, and its lockout group says “Locked out now”', async () => {
    const r = await f.evaluate(() => ({ front: !!__card(/Front/).querySelector('[data-endlock]'), hint: [...__card(/Garage/).querySelectorAll('.sg')].find(g => /Refused-tap lockout/.test(g.querySelector('h4').textContent)).textContent }));
    return [!r.front && /Locked out now/.test(r.hint) && /not the house Lockdown/.test(r.hint), r]; });
  // bridges and send
  await chk('PAGE-039', F.send, 'Send bar has no Wake/Ping; the Link card has its own Wake bands; bridge buttons have hints; Re-send list is under Readers', async () => {
    const r = await f.evaluate(() => ({ send: [...document.querySelectorAll('#send button')].map(b => b.textContent), wake: !!document.querySelector('#link [data-wakeall]'), tip: [...document.querySelectorAll('#bridges [data-press]')].map(b => b.title).filter(Boolean).length, sync: !!document.querySelector('#readers-bar #sync') }));
    return [!r.send.includes('Wake') && !r.send.includes('Ping') && r.wake && r.tip === 4 && r.sync, r]; });
  await chk('PAGE-040', F.btonly, 'Wake bands (Link card) sends a wake through every bridge', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('#link [data-wakeall]').click(); await __w(300); return __since(n0).find(c => c[3] === 'send'); });
    return [r && r[4].effect === 'wake', r]; });
  await chk('PAGE-041', F.render, 'Old wording is gone (Stamp show…, Checking a band, Remove buttons ask…) and the new wording is there', async () => {
    const t = await f.evaluate(() => document.body.textContent); return [!/Stamp show for a new badge|Checking a band|Birthday, welcome sound|Remove buttons ask|found by device model|Push to readers/.test(t) && /Show when a new stamp is earned/.test(t), null]; });
  await chk('PAGE-042', F.ago, 'ago(): just now, min ago, h ago, yesterday h:mm am, weekday h:mm am, month day', async () => {
    const r = await f.evaluate(() => { const h = x => Date.now() - x * 3600e3; const y = new Date(); y.setDate(y.getDate() - 1); y.setHours(9, 14, 0, 0); const w = new Date(); w.setDate(w.getDate() - 4); w.setHours(9, 14, 0, 0); const o = new Date(); o.setDate(o.getDate() - 20); const ly = new Date(); ly.setFullYear(ly.getFullYear() - 1);
      return [ago(h(0.01)), ago(h(0.5)), ago(h(5)), ago(y.getTime()), ago(w.getTime()), ago(o.getTime()), ago(ly.getTime()), ago(null), ago('garbage'), ago(new Date(h(2)).toISOString())]; });
    return [r[0] === 'just now' && /^\d+ min ago$/.test(r[1]) && /^\d+ h ago$/.test(r[2]) && /^(yesterday 9:14 am|\d+ h ago)$/.test(r[3]) && /^[A-Z][a-z]{2} 9:14 am$/.test(r[4]) && /^[A-Z][a-z]{2} \d+(, \d{4})?$/.test(r[5]) && /^[A-Z][a-z]{2} \d+, \d{4}$/.test(r[6]) && r[7] === '–' && r[8] === '–' && r[9] === '2 h ago', r]; });
  await chk('PAGE-043', F.render, 'No console errors or page errors (desktop, default mock, after the checks above)', async () => [!errs.length, errs]);
});

// ── 2. desktop: messages, revert on error, number validation, redraw guard, arming (from probe3) ──
scenario('desk-actions', { width: 1400 }, async ({ p, f, errs }) => {
  await chk('PAGE-044', F.redraw, 'A focused select survives a state change; other sections still redraw; Readers catch up after blur', async () => {
    const r = await f.evaluate(async () => { const s = document.querySelector('#readers select[data-sel]'); s.focus(); window.__keep = s;
      const h = window.parent.__mbHass; h.states['sensor.garage_reader_wi_fi_signal'].state = '-70'; h.states['sensor.morgan_s_magicband_battery'].state = '55'; __push(); await __w(500);
      const kept = document.contains(window.__keep) && document.activeElement === window.__keep, bandsUpd = /55%/.test($('bands').textContent);
      window.__keep.blur(); await __w(700); return { kept, bandsUpd, caughtUp: /−70/.test($('readers').textContent) }; });
    return [r.kept && r.bandsUpd && r.caughtUp, r]; });
  await chk('PAGE-045', F.redraw, 'A focused number box in a settings group survives a state change', async () => {
    const r = await f.evaluate(async () => { document.querySelectorAll('#readers details.more').forEach(d => d.open = true); const s = document.querySelector('.sg [data-num]'); s.focus(); const h = window.parent.__mbHass; h.states['sensor.garage_reader_cpu_temperature'].state = '70'; __push(); await __w(400); return document.activeElement === s; });
    await f.evaluate(() => document.activeElement.blur()); await p.waitForTimeout(600); return [r, r]; });
  await chk('PAGE-046', F.redraw, 'An open fold-out (Ring and tap settings) stays open through a redraw', async () => {
    const r = await f.evaluate(async () => { const h = window.parent.__mbHass; h.states['sensor.front_door_reader_cpu_temperature'].state = '61'; __push(); await __w(500); return [...document.querySelectorAll('#readers details.more')].map(d => d.open); });
    return [r.length >= 4 && r.every(Boolean), r]; });
  await f.evaluate(() => { document.querySelectorAll('#readers details.more').forEach(d => d.open = true); window.parent.__mockReject = /^(select|switch|media_player|button|number)\./; });
  await chk('PAGE-047', F.msgs, 'A failed select shows “Didn’t work: …” in its own settings group and goes back to Home Assistant’s value', async () => {
    const r = await f.evaluate(async () => { const s = [...document.querySelectorAll('#readers .sg select[data-sel]')].find(x => /idle_colour$/.test(x.dataset.sel)), was = s.value; s.value = 'Blue'; s.dispatchEvent(new Event('change'));
      await __w(1200); const s2 = [...document.querySelectorAll('#readers .sg select[data-sel]')].find(x => x.dataset.sel === s.dataset.sel), sg = s2.closest('.sg');
      return { was, now: s2.value, msg: sg.querySelector('.msg').textContent, cls: sg.querySelector('.msg').className }; });
    return [r.now === r.was && /Didn’t work: MOCK-REJECT Reader not connected/.test(r.msg) && /bad/.test(r.cls), r]; });
  await chk('PAGE-048', F.msgs, 'A failed reader switch shows the error on that reader card', async () => {
    const r = await f.evaluate(async () => { document.querySelector('#readers > section [data-tg]').click(); await __w(1200); return [...document.querySelectorAll('#readers > section > .msg')].map(m => m.textContent); });
    return [r.some(t => /Didn’t work/.test(t)), r]; });
  await chk('PAGE-049', F.msgs, 'A failed volume change puts the slider back', async () => {
    const r = await f.evaluate(async () => { const v = document.querySelector('#readers [data-vol]'), was = v.value; v.value = '10'; v.dispatchEvent(new Event('change')); await __w(1200); return { was, now: document.querySelector('#readers [data-vol]').value }; });
    return [r.was === r.now, r]; });
  await chk('PAGE-050', F.msgs, 'A failed bridge button shows the error on that bridge card', async () => {
    const r = await f.evaluate(async () => { document.querySelector('#bridges [data-press]').click(); await __w(1200); return [...document.querySelectorAll('#bridges .msg')].map(m => m.textContent).filter(Boolean); });
    return [r.some(t => /Didn’t work/.test(t)), r]; });
  const ev = await elShot(p, f, '#readers > section', 'reader-error');
  await chk('PAGE-051', F.msgs, 'Errors stay through a redraw and 6 s', async () => {
    const r = await f.evaluate(async () => { const h = window.parent.__mbHass; h.states['sensor.front_door_reader_cpu_temperature'].state = '60'; __push(); await __w(6000); return [...document.querySelectorAll('#readers .msg.bad')].map(m => m.textContent); });
    return [r.length >= 2, r]; }, ev);
  await f.evaluate(() => { window.parent.__mockReject = null; });
  await chk('PAGE-052', F.msgs, 'A success message shows on the card, then goes after a few seconds', async () => {
    const r = await f.evaluate(async () => { document.querySelector('#bridges [data-press]').click(); await __w(900); const a = [...document.querySelectorAll('#bridges .msg')].map(m => m.textContent).filter(Boolean); await __w(4500); const b = [...document.querySelectorAll('#bridges .msg')].map(m => m.textContent).filter(Boolean); return { a, b }; });
    return [r.a.some(t => /sent/.test(t)) && !r.b.some(t => /sent/.test(t)), r]; });
  await chk('PAGE-053', F.msgs, 'A failed people change (integration service) shows “Didn’t work” under People', async () => {
    await f.evaluate(() => { window.parent.__mockReject = /^magicband\.update_person$/; document.querySelectorAll('#people details.more').forEach(d => d.open = true); });
    const r = await f.evaluate(async () => { document.querySelector('[data-lx]').click(); await __w(600); return $('people-msg').textContent; });
    await f.evaluate(() => { window.parent.__mockReject = null; }); return [/Didn’t work: MOCK-REJECT/.test(r), r]; });
  await chk('PAGE-054', F.numbers, 'Numbers: an out-of-range value is not sent, says the range (“LED count: 1–60”) and goes back; a negative offset is sent; a value off the step is refused', async () => {
    const r = await f.evaluate(async () => { const n = [...document.querySelectorAll('[data-num]')].find(x => /night_starts_after_sunset/.test(x.dataset.num)), led = [...document.querySelectorAll('[data-num]')].find(x => /led_count/.test(x.dataset.num));
      const before = __C(); led.value = '500'; led.dispatchEvent(new Event('change')); await __w(300);
      const sent = __since(before).filter(c => c[0] === 'svc').length, msg = led.closest('.sg').querySelector('.msg').textContent, back = led.value;
      n.value = '−90'; n.dispatchEvent(new Event('change')); await __w(500); const call = window.parent.__calls.filter(c => c[0] === 'svc' && c[2] === 'set_value').pop();
      const step = [...document.querySelectorAll('[data-num]')].find(x => /night_ends_after_sunrise/.test(x.dataset.num)); const b2 = __C(); step.value = '7'; step.dispatchEvent(new Event('change')); await __w(300);
      return { sent, msg, back, call: call && call[3], stepMsg: step.closest('.sg').querySelector('.msg').textContent, stepSent: __since(b2).some(c => c[2] === 'set_value') }; });
    return [r.sent === 0 && /LED count: 1–60/.test(r.msg) && r.back === '24' && r.call && r.call.value === -90 && /in steps of 5/.test(r.stepMsg) && !r.stepSent, r]; }, await elShot(p, f, '#readers .sgs', 'number-range'));
  await chk('PAGE-055', F.numbers, 'A box whose range goes below 0 uses the text keyboard (inputmode=text); others the decimal pad; the range is the tooltip', async () => {
    const r = await f.evaluate(() => { const n = [...document.querySelectorAll('[data-num]')].find(x => /night_starts_after_sunset/.test(x.dataset.num)), led = [...document.querySelectorAll('[data-num]')].find(x => /led_count/.test(x.dataset.num)); return { n: n.inputMode, led: led.inputMode, tn: n.title, tl: led.title }; });
    return [r.n === 'text' && r.led === 'decimal' && r.tn === '−240 to 240 min' && r.tl === '1–60', r]; });
  await chk('PAGE-056', F.btonly, 'Bluetooth-only band: Manage has Link to… (NFC bands and people) and Forget, which takes a second tap and calls forget_bluetooth', async () => {
    const r = await f.evaluate(async () => { const card = __band('MagicBand+ 7F3C'); card.querySelector('details').open = true;
      const sel = card.querySelector('[data-bl-to]'), opts = sel ? [...sel.querySelectorAll('optgroup')].map(g => g.label + ':' + g.children.length) : [];
      const n0 = __C(); card.querySelector('[data-forget]').click(); await __w(50); const c2 = __band('MagicBand+ 7F3C'), armedTxt = c2.querySelector('[data-forget]').textContent, firstSent = __since(n0).some(c => c[3] === 'forget_bluetooth');
      c2.querySelector('[data-forget]').click(); await __w(300); const call = __since(n0).find(c => c[3] === 'forget_bluetooth');
      return { opts, armedTxt, firstSent, call: call && call[4] }; });
    return [r.opts.length === 2 && /Tap again/.test(r.armedTxt) && !r.firstSent && r.call && r.call.bluetooth_band === 'mb-7F3C11', r]; });
  await chk('PAGE-057', F.btonly, 'Bluetooth-only band: Link without a choice asks for one; with a choice it calls link_bluetooth', async () => {
    await p.waitForTimeout(800);
    const r = await f.evaluate(async () => { const card = __band('MagicBand+ 7F3C'); card.querySelector('details').open = true; const k = card.querySelector('[data-bl-go]').dataset.blGo; card.querySelector('[data-bl-go]').click(); await __w(80);
      const m1 = $('msg-' + k).textContent; const s = __band('MagicBand+ 7F3C').querySelector('[data-bl-to]'); s.value = 'person:Casey'; const n0 = __C(); __band('MagicBand+ 7F3C').querySelector('[data-bl-go]').click(); await __w(300);
      return { m1, call: (__since(n0).find(c => c[3] === 'link_bluetooth') || [])[4] }; });
    return [/Pick the band or person first/.test(r.m1) && r.call && r.call.bluetooth_band === 'mb-7F3C11' && r.call.person === 'Casey', r]; }, await elShot(p, f, '#bands', 'bands'));
  await chk('PAGE-058', F.lightup, 'Band light-up power drop-down on each reader (−12 dBm here)', async () => {
    const r = await f.evaluate(() => [...document.querySelectorAll('#readers select[data-sel]')].filter(s => /band_light_up_power/.test(s.dataset.sel)).map(s => s.value)); return [r.length === 2 && r[0] === '-12 dBm', r]; });
  await chk('PAGE-059', F.pair, '“Not paired” tag only on the unpaired reader', async () => {
    const r = await f.evaluate(() => [...document.querySelectorAll('#readers > section')].map(s => [s.querySelector('h3').textContent.trim(), /Not paired/.test(s.querySelector('h3').textContent)]));
    return [r.some(x => /Garage/.test(x[0]) && x[1]) && r.some(x => /Front/.test(x[0]) && !x[1]), r]; });
  await chk('PAGE-060', F.readers, 'Re-send list button wording; the Allowed toggle message says the readers update within a few seconds', async () => {
    const a = await f.evaluate(() => $('sync').textContent); const b = await f.evaluate(async () => { document.querySelector('[data-allow]').click(); await __w(200); return $('people-msg').textContent; });
    return [a === 'Re-send list to readers' && /readers update within a few seconds/.test(b), { a, b }]; });
  await f.evaluate(() => { document.querySelectorAll('#people details.more').forEach(d => d.open = true); });
  await p.waitForTimeout(700);
  await chk('PAGE-061', F.arm, 'Clear the pass and Guest off each need a second tap (nothing sent on the first)', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('[data-gclear]').click(); await __w(80);
      const a = { armTxt: document.querySelector('[data-gclear]').textContent, sentFirst: __since(n0).some(c => c[4] && c[4].clear) };
      document.querySelector('[data-gclear]').click(); await __w(200); a.sentSecond = __since(n0).some(c => c[3] === 'set_guest_pass' && c[4].clear);
      const g = document.querySelector('[data-guest].on'); const n1 = __C(); g.click(); await __w(80); a.guestFirst = __since(n1).some(c => c[3] === 'update_person'); a.guestArm = !!document.querySelector('[data-guest].arm') && /Tap again to stop being a guest/.test($('people').textContent);
      return a; });
    return [/Tap again/.test(r.armTxt) && !r.sentFirst && r.sentSecond && !r.guestFirst && r.guestArm, r]; }, await elShot(p, f, '#people', 'guest-arm'));
  await p.waitForTimeout(4300);
  await chk('PAGE-062', F.arm, '“Always allowed” (clear a band’s hours) needs a second tap', async () => {
    const r = await f.evaluate(async () => { const card = [...document.querySelectorAll('#bands section.band')].find(s => s.querySelector('[data-acc-clear]')); card.querySelector('details').open = true; const x = card.querySelector('[data-acc-clear]'); const n0 = __C(); x.click(); await __w(80);
      const t = [...document.querySelectorAll('[data-acc-clear]')].find(y => y.dataset.accClear === x.dataset.accClear); const a = { txt: t.textContent, sent: __since(n0).some(c => c[3] === 'set_band_access') };
      t.click(); await __w(200); a.second = (__since(n0).find(c => c[3] === 'set_band_access') || [])[4]; return a; });
    return [/Tap again/.test(r.txt) && !r.sent && r.second && r.second.clear === true, r]; });
  await chk('PAGE-063', F.every, '“Welcome every band” needs a second pick (“Pick it again”), then the reader gets a red “Lets every band in” tag', async () => {
    const r = await f.evaluate(async () => { const s = [...document.querySelectorAll('#readers select[data-sel]')].find(x => /front_door_reader_response_mode/.test(x.dataset.sel)); const n0 = __C();
      s.value = 'Welcome every band'; s.dispatchEvent(new Event('change')); await __w(100); const s1 = [...document.querySelectorAll('#readers select[data-sel]')].find(x => x.dataset.sel === s.dataset.sel);
      const a = { first: __since(n0).some(c => c[2] === 'select_option'), back: s1.value, msg: s1.closest('section').querySelector(':scope > .msg').textContent };
      s1.value = 'Welcome every band'; s1.dispatchEvent(new Event('change')); await __w(1300); a.second = __since(n0).some(c => c[2] === 'select_option' && c[3].option === 'Welcome every band');
      a.tag = /Lets every band in/.test(__card(/Front/).querySelector('h3').textContent); return a; });
    return [!r.first && r.back === 'Known bands only' && /Pick it again/.test(r.msg) && r.second && r.tag, r]; }, await elShot(p, f, '#readers > section', 'every-band-tag'));
  await chk('PAGE-064', F.arm, 'Remove band and Unlink Bluetooth each need a second tap and then call remove_band / unlink_bluetooth', async () => {
    await p.waitForTimeout(4300);
    const r = await f.evaluate(async () => { const m = __band("Morgan's MagicBand+"); m.querySelector('details').open = true; const n0 = __C();
      m.querySelector('[data-unlink]').click(); await __w(60); const u1 = __band("Morgan's MagicBand+").querySelector('[data-unlink]'); const a = { ut: u1.textContent, uFirst: __since(n0).some(c => c[3] === 'unlink_bluetooth') };
      u1.click(); await __w(200); a.u2 = (__since(n0).find(c => c[3] === 'unlink_bluetooth') || [])[4];
      const n1 = __C(); __band('Blue').querySelector('details').open = true; __band('Blue').querySelector('[data-remove]').click(); await __w(60); const r1 = __band('Blue').querySelector('[data-remove]'); a.rt = r1.textContent; a.rFirst = __since(n1).some(c => c[3] === 'remove_band');
      r1.click(); await __w(200); a.r2 = (__since(n1).find(c => c[3] === 'remove_band') || [])[4]; return a; });
    return [/Tap again to unlink/.test(r.ut) && !r.uFirst && r.u2 && r.u2.bluetooth_band === 'mb-A1B2C3' && /Tap again to remove/.test(r.rt) && !r.rFirst && r.r2 && r.r2.band === '04-1A-2B-3C-4D-5E-02', r]; });
  await chk('PAGE-065', F.arm, 'Restart (reader Health) needs a second tap, then presses the reader’s Restart button', async () => {
    const r = await f.evaluate(async () => { const c = __card(/Front/); c.querySelector('details.hp').open = true; const b = c.querySelector('[data-restart]'); const n0 = __C(); b.click(); await __w(60);
      const b2 = __card(/Front/).querySelector('[data-restart]'); const a = { t: b2.textContent, first: __since(n0).some(x => x[2] === 'press') }; b2.click(); await __w(200); a.call = (__since(n0).find(x => x[2] === 'press') || [])[3]; return a; });
    return [/Tap again to restart/.test(r.t) && !r.first && r.call && r.call.entity_id === 'button.front_door_reader_restart', r]; });
  await chk('PAGE-066', F.render, 'No console errors or page errors (desktop, actions; the mock’s deliberate rejections excluded)', async () => [!errs.length, errs]);
});

// ── 3. desktop: controls, services, accessibility, twin (probe5 desktop + new) ──
scenario('desk-controls', { width: 1400 }, async ({ p, f, errs }) => {
  await chk('PAGE-067', F.layout, 'Desktop: a person is one row of fields (5 columns)', async () => {
    const r = await f.evaluate(() => { const pr = document.querySelector('#people .pc .pr'), kids = [...pr.children].map(c => Math.round(c.getBoundingClientRect().top)); return { cols: getComputedStyle(pr).gridTemplateColumns.split(' ').length, tops: kids }; });
    return [r.cols === 5 && Math.max(...r.tops) - Math.min(...r.tops) <= 16, r]; });
  await chk('PAGE-068', F.twin, 'Desktop: the header shows reader 1’s ring live', async () => [await f.evaluate(() => getComputedStyle(document.querySelector('#hero-twin svg')).display !== 'none' && /Front|Live/.test($('hero-twin').textContent))]);
  const tgl = await f.evaluate(() => { const T = [...document.querySelectorAll('.tg')]; const bad = T.filter(t => t.getAttribute('role') !== 'switch' || t.getAttribute('aria-checked') !== String(t.classList.contains('on')));
    const labs = T.map(t => t.getAttribute('aria-label')); const off = document.querySelector('.tg:not(.on)'), col = getComputedStyle(off).boxShadow.match(/rgba?\([^)]*\)/)[0];
    return { n: T.length, bad: bad.length, sam: labs.includes('Allowed: Sam'), snd: labs.includes('Sound: Front Door Reader'), fast: labs.includes('Fast mode: Kitchen Bridge'), lock: labs.includes('Lockout: Garage Reader'), auto: labs.includes('Automatic updates: Garage Reader') && labs.includes('Automatic updates: Office BP2'),
      offEdge: window.__cr(col, getComputedStyle(off.closest('.tc,.sg,.job') || document.body).backgroundColor), offEdgeSunk: window.__cr(col, getComputedStyle(document.querySelector('.sg')).backgroundColor) }; });
  await chk('PAGE-069', F.a11y, 'Toggles: role=switch, aria-checked in step with the “on” class, labels say what and whose', async () => [tgl.n > 20 && !tgl.bad && tgl.sam && tgl.snd && tgl.fast && tgl.lock && tgl.auto, tgl]);
  await chk('PAGE-070', F.a11y, 'Light mode: a toggle’s off edge is at least 3:1 against its card and the settings group', async () => [tgl.offEdge >= 3 && tgl.offEdgeSunk >= 3, tgl]);
  await chk('PAGE-071', F.a11y, 'aria-checked follows a successful change (Sound on → off)', async () => {
    const r = await f.evaluate(async () => { const t = document.querySelector('[data-tg="switch.front_door_reader_sound"]'); const was = t.getAttribute('aria-checked'); t.click(); await __w(1500); const t2 = document.querySelector('[data-tg="switch.front_door_reader_sound"]'); return { was, now: t2.getAttribute('aria-checked'), on: t2.classList.contains('on'), msg: __card(/Front/).querySelector(':scope > .msg').textContent }; });
    return [r.was !== r.now && String(r.on) === r.now && /Sound: off/.test(r.msg), r]; });
  await chk('PAGE-072', F.a11y, 'Every select, input and button has a label (all fold-outs open)', async () => { const u = await f.evaluate(() => { window.__openAll(); return window.__unlabelled(); }); return [!u.length, u.slice(0, 15)]; });
  await chk('PAGE-073', F.a11y, 'Reader settings: a <label for> on every row (no span titles)', async () => {
    const r = await f.evaluate(() => ({ forOk: [...document.querySelectorAll('.sg label.lab')].every(l => l.control), spanTitle: document.querySelectorAll('.sg span.lab[title]').length, n: document.querySelectorAll('.sg label.lab').length }));
    return [r.forOk && !r.spanTitle && r.n > 40, r]; });
  await chk('PAGE-074', F.a11y, 'Light mode: hints on the sunk settings background and the primary buttons reach 4.5:1', async () => {
    const r = await f.evaluate(() => { const h = document.querySelector('.sg .hint'), pri = document.querySelector('.btn.pri'); return { hint: window.__cr(getComputedStyle(h).color, getComputedStyle(h.closest('.sg')).backgroundColor), pri: window.__cr(getComputedStyle(pri).color, getComputedStyle(pri).backgroundColor) }; });
    return [r.hint >= 4.5 && r.pri >= 4.5, r]; });
  await chk('PAGE-075', F.welcome, 'Upload is a real button that opens the hidden file box; tap pictures are buttons', async () => {
    const r = await f.evaluate(async () => { const up = document.querySelector('[data-snd-up]'); let clicked = 0; const orig = HTMLInputElement.prototype.click; HTMLInputElement.prototype.click = function () { if (this.type === 'file') clicked++; else orig.call(this); };
      up.click(); HTMLInputElement.prototype.click = orig; const fileIn = up.parentElement.querySelector('[data-snd-file]');
      return { tag: up.tagName, type: up.type, clicked, fileHidden: fileIn.hidden, noLabelWrap: !document.querySelector('label.btn input[type=file]'), thumbs: [...document.querySelectorAll('#hist img.snap')].every(i => i.parentElement.tagName === 'BUTTON') }; });
    return [r.tag === 'BUTTON' && r.clicked === 1 && r.fileHidden && r.noLabelWrap && r.thumbs, r]; });
  await chk('PAGE-076', F.camera, 'Picture pop-up: a dialog with Close; focus moves in, Tab stays, Esc closes, focus returns to the thumbnail', async () => {
    await f.focus('#hist .snapbtn'); await p.keyboard.press('Enter'); await p.waitForTimeout(200);
    const s1 = await f.evaluate(() => ({ open: !!$('snappop'), role: $('snappop') && $('snappop').getAttribute('role'), focus: document.activeElement && document.activeElement.id }));
    await p.keyboard.press('Tab'); const trap = await f.evaluate(() => document.activeElement && document.activeElement.id);
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const s2 = await f.evaluate(() => ({ open: !!$('snappop'), back: !!(document.activeElement && document.activeElement.classList.contains('snapbtn')) }));
    return [s1.open && s1.role === 'dialog' && s1.focus === 'snap-x' && trap === 'snap-x' && !s2.open && s2.back, { s1, trap, s2 }]; });
  await chk('PAGE-077', F.battery, 'Battery pop-up (sparkline): focus moves in, 7 / 30 days, Esc closes, focus returns', async () => {
    if (!(await f.evaluate(() => !!document.querySelector('.sparkbtn')))) return [false, 'no battery sparkline drawn'];
    await f.focus('.sparkbtn'); await p.keyboard.press('Enter'); await p.waitForTimeout(500);
    const b1 = await f.evaluate(() => ({ open: !!$('battpop'), inside: $('battpop') && $('battpop').contains(document.activeElement), modal: $('battpop') && $('battpop').querySelector('[role=dialog]').getAttribute('aria-modal'), chart: !!document.querySelector('#battpop svg.bp-c path'), facts: ($('battpop').querySelector('.hlf') || {}).textContent }));
    await f.evaluate(async () => { document.querySelector('#battpop [data-bpd="30"]').click(); await __w(400); });
    const b30 = await f.evaluate(() => ({ pressed: document.querySelector('#battpop [data-bpd="30"]').getAttribute('aria-pressed'), ws: window.parent.__calls.filter(c => c[1] === 'history/history_during_period').length }));
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const b2 = await f.evaluate(() => ({ open: !!$('battpop'), back: !!(document.activeElement && document.activeElement.classList.contains('sparkbtn')) }));
    return [b1.open && b1.inside && b1.modal === 'true' && b1.chart && /Now/.test(b1.facts || '') && b30.pressed === 'true' && !b2.open && b2.back, { b1, b30, b2 }]; });
  await chk('PAGE-078', F.a11y, 'Keyboard focus shows a 2 px outline on jump chips, buttons, toggles, summaries, status chips and KPIs', async () => {
    await f.evaluate(() => { window.scrollTo(0, 0); document.body.focus(); }); const outl = [];
    for (const sel of ['#jump a', '.btn', '.tg', 'details.more>summary', '#status .pchip', 'a.kpi']) { await f.evaluate(s => { const e = document.querySelector(s); e.setAttribute('tabindex', e.getAttribute('tabindex') || '0'); }, sel);
      await f.focus(sel); await p.keyboard.press('Shift+Tab'); await p.keyboard.press('Tab'); outl.push(await f.evaluate(() => { const a = document.activeElement, cs = getComputedStyle(a); return a.tagName + '.' + String(a.className).split(' ')[0] + ':' + cs.outlineStyle + ' ' + cs.outlineWidth; })); }
    return [outl.every(x => /solid 2px/.test(x)), outl]; });
  await chk('PAGE-079', F.a11y, 'Headings: no h3 before the first h2, no skipped levels; band and person cards are h3', async () => {
    const r = await f.evaluate(() => { const Hs = [...document.querySelectorAll('h1,h2,h3,h4')].filter(h => h.getClientRects().length).map(h => +h.tagName[1]); const firstH2 = Hs.indexOf(2);
      const skips = []; for (let i = 1; i < Hs.length; i++) if (Hs[i] > Hs[i - 1] + 1) skips.push(i + ':' + Hs[i - 1] + '>' + Hs[i]); return { h3before: Hs.slice(0, firstH2).includes(3), skips, bandH3: document.querySelectorAll('#bands section.band h3').length, personH3: document.querySelectorAll('#people .pc h3').length, h1: document.querySelectorAll('h1').length, lang: document.documentElement.lang }; });
    return [!r.h3before && !r.skips.length && r.bandH3 === 7 && r.personH3 === 4 && r.h1 === 1 && r.lang === 'en', r]; });
  // twin: Idle circle, default (1 head, auto tail, fade 10 %, forward)
  await chk('PAGE-080', F.twin, 'Live twin, Idle circle (1 head, tail 0 = auto): 4 of 24 LEDs lit, the head brightest, fading along the tail; caption “Idle glow, circling”', async () => {
    const r = await f.evaluate(() => { const tw = __card(/Front/).querySelector('[data-twin]'), L = __lit(tw); const ops = L.map(x => x.op); return { n: L.length, idx: L.map(x => x.i), ops, sub: tw.querySelector('.tw-sub').textContent, cap: tw.querySelector('.tw-cap').textContent, fill: L[0] && L[0].fill }; });
    // contiguous run of 4 (circularly)
    // a run of 4 (circularly); from its head (the leading end) back along the tail each LED is dimmer
    const s = new Set(r.idx), start = r.idx.find(i => !s.has((i + 23) % 24)), run = start != null && [0, 1, 2, 3].map(k => (start + k) % 24), byI = {}; r.idx.forEach((i, k) => byI[i] = r.ops[k]);
    const fades = run && run.every((i, k) => k === 0 || byI[i] > byI[run[k - 1]]);
    return [r.n === 4 && !!run && run.every(i => s.has(i)) && fades && /Idle glow, circling/.test(r.sub) && r.fill === 'rgb(255,255,255)', r]; });
  await chk('PAGE-081', F.twin, 'Live twin, Idle circle Forward: the lit run moves forward round the ring', async () => {
    const r = await f.evaluate(async () => { const tw = __card(/Front/).querySelector('[data-twin]'); const a = __lit(tw).map(x => x.i); await __w(260); const b = __lit(tw).map(x => x.i); return { a, b }; });
    const shift = bestShift(r.a, r.b, 24); return [shift > 0 && shift <= 4, Object.assign(r, { shift })]; });
  await chk('PAGE-082', F.twin, 'Ring preview “Diffused” draws arcs (paths) instead of dots and remembers the choice', async () => {
    const r = await f.evaluate(async () => { document.querySelector('[data-twstyle="diffused"]').click(); await __w(300); const tw = __card(/Front/).querySelector('[data-twin]');
      const a = { paths: tw.querySelectorAll('.tw-leds path').length, dots: tw.querySelectorAll('.tw-leds circle').length, pressed: document.querySelector('[data-twstyle="diffused"]').getAttribute('aria-pressed'), stored: localStorage.getItem('mbh-twin-style'), lit: __lit(tw).length };
      document.querySelector('[data-twstyle="leds"]').click(); await __w(200); return a; });
    return [r.paths === 24 && r.dots === 0 && r.pressed === 'true' && r.stored === 'diffused' && r.lit === 4, r]; });
  await chk('PAGE-083', F.twin, 'Live twin shows a tap: Chase (“Reading a band…”), then Welcome with the band’s name, then Turned away pulses', async () => {
    const r = await f.evaluate(async () => { const h = window.parent.__mbHass, e = 'light.front_door_reader_ring', st = h.states[e], cap = () => __card(/Front/).querySelector('.tw-cap').textContent, out = {};
      const set = eff => { h.states[e] = Object.assign({}, st, { attributes: Object.assign({}, st.attributes, { effect: eff }), last_updated: new Date().toISOString() }); __push(); };
      set('Chase'); await __w(400); out.chase = cap(); out.chaseLit = __lit(__card(/Front/).querySelector('[data-twin]')).length;
      set('Welcome'); await __w(500); out.welcome = cap(); set('Pulse'); await __w(300); out.pulse = cap(); set('Fireworks'); await __w(300); out.show = cap();
      set('Locked out'); await __w(300); out.locked = cap(); h.states[e] = st; __push(); await __w(300); out.back = __card(/Front/).querySelector('.tw-sub').textContent; return out; });
    return [r.chase === 'Reading a band…' && r.chaseLit >= 3 && /^Welcome, Morgan's MagicBand\+$/.test(r.welcome) && r.pulse === 'Turned away' && r.show === 'Light show: Fireworks' && r.locked === 'Locked out' && /circling/.test(r.back), r]; });
  // services wired from the page
  await chk('PAGE-084', F.lockdown, 'Lockdown switches and night times call set_settings (lockdown, lockdown_from)', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('[data-stg="lockdown"]').click(); await __w(200); const t = document.querySelector('[data-st="lockdown_from"]'); t.value = '22:30'; t.dispatchEvent(new Event('change')); await __w(300);
      return { calls: __since(n0).filter(c => c[3] === 'set_settings').map(c => c[4]), msg: $('rules-msg').textContent }; });
    return [r.calls.some(c => c.lockdown === true) && r.calls.some(c => c.lockdown_from === '22:30') && /Saved/.test(r.msg), r]; });
  await chk('PAGE-085', F.lockdown, 'Lockdown card: open state, who gets in during lockdown (Morgan), the alarm list from Home Assistant', async () => {
    const r = await f.evaluate(() => ({ t: $('rules').textContent, alarms: [...document.querySelectorAll('[data-st="lockdown_alarm"] option')].map(o => o.textContent) }));
    return [/Open/.test(r.t) && /only Morgan gets in/.test(r.t) && r.alarms.includes('House alarm'), r]; });
  await chk('PAGE-086', F.celeb, 'Celebrations: today’s birthday, coming-up previews call play_show, house switches call set_settings', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('[data-preview="Thanksgiving"]').click(); await __w(200); document.querySelector('[data-stg="birthday_shows"]').click(); await __w(200);
      return { t: $('celeb').textContent.slice(0, 120), show: (__since(n0).find(c => c[3] === 'play_show') || [])[4], set: (__since(n0).find(c => c[3] === 'set_settings') || [])[4], all: document.querySelectorAll('#celeb details [data-preview]').length }; });
    return [/Morgan’s birthday/.test(r.t) && r.show && r.show.show === 'Thanksgiving' && r.set && r.set.birthday_shows === false && r.all === 9, r]; });
  await chk('PAGE-087', F.passport, 'Passport cards for non-guests: stamps earned, “Next: … at 50 taps (33 to go)”, the full grid in a fold-out', async () => {
    const r = await f.evaluate(() => { const names = [...document.querySelectorAll('#passport .tc h3')].map(h => h.firstChild.textContent.trim()); const c = [...document.querySelectorAll('#passport .tc')].find(x => /Alex/.test(x.querySelector('h3').textContent)); const d = c.querySelector('details');
      return { names, got: [...c.querySelectorAll('.ppgot>span')].map(x => x.textContent), next: (c.querySelector('.ppnext') || {}).textContent, fold: d && d.querySelector('summary').textContent, stamps: d ? d.querySelectorAll('.stamp').length : 0, gotN: d ? d.querySelectorAll('.stamp.got').length : 0 }; });
    return [JSON.stringify(r.names) === '["Alex","Casey","Morgan"]' && r.got.length === 2 && /Next: .*Frequent visitor at 50 taps \(33 to go\)/.test(r.next) && /All 16 stamps/.test(r.fold) && r.stamps === 16 && r.gotN === 2, r]; });
  await chk('PAGE-088', F.passport, 'Passport: past the top tap stamp shows no “Next”; 243 taps → Super fan at 250 (7 to go)', async () => {
    const r = await f.evaluate(() => { const c = [...document.querySelectorAll('#passport .tc')].find(x => /Morgan/.test(x.querySelector('h3').textContent)); return (c.querySelector('.ppnext') || {}).textContent; });
    return [/Super fan at 250 taps \(7 to go\)/.test(r || ''), r]; });
  await chk('PAGE-089', F.send, 'Send bar: Blue sends {effect: color, color: blue} through the integration', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('[data-send="blue"]').click(); await __w(200); return { call: (__since(n0).find(c => c[3] === 'send') || [])[4], msg: $('send-msg').textContent }; });
    return [r.call && r.call.effect === 'color' && r.call.color === 'blue' && /Blue sent/.test(r.msg), r]; });
  await chk('PAGE-090', F.send, 'Build your own: fields follow the effect (Two colours shows Second colour, hides LEDs); Send through one bridge sends its Command entity', async () => {
    const r = await f.evaluate(async () => { $('sx').open = true; const E = $('sx-effect'); E.value = 'dual_color'; E.onchange(); const vis = id => !$(id).closest('[hidden]') && !$(id).hidden;
      const a = { c2: vis('sx-c2'), leds: vis('sx-leds'), anim: vis('sx-anim'), through: [...$('sx-bridge').options].map(o => o.textContent + '=' + o.value) };
      $('sx-bridge').value = $('sx-bridge').options[1].value; const n0 = __C(); $('sx-go').click(); await __w(200); a.call = (__since(n0).find(c => c[3] === 'send') || [])[4]; a.msg = $('sx-msg').textContent;
      E.value = 'wake'; E.onchange(); a.wakeSecs = vis('sx-secs'); $('sx-bridge').value = ''; return a; });
    return [r.c2 && !r.leds && !r.anim && r.through.length === 3 && r.call && r.call.effect === 'dual_color' && r.call.color === 'blue' && r.call.color2 === 'pink' && r.call.bridges && r.call.bridges[0] === 'text.kitchen_bridge_command' && /Sent through Kitchen Bridge/.test(r.msg) && r.wakeSecs, r]; });
  await chk('PAGE-091', F.unknown, 'New band: Assign without a person says “Pick who it’s for first”; “Someone new” needs a name; then add_person + assign_band with the nickname', async () => {
    const r = await f.evaluate(async () => { const go = document.querySelector('[data-u-go]'), k = go.dataset.uGo, msg = () => $('msg-' + k).textContent; go.click(); await __w(50); const a = { m1: msg() };
      const s = document.querySelector(`[data-u-person="${k}"]`); s.value = '__new'; s.onchange(); a.nameShown = !document.querySelector(`[data-u-new="${k}"]`).hidden; go.click(); await __w(50); a.m2 = msg();
      document.querySelector(`[data-u-new="${k}"]`).value = 'Jordan'; document.querySelector(`[data-u-label="${k}"]`).value = 'Castle'; const n0 = __C(); go.click(); await __w(400);
      a.calls = __since(n0).filter(c => c[0] === 'ws' && c[1] === 'call_service' && /add_person|assign_band/.test(c[3])).map(c => [c[3], c[4]]); return a; });
    const add = r.calls.find(c => c[0] === 'add_person'), asg = r.calls.find(c => c[0] === 'assign_band');
    return [/Pick who it’s for first/.test(r.m1) && r.nameShown && /Type their name/.test(r.m2) && add && add[1].name === 'Jordan' && asg && asg[1].person === 'Jordan' && asg[1].band === '04-99-88-77-66-55-44' && asg[1].label === 'Castle', r]; });
  await chk('PAGE-092', F.unknown, 'New bands card shows the last tap line and the band’s reader, time and tap count', async () => {
    const r = await f.evaluate(() => $('unknown').textContent); return [/04-99-88-77-66-55-44/.test(r) && /on Garage Reader/.test(r) && /3 taps/.test(r) && /Last tap: Morgan/.test(r), r.slice(0, 300)]; });
  await chk('PAGE-093', F.btonly, 'Link card: the Bluetooth-only band with a Link to… list; a MagicBand+ not heard yet is named; Link calls link_bluetooth with the chosen band', async () => {
    const r = await f.evaluate(async () => { const t = $('link').textContent, go = document.querySelector('[data-l-go]'), k = go.dataset.lGo; go.click(); await __w(50); const m1 = $('msg-' + k).textContent;
      const s = document.querySelector(`[data-l-to="${k}"]`); s.value = 'band:04-3C-4D-5E-6F-70-05'; const n0 = __C(); document.querySelector('[data-l-go]').click(); await __w(300);
      return { t: t.slice(0, 300), m1, call: (__since(n0).find(c => c[3] === 'link_bluetooth') || [])[4] }; });
    return [/MagicBand\+ 7F3C/.test(r.t) && /hasn’t been heard over Bluetooth yet \(Alex's MagicBand\)/.test(r.t) && /Pick the band or person first/.test(r.m1) && r.call && r.call.bluetooth_band === 'mb-7F3C11' && r.call.band === '04-3C-4D-5E-6F-70-05', r]; });
  await chk('PAGE-094', F.bands, 'Which kind of band?: the unknown band gets MagicBand+ / Standard buttons that set its Band type', async () => {
    const r = await f.evaluate(async () => { const b = document.querySelector('#types [data-opt="classic"]'); if (!b) return null; const txt = $('types').textContent.slice(0, 120), n0 = __C(); b.click(); await __w(200); return { txt, call: (__since(n0).find(c => c[2] === 'select_option') || [])[3] }; });
    return [r && /Old band/.test(r.txt) && r.call && r.call.entity_id === 'select.old_band_band_type' && r.call.option === 'classic', r]; });
  await chk('PAGE-095', F.bands, 'Manage: Owner + nickname Save calls assign_band; owner “nobody” calls unassign_band; Save access sends the hours and days', async () => {
    const r = await f.evaluate(async () => { const c = __band('Dog walker'); c.querySelector('details').open = true; const k = c.querySelector('[data-own-go]').dataset.ownGo; const n0 = __C();
      c.querySelector(`[data-own="${k}"]`).value = 'Casey'; c.querySelector(`[data-lab="${k}"]`).value = 'Walker'; c.querySelector('[data-own-go]').click(); await __w(200);
      const c2 = __band('Dog walker'); c2.querySelector(`[data-own="${k}"]`).value = ''; c2.querySelector('[data-own-go]').click(); await __w(200);
      const c3 = __band('Dog walker'); c3.querySelector(`[data-af="${k}"]`).value = '08:00'; c3.querySelectorAll(`[data-ad="${k}"]`)[5].checked = true; c3.querySelector('[data-acc-go]').click(); await __w(300);
      return __since(n0).filter(c => c[0] === 'ws' && c[1] === 'call_service').map(c => [c[3], c[4]]); });
    const a = r.find(c => c[0] === 'assign_band'), u = r.find(c => c[0] === 'unassign_band'), s = r.find(c => c[0] === 'set_band_access');
    return [a && a[1].person === 'Casey' && a[1].label === 'Walker' && u && u[1].band === '04-4D-5E-6F-70-81-06' && s && s[1].from === '08:00' && s[1].until === '19:00' && s[1].days.includes('sat'), r]; });
  await chk('PAGE-096', F.people, 'People: Enrol bands calls enrol (5 min, chosen reader); the enrol reader list has “any reader” plus both readers', async () => {
    const r = await f.evaluate(async () => { const s = document.querySelector('[data-enrol-on]'), opts = [...s.options].map(o => o.textContent); s.value = 'dev_r2'; s.onchange(); const n0 = __C(); document.querySelector('[data-enrol="Casey"]').click(); await __w(300);
      return { opts, call: (__since(n0).find(c => c[3] === 'enrol') || [])[4], msg: $('people-msg').textContent }; });
    return [JSON.stringify(r.opts) === '["any reader","Front Door Reader","Garage Reader"]' && r.call && r.call.person === 'Casey' && r.call.minutes === 5 && r.call.device_id === 'dev_r2' && /Tap Casey's bands/.test(r.msg), r]; });
  await chk('PAGE-097', F.people, 'Add someone: an empty name is refused; a guest is added with add_person (allowed, guest)', async () => {
    const r = await f.evaluate(async () => { $('np-name').value = ''; $('np-go').click(); await __w(50); const m1 = $('people-msg').textContent; $('np-name').value = 'Jordan'; $('np-guest').checked = true; $('np-ha').value = 'person.jordan';
      const n0 = __C(); $('np-go').click(); await __w(300); return { m1, call: (__since(n0).find(c => c[3] === 'add_person') || [])[4], m2: $('people-msg').textContent, cleared: $('np-name').value }; });
    return [/Type a name/.test(r.m1) && r.call && r.call.name === 'Jordan' && r.call.guest === true && r.call.allowed === true && r.call.ha_person === 'person.jordan' && /Jordan added/.test(r.m2) && r.cleared === '', r]; });
  await chk('PAGE-098', F.people, 'People: Home Assistant person, birthday (month + day) and welcome colour each call update_person', async () => {
    const r = await f.evaluate(async () => { window.__openAll(); const n0 = __C(); const ha = document.querySelector('[data-ha][data-p="Alex"]'); ha.value = 'person.jordan'; ha.onchange(); await __w(150);
      const bm = document.querySelector('[data-bm="Casey"]'), bdd = document.querySelector('[data-bd="Casey"]'); bm.value = '07'; bdd.value = '04'; bdd.onchange(); await __w(150);
      const wc = document.querySelector('[data-wc="Sam"]'); wc.value = 'Blue'; wc.onchange(); await __w(300); return __since(n0).filter(c => c[3] === 'update_person').map(c => c[4]); });
    return [r.some(c => c.person === 'Alex' && c.ha_person === 'person.jordan') && r.some(c => c.person === 'Casey' && c.birthday === '07-04') && r.some(c => c.person === 'Sam' && c.welcome_colour === 'Blue'), r]; });
  await chk('PAGE-099', F.welcome, 'Welcome sound (Morgan): file name, Play here (GET the sound), Play on readers (play_welcome_sound), Replace…; others get Upload…', async () => {
    const r = await f.evaluate(async () => { const w = document.querySelector('#person-Morgan .wsnd'), t = w.textContent, n0 = __C(); w.querySelector('[data-snd-play]').click(); await __w(200); w.querySelector('[data-snd-reader]').click(); await __w(200);
      return { t: t.slice(0, 80), get: __since(n0).find(c => c[0] === 'fetch' && c[2] === 'GET'), svc: (__since(n0).find(c => c[3] === 'play_welcome_sound') || [])[4], up: [...document.querySelectorAll('[data-snd-up]')].map(b => b.textContent) }; });
    return [/castle-fanfare\.mp3/.test(r.t) && r.get && r.get[1] === '/api/magicband/sound/c1b2c3d4e5f6' && r.svc && r.svc.person === 'Morgan' && r.up.filter(x => x === 'Replace…').length === 1 && r.up.filter(x => x === 'Upload…').length === 3, r]; });
  await chk('PAGE-100', F.welcome, 'Welcome sound: Remove takes a second tap and then DELETEs the sound', async () => {
    const r = await f.evaluate(async () => { const n0 = __C(); document.querySelector('#person-Morgan [data-snd-rm]').click(); await __w(60); const b = document.querySelector('#person-Morgan [data-snd-rm]'); const a = { t: b.textContent, first: __since(n0).some(c => c[2] === 'DELETE') };
      b.click(); await __w(300); a.del = __since(n0).find(c => c[0] === 'fetch' && c[2] === 'DELETE'); return a; });
    return [/Tap again to remove/.test(r.t) && !r.first && r.del && r.del[1] === '/api/magicband/sound/c1b2c3d4e5f6', r]; });
  await chk('PAGE-101', F.welcome, 'Welcome sound upload: a file over 2 MB is refused; a small file is POSTed with its name', async () => {
    const input = await f.$('#person-Casey [data-snd-file]');
    await input.setInputFiles({ name: 'big.mp3', mimeType: 'audio/mpeg', buffer: Buffer.alloc(2 * 1024 * 1024 + 10) }); await p.waitForTimeout(200);
    const m1 = await f.evaluate(() => $('people-msg').textContent); const n0 = await f.evaluate(() => __C());
    await (await f.$('#person-Casey [data-snd-file]')).setInputFiles({ name: 'chime.mp3', mimeType: 'audio/mpeg', buffer: Buffer.from('ID3') }); await p.waitForTimeout(400);
    const r = await f.evaluate(n0 => ({ post: __since(n0).find(c => c[0] === 'fetch' && c[2] === 'POST'), m2: $('people-msg').textContent }), n0);
    return [/over 2 MB/.test(m1) && r.post && r.post[1] === '/api/magicband/sound/b1b2c3d4e5f6?name=chime.mp3' && /Welcome sound saved for Casey/.test(r.m2), { m1, r }]; });
  await chk('PAGE-102', F.camera, 'Camera per reader (hint under the row) calls set_reader_camera; “kept for” days: 0 is refused (1–365), 14 calls set_snapshot_days', async () => {
    const r = await f.evaluate(async () => { const s = document.querySelector('[data-cam="dev_r2"]'); const n0 = __C(); s.value = 'camera.front_doorbell'; s.onchange(); await __w(200);
      const d = document.querySelector('[data-snapdays]'); d.value = '0'; d.onchange(); await __w(100); const a = { m: $('msg-rdbar').textContent, back: document.querySelector('[data-snapdays]').value };
      const d2 = document.querySelector('[data-snapdays]'); d2.value = '14'; d2.onchange(); await __w(300); a.calls = __since(n0).filter(c => /set_reader_camera|set_snapshot_days/.test(c[3] || '')).map(c => [c[3], c[4]]); return a; });
    const cam = r.calls.find(c => c[0] === 'set_reader_camera'), sd = r.calls.find(c => c[0] === 'set_snapshot_days');
    return [cam && cam[1].device_id === 'dev_r2' && cam[1].camera === 'camera.front_doorbell' && /1–365 days/.test(r.m) && r.back === '30' && sd && sd[1].days === 14, r]; });
  await chk('PAGE-103', F.readers, 'Reader buttons: Test welcome and Play show press the reader’s buttons; volume sets volume_level; Re-send list calls sync', async () => {
    const r = await f.evaluate(async () => { const c = __card(/Garage/), n0 = __C(); [...c.querySelectorAll('[data-press]')].forEach(b => b.click()); await __w(200); const v = __card(/Garage/).querySelector('[data-vol]'); v.value = '25'; v.dispatchEvent(new Event('change')); await __w(200);
      $('sync').click(); await __w(300); return __since(n0).map(c => [c[1], c[2], c[3]]); });
    const pressed = r.filter(c => c[1] === 'press').map(c => c[2].entity_id);
    return [pressed.includes('button.garage_reader_test_welcome') && pressed.includes('button.garage_reader_play_show') && r.some(c => c[1] === 'volume_set' && c[2].volume_level === 0.25) && r.some(c => c[2] === 'sync'), r]; });
  await chk('PAGE-104', F.autoupd, 'Reader Health has Automatic updates (switch) and Time zone (drop-down with the firmware’s zones)', async () => {
    const r = await f.evaluate(() => { const c = __card(/Front/), hp = c.querySelector('details.hp'), rows = [...hp.querySelectorAll('.row')].map(x => x.textContent.trim().slice(0, 40)), tz = hp.querySelector('select[data-sel$="time_zone"]');
      return { rows, au: !!hp.querySelector('[data-tg="switch.front_door_reader_automatic_updates"]'), tz: tz ? [...tz.options].length : 0, tzv: tz && tz.value }; });
    return [r.au && r.tz === 10 && r.tzv === 'Eastern (New York)' && r.rows.some(x => /Automatic updates/.test(x)) && r.rows.some(x => /Time zone/.test(x)), r]; });
  await chk('PAGE-105', F.autoupd, 'Bridge cards (bridge and BP2) have Automatic updates and Time zone rows', async () => {
    const r = await f.evaluate(() => [...document.querySelectorAll('#bridges > section')].map(s => ({ n: s.querySelector('h3').textContent.trim(), au: !!s.querySelector('[data-tg$="_automatic_updates"]'), tz: !!s.querySelector('select[data-sel$="_time_zone"]') })));
    return [r.length === 2 && r.every(x => x.au && x.tz), r]; });
  await chk('PAGE-106', F.autoupd, 'Time zone change calls select_option with the zone; Automatic updates toggles the switch', async () => {
    const r = await f.evaluate(async () => { const s = document.querySelector('#bridges select[data-sel="select.office_bp2_time_zone"]'); const n0 = __C(); s.value = 'UTC'; s.dispatchEvent(new Event('change')); await __w(300);
      document.querySelector('[data-tg="switch.kitchen_bridge_automatic_updates"]').click(); await __w(300); return { calls: __since(n0).map(c => [c[2], c[3]]), msg: [...document.querySelectorAll('#bridges .msg')].map(m => m.textContent).join('|') }; });
    return [r.calls.some(c => c[0] === 'select_option' && c[1].entity_id === 'select.office_bp2_time_zone' && c[1].option === 'UTC') && r.calls.some(c => c[0] === 'turn_off' && c[1].entity_id === 'switch.kitchen_bridge_automatic_updates') && /Time zone: UTC/.test(r.msg), r]; });
  await chk('PAGE-107', F.bridges, 'Bridges: Fast mode on both; Bluetooth proxy switch on the bridge that has one, “not on this bridge” on the BP2; health tiles (BP2 uptime from “3d 4h 12m”)', async () => {
    const r = await f.evaluate(() => { const k = __bridge(/Kitchen/), o = __bridge(/Office/); return { kf: !!k.querySelector('[data-tg="switch.kitchen_bridge_fast_mode"]'), of: !!o.querySelector('[data-tg="switch.office_bp2_fast_mode"]'), kp: !!k.querySelector('[data-tg="switch.kitchen_bridge_bluetooth_proxy"]'), op: /not on this bridge/.test(o.textContent),
      oh: [...o.querySelectorAll('.hl > div')].map(d => d.textContent), fw: o.querySelector('h3 small').textContent }; });
    return [r.kf && r.of && r.kp && r.op && r.oh.some(t => /Up for3 d 4 h/.test(t)) && /firmware 0\.10\.31/.test(r.fw), r]; });
  await chk('PAGE-108', F.health, 'Reader health tiles: Wi-Fi bars and quality, Up for, CPU, Memory, Loop; colours by threshold (Garage: Wi-Fi weak, CPU warm, loop slow)', async () => {
    const r = await f.evaluate(() => [...__card(/Garage/).querySelectorAll('.hl > div')].map(d => d.className + ':' + d.querySelector('span').textContent + '=' + d.querySelector('b').textContent + '/' + ((d.querySelector(':scope>i') || {}).textContent || '')));
    const has = re => r.some(x => re.test(x));
    return [has(/^b:Wi-Fi=.*−77\/weak$/) && has(/^w:Up for=50 min\/power dip$/) && has(/^w:CPU=68 °C\/warm$/) && has(/^:Memory=82 KB\/free$/) && has(/^w:Loop=1400 ms\/slowest$/), r]; });
  await chk('PAGE-109', F.readers, 'Reader status line: list state tag, last band, known bands, update available (Garage); firmware version in the title', async () => {
    const r = await f.evaluate(() => ({ g: __card(/Garage/).querySelector('.stl').textContent, f: __card(/Front/).querySelector('.stl').textContent, fw: __card(/Front/).querySelector('h3 small').textContent, err: __card(/Garage/).textContent.includes('The list was too long') }));
    return [/list not applied/.test(r.g) && /update available/.test(r.g) && /4 known bands/.test(r.g) && /list up to date/.test(r.f) && /Last band: Morgan's MagicBand\+/.test(r.f) && /Front porch · firmware 0\.10\.31/.test(r.fw) && r.err, r]; });
  await chk('PAGE-173', F.msgs, 'A failed Assign (New bands) or Link (Bluetooth) shows “Didn’t work” on that card', async () => {
    const r = await f.evaluate(async () => { window.parent.__mockReject = /^magicband\.(assign_band|link_bluetooth)$/;
      const k = document.querySelector('[data-u-go]').dataset.uGo, el = $('msg-' + k); document.querySelector(`[data-u-person="${k}"]`).value = 'Casey'; document.querySelector('[data-u-go]').click(); await __w(900);
      // evidence: where the error text went (the message line the click captured, if a redraw replaced it)
      const a = { unknown: $('unknown').textContent.match(/Didn’t work[^.]*/), capturedLineStillOnPage: el.isConnected, capturedLineText: el.textContent, lk: null };
      const l = document.querySelector('[data-l-go]'); if (l) { document.querySelector(`[data-l-to="${l.dataset.lGo}"]`).value = 'person:Casey'; l.click(); await __w(900); a.lk = $('link').textContent.match(/Didn’t work[^.]*/); }
      window.parent.__mockReject = null; a.called = window.parent.__calls.filter(c => /assign_band|link_bluetooth/.test(c[3] || '')).length; return a; });
    return [!!r.unknown && !!r.lk, r]; });
  await chk('PAGE-110', F.layout, 'Desktop 1400 px: no horizontal page scroll and nothing wider than the window (all fold-outs open)', async () => {
    const r = await f.evaluate(() => { window.__openAll(); return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, over: window.__over() }; });
    return [r.sw <= r.cw && !r.over.length, r]; }, await fullShot(p, f, 'desk-open'));
  await chk('PAGE-111', F.render, 'No console errors or page errors (desktop, controls)', async () => [!errs.length, errs]);
});
function bestShift(a, b, n) { let best = 0, bs = -1; for (let d = -n / 2; d <= n / 2; d++) { const A = new Set(a.map(i => ((i + d) % n + n) % n)); const s = b.filter(i => A.has(i)).length; if (s > bs || (s === bs && Math.abs(d) < Math.abs(best))) { bs = s; best = d; } } return bs === b.length && b.length ? best : NaN; }

// ── 4. readers listed before the service device (probe3 #1) ──
scenario('reader-first', { width: 1400, opts: { readerFirst: true } }, async ({ p, f, errs }) => {
  await chk('PAGE-112', F.unknown, 'Readers before the service device: the New bands KPI is 1 and the band waits under New bands', async () => {
    const r = await f.evaluate(() => ({ kpi: [...document.querySelectorAll('#kpis .kpi')].map(k => k.querySelector('span').textContent + '=' + k.querySelector('b').textContent).join(', '), unk: document.querySelectorAll('#unknown .item').length, people: document.querySelectorAll('#people .pc').length }));
    return [/New bands=1/.test(r.kpi) && r.unk === 1 && r.people === 4, r]; }, await elShot(p, f, '.kpis', 'readerfirst-kpis'));
  await chk('PAGE-113', F.enrol, 'The enrolment bar (from the Unknown bands sensor, found without its entity id) shows who, where and how long; Stop calls stop_enrolment', async () => {
    const r = await f.evaluate(async () => { const h = window.parent.__mbHass; h.states['sensor.magicband_unknown_bands'].attributes = Object.assign({}, h.states['sensor.magicband_unknown_bands'].attributes, { enrolling: { person: 'Casey', until: new Date(Date.now() + 180000).toISOString(), count: 1, reader: 'Garage Reader' } }); __push(); await __w(500);
      const t = $('enrol').textContent, n0 = __C(); const s = $('enrol-stop'); if (s) s.click(); await __w(200); return { t, stop: __since(n0).some(c => c[3] === 'stop_enrolment') }; });
    return [/Enrolling bands for Casey/.test(r.t) && /tap them on Garage Reader · about 3 min left · 1 added/.test(r.t) && r.stop, r]; });
  await chk('PAGE-114', F.render, 'No console errors or page errors (readers listed first)', async () => [!errs.length, errs]);
});

// ── 5. phone, touch (probe5) ──
scenario('phone-touch', { width: 390, touch: true }, async ({ p, f, errs }) => {
  await chk('PAGE-115', F.touch, 'Touch emulation: the page sees a coarse pointer', async () => [await f.evaluate(() => matchMedia('(pointer:coarse)').matches)]);
  await f.evaluate(() => window.__openAll()); await p.waitForTimeout(300);
  const pc = await f.evaluate(() => ({ tables: document.querySelectorAll('#people table').length, cards: document.querySelectorAll('#people .pc').length, over: window.__over($('people')),
    scroll: [...document.querySelectorAll('#people *')].filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible').map(e => e.className).slice(0, 5),
    cols: getComputedStyle(document.querySelector('#people .pc .pr')).gridTemplateColumns.split(' ').length, pm: getComputedStyle(document.querySelector('#people .pmset')).gridTemplateColumns.split(' ').length,
    days: [...document.querySelectorAll('#people .days')].map(d => Math.round(d.getBoundingClientRect().right)), wsnd: [...document.querySelectorAll('#people .wsnd')].map(d => Math.round(d.getBoundingClientRect().right)) }));
  await chk('PAGE-116', F.layout, 'Phone: one card per person, no table', async () => [pc.tables === 0 && pc.cards === 4, pc]);
  await chk('PAGE-117', F.layout, 'Phone: nothing in People wider than the screen, nothing scrolls sideways (fold-outs open)', async () => [!pc.over.length && !pc.scroll.length, { over: pc.over, scroll: pc.scroll }]);
  await chk('PAGE-118', F.layout, 'Phone: people stacked (2-column head, 1-column fold-outs); weekday boxes and the sound row fit', async () => [pc.cols === 2 && pc.pm === 1 && pc.days.every(x => x <= 374) && pc.wsnd.every(x => x <= 374), pc]);
  await chk('PAGE-119', F.layout, 'Phone: band facts in two columns; body font except the IDs (mono)', async () => {
    const r = await f.evaluate(() => { const c = __band("Morgan's MagicBand+"); const dds = [...c.querySelectorAll('dl.kv dd')], dts = [...c.querySelectorAll('dl.kv dt')].map(x => x.textContent); const fam = i => getComputedStyle(dds[i]).fontFamily;
      return { cols: getComputedStyle(c.querySelector('dl.kv')).gridTemplateColumns.split(' ').length, owner: fam(dts.indexOf('Owner')), nfc: fam(dts.indexOf('NFC ID')), bt: fam(dts.indexOf('Bluetooth')) }; });
    return [r.cols === 2 && !/Mono/.test(r.owner) && /Mono/.test(r.nfc) && /Mono/.test(r.bt), r]; });
  const tt = await f.evaluate(() => { const min = (sel, dim) => { const L = [...document.querySelectorAll(sel)].filter(e => e.getClientRects().length && !e.closest('[hidden]')).map(e => e.getBoundingClientRect()[dim || 'height']); return L.length ? Math.round(Math.min(...L) * 10) / 10 : null; };
    const tgs = [...document.querySelectorAll('.tg')].filter(e => e.getClientRects().length); let hit = 0; const miss = [];
    tgs.forEach(t => { t.scrollIntoView({ block: 'center' }); const r = t.getBoundingClientRect(), x = r.left + r.width / 2; const top = document.elementFromPoint(x, r.top - 5), bot = document.elementFromPoint(x, r.bottom + 5); if (top === t && bot === t) hit++; else miss.push((t.getAttribute('aria-label') || '') + ' top:' + (top && top.className) + ' bot:' + (bot && bot.className)); });
    const t0 = tgs[0].getBoundingClientRect(); window.scrollTo(0, 0);
    return { btn: min('.btn:not(.sm)'), sm: min('.btn.sm'), tgH: Math.round(t0.height), tgW: Math.round(t0.width), tgHit: hit + '/' + tgs.length, miss: miss.slice(0, 6), summary: min('details.more>summary'), cb: min('input[type=checkbox]'), cbW: min('input[type=checkbox]', 'width'),
      range: min('input[type=range]'), select: min('select'), text: min('input[type=text]:not(.nu input)'), nu: min('.sg .nu'), time: min('input[type=time]'), dt: min('input[type=datetime-local]'), num: min('input[type=number]'), spark: min('.sparkbtn'), days: min('.days label'), chip: min('#jump a'), pchip: min('#status .pchip') }; });
  await chk('PAGE-120', F.touch, 'Touch: buttons, small buttons, summaries, sliders, selects, boxes, sparkline buttons and weekday labels are at least 44 px tall', async () => {
    const k = ['btn', 'sm', 'summary', 'range', 'select', 'text', 'nu', 'time', 'dt', 'num', 'spark', 'days'], low = k.filter(x => !(tt[x] >= 44)); return [!low.length, { low, tt }]; });
  await chk('PAGE-121', F.touch, 'Touch: toggles are 52 x 32 with a 44 px touch area; checkboxes 20 px', async () => [tt.tgH === 32 && tt.tgW === 52 && tt.tgHit.split('/')[0] === tt.tgHit.split('/')[1] && tt.cb >= 20 && tt.cbW >= 20, tt]);
  // PAGE-122 (status chips 44 px on a phone) is retired: since 0.10.38 the phone hides them (PAGE-186)
  await chk('PAGE-186', F.touch, 'Phone: jump chips are at least 44 px tall; the status chips are hidden (Needs attention lists the same problems)', async () => {
    const r = await f.evaluate(() => ({ chip: Math.min(...[...document.querySelectorAll('#jump a')].map(a => a.getBoundingClientRect().height)), status: getComputedStyle($('status')).display, chips: document.querySelectorAll('#status .pchip').length }));
    return [r.chip >= 44 && r.status === 'none' && r.chips > 0, r]; });
  await chk('PAGE-123', F.taps, 'Phone: the reader moves under the band, the time stays on one line, the picture is fully shown', async () => {
    const r = await f.evaluate(() => { const td = document.querySelector('#hist td.rd'), sub = document.querySelector('#hist .rdsub'), w = document.querySelector('#hist td.when'), pic = document.querySelector('#hist td.pic .snapbtn');
      return { rd: getComputedStyle(td).display, sub: getComputedStyle(sub).display, subT: sub.textContent, nowrap: getComputedStyle(w).whiteSpace, over: window.__over($('hist')), picR: Math.round(pic.getBoundingClientRect().right), card: Math.round($('hist').getBoundingClientRect().right) }; });
    return [r.rd === 'none' && r.sub === 'block' && /^on /.test(r.subT) && r.nowrap === 'nowrap' && !r.over.length && r.picR <= r.card, r]; });
  await chk('PAGE-124', F.health, 'Phone: health tiles cut nothing; the bridge Wi-Fi tile says just the quality (dBm in the tooltip)', async () => {
    const r = await f.evaluate(() => { const cut = [...document.querySelectorAll('.hl i,.hl b,.hl span')].filter(e => e.getClientRects().length && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent);
      const wifi = [...document.querySelectorAll('#bridges .hl>div')].filter(d => /Wi-Fi/.test(d.textContent)).map(d => d.querySelector(':scope>i').textContent + ' | ' + d.title); return { cut, wifi }; });
    return [!r.cut.length && r.wifi.length && r.wifi.every(t => /^(excellent|good|fair|weak) \| Wi-Fi signal −\d+ dBm$/.test(t)), r]; });
  await chk('PAGE-125', F.layout, 'Phone: settings rows line up (number boxes, unit inside, end where the drop-downs end)', async () => {
    const r = await f.evaluate(() => { const bad = []; document.querySelectorAll('#readers .sg .set').forEach(s => { const R = [...s.children].filter(x => !x.classList.contains('lab') && !x.classList.contains('full') && x.matches('select,.nu')).map(x => Math.round(x.getBoundingClientRect().right)); if (R.length > 1 && Math.max(...R) - Math.min(...R) > 1) bad.push(R); });
      const u = document.querySelector('.sg .nu .u'); return { bad, unitInside: !!u && u.parentElement.classList.contains('nu') && getComputedStyle(u.parentElement).borderTopStyle === 'solid' }; });
    return [!r.bad.length && r.unitInside, r]; });
  await chk('PAGE-126', F.layout, 'Phone: the two night lockdown times sit together on their own line under At night', async () => {
    const r = await f.evaluate(() => { const a = document.querySelector('[data-st="lockdown_from"]').getBoundingClientRect(), b = document.querySelector('[data-st="lockdown_until"]').getBoundingClientRect(), t = document.querySelector('[data-stg="lockdown_night"]').getBoundingClientRect(), l = [...document.querySelectorAll('#rules label')].find(x => x.textContent === 'At night').getBoundingClientRect();
      return { sameLine: Math.abs(a.top - b.top) < 2, below: a.top >= t.bottom - 1 && a.top >= l.bottom - 1, right: Math.round(b.right) }; });
    return [r.sameLine && r.below && r.right <= 374, r]; });
  await chk('PAGE-127', F.twin, 'Phone: the header ring is hidden (reader 1’s card shows it) and the live line stays', async () => {
    const r = await f.evaluate(() => { const s = document.querySelector('#hero-twin svg'); return { svg: s ? getComputedStyle(s).display : 'none', live: getComputedStyle(document.querySelector('#hero-twin .tw-live')).display, txt: $('lstatus').textContent, readerTwin: !!document.querySelector('#readers .twin svg') }; });
    return [r.svg === 'none' && r.live !== 'none' && /Live/.test(r.txt) && r.readerTwin, r]; });
  await chk('PAGE-128', F.camera, 'Phone: the camera hint sits under its row (aria-describedby) and the camera drop-down isn’t squeezed', async () => {
    const r = await f.evaluate(() => { const s = document.querySelector('[data-cam]'), row = s.closest('.row'), h = row.nextElementSibling; s.style.flex = 'none'; s.style.maxWidth = 'none'; const nat = s.getBoundingClientRect().width; s.style.flex = ''; s.style.maxWidth = '';
      return { nat: Math.round(nat), oneLine: Math.abs(row.firstElementChild.getBoundingClientRect().top - s.getBoundingClientRect().top) < 12, hint: h && h.classList.contains('rowhint') ? h.textContent : null, inRow: /picture/.test(row.textContent), selW: Math.round(s.getBoundingClientRect().width), desc: s.getAttribute('aria-describedby') === h.id }; });
    return [r.hint && !r.inRow && r.selW >= r.nat - 1 && r.oneLine && r.desc, r]; });
  // PAGE-129 (KPIs in 2 columns on a phone) is retired: since 0.10.38 they're 3 compact columns (PAGE-187)
  await chk('PAGE-187', F.nav, 'Phone: KPIs in 3 compact columns, jump chips scroll sideways on one line, and Needs attention starts on the first screen', async () => {
    const r = await f.evaluate(() => { scrollTo(0, 0); return { cols: getComputedStyle($('kpis')).gridTemplateColumns.split(' ').length, wrap: getComputedStyle($('jump')).flexWrap, ox: getComputedStyle($('jump')).overflowX, attnTop: Math.round($('s-attn').getBoundingClientRect().top + scrollY) }; });
    return [r.cols === 3 && r.wrap === 'nowrap' && r.ox === 'auto' && r.attnTop < 844, r]; });
  await chk('PAGE-130', F.layout, 'Phone 390 px touch: no horizontal page scroll', async () => { const r = await f.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]); return [r[0] <= r[1], r]; });
  await chk('PAGE-131', F.layout, 'Phone 390 px touch: nothing wider than the screen (except the jump-chip scroller), every fold-out open', async () => { const o = await f.evaluate(() => { window.__openAll(); return window.__over(); }); return [!o.length, o]; }, await fullShot(p, f, 'phone-touch-open'));
  await chk('PAGE-132', F.a11y, 'Phone: every control has a label (all fold-outs open)', async () => { const u = await f.evaluate(() => window.__unlabelled()); return [!u.length, u.slice(0, 15)]; });
  await chk('PAGE-133', F.render, 'No console errors or page errors (phone, touch)', async () => [!errs.length, errs]);
});

// ── 6. dark mode, desktop and phone ──
scenario('dark-desk', { width: 1400, dark: true }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => { window.__openAll(); const c = e => { const cs = getComputedStyle(e); return window.__cr(cs.color, cs.backgroundColor); };
    const pri = [...document.querySelectorAll('.btn.pri')].map(c), seg = [...document.querySelectorAll('.seg .btn.on')].map(c);
    const on = document.querySelector('.tg.on'), knob = getComputedStyle(on, '::after').backgroundColor, track = getComputedStyle(on).backgroundColor;
    const off = document.querySelector('.tg:not(.on)'), edge = getComputedStyle(off).boxShadow.match(/rgba?\([^)]*\)/)[0];
    const h = document.querySelector('.sg .hint'), sub = document.querySelector('.pl li .sub2'), body = getComputedStyle(document.body);
    return { pri: Math.min(...pri), seg: Math.min(...seg), knob: window.__cr(knob, track), offEdge: window.__cr(edge, getComputedStyle(off.closest('.tc')).backgroundColor), offEdgeSunk: window.__cr(edge, getComputedStyle(document.querySelector('.sg')).backgroundColor),
      hint: window.__cr(getComputedStyle(h).color, getComputedStyle(h.closest('.sg')).backgroundColor), plsub: sub ? window.__cr(getComputedStyle(sub).color, getComputedStyle(sub.closest('li')).backgroundColor) : null, bodyBg: body.backgroundColor, ink: window.__cr(body.color, body.backgroundColor), scheme: getComputedStyle(document.documentElement).colorScheme }; });
  await chk('PAGE-134', F.dark, 'Dark: the page uses the dark palette (dark background, light text >= 7:1, color-scheme dark)', async () => [/rgb\(12, 18, 24\)/.test(r.bodyBg) && r.ink >= 7 && /dark/.test(r.scheme), r]);
  await chk('PAGE-135', F.dark, 'Dark: Assign/Link/Send and the active preview button reach 4.5:1', async () => [r.pri >= 4.5 && r.seg >= 4.5, r]);
  await chk('PAGE-136', F.dark, 'Dark: toggle knob on the accent >= 3:1, off edge >= 3:1 on card and settings group', async () => [r.knob >= 3 && r.offEdge >= 3 && r.offEdgeSunk >= 3, r]);
  await chk('PAGE-137', F.dark, 'Dark: hints on --sunk and attention sub-lines reach 4.5:1', async () => [r.hint >= 4.5 && (r.plsub == null || r.plsub >= 4.5), r]);
  await chk('PAGE-138', F.dark, 'Dark 1400 px: no horizontal overflow (all fold-outs open)', async () => { const o = await f.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, over: window.__over() })); return [o.sw <= o.cw && !o.over.length, o]; }, await fullShot(p, f, 'dark-desk-open'));
  await chk('PAGE-139', F.render, 'No console errors or page errors (dark, desktop)', async () => [!errs.length, errs]);
});
scenario('dark-phone', { width: 390, dark: true, touch: true }, async ({ p, f, errs }) => {
  await chk('PAGE-140', F.dark, 'Dark phone 390 px touch: no horizontal overflow, every fold-out open', async () => { const o = await f.evaluate(() => { window.__openAll(); return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, over: window.__over() }; }); return [o.sw <= o.cw && !o.over.length, o]; }, await fullShot(p, f, 'dark-phone-open'));
  await chk('PAGE-141', F.render, 'No console errors or page errors (dark, phone)', async () => [!errs.length, errs]);
});

// ── 7. nothing wrong ──
scenario('clean', { width: 1400, opts: { clean: true } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => ({ status: $('status').textContent.trim(), attn: $('attn-wrap').hidden, jump: [...document.querySelectorAll('#jump a')].map(a => a.textContent), kpi: [...document.querySelectorAll('#kpis .kpi')].map(k => k.textContent),
    endlock: !!document.querySelector('[data-endlock]'), tags: [...document.querySelectorAll('#readers > section h3')].map(h => h.textContent), unk: $('unknown').textContent }));
  await chk('PAGE-142', F.status, 'Nothing wrong: the status strip says “No problems…” and Needs attention is hidden', async () => [/No problems: readers and bridges online, lists applied/.test(r.status) && r.attn, r], await fullShot(p, f, 'clean'));
  await chk('PAGE-143', F.nav, 'Nothing wrong: six jump chips (no Needs attention); Readers OK 2 / 2 “online, list applied”; New bands 0 “none waiting”', async () =>
    [r.jump.length === 6 && !r.jump.some(j => /attention/.test(j)) && r.kpi.some(k => /Readers OK2 \/ 2online, list applied/.test(k)) && r.kpi.some(k => /New bands0none waiting/.test(k)), r]);
  await chk('PAGE-144', F.lockout, 'Nothing wrong: no End lockout now anywhere; no Locked out or Not paired tags', async () => [!r.endlock && !r.tags.some(t => /Locked out|Not paired/.test(t)), r.tags]);
  await chk('PAGE-145', F.render, 'No console errors or page errors (nothing wrong)', async () => [!errs.length, errs]);
});

// ── 8. old firmware: the newer entities don't exist ──
scenario('old-firmware', { width: 1400, opts: { oldFirmware: true } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => { window.__openAll(); const g = __card(/Garage/), fr = __card(/Front/);
    return { groups: [...fr.querySelectorAll('.sg h4')].map(h => h.firstChild.textContent.trim()), labs: [...document.querySelectorAll('#readers .sg .lab')].map(x => x.textContent), tags: g.querySelector('h3').textContent,
      hp: [...document.querySelectorAll('#readers details.hp .row')].map(x => x.textContent), br: [...document.querySelectorAll('#bridges .row')].map(x => x.textContent.trim().slice(0, 30)), fw: fr.querySelector('h3 small').textContent,
      kpi: [...document.querySelectorAll('#kpis .kpi')].find(k => /Readers OK/.test(k.textContent)).textContent, dash: [...fr.querySelectorAll('.sg .set')].some(s => /–/.test(s.textContent)), twin: !!fr.querySelector('[data-twin] svg') }; });
  await chk('PAGE-146', F.fw, 'Old firmware: settings for missing entities are left out (no Refused-tap lockout group, no circle rows, Style at night, Sound at night, Quieter volume, Band light-up power)', async () =>
    [!r.groups.includes('Refused-tap lockout') && !['Heads', 'Tail fades to', 'Direction', 'Style', 'Style at night', 'Sound at night', 'Quieter volume', 'Band light-up power'].some(l => r.labs.includes(l)) && r.labs.includes('Colour') && r.labs.includes('LED count') && !r.dash, r]);
  await chk('PAGE-147', F.fw, 'Old firmware: no Not paired / Locked out tags and no Automatic updates or Time zone rows (readers and bridges)', async () =>
    [!/Not paired|Locked out/.test(r.tags) && !r.hp.some(x => /Automatic updates|Time zone/.test(x)) && !r.br.some(x => /Automatic updates|Time zone/.test(x)), r]);
  await chk('PAGE-148', F.fw, 'Old firmware: the version shows (0.10.4); Readers OK counts only what the firmware reports (list not applied: 1 / 2); the twin still draws', async () => [/firmware 0\.10\.4/.test(r.fw) && /1 \/ 21 problem/.test(r.kpi) && r.twin, r]);
  await chk('PAGE-149', F.render, 'No console errors or page errors (old firmware)', async () => [!errs.length, errs], await fullShot(p, f, 'old-firmware'));
});

// ── 9. firmware without Automatic updates / Time zone (0.10.30) ──
scenario('no-auto-updates', { width: 1400, opts: { autoUpdates: false } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => { window.__openAll(); return { hp: [...document.querySelectorAll('#readers details.hp .row')].map(x => x.textContent), br: [...document.querySelectorAll('#bridges .row')].map(x => x.textContent.trim().slice(0, 30)),
    lock: [...document.querySelectorAll('#readers .sg h4')].some(h => /Refused-tap lockout/.test(h.textContent)), tz: document.querySelectorAll('select[data-sel$="_time_zone"]').length }; });
  await chk('PAGE-150', F.autoupd, 'Without the entities: no Automatic updates or Time zone rows on reader Health or bridge cards; the other newer settings stay', async () =>
    [!r.hp.some(x => /Automatic updates|Time zone/.test(x)) && !r.br.some(x => /Automatic updates|Time zone/.test(x)) && r.tz === 0 && r.lock, r]);
  await chk('PAGE-151', F.render, 'No console errors or page errors (no Automatic updates)', async () => [!errs.length, errs]);
});

// ── 10. a combination of knobs: night, lockdown, expired pass, RGBW, every band, night circle, no proxy, passport off, 2 unknown bands, 2 heads ──
scenario('combo', { width: 1400, opts: { night: true, lockdown: true, guestPass: 'expired', rgbw: true, everyBand: true, idleStyleGarage: 'Static', idleStyleNightGarage: 'Circle', soundAtNight: 'Normal', bridgeProxy: false, passport: false, welcomeSound: false, unknown: 2, idleHeads: 2, idleTail: 3, idleFade: 100, idleDir: 'Reverse' } }, async ({ p, f, errs }) => {
  await chk('PAGE-152', F.night, 'Night now: both readers carry a Night tag and the Night group says “Night now.”', async () => {
    const r = await f.evaluate(() => { window.__openAll(); return { tags: [...document.querySelectorAll('#readers > section h3')].map(h => /Night/.test(h.textContent)), hint: [...__card(/Front/).querySelectorAll('.sg')].find(g => /^Night/.test(g.querySelector('h4').textContent)).querySelector('.hint').textContent }; });
    return [r.tags.every(Boolean) && r.tags.length === 2 && /^Night now\. Tonight: /.test(r.hint), r]; });
  await chk('PAGE-153', F.lockdown, 'Lockdown on: the card says Lockdown (by hand); the status strip has “Lockdown is on”; it is not in the Needs attention list', async () => {
    const r = await f.evaluate(() => ({ rules: $('rules').textContent.slice(0, 80), st: [...document.querySelectorAll('#status .pchip')].map(x => x.className + ':' + x.textContent.trim()), pr: $('probs').textContent }));
    return [/Lockdown by hand/.test(r.rules) && r.st.some(s => /pchip w:• Lockdown is on/.test(s)) && !/Lockdown is on/.test(r.pr), r]; });
  await chk('PAGE-154', F.guest, 'Expired guest pass: the summary shows the past end date, 0 uses left and “not now”', async () => {
    const r = await f.evaluate(() => document.querySelector('#person-Sam .pc-n').textContent); return [/Guest · Mo We Fr 11:00–14:00 · 0 uses left · until .* · not now/.test(r), r]; });
  await chk('PAGE-155', F.rgbw, 'RGBW ring: Ring type shows RGBW warm white and the twin draws the white channel as warm white (rgb(255,235,204))', async () => {
    const r = await f.evaluate(() => ({ rt: [...__card(/Front/).querySelectorAll('select[data-sel]')].find(x => /ring_type$/.test(x.dataset.sel)).value, fills: [...new Set(__lit(__card(/Front/).querySelector('[data-twin]')).map(x => x.fill))] }));
    return [r.rt === 'RGBW warm white' && r.fills.length === 1 && r.fills[0] === 'rgb(255,235,204)', r]; });
  await chk('PAGE-156', F.every, 'Welcome every band already on: the red tag shows and picking another mode is sent straight away', async () => {
    const r = await f.evaluate(async () => { const tag = /Lets every band in/.test(__card(/Front/).querySelector('h3').textContent), s = [...__card(/Front/).querySelectorAll('select[data-sel]')].find(x => /response_mode$/.test(x.dataset.sel)), n0 = __C();
      s.value = 'Known bands only'; s.dispatchEvent(new Event('change')); await __w(300); return { tag, sent: __since(n0).some(c => c[2] === 'select_option' && c[3].option === 'Known bands only'), attn: /Lets every band in/.test($('probs').textContent) }; });
    return [r.tag && r.sent, r]; });
  await chk('PAGE-157', F.idle, 'Style Static but Style at night Circle: the circle rows show (Garage)', async () => {
    const r = await f.evaluate(() => [...__card(/Garage/).querySelectorAll('.sg .lab')].map(x => x.textContent)); return [r.includes('Heads') && r.includes('Direction'), r.slice(0, 9)]; });
  await chk('PAGE-158', F.night, 'Sound at night Normal: no Quieter volume row', async () => {
    const r = await f.evaluate(() => [...__card(/Front/).querySelectorAll('.sg .lab')].map(x => x.textContent)); return [r.includes('Sound at night') && !r.includes('Quieter volume'), r.filter(x => /night|Quieter/i.test(x))]; });
  await chk('PAGE-159', F.bridges, 'No bridge has a Bluetooth proxy switch: both say “not on this bridge”', async () => {
    const r = await f.evaluate(() => [...document.querySelectorAll('#bridges > section')].map(s => /not on this bridge/.test(s.textContent) && !s.querySelector('[data-tg$="_bluetooth_proxy"]'))); return [r.length === 2 && r.every(Boolean), r]; });
  await chk('PAGE-160', F.passport, 'Passport off: “The tap passport is off” and no cards', async () => {
    const r = await f.evaluate(() => ({ t: $('passport').textContent, n: document.querySelectorAll('#passport .tc').length })); return [/The tap passport is off/.test(r.t) && r.n === 0, r]; });
  await chk('PAGE-161', F.welcome, 'No welcome sounds: every person gets “None: the reader’s tap-in sound” and Upload…', async () => {
    const r = await f.evaluate(() => ({ none: document.querySelectorAll('#people .wsnd').length, txt: [...document.querySelectorAll('#people .wsnd')].filter(w => /None: the reader’s tap-in sound/.test(w.textContent)).length, up: [...document.querySelectorAll('[data-snd-up]')].map(b => b.textContent) }));
    return [r.none === 4 && r.txt === 4 && r.up.every(x => x === 'Upload…') && r.up.length === 4, r]; });
  await chk('PAGE-162', F.unknown, 'Two unknown bands: two cards under New bands, the KPI says 2, and the Needs attention chip counts them', async () => {
    const r = await f.evaluate(() => ({ n: document.querySelectorAll('#unknown .item').length, kpi: [...document.querySelectorAll('#kpis .kpi')].find(k => /New bands/.test(k.textContent)).textContent, jump: document.querySelector('#jump a').textContent }));
    const n = +((r.jump.match(/(\d+)$/) || [])[1]); return [r.n === 2 && /New bands2to assign/.test(r.kpi) && n >= 2, r]; });
  await chk('PAGE-163', F.idle, 'Live twin, 2 heads, tail 3, fade 100 %: 6 LEDs lit in two runs of 3, half a ring apart, all equally bright; caption “Night glow, circling”', async () => {
    const r = await f.evaluate(() => { const tw = __card(/Front/).querySelector('[data-twin]'), L = __lit(tw); return { idx: L.map(x => x.i), ops: [...new Set(L.map(x => x.op))], sub: tw.querySelector('.tw-sub').textContent }; });
    const s = new Set(r.idx), runs = r.idx.filter(i => !s.has((i + 23) % 24)), opposite = runs.length === 2 && (Math.abs(runs[0] - runs[1]) === 12);
    return [r.idx.length === 6 && runs.length === 2 && opposite && r.ops.length === 1 && /Night glow, circling/.test(r.sub), r]; });
  await chk('PAGE-164', F.idle, 'Live twin, direction Reverse: the lit runs move backwards round the ring', async () => {
    const r = await f.evaluate(async () => { const tw = __card(/Front/).querySelector('[data-twin]'); const a = __lit(tw).map(x => x.i); await __w(260); const b = __lit(tw).map(x => x.i); return { a, b }; });
    const shift = bestShift(r.a, r.b, 24); return [shift < 0 && shift >= -4, Object.assign(r, { shift })]; });
  await chk('PAGE-183', F.msgs, 'New bands: a failed Assign keeps its error under that band after another band is assigned and leaves the list, and the other band’s “Assigned” message never shows under it (messages keyed by band, not position)', async () => {
    const r = await f.evaluate(async () => { const A = '04-99-88-77-66-55-44', B = '04-77-66-55-44-33-22', h = window.parent.__mbHass, U = 'sensor.magicband_unknown_bands';
      const go = band => document.querySelector(`[data-u-go][data-band="${band}"]`), pick = band => { document.querySelector(`[data-u-person="${go(band).dataset.uGo}"]`).value = 'Casey'; };
      window.parent.__mockReject = /^magicband\.assign_band$/; pick(B); go(B).click(); await __w(900); window.parent.__mockReject = null;
      const keyB = go(B).dataset.uGo; pick(A); go(A).click(); await __w(300);
      h.states[U] = Object.assign({}, h.states[U], { state: '1', attributes: Object.assign({}, h.states[U].attributes, { bands: h.states[U].attributes.bands.filter(u => u.band === B) }) }); __push(); await __w(900);
      const item = $('unk-04776655443322'); return { keyB, items: document.querySelectorAll('#unknown .item').length, b: item ? item.textContent.replace(/\s+/g, ' ').slice(-120) : null, card: ($('msg-unk') || {}).textContent }; });
    return [r.items === 1 && /Didn’t work/.test(r.b || '') && !/Assigned/.test(r.b || '') && /Assigned 04-99-88-77-66-55-44 to Casey/.test(r.card || '') && !/^u\d+$/.test(r.keyB), r]; });
  await chk('PAGE-165', F.render, 'No console errors or page errors (combination)', async () => [!errs.length, errs], await fullShot(p, f, 'combo'));
});

// ── 11. the garage reader is offline ──
scenario('reader-offline', { width: 1400, opts: { garageOffline: true } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => { const g = __card(/Garage/); return { tags: g.querySelector('h3').textContent, st: [...document.querySelectorAll('#status .pchip')].map(x => x.textContent.trim()), kpi: [...document.querySelectorAll('#kpis .kpi')].find(k => /Readers OK/.test(k.textContent)).textContent,
    cap: g.querySelector('.tw-cap').textContent, dis: [...g.querySelectorAll('select[data-sel],[data-tg],[data-num]')].every(x => x.disabled), pr: $('probs').textContent }; });
  await chk('PAGE-166', F.offline, 'Offline reader: Offline tag, “Garage Reader is offline” first in the status strip and attention list, Readers OK 1 / 2', async () =>
    [/Offline/.test(r.tags) && /Garage Reader is offline/.test(r.st[0]) && /Garage Reader is offline/.test(r.pr) && /1 \/ 21 problem/.test(r.kpi), r]);
  await chk('PAGE-167', F.offline, 'Offline reader: its twin says “Reader offline” and its controls are disabled', async () => [r.cap === 'Reader offline' && r.dis, r]);
  await chk('PAGE-174', F.offline, 'Offline reader without the entity registry\'s platforms: still offline (the integration\'s Allowed list and Last band name are told apart by their attributes); the front reader stays online', async () => {
    const r = await f.evaluate(() => { const I = index(), D = H().devices(), g = D.find(d => d.name === 'Garage Reader'), fr = D.find(d => d.name === 'Front Door Reader');
      const bare = Object.assign({}, I, { plat: {} }); return { withPlat: online(I, g), garage: online(bare, g), front: online(bare, fr), avail: (I.byDev[g.id] || []).filter(e => avail(e)) }; });
    return [r.withPlat === false && r.garage === false && r.front === true && r.avail.length === 2, r]; });
  await chk('PAGE-168', F.render, 'No console errors or page errors (reader offline)', async () => [!errs.length, errs]);
});

// ── 12. no history (not an admin), no guest, no cameras ──
scenario('no-history', { width: 1400, opts: { history: false, guestPass: 'none', cameras: false } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => { window.__openAll(); return { hist: $('hist').textContent, sam: document.querySelector('#person-Sam').textContent, pass: [...document.querySelectorAll('#passport .tc h3')].map(h => h.firstChild.textContent.trim()), cam: !!document.querySelector('[data-cam]'), days: !!document.querySelector('[data-snapdays]') }; });
  await chk('PAGE-169', F.taps, 'History refused (Unauthorized): Recent taps says only administrators can see it', async () => [/Only administrators can see the tap history/.test(r.hist), r.hist]);
  await chk('PAGE-170', F.guest, 'Not a guest: no guest pass block, Guest switch off; non-guests get a passport (Sam has one)', async () =>
    [!/guest pass \(all their bands\)/.test(r.sam) && !!(await f.evaluate(() => document.querySelector('[data-guest="Sam"]:not(.on)'))) && r.pass.includes('Sam'), r]);
  await chk('PAGE-171', F.camera, 'No cameras in Home Assistant: no Camera row and no “kept for” box', async () => [!r.cam && !r.days, r]);
  await chk('PAGE-172', F.render, 'No console errors or page errors (no history, no cameras)', async () => [!errs.length, errs]);
});

// ── 13. the browser is in another time zone than the readers' Time zone setting ──
const TZ_NIGHT = async f => f.evaluate(() => { window.__openAll(); const card = __card(/Front/);
  const hint = [...card.querySelectorAll('.sg')].find(g => /^Night/.test(g.querySelector('h4').textContent)).querySelector('.hint').textContent;
  return { hint, browserZone: Intl.DateTimeFormat().resolvedOptions().timeZone }; });
scenario('reader-time-zone', { width: 1400, tz: 'America/Los_Angeles', opts: {} }, async ({ p, f, errs }) => {
  // the mock's sunset is 16:52 and sunrise 07:11 in the browser's zone (Los Angeles): 19:52 and 10:11 in New York
  const r = await TZ_NIGHT(f);
  await chk('PAGE-175', F.night, 'Browser in Los Angeles, reader Time zone Eastern: “Tonight” shows sunset and sunrise in the reader\'s zone (19:52, 10:11), not the browser\'s', async () =>
    [r.browserZone === 'America/Los_Angeles' && /sunset 19:52, sunrise 10:11/.test(r.hint) && /Tonight: 19:52 to 10:41/.test(r.hint), r]);
  await chk('PAGE-176', F.night, 'Without the reader\'s own Night now answer, the twin judges night in the reader\'s zone: Set hours from this hour to the next in New York is night, and from this hour to the next in Los Angeles is not', async () => {
    const t = await f.evaluate(() => { const st = H().all(), card = __card(/Front/), ids = Object.assign({}, JSON.parse(card.querySelector('[data-twin]').dataset.ids));
      delete ids['Night now']; const keys = ['Night mode', 'Night from', 'Night until'], saved = keys.map(k => st[ids[k]].state);
      const set = (from) => { st[ids['Night mode']].state = 'Set hours'; st[ids['Night from']].state = String(from); st[ids['Night until']].state = String((from + 1) % 24); return twinNight(ids); };
      const nyH = Math.floor(minsIn(new Date(), 'America/New_York') / 60), laH = new Date().getHours();
      const r = { nyH, laH, nyHour: set(nyH), laHour: set(laH), hasTz: !!ids['Time zone'] }; keys.forEach((k, i) => st[ids[k]].state = saved[i]); return r; });
    return [t.hasTz && t.nyH !== t.laH && t.nyHour === true && t.laHour === false, t]; });
  await chk('PAGE-177', F.render, 'No console errors or page errors (browser in another time zone)', async () => [!errs.length, errs]);
});
scenario('reader-time-zone-pacific', { width: 1400, tz: 'America/Los_Angeles', opts: { readerTz: 'Pacific (Los Angeles)' } }, async ({ p, f, errs }) => {
  const r = await TZ_NIGHT(f);
  await chk('PAGE-178', F.night, 'Reader Time zone Pacific and the browser in Los Angeles: “Tonight” shows the browser\'s own times (sunset 16:52, sunrise 07:11)', async () =>
    [/sunset 16:52, sunrise 07:11/.test(r.hint), r]);
});

// ── 14. the page's controls reach only MagicbHAnds devices ──
scenario('household-member', { width: 1400, opts: { admin: false, history: false, historyError: 'Unauthorized', reject: '^magicband\\.(list|list_bluetooth_bands|history|add_person|update_person|remove_person|assign_band|unassign_band|remove_band|set_guest_pass|set_settings|set_band_access|enrol|stop_enrolment|link_bluetooth|set_snapshot_days|set_reader_camera)$', rejectWith: 'Unauthorized' } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(() => ({
    note: !$('ro-note').hidden && /household member/.test($('ro-note').textContent),
    chips: [...document.querySelectorAll('#jump a')].map(a => a.textContent.replace(/\d+$/, '').trim()),
    hidden: ['s-taps', 'hist', 'rules-card', 'enrol', 'addp', 's-celeb', 'celeb', 'passport'].filter(id => $(id).offsetParent !== null),
    jobs: ['j-unknown', 'j-link', 'j-types'].filter(id => !$(id).hidden),
    enabled: [...document.querySelectorAll('#people button,#people input,#people select,#bands select,#bands button:not(.sparkbtn)')].filter(e => !e.disabled && e.offsetParent !== null).map(e => e.id || e.className).slice(0, 8),
    why: (document.querySelector('#people button[disabled]') || {}).title,
    readers: [...document.querySelectorAll('#readers .tg,#readers select')].filter(e => !e.disabled).length,
    adminCalls: window.parent.__calls.filter(c => c[0] === 'ws' && /^(list|history|list_bluetooth_bands)$/.test(c[3] || '')).length }));
  await chk('PAGE-188', F.member, 'Household member: one note at the top says what they can and can’t do', async () => [r.note, r]);
  await chk('PAGE-189', F.member, 'Household member: Recent taps, Lockdown, enrolment, Add someone, Celebrations and the passport are hidden, and Recent taps and Celebrations aren’t in the jump menu', async () =>
    [!r.hidden.length && !r.chips.includes('Recent taps') && !r.chips.includes('Celebrations') && r.chips.includes('People'), r]);
  await chk('PAGE-190', F.member, 'Household member: People and Bands controls are switched off with “Only a Home Assistant administrator can change this”; reader settings stay usable; New bands and linking jobs are hidden', async () =>
    [!r.enabled.length && /administrator/.test(r.why || '') && r.readers > 0 && !r.jobs.length, r]);
  await chk('PAGE-191', F.member, 'Household member: the page doesn’t ask Home Assistant for the administrators-only lists and history (no Unauthorized errors)', async () => [r.adminCalls === 0 && !errs.length, { calls: r.adminCalls, errs }]);
});

scenario('shim-scope', { width: 1400, opts: { strangers: true } }, async ({ p, f, errs }) => {
  const r = await f.evaluate(async () => { const n0 = __C(), tryIt = (...a) => H().call(...a).then(() => 'ok', e => String(e.message || e));
    const out = { plug: await tryIt('switch', 'turn_on', 'switch.kitchen_kettle'), wipe: await tryIt('button', 'press', 'button.front_door_reader_wipe'),
      tidy: await tryIt('button', 'press', 'button.front_door_reader_tidy'), ping: await tryIt('button', 'press', 'button.kitchen_bridge_ping'),
      bandType: await tryIt('select', 'select_option', 'select.blue_band_type', { option: 'classic' }), ring: await tryIt('light', 'turn_on', 'light.front_door_reader_ring') };
    await __w(200); out.calls = __since(n0).map(c => c[2] + ':' + (c[3] && c[3].entity_id)); return out; });
  await chk('PAGE-179', F.security, 'Controls reach only MagicbHAnds devices: a switch on another integration\'s device is refused and never called', async () =>
    [/not a MagicbHAnds device/.test(r.plug) && !r.calls.some(c => /kitchen_kettle/.test(c)), r]);
  await chk('PAGE-180', F.security, 'A reader button named Factory reset (friendly name) or Forget all bands (registry name) is refused whatever its entity id', async () =>
    [/not allowed from this page/.test(r.wipe) && /not allowed from this page/.test(r.tidy) && !r.calls.some(c => /_wipe|_tidy/.test(c)), r]);
  await chk('PAGE-181', F.security, 'The page\'s own controls still work: a bridge button, a band\'s type (the integration\'s entity), a reader\'s ring', async () =>
    [r.ping === 'ok' && r.bandType === 'ok' && r.ring === 'ok', r]);
  await chk('PAGE-182', F.render, 'No console errors or page errors (controls scope)', async () => [!errs.length, errs]);
});

// ───────── run ─────────
(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const f of fs.readdirSync(SHOTS)) if (f.endsWith('.png')) fs.unlinkSync(path.join(SHOTS, f));
  const browser = await chromium.launch();
  for (const s of SCEN) {
    if (ONLY.length && !ONLY.includes(s.name)) continue;
    console.log('\n== ' + s.name);
    let ctx;
    try { ctx = await open(browser, s.o); }
    catch (e) { console.log('   (page did not load: ' + e.message + ')'); ctx = broken(e.message); }
    try { await s.fn(ctx); }
    catch (e) { console.log('   scenario stopped: ' + e.message); results.push({ id: 'PAGE-HARNESS-' + s.name, feature: 'Harness', check: 'Scenario ' + s.name + ' ran to the end', status: 'fail', detail: clip(String(e.stack || e)) }); }
    if (ctx && ctx.ctx) await ctx.ctx.close();
  }
  await browser.close();
  const out = { stage: 'page', started: started.toISOString().replace(/\.\d+Z$/, 'Z'), finished: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    environment: { note: 'Headless Chromium (Playwright ' + require('playwright/package.json').version + '), page built by ' + H.build() + ', loaded by frontend/panel.js with the mock hass in regression/page/mock.js; all network outside the mock blocked (Google Fonts fall back to system fonts).' },
    results };
  fs.mkdirSync(OUT, { recursive: true }); fs.writeFileSync(path.join(OUT, 'page.json'), JSON.stringify(out, null, 2) + '\n');
  const n = k => results.filter(r => r.status === k).length;
  console.log(`\npage: ${n('pass')} pass, ${n('fail')} fail, ${n('skip')} skip of ${results.length} -> regression/out/page.json`);
  if (results.some(r => /^PAGE-HARNESS/.test(r.id))) process.exitCode = 2;
})().catch(e => { console.error('harness failed:', e); process.exit(1); });
