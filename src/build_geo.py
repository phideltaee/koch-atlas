"""Turn raw Overpass JSON around the Koch-Areal into a compact scene file for the 3D explorer.

Usage: python3 -I build_geo.py <raw_dir> <out_json>

Coordinates: metres, origin at the Koch Hochhaus, x = east, y = north, quantised to 0.5 m.
Everything is clipped to a circular model board of radius R.
"""
import json, math, sys, os, glob

LAT0, LON0 = 47.38254, 8.49341          # Koch Hochhaus centroid (OSM way 1501346688)
R = 1800.0                               # model board radius, metres
Q = 2.0                                  # quantisation: 1 unit = 0.5 m
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110574.0

KOCH_WAYS = {1501346688: 'hochhaus', 1501346689: 'zeilenbau', 1501346686: 'kraftwerk1', 1501346687: 'mach', 48646148: 'halle'}
BC = (160.0, 20.0)                       # board centre (shifted east so Hardbruecke fits on the board)


def proj(lat, lon):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def dist(p):
    return math.hypot(p[0] - BC[0], p[1] - BC[1])


# ---------- geometry helpers ----------
def dp(points, eps):
    """Douglas-Peucker on a polyline (list of (x,y))."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]; bx, by = points[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        best, idx = -1, -1
        for i in range(a + 1, b):
            px, py = points[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / L
            if d > best:
                best, idx = d, i
        if best > eps:
            keep[idx] = True
            stack.append((a, idx)); stack.append((idx, b))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring, eps):
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return ring
    # split the closed ring at the farthest point from ring[0] so DP has two anchors
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    a = dp(ring[:far + 1], eps)
    b = dp(ring[far:] + [ring[0]], eps)
    out = a[:-1] + b[:-1]
    return out


def area(ring):
    s = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % len(ring)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def centroid(ring):
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def pip(pt, ring):
    x, y = pt; inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


CLIP = [(BC[0] + R * math.cos(2 * math.pi * i / 160), BC[1] + R * math.sin(2 * math.pi * i / 160)) for i in range(160)]


def clip_poly(ring):
    """Sutherland-Hodgman against the (convex, CCW) board polygon."""
    out = ring
    for i in range(len(CLIP)):
        if not out:
            break
        A = CLIP[i]; B = CLIP[(i + 1) % len(CLIP)]
        def inside(p):
            return (B[0] - A[0]) * (p[1] - A[1]) - (B[1] - A[1]) * (p[0] - A[0]) >= 0
        def inter(p, q):
            x1, y1 = p; x2, y2 = q; x3, y3 = A; x4, y4 = B
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-12:
                return q
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        inp = out; out = []
        for j in range(len(inp)):
            P = inp[j]; Qp = inp[(j + 1) % len(inp)]
            if inside(Qp):
                if not inside(P):
                    out.append(inter(P, Qp))
                out.append(Qp)
            elif inside(P):
                out.append(inter(P, Qp))
    return out


def clip_line(pts):
    """Split a polyline into pieces inside the board (cuts at the circle)."""
    pieces, cur = [], []
    def edge(p, q):
        # point on segment p->q at the circle boundary
        lo, hi = 0.0, 1.0
        pin = dist(p) <= R
        for _ in range(30):
            m = (lo + hi) / 2
            x = (p[0] + (q[0] - p[0]) * m, p[1] + (q[1] - p[1]) * m)
            if (dist(x) <= R) == pin:
                lo = m
            else:
                hi = m
        return (p[0] + (q[0] - p[0]) * lo, p[1] + (q[1] - p[1]) * lo)
    for i, p in enumerate(pts):
        if dist(p) <= R:
            if not cur and i > 0:
                cur.append(edge(p, pts[i - 1]))
            cur.append(p)
        else:
            if cur:
                cur.append(edge(pts[i - 1], p))
                pieces.append(cur); cur = []
    if cur:
        pieces.append(cur)
    return [c for c in pieces if len(c) >= 2]


def enc(ring):
    """Quantise + delta-encode a ring/polyline -> flat int list."""
    out = []; px = py = 0
    for x, y in ring:
        qx, qy = int(round(x * Q)), int(round(y * Q))
        out += [qx - px, qy - py]; px, py = qx, qy
    return out


def num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace('m', '').replace(',', '.').split(';')[0].strip())
    except ValueError:
        return None


def assemble(members):
    """Stitch relation member ways into closed rings."""
    segs = [[(p['lat'], p['lon']) for p in m['geometry']] for m in members if m.get('geometry')]
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i); changed = True
                break
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def polys_of(el):
    """Return list of (outer, [inners]) in lat/lon for a way or multipolygon relation."""
    if el['type'] == 'way':
        g = el.get('geometry')
        if not g or len(g) < 4:
            return []
        return [([(p['lat'], p['lon']) for p in g], [])]
    outers = assemble([m for m in el.get('members', []) if m.get('role') in ('outer', '')])
    inners = assemble([m for m in el.get('members', []) if m.get('role') == 'inner'])
    res = []
    for o in outers:
        po = [proj(*p) for p in o]
        mine = [i for i in inners if pip(proj(*i[0]), po)]
        res.append((o, mine))
    return res


# ---------- buildings ----------
DEFAULT_H = {
    'house': 8, 'detached': 8, 'semidetached_house': 8, 'terrace': 9, 'residential': 14, 'apartments': 15,
    'garage': 3, 'garages': 3, 'shed': 2.5, 'carport': 2.6, 'hut': 2.5, 'kiosk': 3, 'service': 4, 'transformer_tower': 6,
    'industrial': 10, 'warehouse': 10, 'commercial': 14, 'office': 16, 'retail': 9, 'supermarket': 8,
    'school': 12, 'kindergarten': 5, 'university': 14, 'church': 16, 'chapel': 8, 'civic': 12, 'public': 12,
    'hospital': 18, 'train_station': 10, 'transportation': 8, 'sports_hall': 10, 'sports_centre': 10, 'stadium': 18,
    'grandstand': 15, 'hotel': 20, 'construction': 12, 'roof': 4, 'yes': 11,
}
PUBLIC = {'school', 'kindergarten', 'university', 'church', 'chapel', 'civic', 'public', 'hospital', 'train_station',
          'transportation', 'sports_hall', 'sports_centre', 'stadium', 'grandstand', 'college', 'library', 'museum'}
WORK = {'industrial', 'warehouse', 'commercial', 'office', 'retail', 'supermarket', 'service', 'hotel', 'manufacture'}
SMALL = {'garage', 'garages', 'shed', 'carport', 'hut', 'kiosk', 'roof', 'transformer_tower'}


def height_of(t):
    h = num(t.get('height'))
    lv = num(t.get('building:levels'))
    if h is None and lv is not None:
        h = lv * 3.1 + 1.2 + (num(t.get('roof:levels')) or 0) * 1.8
    mh = num(t.get('min_height'))
    ml = num(t.get('building:min_level'))
    if mh is None and ml is not None:
        mh = ml * 3.1
    return h, (mh or 0.0)


def build_buildings(raw):
    files = sorted(glob.glob(os.path.join(raw, 'b[0-9].json')) + glob.glob(os.path.join(raw, 'e[0-9].json')))
    seen, outlines, parts = set(), [], []
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:
            continue
        for el in d.get('elements', []):
            key = (el['type'], el['id'])
            if key in seen:
                continue
            seen.add(key)
            t = el.get('tags', {})
            for outer, inners in polys_of(el):
                po = [proj(*p) for p in outer]
                c = centroid(po)
                if dist(c) > R - 8:
                    continue
                rec = {'id': el['id'], 't': t, 'outer': po, 'inners': [[proj(*p) for p in i] for i in inners], 'c': c}
                (parts if 'building:part' in t and 'building' not in t else outlines).append(rec)
    print('outlines', len(outlines), 'parts', len(parts))
    # enrich missing heights from parts
    for b in outlines:
        h, _ = height_of(b['t'])
        if h is None:
            hs = [height_of(p['t'])[0] for p in parts if pip(p['c'], b['outer']) and height_of(p['t'])[0]]
            if hs:
                b['t'] = dict(b['t'], height=str(max(hs)))
    out, koch, stats = [], [], {'h_tag': 0, 'lv': 0, 'default': 0}
    for b in outlines:
        t = b['t']; typ = t.get('building', 'yes')
        h, mh = height_of(t)
        if h is not None:
            stats['h_tag' if 'height' in t else 'lv'] += 1
        else:
            h = DEFAULT_H.get(typ, 11); stats['default'] += 1
        h = max(2.5, min(h, 140.0))
        if typ == 'roof':
            mh = max(mh, h - 0.6)
        ring = simplify_ring(b['outer'], 0.35)
        if len(ring) < 3 or abs(area(ring)) < 6:
            continue
        if area(ring) < 0:
            ring = ring[::-1]                  # CCW outer
        inners = []
        for i in b['inners']:
            ir = simplify_ring(i, 0.35)
            if len(ir) >= 3 and abs(area(ir)) > 4:
                inners.append(ir if area(ir) < 0 else ir[::-1])   # CW holes
        cat = 0
        if typ in PUBLIC: cat = 2
        elif typ in WORK: cat = 1
        elif typ in SMALL: cat = 3
        if typ == 'construction': cat = 5
        name = t.get('name')
        if b['id'] in KOCH_WAYS:
            koch.append({'role': KOCH_WAYS[b['id']], 'ring': enc(ring), 'n': len(ring), 'h': round(h, 1)})
            continue
        rec = [int(round(h * Q)), int(round(mh * Q)), cat, len(inners)]
        rec += [len(ring)] + enc(ring)
        for ir in inners:
            rec += [len(ir)] + enc(ir)
        out.append(rec)
    print('buildings kept', len(out), stats, 'koch', [k['role'] for k in koch])
    return out, koch


# ---------- land, roads, rail, water ----------
GREEN = {
    ('leisure', 'park'): 'park', ('leisure', 'garden'): 'garden', ('leisure', 'playground'): 'play',
    ('leisure', 'pitch'): 'pitch', ('leisure', 'recreation_ground'): 'park', ('leisure', 'sports_centre'): 'sport',
    ('leisure', 'stadium'): 'sport', ('leisure', 'swimming_pool'): 'pool',
    ('landuse', 'grass'): 'grass', ('landuse', 'meadow'): 'grass', ('landuse', 'village_green'): 'grass',
    ('landuse', 'recreation_ground'): 'park', ('landuse', 'forest'): 'forest', ('natural', 'wood'): 'forest',
    ('natural', 'scrub'): 'scrub', ('natural', 'grassland'): 'grass', ('landuse', 'allotments'): 'allot',
    ('landuse', 'cemetery'): 'cemetery', ('landuse', 'orchard'): 'grass', ('landuse', 'farmland'): 'farm',
    ('landuse', 'railway'): 'rail', ('landuse', 'construction'): 'constr',
    ('natural', 'water'): 'water', ('waterway', 'riverbank'): 'water',
}
AREA_ORDER = ['farm', 'grass', 'rail', 'constr', 'cemetery', 'allot', 'forest', 'scrub', 'park', 'garden', 'sport', 'pitch', 'play', 'pool', 'water']
ROAD_W = {'motorway': 0, 'trunk': 0, 'motorway_link': 1, 'trunk_link': 1, 'primary': 1, 'primary_link': 2, 'secondary': 2,
          'secondary_link': 3, 'tertiary': 3, 'unclassified': 4, 'residential': 4, 'living_street': 5, 'pedestrian': 5,
          'service': 6, 'footway': 7, 'cycleway': 7, 'path': 7}


def build_land(raw):
    d = json.load(open(os.path.join(raw, 'land.json')))
    areas = {k: [] for k in AREA_ORDER}
    roads, rails, trams, rivers = [], [], [], []
    names = {}
    for el in d['elements']:
        t = el.get('tags', {})
        kind = None
        for (k, v), cls in GREEN.items():
            if t.get(k) == v:
                kind = cls; break
        hw = t.get('highway'); rw = t.get('railway'); ww = t.get('waterway')
        if kind and (el['type'] == 'relation' or (el.get('geometry') and el['geometry'][0] == el['geometry'][-1])):
            for outer, inners in polys_of(el):
                po = [proj(*p) for p in outer]
                if min(dist(p) for p in po) > R:
                    continue
                ring = simplify_ring(po, 0.8 if kind != 'water' else 1.0)
                if area(ring) < 0:
                    ring = ring[::-1]
                ring = clip_poly(ring)
                if len(ring) < 3 or abs(area(ring)) < 12:
                    continue
                holes = []
                for i in inners:
                    ir = simplify_ring([proj(*p) for p in i], 0.8)
                    if len(ir) >= 3 and max(dist(p) for p in ir) < R and abs(area(ir)) > 10:
                        holes.append(ir if area(ir) < 0 else ir[::-1])
                rec = [len(holes), len(ring)] + enc(ring)
                for h in holes:
                    rec += [len(h)] + enc(h)
                areas[kind].append(rec)
                if t.get('name') and kind in ('park', 'cemetery', 'forest', 'sport', 'allot', 'water'):
                    names.setdefault(t['name'], (kind, centroid(ring), abs(area(ring))))
            continue
        if el['type'] != 'way' or not el.get('geometry'):
            continue
        pts = [proj(p['lat'], p['lon']) for p in el['geometry']]
        if hw in ROAD_W:
            if t.get('tunnel') in ('yes', 'building_passage') or t.get('area') == 'yes':
                continue
            if hw in ('footway', 'path', 'cycleway') and t.get('footway') in ('sidewalk', 'crossing'):
                continue
            layer = int(num(t.get('layer')) or 0) if t.get('bridge') in ('yes', 'viaduct') else 0
            for piece in clip_line(pts):
                piece = dp(piece, 0.7)
                roads.append([ROAD_W[hw], max(0, min(layer, 3)), len(piece)] + enc(piece))
        elif rw in ('rail',) and t.get('tunnel') != 'yes':
            if t.get('service') in ('yard', 'siding', 'spur') and len(pts) < 3:
                pass
            layer = int(num(t.get('layer')) or 0) if t.get('bridge') == 'yes' else 0
            for piece in clip_line(pts):
                piece = dp(piece, 0.8)
                rails.append([max(0, min(layer, 3)), len(piece)] + enc(piece))
        elif rw in ('tram', 'light_rail') and t.get('tunnel') != 'yes':
            for piece in clip_line(pts):
                piece = dp(piece, 0.6)
                trams.append([len(piece)] + enc(piece))
        elif ww in ('river', 'stream', 'canal') and t.get('tunnel') not in ('culvert', 'yes'):
            for piece in clip_line(pts):
                piece = dp(piece, 1.0)
                rivers.append([1 if ww == 'river' else 0, len(piece)] + enc(piece))
    print({k: len(v) for k, v in areas.items()}, 'roads', len(roads), 'rails', len(rails), 'trams', len(trams), 'rivers', len(rivers))
    named = sorted(names.items(), key=lambda kv: -kv[1][2])[:60]
    return areas, roads, rails, trams, rivers, [[n, k, round(c[0]), round(c[1])] for n, (k, c, a) in named]


def build_points(raw):
    d = json.load(open(os.path.join(raw, 'points.json')))
    trees, recyc, stops, stations, bikes, cars, water = [], [], {}, [], [], [], []
    for el in d['elements']:
        t = el.get('tags', {})
        lat = el.get('lat') or el.get('center', {}).get('lat'); lon = el.get('lon') or el.get('center', {}).get('lon')
        if lat is None:
            continue
        p = proj(lat, lon)
        if dist(p) > R - 5:
            continue
        q = [int(round(p[0] * Q)), int(round(p[1] * Q))]
        if t.get('natural') == 'tree':
            trees.append(q)
        elif t.get('amenity') == 'recycling':
            kinds = sorted(k.split(':', 1)[1] for k, v in t.items() if k.startswith('recycling:') and v == 'yes')
            recyc.append(q + [t.get('recycling_type', ''), ','.join(kinds), t.get('name', '')])
        elif t.get('railway') == 'station':
            stations.append(q + [t.get('name', '')])
        elif t.get('highway') == 'bus_stop' or t.get('railway') == 'tram_stop' or t.get('public_transport') == 'platform':
            n = t.get('name')
            if not n:
                continue
            refs = t.get('route_ref', '')
            s = stops.setdefault(n, {'xs': [], 'ys': [], 'refs': set(), 'tram': False})
            s['xs'].append(q[0]); s['ys'].append(q[1])
            s['refs'].update(r.strip() for r in refs.replace(',', ';').split(';') if r.strip())
            if t.get('railway') == 'tram_stop' or t.get('tram') == 'yes':
                s['tram'] = True
        elif t.get('amenity') == 'bicycle_rental':
            bikes.append(q + [t.get('network', t.get('operator', '')), t.get('name', '')])
        elif t.get('amenity') == 'car_sharing':
            cars.append(q + [t.get('operator', t.get('network', '')), t.get('name', '')])
        elif t.get('amenity') == 'drinking_water':
            water.append(q)
    stops_l = []
    for n, s in stops.items():
        def key(r):
            return (0, int(r)) if r.isdigit() else (1, r)
        stops_l.append([round(sum(s['xs']) / len(s['xs'])), round(sum(s['ys']) / len(s['ys'])), n.replace('Zürich, ', ''),
                        ' '.join(sorted(s['refs'], key=key)), 1 if s['tram'] else 0])
    print('trees', len(trees), 'recycling', len(recyc), 'stops', len(stops_l), 'stations', len(stations), 'bikes', len(bikes), 'cars', len(cars), 'fountains', len(water))
    return trees, recyc, stops_l, stations, bikes, cars, water


def main():
    raw, out = sys.argv[1], sys.argv[2]
    b, koch = build_buildings(raw)
    areas, roads, rails, trams, rivers, names = build_land(raw)
    trees, recyc, stops, stations, bikes, cars, water = build_points(raw)
    scene = {'origin': [LAT0, LON0], 'R': R, 'bc': BC, 'q': Q, 'b': b, 'koch': koch, 'areas': areas, 'roads': roads,
             'rails': rails, 'trams': trams, 'rivers': rivers, 'names': names, 'trees': trees, 'recycling': recyc,
             'stops': stops, 'stations': stations, 'bikes': bikes, 'carshare': cars, 'fountains': water}
    s = json.dumps(scene, separators=(',', ':'), ensure_ascii=False)
    open(out, 'w').write(s)
    print('wrote', out, round(len(s) / 1024), 'KB')
    for k in ['b', 'areas', 'roads', 'rails', 'trees']:
        print('  ', k, round(len(json.dumps(scene[k], separators=(',', ':'))) / 1024), 'KB')


if __name__ == '__main__':
    main()
