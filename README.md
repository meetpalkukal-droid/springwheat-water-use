# Southern Idaho Spring Wheat Water Use (prototype)

Phone-first single-page PWA that estimates daily irrigated spring wheat ET (inches) as
**Kc × AgriMet station ETrs**. The crop coefficients come from the Declo, ID eddy-covariance
towers (2025 and 2026), on the ASCE standardized alfalfa reference basis. It is derived from the
PNW Crop Water Use Viewer (`AgriMET_scraping website/files_latest`). That folder was not changed.

## Run locally

```
cd web_tool
python serve_local.py          # http://localhost:8000  (optional port argument)
```

Weather data are static snapshots in `data/` (`data/<id>/<year>.csv` with date, etrs, mx, mn, pp,
and `data/index.json` listing each station's seasons). AgriMet ETRS starts in 2003, so seasons run
2003-present at the long-running stations and 2014/2015-present at the newer ones.
`tools/fetch_agrimet.py` rebuilds the full record; `--recent` refreshes only the current and
previous year. The GitHub Action `.github/workflows/refresh-data.yml` runs `--recent` twice a day
and commits any change, so the deployed site needs no relay.

Useful links:
- `#view/malich/2026-03-28`: Malta, 2026 season, emergence Mar 28 (not saved)
- `#stations/map`: station map
- `?demo=1#home`: adds two example fields if none are saved
- `?focus=kc#view/...`: opens the dashboard scrolled to the Kc chart

## Deploy

GitHub Pages serves the repository root as is. The refresh Action keeps `data/` current.
`relay_worker.js` and the `/api/daily` proxy in `serve_local.py` are no longer used by the app;
they are kept for reference.

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole app: stations, Kc model, SVG charts, hash router, the **forecast module** (its own `<script>` block, `Forecast.get()`) |
| `serve_local.py` | Development server and AgriMet proxy (stdlib) |
| `relay_worker.js` | Cloudflare Worker `?daily=` route: params limited to etrs/mx/mn/pp, input validation, CORS, edge cache |
| `sw.js` | Shell-only service worker. It never caches weather data |
| `manifest.json`, `icon.png` | PWA install (icon copied from the PNW viewer) |
| `screenshots/` | Headless Chrome captures. Phone shots are 430×932 @2x; the desktop shot is 1440×900 |

## Model

- GDD (°F) = max(0, min((Tmax+Tmin)/2, 86) − 32). It uses station `mx`/`mn` and accumulates from the
  emergence day. Forecast days use forecast temperatures.
- FAO-56 four-stage Kc from `presentation/data/kc_fits.json`:
  - `fits.CGDD_F.pooled` (default): Kc 0.63 / 1.07 / 0.04, stages end at 312 / 1334 / 1912 / 3118 GDD°F.
  - `fits.DAE.pooled` (toggle): Kc 0.60 / 0.94 / 0.15, x_end 122 days.
  - `fits.CGDD_F.Kcb_pooled` appears only in the guide text.
- The season ends when x reaches x_end (maturity). Totals run from emergence to maturity, or to the
  latest data day.
- AgriMet SGRN (21-point table; 03/15, 06/10, 07/20) is drawn as a dashed comparison line. It is not
  drawn outside its 0–200 % window.
- Forecast (beta): Open-Meteo daily Tmax, Tmin, mean dew point, 10 m wind (m/s) and Rs (MJ m⁻²) at the
  station lat/lng. ETrs is the ASCE-EWRI 2005 standardized tall reference (Cn 1600, Cd 0.38), with wind
  reduced from 10 m to 2 m by the log profile. Rn comes from Rs, Rso and Ra, using the elevation that
  Open-Meteo returns. When a season is active and the station data are no more than 4 days old, the
  forecast continues the GDD/Kc series for 7 days.

## Stations kept (32, southern Idaho irrigated valleys)

AgriMet id = crop-chart code minus the trailing `ch` (malich → **mali**, ichich → ichi).

- **Treasure Valley & Western Snake:** Nampa (nmpi), Parma (pmai), Grand View (gdvi), Glenns Ferry (gfri)
- **Camas Prairie & Wood River:** Fairfield (fafi), Picabo (pici)
- **Magic Valley:** Twin Falls/Kimberly (twfi), Twin Falls Fairgrounds/Filer (tfgi), Dietrich (drti),
  Richfield INL (ichi), Rupert (rpti), Minidoka INL (mdki), Malta (mali)
- **Eastern Snake Plain:** Aberdeen (abei), Fort Hall (fthi), Blackfoot INL (acki), Shelley (shli),
  Idaho Falls INL (ifai), Osgood (osgi), Rigby (rgbi), Ririe (rrii), Roberts INL (robi), Rexburg (rxgi),
  Sugar City INL (sugi), Terreton (trti), Terreton INL (teri), Hamer INL (hami), Ashton (ahti)
- **Southeast Valleys:** Downey (dwni), Grace (grei), Preston (psti), Montpelier (mnpi)

**Excluded:**
- North of the cutoff, or not Idaho: all northern Idaho stations, Salmon, and Cokeville (WY).
- No `etrs` in 2026: INL Material Fuels Complex (ebri), INL INTEC (igri), INL Specific Manufacturing
  (lofi), Kettle Butte (ktbi), Monteview (mnti), and Michaud Canal (mchi, which has no data at all).
- INL desert facility sites, not irrigated land: Taber (tabi), Howe (owei), Arco (rrci).
- Urban sites: Boise (boii), whose 2026 ETrs ran about 35 % below Nampa's, and Boise Fairgrounds
  (bfgi), which is also missing about 55 days in 2026.

## Verification (8 Nov 2026, live data)

- Malta (mali), emergence 2026-03-28, GDD curve: the season reaches maturity on **Jul 24, 2026**
  (3,162 GDD). The total is **27.5 in** from emergence to maturity. Over the tower window
  (Apr 9 – Jul 28) the same calculation gives 26.05 in, which matches `stats.2026.ETc_tool_in` in
  kc_fits.json. The DAE curve gives 29.8 in.
- Aberdeen, 2025-04-15 emergence: 23.3 in, maturity Aug 1, 2025.
- Current-season and forecast case: Twin Falls (twfi), emergence 2026-09-20. The app shows the
  development stage, data through Nov 7, and a 7-day forecast of 0.88 in (beta).
- The forecast ETrs code was compared with AgriMet over the previous 21 days, using Open-Meteo
  `past_days`. The ratio of the Open-Meteo-based ETrs to station ETrs was 1.01 at Malta, 1.20 at
  Twin Falls and 0.82 at Aberdeen.
- Headless Chrome: no console errors, and no horizontal scroll at 430 px.

## Data quirks

- In this period, missing AgriMet values came back blank. The current day, for example, is blank.
  The app also treats values ≤ −90 (−99.99-style flags) as missing.
- Precipitation sometimes reads slightly negative (−0.01 in at twfi in Nov 2026). The app clamps
  it to 0.
- Malta reported some very high ETrs days, for example 0.75 in on 2026-06-17. The app uses these
  values unchanged.
