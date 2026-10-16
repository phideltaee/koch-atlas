"""Merge researched places/events into the explorer's content file and route the guided walks.

Usage: python3 -I build_content.py <research_dir> <raw_dir> <out_json>
"""
import json, math, sys, os, time, urllib.request

LAT0, LON0 = 47.38254, 8.49341
KX = 111320.0 * math.cos(math.radians(LAT0)); KY = 110574.0
BC, R = (160.0, 20.0), 1800.0
HOME = (47.382572, 8.493407)   # Flurstrasse 71, official address point


def proj(lat, lon):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


GROUP = {'kita': 'kita', 'kindergarten': 'school', 'school': 'school', 'playground': 'play', 'park': 'green',
         'nature': 'green', 'pool': 'sport', 'sport': 'sport', 'library': 'culture', 'culture': 'culture',
         'history': 'culture', 'landmark': 'culture', 'food': 'food', 'market': 'food', 'shop': 'food',
         'community': 'community', 'health': 'health', 'transport': 'mobility', 'sharing': 'mobility'}

# places that get a permanent label on the model
FEATURED = {'koch-park', 'kohlenlagerhalle', 'stadion-letzigrund', 'freibad-letzigraben', 'bahnhof-altstetten',
            'bahnhof-hardbruecke', 'gz-bachwiesen', 'lindenplatz-wochenmarkt', 'friedhof-sihlfeld', 'hardaupark',
            'albisrieden-dorfkern', 'letzipark', 'freilager-albisrieden', 'gz-loogarten', 'hallenbad-altstetten',
            'kita-bethanien-altstetten', 'spielplatz-koch-park', 'pfingstweidpark', 'bachwiesenpark'}


def merge_pois(research):
    fam = json.load(open(os.path.join(research, 'pois-family.json')))
    qua = json.load(open(os.path.join(research, 'pois-quartier.json')))
    by = {}
    for src in (fam, qua):
        for p in src:
            if p['id'] in by:
                o = by[p['id']]
                if len(str(p.get('desc_de') or '')) > len(str(o.get('desc_de') or '')):
                    o['desc_de'], o['desc_en'] = p.get('desc_de'), p.get('desc_en')   # DE and EN from the same record
                for k in ('address', 'url'):
                    if len(str(p.get(k) or '')) > len(str(o.get(k) or '')):
                        o[k] = p[k]
                o['tags'] = sorted(set(o.get('tags', [])) | set(p.get('tags', [])))
                o['details'] = {**(p.get('details') or {}), **(o.get('details') or {})}
            else:
                by[p['id']] = dict(p)
    out = []
    for p in by.values():
        if p['id'] == 'koch-quartier':
            continue                              # the model itself shows the Koch-Quartier
        x, y = proj(p['lat'], p['lon'])
        g = GROUP.get(p['cat'], 'community')
        det = p.get('details') or {}
        keep = {}
        for k in ('ages', 'hours', 'opening_hours', 'price_day', 'price', 'subsidised', 'subsidized', 'labels', 'languages',
                  'operator', 'phone', 'status', 'lines', 'waitlist', 'places', 'note', 'when'):
            v = det.get(k)
            if v not in (None, '', [], {}):
                keep[k] = v if not isinstance(v, list) else ', '.join(map(str, v))
        rec = {'id': p['id'], 'n': p['name'], 'g': g, 'c': p['cat'], 'x': round(x, 1), 'y': round(y, 1),
               'w': p.get('walk_min'), 'a': p.get('address') or '', 'dd': p.get('desc_de') or '', 'de': p.get('desc_en') or '',
               'u': p.get('url') or '', 's': p.get('source') or '', 't': [t for t in (p.get('tags') or [])][:8]}
        if keep:
            rec['d'] = keep
        if p.get('approx'):
            rec['ap'] = 1
        if p['id'] in FEATURED:
            rec['f'] = 1
        if math.hypot(x - BC[0], y - BC[1]) > R - 25:
            rec['out'] = 1
        out.append(rec)
    out.sort(key=lambda r: (r['w'] if r['w'] is not None else 999))
    return out


