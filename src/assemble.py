"""Inject data into the app template.

Usage: python3 -I assemble.py <template> <scene> <content> <routes> <out> [--standalone | --public] [--overlay <file.json>]
  (none)        body only, for a host page that supplies <html> and <head>
  --standalone  full HTML page for local preview, with test hooks
  --public      full HTML page for GitHub Pages, without test hooks
  --overlay     JSON merged over the default texts: {"de": {...}, "en": {...}, "ideas": {id: {...}}, "walkthrough": url}
"""
import sys, json
tpl, scene, content, routes, out = sys.argv[1:6]
public = '--public' in sys.argv
standalone = '--standalone' in sys.argv or public
def j(path):
    return json.dumps(json.load(open(path)), ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
overlay = j(sys.argv[sys.argv.index('--overlay') + 1]) if '--overlay' in sys.argv else '{}'
s = open(tpl).read().replace('__OVERLAY__', overlay)
s = s.replace('__SCENE__', j(scene)).replace('__CONTENT__', j(content)).replace('__ROUTES__', j(routes))
TEST = '''
<script>
// local test hooks (not part of the public build): #overview, #poi-<id>, #koch-<role>, #tour-<id>, #event-<id>, #day
addEventListener('load', () => setTimeout(() => {
  const k = window.__kq, h = location.hash.slice(1); if (!k || !h) return;
  if (h.includes('day')) k.setDark(false);
  if (h.includes('night')) k.setDark(true);
  const m = h.replace(/(day|night)-?/, '');
  if (m === 'overview') k.flyTo(k.W(160, 20, 0), 4300, { polar: 0.7, exact: true, dur: 10 });
  if (m.startsWith('poi-')) { k.selectPoi(m.slice(4).replace('-route', '')); if (m.endsWith('-route')) setTimeout(() => document.querySelector('[data-act=route]')?.click(), 1400); }
  if (m.startsWith('koch-')) { k.selectKoch(m.slice(5).replace('-bands', '')); if (m.endsWith('bands')) setTimeout(() => document.querySelector('[data-act=bands]')?.click(), 300); }
  if (m.startsWith('event-')) k.selectEvent(m.slice(6));
  if (h.includes('en-')) document.querySelector('[data-lang=en]')?.click();
  const tb = h.match(/tab-([a-z]+)/); if (tb) document.querySelector('[data-tab=' + tb[1] + ']')?.click();
  if (m.startsWith('tour-')) { k.startTour(m.slice(5)); setTimeout(() => { const t = k.T(); if (t) { t.t = 0.55; } }, 1500); }
  setTimeout(() => console.log('KQTEST labels=' + [...document.querySelectorAll('#labels .lb')].filter(e => e.style.display !== 'none').length + ' pool=' + document.querySelectorAll('#labels .lb').length + ' errs=' + JSON.stringify(window.__kqErr)), 5000);
}, 4500));
</script>'''
DESC = ('Inoffizieller 3D-Quartieratlas von Albisrieden und Altstetten rund um das Koch-Quartier: Kitas, Spielplätze, Parks, '
        'Anlässe und Rundgänge. Open Source, von Nachbarn gemacht.')
if standalone:  # local preview / GitHub Pages: add the document skeleton a host page would add
    s = ('<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
         '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Crect width=%2732%27 height=%2732%27 rx=%277%27 fill=%27%23f2ede4%27/%3E%3Crect x=%275%27 y=%2721%27 width=%2722%27 height=%276%27 rx=%271%27 fill=%27%23d6cfc2%27/%3E%3Crect x=%2712%27 y=%274%27 width=%278%27 height=%2723%27 rx=%271%27 fill=%27%23c8955a%27/%3E%3C/svg%3E">'
         f'<meta name="description" content="{DESC}"><meta property="og:title" content="Koch-Quartier Atlas">'
         f'<meta property="og:description" content="{DESC}"><meta property="og:type" content="website">'
         '<style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
         'body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style></head><body>\n'
         + s + ('' if public else TEST) + '\n</body></html>')
open(out, 'w').write(s)
print('wrote', out, round(len(s.encode()) / 1024), 'KB')
