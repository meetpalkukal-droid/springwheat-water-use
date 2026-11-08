/**
 * AgriMet relay — `?daily=` route for the Spring Wheat Water Use app.
 *
 * Adds:  GET /?daily=<id>&start=YYYY-MM-DD&end=YYYY-MM-DD
 *   -> proxies https://www.usbr.gov/pn-bin/daily.pl for ONLY the
 *      etrs, mx, mn, pp parameters of one station, adds CORS headers,
 *      and caches the CSV at the edge for a short time.
 *   Response: text/csv  "DateTime,<id>_etrs,<id>_mx,<id>_mn,<id>_pp"
 *
 * ── HOW TO MERGE INTO THE EXISTING RELAY ─────────────────────────────
 * The live worker (agrimet-relay.meetpal-kukal.workers.dev) already answers
 * `?station=<code>` with the 4-day crop chart. Keep that code as is and add
 * the daily route in front of it:
 *
 *   1. Paste everything between "BEGIN daily route" and "END daily route"
 *      into the existing worker file (top level).
 *   2. At the very top of the existing fetch handler add:
 *
 *        const url = new URL(request.url);
 *        if (request.method === "OPTIONS") return dailyPreflight();
 *        if (url.searchParams.has("daily")) return handleDaily(request, url, ctx);
 *        // ...existing ?station= logic continues unchanged...
 *
 *   3. Deploy:  `npx wrangler deploy`  (or paste into the Cloudflare dashboard
 *      editor: Workers & Pages -> agrimet-relay -> Edit code -> Deploy).
 *   4. Test:
 *      https://agrimet-relay.meetpal-kukal.workers.dev/?daily=mali&start=2026-04-01&end=2026-04-08
 *
 * If you would rather deploy this file on its own, the default export at the
 * bottom works stand-alone (the ?station= branch then returns 404); point the
 * app's DATA_BASE at that worker's URL.
 *
 * Notes
 *  - usbr.gov sends no CORS headers; that is the only reason this relay exists.
 *  - Missing values come back as blanks (and occasionally -99.99-style flags);
 *    they are passed through untouched and handled by the app.
 *  - Station ids are the 4-letter AgriMet ids (mali, twfi, abei...). The crop
 *    chart codes used by ?station= append "ch" (malich) — strip it for ?daily=.
 */

// ════════════════ BEGIN daily route ════════════════
const DAILY_USBR = "https://www.usbr.gov/pn-bin/daily.pl";
const DAILY_PARAMS = ["etrs", "mx", "mn", "pp"];   // whitelist — nothing else is ever requested
const DAILY_MAX_DAYS = 400;
const DAILY_ALLOWED_ORIGINS = "*";                 // tighten to your app's origin if desired

function dailyCors(extra = {}) {
  return {
    "Access-Control-Allow-Origin": DAILY_ALLOWED_ORIGINS,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    ...extra,
  };
}

function dailyPreflight() {
  return new Response(null, { status: 204, headers: dailyCors() });
}

function dailyError(status, msg) {
  return new Response(JSON.stringify({ error: msg }), {
    status,
    headers: dailyCors({ "Content-Type": "application/json" }),
  });
}

function dailyParseDate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s || "")) return null;
  const d = new Date(s + "T00:00:00Z");
  return isNaN(d) || d.toISOString().slice(0, 10) !== s ? null : d;
}

async function handleDaily(request, url, ctx) {
  if (request.method !== "GET") return dailyError(405, "GET only");
  const id = (url.searchParams.get("daily") || "").trim().toLowerCase();
  const start = (url.searchParams.get("start") || "").trim();
  const end = (url.searchParams.get("end") || "").trim();

  if (!/^[a-z]{3,5}$/.test(id)) return dailyError(400, "daily must be a 3-5 letter AgriMet station id, e.g. mali");
  const s = dailyParseDate(start), e = dailyParseDate(end);
  if (!s || !e) return dailyError(400, "start and end must be valid YYYY-MM-DD dates");
  if (s > e) return dailyError(400, "start must be on or before end");
  const spanDays = (e - s) / 86400000;
  if (spanDays > DAILY_MAX_DAYS) return dailyError(400, `date range limited to ${DAILY_MAX_DAYS} days`);
  if (s.getUTCFullYear() < 1980 || e > new Date(Date.now() + 2 * 86400000)) return dailyError(400, "dates out of range");

  const list = DAILY_PARAMS.map(p => `${id} ${p}`).join(",");
  const upstream = `${DAILY_USBR}?list=${encodeURIComponent(list)}&start=${start}&end=${end}&format=csv`;

  // Edge cache keyed on the normalised request. Ranges that include the last
  // couple of days refresh every 15 min; fully historical ranges keep 12 h.
  const recent = e > new Date(Date.now() - 3 * 86400000);
  const ttl = recent ? 900 : 43200;
  const cacheKey = new Request(`https://agrimet-relay.cache/daily/${id}/${start}/${end}`);
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) return hit;

  let resp;
  try {
    resp = await fetch(upstream, {
      headers: { "User-Agent": "agrimet-relay (University of Idaho spring wheat app)" },
      cf: { cacheTtl: ttl, cacheEverything: true },
    });
  } catch (err) {
    return dailyError(502, "AgriMet unreachable");
  }
  if (!resp.ok) return dailyError(502, `AgriMet returned ${resp.status}`);
  const body = await resp.text();
  if (!body.trimStart().startsWith("DateTime")) return dailyError(502, "Unexpected response from AgriMet");

  const out = new Response(body, {
    status: 200,
    headers: dailyCors({
      "Content-Type": "text/csv; charset=utf-8",
      "Cache-Control": `public, max-age=${ttl}`,
    }),
  });
  if (ctx && ctx.waitUntil) ctx.waitUntil(cache.put(cacheKey, out.clone()));
  return out;
}
// ════════════════ END daily route ════════════════

// Stand-alone entry point (only used if this file is deployed by itself).
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return dailyPreflight();
    if (url.searchParams.has("daily")) return handleDaily(request, url, ctx);
    // In the merged worker, the existing ?station= crop-chart handler goes here.
    return dailyError(404, "use ?daily=<id>&start=YYYY-MM-DD&end=YYYY-MM-DD");
  },
};