def events(research):
    ev = json.load(open(os.path.join(research, 'events.json')))
    out = []
    for e in ev:
        rec = {'id': e['id'], 'n': e['name'], 'r': e['recurrence'], 'wd': e.get('when_de') or '', 'we': e.get('when_en') or '',
               'ds': e.get('date_start'), 'dz': e.get('date_end'), 'm': e.get('month'), 'v': e.get('venue') or '',
               'dd': e.get('desc_de') or '', 'de': e.get('desc_en') or '', 'fam': bool(e.get('family_friendly')),
               'u': e.get('url') or ''}
        if e.get('lat') and e.get('lon'):
            x, y = proj(e['lat'], e['lon']); rec['x'] = round(x, 1); rec['y'] = round(y, 1)
        out.append(rec)
    return out


def osrm(a, b, prof='foot'):
    url = (f"https://routing.openstreetmap.de/routed-{prof}/route/v1/{prof}/{a[1]},{a[0]};{b[1]},{b[0]}"
           f"?overview=full&geometries=geojson")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'koch-quartier-research/1.0'})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.load(r)
            rt = d['routes'][0]
            return rt['geometry']['coordinates'], rt['distance'], rt['duration']
        except Exception as ex:
            print('osrm retry', attempt, ex); time.sleep(2 + attempt * 2)
    raise RuntimeError('osrm failed')


def bus83(raw, start, end):
    """Slice the bus 83 path (Altstetten -> Milchbuck) between two points, using OSM route relation 5583695."""
    d = json.load(open(os.path.join(raw, 'routes_geom.json')))
    rel = [e for e in d['elements'] if e['id'] == 5583695][0]
    ways = [[(p['lat'], p['lon']) for p in m['geometry']] for m in rel['members'] if m['type'] == 'way' and m.get('geometry') and m.get('role', '') in ('', 'forward', 'backward')]
    line = list(ways[0])
    for w in ways[1:]:
        if line[-1] == w[0]: line += w[1:]
        elif line[-1] == w[-1]: line += w[::-1][1:]
        elif line[0] == w[-1] and len(line) == len(ways[0]): line = w[:-1] + line
        elif line[0] == w[0] and len(line) == len(ways[0]): line = w[::-1][:-1] + line
        else:
            # gap: just continue with the nearer end
            da = (line[-1][0] - w[0][0]) ** 2 + (line[-1][1] - w[0][1]) ** 2
            db = (line[-1][0] - w[-1][0]) ** 2 + (line[-1][1] - w[-1][1]) ** 2
            line += w if da <= db else w[::-1]
    def near(pt):
        return min(range(len(line)), key=lambda i: (line[i][0] - pt[0]) ** 2 + ((line[i][1] - pt[1]) * 0.68) ** 2)
    i, j = near(start), near(end)
    seg = line[i:j + 1] if i <= j else line[j:i + 1][::-1]
    return [[lon, lat] for lat, lon in seg]


def to_xy(coords):
    pts = []
    for lon, lat in coords:
        x, y = proj(lat, lon)
        if not pts or math.hypot(x - pts[-1][0], y - pts[-1][1]) > 1.5:
            pts.append([round(x, 1), round(y, 1)])
    return pts


