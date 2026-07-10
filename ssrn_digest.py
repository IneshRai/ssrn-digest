import argparse
import html
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# journal_id from the browse URL works as the binding id
# 203 = Financial Economics Network
# 1504400 = Derivatives eJournal, 1504403 = Capital Markets eJournal
QUOTAS = [
    {"binding": 203, "label": "Fin Econ", "quota": 15},
    {"binding": 1504400, "label": "Derivatives", "quota": 5},
    {"binding": 1504403, "label": "Capital Markets", "quota": 5},
]

API = "https://api.ssrn.com/content/v1/bindings/{}/papers"
PAGE_SIZE = 50
MAX_PAGES = 40
SLEEP = 2.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.ssrn.com/",
}

DEBUG = Path("debug")


def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def get(binding, index, count):
    r = requests.get(API.format(binding), headers=HEADERS,
                     params={"index": index, "count": count, "sort": 0}, timeout=30)
    r.raise_for_status()
    data = r.json()
    DEBUG.mkdir(exist_ok=True)
    (DEBUG / f"binding_{binding}_{index}.json").write_text(json.dumps(data, indent=2))
    return data


def parse_paper(p):
    authors = []
    for a in p.get("authors", []):
        name = a.get("name") if isinstance(a, dict) else str(a)
        if not name and isinstance(a, dict):
            name = " ".join(x for x in [a.get("first_name"), a.get("last_name")] if x)
        if name:
            authors.append(clean(name))

    posted = None
    raw_date = p.get("approved_date")
    if raw_date:
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                posted = datetime.strptime(str(raw_date)[:19], fmt)
                break
            except ValueError:
                pass

    aid = p.get("id") or p.get("abstract_id")
    return {
        "title": clean(p.get("title", "")),
        "abstract_id": aid,
        "url": p.get("url") or f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={aid}",
        "authors": authors,
        "posted": posted.strftime("%Y-%m-%d") if posted else None,
        "_dt": posted,
        "downloads": p.get("downloads"),
    }


def fetch_recent(binding, cutoff, label):
    out = {}
    for page in range(MAX_PAGES):
        data = get(binding, page * PAGE_SIZE, PAGE_SIZE)
        papers = data.get("papers", [])
        print(f"  [{label}] page {page + 1}: {len(papers)} papers")
        if not papers:
            break
        dates = []
        for raw in papers:
            p = parse_paper(raw)
            if p["_dt"] is None:
                continue
            dates.append(p["_dt"])
            if p["_dt"] >= cutoff:
                out[p["abstract_id"]] = p
        if dates and max(dates) < cutoff:
            break
        time.sleep(SLEEP)
    print(f"  [{label}] {len(out)} papers in window")
    return list(out.values())


def build(days):
    cutoff = datetime.now() - timedelta(days=days)
    print(f"papers posted since {cutoff:%Y-%m-%d}\n")

    seen = set()
    final = []
    for q in QUOTAS:
        print(f"{q['label']} (binding {q['binding']})")
        papers = fetch_recent(q["binding"], cutoff, q["label"])
        ranked = sorted([p for p in papers if p["downloads"] is not None],
                        key=lambda p: p["downloads"], reverse=True)
        n = 0
        for p in ranked:
            if p["abstract_id"] in seen:
                continue
            p["network"] = q["label"]
            final.append(p)
            seen.add(p["abstract_id"])
            n += 1
            if n >= q["quota"]:
                break
        print(f"  took {n}\n")

    final.sort(key=lambda p: p["downloads"], reverse=True)

    for i, p in enumerate(final, 1):
        auth = ", ".join(p["authors"][:4]) + (" et al." if len(p["authors"]) > 4 else "")
        print(f"{i:2d}. [{p['downloads']:,} dl] ({p['network']}) {p['title']}")
        print(f"      {auth}")
        print(f"      {p['posted']}  {p['url']}\n")

    out = {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "window_days": days,
        "composition": [{"label": q["label"], "quota": q["quota"]} for q in QUOTAS],
        "papers": [{k: v for k, v in p.items() if k != "_dt"} for p in final],
    }
    path = f"digest_{out['generated']}.json"
    Path(path).write_text(json.dumps(out, indent=2))
    print(f"saved {path}")


def discover(start, end):
    for bid in range(start, end + 1):
        print(f"--- {bid} ---")
        try:
            data = get(bid, 0, 3)
        except Exception as e:
            print(f"  {e}")
            time.sleep(SLEEP)
            continue
        print(f"  total: {data.get('total')}")
        for raw in data.get("papers", []):
            print(f"  {parse_paper(raw)['title'][:90]}")
        time.sleep(SLEEP)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--discover", nargs=2, type=int, metavar=("START", "END"))
    args = ap.parse_args()
    if args.discover:
        discover(*args.discover)
    else:
        build(args.days)