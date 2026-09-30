#!/usr/bin/env python3
"""Fetch all data sources and write site/data.json. Standard library only.

Every source is fetched independently: a failure never stops the build. If a
source fails, the previous good data (passed with --prev) is reused and marked
stale, otherwise the section is marked unavailable.
"""
import argparse, html, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (compatible; DailyDashboard/1.0)"
NOW = datetime.now(timezone.utc)


def http_get(url, tries=3, timeout=25):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def get_json(url):
    return json.loads(http_get(url))


# ---------------------------------------------------------------- RSS
def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s.strip())
    except Exception:
        try:
            d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def fetch_feed(feed, limit=30):
    root = ET.fromstring(http_get(feed["url"]))
    out = []
    for it in root.iter():
        if local(it.tag) not in ("item", "entry"):
            continue
        f = {}
        for ch in it:
            k = local(ch.tag)
            if k == "link":
                f.setdefault("link", ch.attrib.get("href") or (ch.text or "").strip())
            elif k not in f:
                f[k] = ch.text or ""
        title = strip_html(f.get("title"))
        link = f.get("link", "")
        if not title or not link:
            continue
        summary = strip_html(f.get("description") or f.get("summary") or f.get("encoded") or "")
        if len(summary) > 260:
            summary = summary[:257].rsplit(" ", 1)[0] + "…"
        if summary.lower().startswith(title.lower()[:40]):
            summary = ""
        d = parse_date(f.get("pubDate") or f.get("published") or f.get("updated") or f.get("date"))
        out.append({"title": title, "summary": summary, "time": d.isoformat() if d else None,
                    "sources": [{"name": feed["name"], "url": link}]})
        if len(out) >= limit:
            break
    return out


STOP = set("with from that this have will after over into about their they says said what when more than been were also your amid against".split())


def tokens(t):
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if len(w) > 3 and w not in STOP}


def similar(a, b):
    if not a or not b:
        return False
    inter = len(a & b)
    return inter >= 3 and (inter / len(a | b) >= 0.4 or inter / min(len(a), len(b)) >= 0.7)


def dedupe(items):
    items = sorted(items, key=lambda x: x["time"] or "", reverse=True)
    groups = []
    for it in items:
        tk = tokens(it["title"])
        for g in groups:
            if similar(tk, g["_tk"]):
                names = {s["name"] for s in g["sources"]}
                for s in it["sources"]:
                    if s["name"] not in names:
                        g["sources"].append(s)
                if len(it["summary"]) > len(g["summary"]):
                    g["summary"] = it["summary"]
                g["_tk"] |= tk
                break
        else:
            it["_tk"] = tk
            groups.append(it)
    for g in groups:
        g.pop("_tk")
    return groups


REGIONS = {
    "Middle East": "israel gaza palestin hamas hezbollah lebanon syria iran iraq yemen houthi saudi qatar emirates uae jordan egypt turkey turkish tehran beirut damascus riyadh west bank jerusalem tel aviv kurd",
    "Europe": "ukraine russia russian putin kyiv kremlin moscow eu european brussels germany german france french paris berlin uk britain british london starmer macron italy italian spain spanish portugal lisbon poland polish nato greece hungary netherlands dutch sweden norway finland ireland scotland brexit",
    "Asia": "china chinese beijing xi japan japanese tokyo india indian delhi modi pakistan taiwan korea korean seoul pyongyang afghanistan taliban myanmar thailand vietnam indonesia philippines bangladesh hong kong asia singapore malaysia nepal sri lanka",
    "Americas": "us trump biden white house congress washington senate american america canada canadian mexico mexican brazil brazilian argentina venezuela colombia cuba chile peru ecuador haiti latin pentagon",
    "Africa": "africa african sudan nigeria ethiopia kenya congo somalia sahel mali niger libya tunisia algeria morocco ghana uganda rwanda mozambique zimbabwe south africa cameroon burkina",
}
PHRASES = {"Middle East": ["west bank", "tel aviv"], "Asia": ["hong kong", "sri lanka", "north korea", "south korea"],
           "Africa": ["south africa"], "Americas": ["white house", "latin america"]}
