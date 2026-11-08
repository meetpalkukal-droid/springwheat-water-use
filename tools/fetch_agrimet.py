"""Snapshot AgriMet daily data for the Spring Wheat Water Use app.

Writes, for every station in STATIONS:
    data/<id>/<year>.csv   date,etrs,mx,mn,pp   (inches / deg F; blank = missing)
    data/index.json        {"updated": ..., "stations": {id: {"years": [...]}}}

A season (year) is listed when the station reported alfalfa reference ET
(ETRS) on at least MIN_SEASON_DAYS days between Apr 1 and Sep 30; the current
year is always listed once it has any ETRS.

    python tools/fetch_agrimet.py            # full record (1980 -> today)
    python tools/fetch_agrimet.py --recent   # current + previous year only (daily GitHub Action)

Standard library only.
"""
import argparse
import csv
import datetime as dt
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
USBR = "https://www.usbr.gov/pn-bin/daily.pl"
PARAMS = ("etrs", "mx", "mn", "pp")
MIN_SEASON_DAYS = 120
STATIONS = ["nmpi", "pmai", "gdvi", "gfri", "fafi", "pici", "twfi", "tfgi", "drti", "ichi",
            "rpti", "mdki", "mali", "abei", "fthi", "acki", "shli", "ifai", "osgi", "rgbi",
            "rrii", "robi", "rxgi", "sugi", "trti", "teri", "hami", "ahti", "dwni", "grei",
            "psti", "mnpi"]


def fetch(sid, start, end):
    lst = ",".join(f"{sid} {p}" for p in PARAMS)
    url = f"{USBR}?" + urllib.parse.urlencode(
        {"list": lst, "start": start, "end": end, "format": "csv"}, quote_via=urllib.parse.quote)
    req = urllib.request.Request(url, headers={"User-Agent": "spring-wheat-water-use (University of Idaho)"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read().decode("utf-8", "replace")
            if body.lstrip().startswith("DateTime"):
                return body
            raise RuntimeError("unexpected response")
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            print(f"  retry {sid} ({e})")
            time.sleep(5 * (attempt + 1))


def clean(v, kind):
    v = v.strip()
    if not v:
        return ""
    try:
        x = float(v)
    except ValueError:
        return ""
    if x <= -90 or x > 900:  # -99.99 style flags
        return ""
    if kind == "pp":
        x = max(0.0, x)
    return f"{x:g}"


def write_station(sid, body, years_wanted):
    rows_by_year = {}
    rdr = csv.reader(io.StringIO(body))
    hdr = [h.strip().lower() for h in next(rdr)]
    ci = {p: hdr.index(f"{sid}_{p}") if f"{sid}_{p}" in hdr else -1 for p in PARAMS}
    for c in rdr:
        if not c or len(c[0]) < 10:
            continue
        d = c[0][:10]
        vals = [clean(c[ci[p]], p) if ci[p] >= 0 and ci[p] < len(c) else "" for p in PARAMS]
        if not any(vals):
            continue
        rows_by_year.setdefault(int(d[:4]), []).append([d] + vals)
    (DATA / sid).mkdir(parents=True, exist_ok=True)
    for y, rows in rows_by_year.items():
        if years_wanted and y not in years_wanted:
            continue
        with open(DATA / sid / f"{y}.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["date", *PARAMS])
            w.writerows(rows)


def season_years(sid, this_year):
    out = []
    for p in sorted((DATA / sid).glob("*.csv")):
        y = int(p.stem)
        n = 0
        with open(p) as f:
            for r in csv.DictReader(f):
                if r["etrs"] and f"{y}-04-01" <= r["date"] <= f"{y}-09-30":
                    n += 1
        if n >= MIN_SEASON_DAYS or (y == this_year and n > 0):
            out.append(y)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", action="store_true", help="only refresh the current and previous year")
    a = ap.parse_args()
    today = dt.date.today()
    if a.recent:
        start, years_wanted = f"{today.year - 1}-01-01", {today.year - 1, today.year}
    else:
        start, years_wanted = "1980-01-01", None
    index = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "stations": {}}
    for sid in STATIONS:
        print(sid)
        body = fetch(sid, start, today.isoformat())
        write_station(sid, body, years_wanted)
        yrs = season_years(sid, today.year)
        for p in (DATA / sid).glob("*.csv"):   # drop years without a usable ETRS season
            if int(p.stem) not in yrs and int(p.stem) < today.year - 1:
                p.unlink()
        index["stations"][sid] = {"years": yrs}
        time.sleep(0.5)
    with open(DATA / "index.json", "w") as f:
        json.dump(index, f, separators=(",", ":"))
    print("done:", sum(len(v["years"]) for v in index["stations"].values()), "station-seasons")


if __name__ == "__main__":
    main()