TOURS = [
    {'id': 'arbeitsweg', 'icon': 'commute',
     'n_de': 'Kita-Morgen & Arbeitsweg', 'n_en': 'Kita morning & commute',
     'sum_de': 'Vom Hochhaus in die Kita, mit dem 83er zur Hardbrücke, dann 5 Minuten S-Bahn nach Oerlikon. Tür zu Tür rund 25 Minuten.',
     'sum_en': 'From the tower to the Kita, bus 83 to Hardbrücke, then 5 minutes by S-Bahn to Oerlikon. About 25 minutes door to door.',
     'legs': [
         {'mode': 'foot', 'to': 'kita-bethanien-altstetten', 'de': 'Vier Minuten zu Fuss zur Kita Bethanien an der Buckhauserstrasse. Gemeinnützig, mit wöchentlichem Naturtag.', 'en': 'Four minutes on foot to Kita Bethanien on Buckhauserstrasse. Non-profit, with a weekly nature day.'},
         {'mode': 'foot', 'to': 'bus-flurstrasse', 'de': 'Weiter zur Haltestelle Flurstrasse. Der 83er fährt am Morgen alle 7 bis 8 Minuten.', 'en': 'On to the Flurstrasse stop. In the morning bus 83 runs every 7 to 8 minutes.'},
         {'mode': 'bus', 'to': 'bahnhof-hardbruecke', 'de': 'Mit dem Bus 83 in rund 11 Minuten zum Bahnhof Hardbrücke.', 'en': 'Bus 83 takes about 11 minutes to Hardbrücke station.'},
     ],
     'tail_de': 'Ab Hardbrücke fahren S6, S7, S9, S15, S16 und S21 in 5 Minuten nach Oerlikon.',
     'tail_en': 'From Hardbrücke the S6, S7, S9, S15, S16 and S21 reach Oerlikon in 5 minutes.'},
    {'id': 'samstag', 'icon': 'basket',
     'n_de': 'Samstag im Quartier', 'n_en': 'Saturday in the quarter',
     'sum_de': 'Markt am Lindenplatz, Bücher in der PBZ, Tiere und Bach im GZ Bachwiesen, zurück durch den Koch-Park.',
     'sum_en': 'Market at Lindenplatz, books at the PBZ library, animals and the stream at GZ Bachwiesen, back through Koch-Park.',
     'legs': [
         {'mode': 'foot', 'to': 'kohlenlagerhalle', 'de': 'Erst durch die Kohlenlagerhalle: das denkmalgeschützte Dach mit «Kohlen Koch Heizoel» ist rund um die Uhr offen.', 'en': 'First through the old coal hall: the listed roof with its "Kohlen Koch Heizoel" lettering is open around the clock.'},
         {'mode': 'foot', 'to': 'lindenplatz-wochenmarkt', 'de': 'Zum Wochenmarkt am Lindenplatz, jeden Samstag von 6 bis 12 Uhr.', 'en': 'To the weekly market at Lindenplatz, every Saturday from 6 to 12.'},
         {'mode': 'foot', 'to': 'pbz-altstetten', 'de': 'Bilderbücher holen in der PBZ Bibliothek Altstetten.', 'en': 'Pick up picture books at the PBZ library in Altstetten.'},
         {'mode': 'foot', 'to': 'gz-bachwiesen', 'de': 'Im GZ Bachwiesen gibt es Tiere, einen Bach und im Sommer ein Planschbecken.', 'en': 'GZ Bachwiesen has animals, a stream and a paddling pool in summer.'},
         {'mode': 'foot', 'to': 'spielplatz-koch-park', 'de': 'Zum Schluss der Sandspielplatz im Koch-Park, zwei Minuten vor der Haustür.', 'en': 'Last stop: the sand playground in Koch-Park, two minutes from the front door.'},
     ]},
    {'id': 'gruen', 'icon': 'leaf',
     'n_de': 'Grüne Runde mit Kinderwagen', 'n_en': 'Green loop with a stroller',
     'sum_de': 'Koch-Park, Letzibad, Heiligfeld, Friedhof Sihlfeld und Hardaupark: flach, schattig und gut mit dem Kinderwagen.',
     'sum_en': 'Koch-Park, Letzibad, Heiligfeld, Sihlfeld cemetery and Hardaupark: flat, shady and easy with a stroller.',
     'legs': [
         {'mode': 'foot', 'to': 'koch-park', 'de': 'Start im Koch-Park: rund 12 000 m², etwa 200 Bäume, Konzept «Jardin Sauvage».', 'en': 'Start in Koch-Park: about 12,000 m², around 200 trees, designed as a "jardin sauvage".'},
         {'mode': 'foot', 'to': 'freibad-letzigraben', 'de': 'Am Freibad Letzigraben vorbei, dem Max-Frisch-Bad mit grosser Liegewiese.', 'en': 'Past the Letzigraben open-air pool, the Max Frisch pool with its big lawn.'},
         {'mode': 'foot', 'to': 'spielplatz-heiligfeld', 'de': 'Spielplatz Heiligfeld im Grünzug zwischen den Wohnhäusern.', 'en': 'Heiligfeld playground in the green strip between the housing blocks.'},
         {'mode': 'foot', 'to': 'friedhof-sihlfeld', 'de': 'Durch den Friedhof Sihlfeld, einen der grössten Parks der Stadt.', 'en': 'Through Sihlfeld cemetery, one of the largest green spaces in the city.'},
         {'mode': 'foot', 'to': 'hardaupark', 'de': 'Hardaupark mit dem Weidendschungel-Spielplatz.', 'en': 'Hardaupark with its willow-jungle playground.'},
         {'mode': 'foot', 'to': '@home', 'de': 'Zurück über das Letzigrund-Quartier.', 'en': 'Back past the Letzigrund stadium.'},
     ]},
    {'id': 'dorf', 'icon': 'church',
     'n_de': 'Albisrieder Dorfspaziergang', 'n_en': 'Albisrieden village walk',
     'sum_de': 'Vom neuen Quartier ins alte Dorf: Bachwiesen, Alte Mühle, Quartiertanne, Alte Kirche und Ortsmuseum.',
     'sum_en': 'From the new quarter to the old village: Bachwiesen, the old mill, the quarter fir, the old church and the local museum.',
     'legs': [
         {'mode': 'foot', 'to': 'bachwiesenpark', 'de': 'Durch den Bachwiesenpark Richtung Albisrieden.', 'en': 'Through Bachwiesenpark towards Albisrieden.'},
         {'mode': 'foot', 'to': 'alte-muehle-albisrieden', 'de': 'Die Alte Mühle erinnert an das Bauerndorf, das Albisrieden bis 1934 war.', 'en': 'The old mill recalls the farming village Albisrieden was until 1934.'},
         {'mode': 'foot', 'to': 'albisriederhaus', 'de': 'Beim Albisriederhaus steht die Quartiertanne. Hier gibt es im Advent den Umtrunk.', 'en': 'The quarter fir stands by the Albisriederhaus, where neighbours meet for a drink in Advent.'},
         {'mode': 'foot', 'to': 'ortsmuseum-albisrieden', 'de': 'Ortsmuseum und Alte Kirche im Dorfkern.', 'en': 'The local museum and the old church in the village core.'},
         {'mode': 'foot', 'to': 'spielplatz-suessleren', 'de': 'Zum Abschluss der Spielplatz Süsslerenanlage.', 'en': 'To finish, the Süsslerenanlage playground.'},
     ]},
]