REGION_RE = {}
for _r, _kw in REGIONS.items():
    _terms = [w for w in _kw.split() if w not in ("west", "bank", "tel", "aviv", "hong", "kong", "sri", "lanka", "south", "africa", "white", "house", "latin", "america")]
    _terms += ["africa"] if _r == "Africa" else ["america"] if _r == "Americas" else []
    _terms += PHRASES.get(_r, [])
    REGION_RE[_r] = re.compile(r"\b(" + "|".join(re.escape(t) for t in _terms) + r")\b", re.I)


def tag_region(item):
    text = item["title"] + " " + item["summary"]
    best, score = "Global", 0
    for r, rx in REGION_RE.items():
        n = len(rx.findall(item["title"])) * 3 + len(rx.findall(text))
        if n > score:
            best, score = r, n
    return best


def news_section(feeds, keep, tag=False):
    items, errors = [], []
    for f in feeds:
        try:
            items += fetch_feed(f)
        except Exception as e:
            errors.append(f"{f['name']}: {type(e).__name__}")
    if not items:
        raise RuntimeError("all feeds failed: " + "; ".join(errors))
    items = dedupe(items)[:keep]
    if tag:
        for i in items:
            i["region"] = tag_region(i)
    return {"items": items, "errors": errors}


# ---------------------------------------------------------------- Markets
def yahoo(symbol):
    q = urllib.parse.quote(symbol)
    last = None
    for host in ("query1", "query2"):
        try:
            j = get_json(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range=1mo&interval=1d")
            res = j["chart"]["result"][0]
            closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
            price = res["meta"].get("regularMarketPrice") or closes[-1]
            closes[-1] = price
            prev = closes[-2]
            return {"value": price, "change_pct": (price / prev - 1) * 100, "spark": [round(c, 4) for c in closes[-7:]]}
        except Exception as e:
            last = e
    raise last


def per_item(specs, fetch, prev_items, label):
    items, errors = [], []
    old = {i["name"]: i for i in (prev_items or [])}
    for s in specs:
        try:
            d = fetch(s)
            d.update(name=s["name"], **({"unit": s["unit"]} if "unit" in s else {}))
            items.append(d)
        except Exception as e:
            errors.append(f"{s['name']}: {type(e).__name__}")
            if s["name"] in old:
                o = dict(old[s["name"]]); o["stale"] = True; items.append(o)
    if not items:
        raise RuntimeError(f"{label}: nothing fetched ({'; '.join(errors)})")
    return {"items": items, "errors": errors}


def fx_section(cfg):
    start = (NOW - timedelta(days=21)).strftime("%Y-%m-%d")
    j = get_json(f"https://api.frankfurter.dev/v1/{start}..?base=EUR&symbols=USD,GBP,JPY,CNY")
    days = sorted(j["rates"])
    def rate(pair, day):
        a, b = pair.split("/")
        r = {"EUR": 1.0, **j["rates"][day]}
        return r[b] / r[a]
    items = []
    for pair in cfg["fx_pairs"]:
        series = [rate(pair, d) for d in days]
        latest, prev = series[-1], series[-2]
        week_ago = None
        target = (datetime.strptime(days[-1], "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        older = [d for d in days if d <= target]
        if older:
            week_ago = rate(pair, older[-1])
        items.append({"name": pair, "value": latest, "change_pct": (latest / prev - 1) * 100,
                      "week_change_pct": (latest / week_ago - 1) * 100 if week_ago else None,
                      "week_ago": week_ago, "spark": [round(x, 5) for x in series[-7:]], "date": days[-1]})
    return {"items": items, "errors": []}


def crypto_section(cfg):
    ids = ",".join(c["id"] for c in cfg["crypto"])
    j = get_json(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&sparkline=true&price_change_percentage=24h")
    names = {c["id"]: c["name"] for c in cfg["crypto"]}
    items = []
    for c in j:
        sp = c.get("sparkline_in_7d", {}).get("price", [])
        step = max(1, len(sp) // 28)
        items.append({"name": names.get(c["id"], c["name"]), "value": c["current_price"],
                      "change_pct": c.get("price_change_percentage_24h"), "spark": [round(x, 2) for x in sp[::step]]})
    if not items:
        raise RuntimeError("empty CoinGecko response")
    return {"items": items, "errors": []}


# ---------------------------------------------------------------- Weather
def weather_section(cfg):
    cities = []
    for c in cfg["cities"]:
        u = ("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": c["latitude"], "longitude": c["longitude"], "timezone": "auto", "forecast_days": 6,
            "current": "temperature_2m,weather_code,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"}))
        j = get_json(u)
        d = j["daily"]
        cities.append({"name": c["name"], "temp": j["current"]["temperature_2m"], "code": j["current"]["weather_code"],
                       "is_day": j["current"]["is_day"], "high": d["temperature_2m_max"][0], "low": d["temperature_2m_min"][0],
                       "rain": d["precipitation_probability_max"][0],
                       "forecast": [{"date": d["time"][i], "code": d["weather_code"][i], "high": d["temperature_2m_max"][i],
                                     "low": d["temperature_2m_min"][i], "rain": d["precipitation_probability_max"][i]}
                                    for i in range(1, len(d["time"]))]})
    return {"items": cities, "errors": []}


# ---------------------------------------------------------------- Main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--prev", default="")
    ap.add_argument("--out", default="site/data.json")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    prev = {}
    if a.prev:
        try:
            prev = json.load(open(a.prev)).get("sections", {})
        except Exception:
            print("no previous data to fall back on", file=sys.stderr)

    pi = lambda k: (prev.get(k, {}).get("data") or {}).get("items")
    jobs = {
        "world": lambda: news_section(cfg["world_feeds"], 40, tag=True),
        "economic": lambda: news_section(cfg["economic_feeds"], 25),
        "central_banks": lambda: news_section(cfg["central_bank_feeds"], 6),
        "indices": lambda: per_item(cfg["indices"], lambda s: yahoo(s["symbol"]), pi("indices"), "indices"),
        "commodities": lambda: per_item(cfg["commodities"], lambda s: yahoo(s["symbol"]), pi("commodities"), "commodities"),
        "fx": lambda: fx_section(cfg),
        "crypto": lambda: crypto_section(cfg),
        "weather": lambda: weather_section(cfg),
    }
    sections = {}
    for name, fn in jobs.items():
        try:
            sections[name] = {"status": "ok", "data": fn()}
            errs = sections[name]["data"]["errors"]
            if errs:
                sections[name]["status"] = "partial"
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"[:200]
            if prev.get(name, {}).get("data"):
                sections[name] = {"status": "stale", "error": msg, "data": prev[name]["data"],
                                  "stale_since": prev[name].get("stale_since") or prev[name].get("fetched_at")}
            else:
                sections[name] = {"status": "error", "error": msg, "data": None}
        sections[name]["fetched_at"] = NOW.isoformat() if sections[name]["status"] in ("ok", "partial") else prev.get(name, {}).get("fetched_at")
        print(f"{name:14} {sections[name]['status']}", sections[name].get("error", ""), file=sys.stderr)

    def items(k):
        return (sections[k]["data"] or {}).get("items", []) if sections[k]["data"] else []

    # movers
    pool = [("Index", i) for i in items("indices")] + [("Currency", i) for i in items("fx")] + [("Commodity", i) for i in items("commodities")]
    if cfg.get("crazy_include_crypto"):
        pool += [("Crypto", i) for i in items("crypto")]
    pool = [(k, i) for k, i in pool if i.get("change_pct") is not None]
    th = cfg["crazy_threshold_pct"]
    crazy = sorted([{"kind": k, "name": i["name"], "change_pct": i["change_pct"], "value": i["value"], "stale": i.get("stale", False)}
                    for k, i in pool if abs(i["change_pct"]) > th], key=lambda x: -abs(x["change_pct"]))

    notd = None
    if pool:
        k, i = max(pool, key=lambda p: abs(p[1]["change_pct"]))
        c = i["change_pct"]
        notd = {"value": f"{c:+.2f}%", "label": f"{i['name']} — the biggest move across tracked {'indices, currencies and commodities'}",
                "detail": f"{'Up' if c > 0 else 'Down'} to {i['value']:,.4f}".rstrip("0").rstrip(".") + f" ({k.lower()})"}

    out = {"generated_at": NOW.isoformat(), "greeting": cfg["greeting"], "timezone": cfg["timezone"],
           "news_items_shown": cfg["news_items_shown"], "crazy_threshold_pct": th,
           "sections": sections, "crazy": crazy, "number_of_day": notd}
    with open(a.out, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", a.out, file=sys.stderr)


if __name__ == "__main__":
    main()
