"""Local dev server for the Spring Wheat Water Use prototype.

Serves the static files in this folder and proxies daily AgriMet data so the
browser does not hit usbr.gov's missing CORS headers.

    python serve_local.py            # http://localhost:8000
    python serve_local.py 8080       # another port

Proxy route (same contract as the Cloudflare worker's ?daily= route):
    /api/daily?daily=mali&start=2026-03-28&end=2026-10-24
returns AgriMet CSV: DateTime,mali_etrs,mali_mx,mali_mn,mali_pp

Standard library only.
"""
import datetime as dt
import http.server
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
USBR = "https://www.usbr.gov/pn-bin/daily.pl"
PARAMS = ("etrs", "mx", "mn", "pp")   # whitelist: alfalfa ref ET, Tmax, Tmin, precip
MAX_DAYS = 400
CACHE_TTL = 600                        # seconds
_cache = {}


def _bad(msg):
    raise ValueError(msg)


def validate(qs):
    code = (qs.get("daily") or [""])[0].strip().lower()
    start = (qs.get("start") or [""])[0].strip()
    end = (qs.get("end") or [""])[0].strip()
    if not re.fullmatch(r"[a-z]{3,5}", code):
        _bad("daily must be a 3-5 letter AgriMet station id, e.g. mali")
    try:
        s = dt.date.fromisoformat(start)
        e = dt.date.fromisoformat(end)
    except ValueError:
        _bad("start and end must be YYYY-MM-DD")
    if s > e:
        _bad("start must be on or before end")
    if (e - s).days > MAX_DAYS:
        _bad(f"date range limited to {MAX_DAYS} days")
    if s.year < 1980 or e > dt.date.today() + dt.timedelta(days=1):
        _bad("dates out of range")
    return code, s.isoformat(), e.isoformat()


def fetch_usbr(code, start, end):
    key = (code, start, end)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    lst = ",".join(f"{code} {p}" for p in PARAMS)
    url = f"{USBR}?" + urllib.parse.urlencode(
        {"list": lst, "start": start, "end": end, "format": "csv"}, quote_via=urllib.parse.quote)
    req = urllib.request.Request(url, headers={"User-Agent": "spring-wheat-water-use/dev"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    if not body.lstrip().startswith(b"DateTime"):
        raise RuntimeError("unexpected response from AgriMet")
    _cache[key] = (time.time(), body)
    return body


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.rstrip("/") == "/api/daily":
            try:
                code, s, e = validate(urllib.parse.parse_qs(u.query))
            except ValueError as ex:
                return self._send(400, ('{"error":"%s"}' % ex).encode(), "application/json")
            try:
                body = fetch_usbr(code, s, e)
            except Exception as ex:  # noqa: BLE001
                return self._send(502, ('{"error":"AgriMet fetch failed: %s"}' % type(ex).__name__).encode(),
                                  "application/json")
            return self._send(200, body, "text/csv; charset=utf-8")
        return super().do_GET()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving {ROOT} at http://localhost:{port}/  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