def build_tours(pois, raw):
    byid = {p['id']: p for p in pois}
    def latlon(pid):
        if pid == '@home':
            return HOME
        p = byid[pid]
        return (LAT0 + p['y'] / KY, LON0 + p['x'] / KX)
    out = []
    for t in TOURS:
        cur = HOME; legs = []; total_d = total_t = 0
        for leg in t['legs']:
            nxt = latlon(leg['to'])
            if leg['mode'] == 'bus':
                coords = bus83(raw, cur, nxt); d = 0; dur = 11 * 60
                for a, b in zip(coords, coords[1:]):
                    d += math.hypot((b[0] - a[0]) * KX, (b[1] - a[1]) * KY)
            else:
                coords, d, dur = osrm(cur, nxt); time.sleep(1.1)
            pts = to_xy(coords)
            legs.append({'mode': leg['mode'], 'to': leg['to'], 'de': leg['de'], 'en': leg['en'], 'p': pts,
                         'dist': round(d), 'min': round(dur / 60) if leg['mode'] == 'bus' else max(1, round(d / 75))})
            total_d += d; total_t += legs[-1]['min']
            cur = nxt
        rec = {k: v for k, v in t.items() if k != 'legs'}
        rec['legs'] = legs; rec['dist'] = round(total_d); rec['min'] = total_t
        out.append(rec)
        print(t['id'], round(total_d), 'm', total_t, 'min', [l['min'] for l in legs])
    return out


def transit_lines(raw):
    d = json.load(open(os.path.join(raw, 'routes_geom.json')))
    lines = []
    for e in d['elements']:
        ref = e['tags'].get('ref'); kind = e['tags'].get('route')
        segs = []
        for m in e['members']:
            if m['type'] == 'way' and m.get('geometry') and m.get('role', '') in ('', 'forward', 'backward'):
                pts = to_xy([[p['lon'], p['lat']] for p in m['geometry']])
                pts = [p for p in pts if math.hypot(p[0] - BC[0], p[1] - BC[1]) < R - 5]
                if len(pts) >= 2:
                    segs.append(pts)
        lines.append({'ref': ref, 'kind': kind, 'segs': segs})
        print('line', kind, ref, len(segs))
    return lines


def main():
    research, raw, out = sys.argv[1], sys.argv[2], sys.argv[3]
    pois = merge_pois(research)
    ev = events(research)
    tours = build_tours(pois, raw)
    lines = transit_lines(raw)
    home = proj(*HOME)
    data = {'home': [round(home[0], 1), round(home[1], 1)], 'pois': pois, 'events': ev, 'tours': tours, 'lines': lines}
    s = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    open(out, 'w').write(s)
    from collections import Counter
    print('pois', len(pois), Counter(p['g'] for p in pois), 'outside board', sum(1 for p in pois if p.get('out')))
    print('events', len(ev), 'wrote', out, round(len(s) / 1024), 'KB')


if __name__ == '__main__':
    main()
