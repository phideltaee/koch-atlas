# Koch-Quartier Atlas

An open, 3D neighbourhood model of **Albisrieden and Altstetten (Zürich, Kreis 9)** around the new Koch-Quartier.
It works like a Swiss architecture-competition model: a plaster-white city on a model board, with the Koch-Areal set
in as birch wood. Explore places, take guided walks, see what's on, and add what is missing.

*Ein offenes 3D-Quartiermodell von Albisrieden und Altstetten rund um das neue Koch-Quartier. Orte entdecken,
Rundgänge machen, Anlässe finden und Fehlendes ergänzen.*

**Live:** https://phideltaee.github.io/koch-atlas/

> **Unofficial.** This is a private neighbourhood project, not affiliated with the Koch-Quartier developers
> (ABZ, Kraftwerk1, SENN/SFP, Grün Stadt Zürich). The official site is [kochquartier.ch](https://www.kochquartier.ch).
> *Inoffiziell: ein privates Nachbarschaftsprojekt, nicht mit den Bauträgern verbunden.*

## What's in it

| | |
|---|---|
| 3D model | 7,167 OpenStreetMap buildings (heights from OSM levels or type defaults), land use, streets, rail, tram and 7,915 street trees within 1.8 km. The Koch-Areal buildings are modelled separately (the 85 m tower with floor lines and floor bands). |
| Places | 159 in 10 groups (Kitas, school, playgrounds, parks, sport, culture, food, community, health, mobility), each with a walking time from Flurstrasse 71, a description in German and English, and a source |
| Walking routes | 136 pre-routed footpaths (OSRM) from the tower to every place on the board |
| Walks | 4 guided routes: Kita morning & commute, Saturday in the quarter, green loop with a stroller, Albisrieden village walk |
| Events | 33, November 2026 – October 2027, with a month strip and regular events |
| Layers | trees, place names, walking-time rings, stops, bus 83/89 and tram 2, 153 drinking fountains, 96 recycling points, bike and car sharing |
| Contribute | community ideas plus "suggest a place": drop a pin and get a JSON record to copy |
| Modes | German/English, light and dark UI, day and night model (windows light up), phone layout |

## How it's built

One static HTML page, no server and no build tools beyond Python 3 (standard library only). three.js 0.170 loads
from jsDelivr.

```
src/app.html          UI + three.js engine (template with __SCENE__/__CONTENT__/__ROUTES__ placeholders)
src/assemble.py       injects the data into the template → a single HTML file
src/build_geo.py      Overpass JSON → data/scene.json (projection, simplification, clipping, encoding)
src/build_content.py  research JSON → data/content.json (merge places, events, routed walks, transit lines)
src/build_routes.py   OSRM walking routes → data/routes.json (cached)
src/queries/*.txt     the Overpass queries used (buildings were fetched in 2×2 + 8 tiles)
data/research/*.json  researched places (pois-family, pois-quartier), events, tower flat list
data/raw/             bus-83 route geometry used by the commute walk
```

Build and preview locally (run from the repo root):

```bash
python3 -I src/assemble.py src/app.html data/scene.json data/content.json data/routes.json index.html --public
python3 -m http.server   # then open http://localhost:8000
```

Every push to `main` builds the page the same way and publishes it to GitHub Pages
(`.github/workflows/pages.yml`).

What to re-run after a change:

- **UI or text** (`src/app.html`): nothing; the deploy runs `assemble.py`.
- **Places, events or walks** (`data/research/*.json`, `TOURS` in `build_content.py`): run `build_content.py`, then
  `build_routes.py` for new places (it is cached), and commit the updated `data/*.json`.
- **The 3D city:** re-fetch OpenStreetMap with the queries in `src/queries` (overpass-api.de, in tiles with pauses),
  then run `build_geo.py`. The raw downloads (about 20 MB) are not stored.

```bash
python3 -I src/build_content.py data/research data/raw data/content.json
python3 -I src/build_routes.py data/content.json data/routes.json
python3 -I src/build_geo.py raw data/scene.json
```

## Adding a place

Use "Mitmachen → Ort auf der Karte setzen" in the app and paste the JSON into an issue, or add an object to
`data/research/pois-quartier.json` in a pull request:

```json
{"id":"kebab-case","name":"…","cat":"community|culture|food|market|shop|sport|nature|park|transport|sharing|history|landmark",
 "lat":47.38,"lon":8.49,"address":"…","walk_min":5,"desc_de":"…","desc_en":"…","url":"https://…","tags":[],"source":"https://…"}
```

Corrections are welcome the same way: open an issue with the place and what is wrong.

## Data and licences

- Code: MIT (see `LICENSE`).
- Map data © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright). Routing: OSRM
  (routing.openstreetmap.de).
- Places and events: own research from City of Zürich open data, the Koch-Quartier developers, community centres and
  Quartiervereine. Every record carries its `source`. Opening hours, prices and dates change; check the source before
  you go.
- Koch buildings: OSM footprints, heights from the developers. The base and roof garden are schematic.
