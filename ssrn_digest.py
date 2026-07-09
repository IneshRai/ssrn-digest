"""
SSRN weekly digest: top 25 papers by downloads added to the Financial
Economics Network in the trailing N days.

Usage:
    pip install requests
    python ssrn_digest.py --discover      (first run: confirm the FEN binding ID)
    python ssrn_digest.py                 (normal run: build the digest)
    python ssrn_digest.py --days 14 --top 25 --binding 203

All raw API responses are saved under ./debug/ so if anything about the
schema is off we can inspect exactly what SSRN returned.

Output:
    prints the digest to stdout
    writes digest_YYYY-MM-DD.json with the ranked papers
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API_BASE = "https://api.ssrn.com/content/v1"
DEFAULT_BINDING = 203
PAGE_SIZE = 50
MAX_PAGES = 40
SLEEP_BETWEEN_REQUESTS = 2.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.ssrn.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

DEBUG_DIR = Path("debug")

DATE_FIELD_CANDIDATES = [
    "approved_date",
    "approvedDate",
    "publication_date",
    "publicationDate",
    "posted_date",
    "postedDate",
    "date_posted",
    "online_date",
]

DOWNLOAD_FIELD_CANDIDATES = [
    "downloads",
    "download_count",
    "downloadCount",
    "total_downloads",
    "totalDownloads",
    "abstract_downloads",
]

DATE_FORMATS = [
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%m/%d/%Y",
    "%b %d, %Y",
    "%B %d, %Y",
]


def save_debug(name, payload):
    DEBUG_DIR.mkdir(exist_ok=True)
    path = DEBUG_DIR / name
    with open(path, "w") as f:
        if isinstance(payload, (dict, list)):
            json.dump(payload, f, indent=2)
        else:
            f.write(str(payload))


def api_get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    stamp = datetime.now().strftime("%H%M%S")
    if r.status_code != 200:
        save_debug(f"error_{stamp}.txt", f"URL: {r.url}\nSTATUS: {r.status_code}\n\n{r.text[:5000]}")
        raise RuntimeError(
            f"HTTP {r.status_code} from {r.url}. "
            f"Raw response saved to debug/. If this is a 403, Cloudflare is "
            f"blocking plain requests and we should switch to curl_cffi."
        )
    try:
        data = r.json()
    except ValueError:
        save_debug(f"nonjson_{stamp}.txt", r.text[:10000])
        raise RuntimeError(
            f"Non-JSON response from {r.url}, first bytes saved to debug/. "
            f"Likely a Cloudflare challenge page."
        )
    return data


def parse_date(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            if raw > 1e12:
                raw = raw / 1000.0
            return datetime.fromtimestamp(raw, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError, OverflowError):
            return None
    s = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    return None


def first_present(d, candidates):
    for key in candidates:
        if key in d and d[key] not in (None, ""):
            return key, d[key]
    return None, None


def extract_papers_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["papers", "results", "items", "content", "data"]:
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def normalize_paper(p):
    title = p.get("title") or p.get("paper_title") or "(no title)"
    if isinstance(title, str):
        title = re.sub(r"<[^>]+>", "", title).strip()

    abstract_id = (
        p.get("abstract_id")
        or p.get("abstractId")
        or p.get("id")
        or p.get("ssrn_id")
    )

    url = p.get("url") or p.get("abstract_url")
    if not url and abstract_id:
        url = f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={abstract_id}"

    authors_raw = p.get("authors") or p.get("author") or []
    authors = []
    if isinstance(authors_raw, list):
        for a in authors_raw:
            if isinstance(a, dict):
                name = (
                    a.get("name")
                    or " ".join(x for x in [a.get("first_name"), a.get("last_name")] if x)
                    or " ".join(x for x in [a.get("firstName"), a.get("lastName")] if x)
                )
                if name:
                    authors.append(name)
            elif isinstance(a, str):
                authors.append(a)
    elif isinstance(authors_raw, str):
        authors = [authors_raw]

    date_key, date_raw = first_present(p, DATE_FIELD_CANDIDATES)
    posted = parse_date(date_raw)

    dl_key, dl_raw = first_present(p, DOWNLOAD_FIELD_CANDIDATES)
    try:
        downloads = int(str(dl_raw).replace(",", "")) if dl_raw is not None else None
    except ValueError:
        downloads = None

    return {
        "title": title,
        "abstract_id": abstract_id,
        "url": url,
        "authors": authors,
        "posted": posted.strftime("%Y-%m-%d") if posted else None,
        "_posted_dt": posted,
        "downloads": downloads,
        "_date_field_used": date_key,
        "_download_field_used": dl_key,
    }


def discover(candidate_ids):
    print("Discovery mode: probing candidate binding IDs.\n")
    for bid in candidate_ids:
        print(f"--- binding {bid} ---")
        try:
            data = api_get(f"{API_BASE}/bindings/{bid}/papers", params={"index": 0, "count": 2, "sort": 0})
        except RuntimeError as e:
            print(f"  {e}")
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue
        save_debug(f"discover_binding_{bid}.json", data)
        if isinstance(data, dict):
            meta_hints = {k: v for k, v in data.items() if isinstance(v, (str, int)) and k.lower() not in ("index", "count")}
            if meta_hints:
                print(f"  metadata: {meta_hints}")
        papers = extract_papers_list(data)
        print(f"  papers returned: {len(papers)}")
        if papers:
            sample = papers[0]
            print(f"  sample paper keys: {sorted(sample.keys())}")
            norm = normalize_paper(sample)
            print(f"  sample title: {norm['title'][:80]}")
            print(f"  date field detected: {norm['_date_field_used']} -> {norm['posted']}")
            print(f"  download field detected: {norm['_download_field_used']} -> {norm['downloads']}")
        print()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    print("Full raw responses are in debug/discover_binding_*.json")
    print("Confirm which binding is Financial Economics, then run without --discover.")


def build_digest(binding, days, top_n):
    cutoff = datetime.now() - timedelta(days=days)
    print(f"Fetching binding {binding}, papers posted on or after {cutoff.strftime('%Y-%m-%d')}.\n")

    collected = {}
    undated = 0
    stop = False

    for page in range(MAX_PAGES):
        index = page * PAGE_SIZE
        print(f"page {page + 1} (index {index}) ...", end=" ", flush=True)
        data = api_get(
            f"{API_BASE}/bindings/{binding}/papers",
            params={"index": index, "count": PAGE_SIZE, "sort": 0},
        )
        save_debug(f"page_{page + 1}.json", data)
        papers = extract_papers_list(data)
        print(f"{len(papers)} papers")
        if not papers:
            break

        page_dates = []
        for raw in papers:
            norm = normalize_paper(raw)
            if norm["_posted_dt"] is None:
                undated += 1
                continue
            page_dates.append(norm["_posted_dt"])
            if norm["_posted_dt"] >= cutoff:
                key = norm["abstract_id"] or norm["title"]
                collected[key] = norm

        if page_dates and max(page_dates) < cutoff:
            stop = True
        if stop:
            print("Reached papers older than the cutoff, stopping pagination.")
            break
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    papers = list(collected.values())
    print(f"\nCollected {len(papers)} papers within the window ({undated} skipped for unparseable dates).")

    if undated > 0 and len(papers) == 0:
        print("Every paper had an unparseable date. Check debug/page_1.json for the")
        print("actual date field name and format, then we patch DATE_FIELD_CANDIDATES.")
        sys.exit(1)

    with_dl = [p for p in papers if p["downloads"] is not None]
    if len(with_dl) < len(papers):
        print(f"Note: {len(papers) - len(with_dl)} papers had no download count and were excluded from ranking.")
    if not with_dl:
        print("No download counts found on any paper. Check debug/page_1.json for the")
        print("actual field name, then we patch DOWNLOAD_FIELD_CANDIDATES.")
        sys.exit(1)

    ranked = sorted(with_dl, key=lambda p: p["downloads"], reverse=True)[:top_n]

    print(f"\n{'=' * 78}")
    print(f"TOP {len(ranked)} SSRN PAPERS BY DOWNLOADS, POSTED IN LAST {days} DAYS (binding {binding})")
    print(f"{'=' * 78}\n")
    for i, p in enumerate(ranked, 1):
        authors = ", ".join(p["authors"][:4])
        if len(p["authors"]) > 4:
            authors += " et al."
        print(f"{i:2d}. [{p['downloads']:,} dl] {p['title']}")
        if authors:
            print(f"      {authors}")
        print(f"      posted {p['posted']}  |  {p['url']}\n")

    out_path = f"digest_{datetime.now().strftime('%Y-%m-%d')}.json"
    serializable = [{k: v for k, v in p.items() if not k.startswith('_')} for p in ranked]
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"Saved ranked list to {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="probe candidate binding IDs and exit")
    ap.add_argument("--binding", type=int, default=DEFAULT_BINDING, help="SSRN binding ID (default 203)")
    ap.add_argument("--days", type=int, default=7, help="trailing window in days (default 7)")
    ap.add_argument("--top", type=int, default=25, help="number of papers in digest (default 25)")
    args = ap.parse_args()

    if args.discover:
        discover([202, 203, 204, 205, 3388738])
    else:
        build_digest(args.binding, args.days, args.top)


if __name__ == "__main__":
    main()
