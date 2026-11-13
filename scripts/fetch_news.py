"""Collects fresh medical news for Dr. Anan's library and writes news.json.
Runs on GitHub Actions every hour. Uses only the Python standard library."""
import json, re, html, sys, urllib.request, urllib.parse, datetime as dt
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

def gn(q, days=30):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{q} when:{days}d", "hl": "en-US", "gl": "US", "ceid": "US:en"})

HEALTH = r"health|medic|hospital|clinic|doctor|physician|patient|disease|vaccin|drug|medicine|cancer|diabet|heart|cardio|infect|outbreak|virus|pharma|nurs|surg|treatment|therap|screening|mental|maternal|child|antibiot|epidemic|pandemic|WHO\b|ministry of health"
REGION = r"jordan|saudi|emirat|\bUAE\b|qatar|kuwait|oman|bahrain|egypt|iraq|lebanon|syria|palestin|middle east|gulf|\bGCC\b|eastern mediterranean|\bEMRO\b|\barab"
# tag, url, title must match (regex, case-insensitive)
FEEDS = [
    ("Jordan",          gn("Jordan Ministry of Health"),                       r"jordan"),
    ("Jordan",          gn("Jordan hospital patients doctors"),                r"jordan"),
    ("Jordan",          gn("Jordan Food and Drug Administration JFDA"),        r"jordan|JFDA"),
    ("Middle East",     gn("Saudi Ministry of Health"),                        REGION),
    ("Middle East",     gn("WHO Eastern Mediterranean region"),                REGION),
    ("Middle East",     gn("Gulf health ministry hospitals"),                  REGION),
    ("Guidelines",      gn("new clinical practice guideline", 45),             r"guideline|recommend"),
    ("Guidelines",      gn("updated guidelines primary care", 45),             r"guideline|recommend"),
    ("WHO",             gn("World Health Organization recommends"),            r"\bWHO\b|world health organi"),
    ("Drug safety",     gn("FDA drug safety warning", 60),                     r"\bFDA\b|recall|warning|safety"),
    ("Family medicine", "https://www.medscape.com/cx/rssfeeds/2700.xml",       r"."),
]
# Never show these (violence, politics, business noise)
EXCLUDE = r"martyr|shelling|gunfire|aggression|enemy|casualt|wounded|spoiler|\bsoap\b|episode|general hospital|actor|actress|tv series|markets|export|invest|strike|airstrike|killed|kills|bomb|attack|war\b|militar|hamas|hezbollah|israeli|missile|troops|ceasefire|stock|shares|earnings|revenue|investor|career|salary|lawsuit|celebrity|football|soccer"
MAX_AGE = {"Guidelines": 60, "Drug safety": 90}
PER_TAG, TOTAL = 6, 36
TAG_CAP = {"Drug safety": 3}
STOP = set("a an the to of in on for and or with over new adds get gets after as at by from is are be its into says say said".split())
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

def fetch(tag, url, must):
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
        if not re.search(must, title, re.I) or re.search(EXCLUDE, title, re.I): continue
        if tag in ("Jordan", "Middle East", "WHO") and not re.search(HEALTH, title + " " + summary, re.I): continue
        if (NOW - date).days > MAX_AGE.get(tag, 30) or date > NOW + dt.timedelta(days=1): continue
        if summary and summary.lower().startswith(title.lower()[:40]): summary = ""
        out.append({"tag": tag, "title": title, "source": source, "date": date.isoformat(), "link": link, "summary": summary})
    return out

def key(t): return re.sub(r"[^a-z0-9]", "", t.lower())[:70]
def words(t): return {w for w in re.findall(r"[a-z0-9\-]+", t.lower()) if w not in STOP and len(w) > 2}
def similar(a, b):
    A, B = words(a), words(b)
    return bool(A and B) and len(A & B) / min(len(A), len(B)) >= 0.4

items, seen, log = [], set(), []
for tag, url, must in FEEDS:
    try:
        got = fetch(tag, url, must); n = 0
        for it in sorted(got, key=lambda x: x["date"], reverse=True):
            k = key(it["title"])
            if k in seen: continue
            if any(o["tag"] == tag and similar(o["title"], it["title"]) for o in items): continue
            seen.add(k); items.append(it); n += 1
        log.append(f"{tag:16} {n:3} items  {url[:80]}")
    except Exception as ex:
        log.append(f"{tag:16} FAILED ({type(ex).__name__}: {ex})  {url[:80]}")
print("\n".join(log))

by_tag = {}
for it in sorted(items, key=lambda x: x["date"], reverse=True):
    by_tag.setdefault(it["tag"], [])
    if len(by_tag[it["tag"]]) < TAG_CAP.get(it["tag"], PER_TAG): by_tag[it["tag"]].append(it)
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
