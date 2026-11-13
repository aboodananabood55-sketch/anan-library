"""Collects fresh medical news for Dr. Anan's library and writes news.json.
Runs on GitHub Actions every hour. Uses only the Python standard library."""
import json, re, html, sys, urllib.request, urllib.parse, datetime as dt
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

def gn(q, days=30):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{q} when:{days}d", "hl": "en-US", "gl": "US", "ceid": "US:en"})

FEEDS = [
    ("Jordan",          gn("Jordan Ministry of Health")),
    ("Jordan",          gn("Jordan hospitals doctors health")),
    ("Middle East",     gn("WHO Eastern Mediterranean region health")),
    ("Middle East",     gn("Middle East disease outbreak health")),
    ("Guidelines",      gn("new clinical practice guideline", 45)),
    ("Guidelines",      gn("updated guidelines primary care physicians", 45)),
    ("WHO",             "https://www.who.int/rss-feeds/news-english.xml"),
    ("Drug safety",     "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drug-safety-communications/rss.xml"),
    ("Family medicine", "https://www.medscape.com/cx/rssfeeds/2700.xml"),
]
MAX_AGE = {"Guidelines": 60, "Drug safety": 90}
PER_TAG, TOTAL = 6, 36
NOW = dt.datetime.now(dt.timezone.utc)

def text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None and (x.text or x.get("href")):
            return (x.text or x.get("href") or "").strip()
    return ""

def clean(s, limit=240):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"

def parse_date(s):
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)

def fetch(tag, url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DrAnanLibrary news bot)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())
    ns = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(".//item") or root.findall(f".//{ns}entry")
    out = []
    for e in entries:
        title = clean(text(e, "title", f"{ns}title"), 200)
        link = text(e, "link") or (e.find(f"{ns}link").get("href") if e.find(f"{ns}link") is not None else "")
        date = parse_date(text(e, "pubDate", f"{ns}updated", f"{ns}published", "{http://purl.org/dc/elements/1.1/}date"))
        src_el = e.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        summary = clean(text(e, "description", f"{ns}summary"))
        if "news.google.com" in url:
            if source and title.endswith(" - " + source): title = title[: -len(source) - 3]
            summary = ""  # Google News descriptions are only link lists
        if not source:
            source = {"WHO": "World Health Organization", "Drug safety": "U.S. FDA", "Family medicine": "Medscape"}.get(tag, "")
        if not title or not link or not date: continue
        if (NOW - date).days > MAX_AGE.get(tag, 30) or date > NOW + dt.timedelta(days=1): continue
        if summary and summary.lower().startswith(title.lower()[:40]): summary = ""
        out.append({"tag": tag, "title": title, "source": source, "date": date.isoformat(), "link": link, "summary": summary})
    return out

def key(t): return re.sub(r"[^a-z0-9]", "", t.lower())[:70]

items, seen, log = [], set(), []
for tag, url in FEEDS:
    try:
        got = fetch(tag, url); n = 0
        for it in sorted(got, key=lambda x: x["date"], reverse=True):
            k = key(it["title"])
            if k in seen: continue
            seen.add(k); items.append(it); n += 1
        log.append(f"{tag:16} {n:3} items  {url[:80]}")
    except Exception as ex:
        log.append(f"{tag:16} FAILED ({type(ex).__name__}: {ex})  {url[:80]}")
print("\n".join(log))

by_tag = {}
for it in sorted(items, key=lambda x: x["date"], reverse=True):
    by_tag.setdefault(it["tag"], [])
    if len(by_tag[it["tag"]]) < PER_TAG: by_tag[it["tag"]].append(it)
mixed, i = [], 0
while len(mixed) < TOTAL and any(by_tag.values()):
    for t in list(by_tag):
        if by_tag[t]: mixed.append(by_tag[t].pop(0))
mixed = mixed[:TOTAL]

try:
    old = json.load(open("news.json", encoding="utf-8"))
except Exception:
    old = {"items": []}
if not mixed:
    print("No items fetched; keeping previous news.json"); sys.exit(0)
if [x["link"] for x in mixed] == [x.get("link") for x in old.get("items", [])]:
    print("No change"); sys.exit(0)
json.dump({"updated": NOW.isoformat(timespec="seconds"), "items": mixed}, open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"Wrote {len(mixed)} items")
