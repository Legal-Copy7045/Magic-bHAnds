// Shared by the page stage (regression/page/run.js) and the walkthrough (regression/walkthrough/run.js):
// builds the MagicbHAnds page exactly as custom_components/magicband/panel.py build_page() does, and opens it in
// the real sidebar panel (frontend/panel.js) with the mock `hass` (mock.js). Every request outside the mock host
// is blocked. Made-up names and IDs only: this repository is public.
'use strict';
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const MB = path.join(ROOT, 'custom_components', 'magicband'), FE = path.join(MB, 'frontend');

let BUILD = 'panel.py build_page() via python3';
function buildPage() {
  const py = `import ast, pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "build_page"][0]
ns = {"FRONTEND": pathlib.Path(sys.argv[1]).parent / "frontend", "Path": pathlib.Path}
exec(compile(ast.Module([fn], []), "panel.py", "exec"), ns)
sys.stdout.write(ns["build_page"]())`;
  try { return execFileSync('python3', ['-I', '-c', py, path.join(MB, 'panel.py')], { encoding: 'utf8', env: Object.assign({}, process.env, { PYTHONIOENCODING: 'utf-8' }), maxBuffer: 64 << 20 }); }
  catch (e) {
    BUILD = 'JavaScript copy of build_page() (python3 failed: ' + String(e.message).split('\n')[0] + ')';
    const rd = f => fs.readFileSync(path.join(FE, f), 'utf8');
    let html = rd('page.html').split('/*COMMON*/').join(rd('common.js'));
    html = html.replace('<head>', () => '<head><script>' + rd('shim.js') + '</script>\n');
    const style = rd('fonts.html') + '<style>' + rd('style.css') + '</style>\n', i = html.indexOf('</head>');
    return i >= 0 ? html.slice(0, i) + style + html.slice(i) : style + html;
  }
}
const PAGE = buildPage();
const MOCK = fs.readFileSync(path.join(__dirname, 'mock.js'), 'utf8');
const parentHtml = opts => `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0}</style><script>window.__MOCK_OPTS=${JSON.stringify(opts || {})};</script><script src="/mock.js"></script>
<script src="/magicbhands_static/panel.js"></script></head><body><script>
const el=document.createElement('magicbhands-panel'); document.body.appendChild(el); el.hass=window.__mock.hass; window.__panel=el;
// Home Assistant hands the panel a new hass (a new states object) on every change
window.__push=()=>{ const h=window.__mbHass; h.states=Object.assign({},h.states); el.hass=h; };
</script></body></html>`;

// Console messages that aren't page errors (blocked network requests, the mock's deliberate rejections).
const IGNORE = /Failed to load resource|net::ERR_|MOCK-REJECT/;

// Serve the mock host on a page: the parent page, the mock, the built page and the panel's static files.
async function route(p, o) {
  await p.route('**/*', r => {
    const u = new URL(r.request().url());
    if (u.host !== 'ha.test') return r.abort();
    if (u.pathname === '/') return r.fulfill({ contentType: 'text/html; charset=utf-8', body: parentHtml(o.opts) });
    if (u.pathname === '/mock.js') return r.fulfill({ contentType: 'text/javascript; charset=utf-8', body: MOCK });
    if (u.pathname === '/api/magicband/page') return r.fulfill({ contentType: 'text/html; charset=utf-8', body: PAGE });
    if (u.pathname.startsWith('/magicbhands_static/')) {
      const f = path.join(FE, decodeURIComponent(u.pathname.slice('/magicbhands_static/'.length)));
      if (f.startsWith(FE + path.sep) && fs.existsSync(f) && fs.statSync(f).isFile())
        return r.fulfill({ body: fs.readFileSync(f), contentType: f.endsWith('.js') ? 'text/javascript' : f.endsWith('.otf') ? 'font/otf' : 'application/octet-stream' });
    }
    return r.abort();
  });
}

// Wait for the page (inside the panel's srcdoc frame) to draw its people cards; returns the frame.
async function pageFrame(p) {
  let f = null;
  for (let i = 0; i < 150 && !f; i++) {
    const c = p.frames().find(x => x !== p.mainFrame());
    if (c) { try { if (await c.evaluate(() => !!document.querySelector('#people .pc'))) f = c; } catch (e) { /* loading */ } }
    if (!f) await p.waitForTimeout(100);
  }
  if (!f) throw new Error('the page never drew its people cards (15 s)');
  return f;
}

module.exports = { ROOT, MB, FE, PAGE, MOCK, parentHtml, IGNORE, route, pageFrame, build: () => BUILD };
