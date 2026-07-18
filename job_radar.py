"""
Daily radar for MLOps/DevOps jobs and volunteer openings in Innsbruck, Austria,
with a focus on postings that support relocation. Sends new results to Telegram.

Data sources:
  - Arbeitnow Job Board API (https://arbeitnow.com/api/job-board-api) - free, no key.
  - Google Programmable Search Engine (Custom Search JSON API) - free tier, 100
    queries/day. Used to search specific job boards and volunteer sites that
    don't expose a public API. Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID.

State: seen_jobs.json stores IDs already notified about, so only new postings
are sent each run. The GitHub Actions workflow commits this file back after
each run.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request

SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")

MLOPS_KEYWORDS = [
    "mlops", "ml ops", "machine learning engineer", "ml engineer",
    "ml platform", "ai infrastructure", "machine learning infrastructure",
]
DEVOPS_KEYWORDS = [
    "devops", "site reliability", " sre ", "platform engineer",
    "cloud engineer", "infrastructure engineer",
]
LEVEL_KEYWORDS = [
    "junior", "intern", "internship", "entry level", "entry-level",
    "graduate", "working student", "werkstudent", "praktikum",
    "mid-level", "mid level", "middle",
]
RELOCATION_KEYWORDS = [
    "relocation", "relocate", "visa sponsorship", "visa support",
    "relocation package", "relocation assistance", "umzug",
]
LOCATION_KEYWORDS = ["innsbruck", "tyrol", "tirol", "austria", "österreich"]

VOLUNTEER_SITES = [
    "freiwilligenweb.at",
    "freiwilligenzentren-tirol.at",
    "tsd.gv.at",
    "caritas-tirol.at",
]
JOB_SITES = ["karriere.at", "stepstone.at", "eures.europa.eu", "jobs.tirol.gv.at"]


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def contains_any(text, keywords):
    text = text.lower()
    return any(k in text for k in keywords)


def fetch_arbeitnow():
    """Pull recent listings from the Arbeitnow job board API and filter for
    MLOps/DevOps roles that mention Innsbruck/Tyrol/Austria or relocation
    support. Arbeitnow skews remote/DACH-region, so this mainly catches
    Austria-wide and relocation-friendly remote postings, not just Innsbruck."""
    results = []
    for page in range(1, 4):
        url = f"https://arbeitnow.com/api/job-board-api?page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "innsbruck-job-radar/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[arbeitnow] page {page} failed: {e}")
            break
        jobs = payload.get("data", [])
        if not jobs:
            break
        for job in jobs:
            haystack = " ".join([
                job.get("title", ""),
                job.get("description", ""),
                job.get("location", ""),
                " ".join(job.get("tags", [])),
                " ".join(job.get("job_types", [])),
            ])
            is_mlops = contains_any(haystack, MLOPS_KEYWORDS)
            is_devops = contains_any(haystack, DEVOPS_KEYWORDS)
            if not (is_mlops or is_devops):
                continue
            is_local = contains_any(haystack, LOCATION_KEYWORDS)
            supports_relocation = contains_any(haystack, RELOCATION_KEYWORDS)
            if not (is_local or supports_relocation):
                continue
            is_right_level = contains_any(haystack, LEVEL_KEYWORDS)
            results.append({
                "id": "arbeitnow:" + job.get("slug", job.get("url", "")),
                "title": job.get("title", ""),
                "company": job.get("company_name", ""),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
                "category": "MLOps" if is_mlops else "DevOps",
                "level_match": is_right_level,
                "relocation_mentioned": supports_relocation,
                "source": "Arbeitnow",
            })
        time.sleep(0.5)
    return results


def google_cse_search(query, num=10):
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):
        return []
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": min(num, 10),
    }
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[google_cse] query failed ({query!r}): {e}")
        return []
    return payload.get("items", [])


def fetch_web_jobs():
    """Search specific Austrian job boards + EURES via Google Custom Search,
    for MLOps/DevOps roles near Innsbruck that mention relocation support."""
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):
        print("[web_jobs] GOOGLE_CSE_API_KEY / GOOGLE_CSE_ID not set, skipping web search")
        return []
    results = []
    queries = [
        ('site:{site} MLOps OR "ML Engineer" Innsbruck junior OR intern OR "entry level" relocation', "MLOps"),
        ('site:{site} DevOps OR "Site Reliability" Innsbruck junior OR intern OR "entry level" relocation', "DevOps"),
    ]
    for site in JOB_SITES:
        for template, category in queries:
            items = google_cse_search(template.format(site=site))
            for item in items:
                link = item.get("link", "")
                results.append({
                    "id": "web:" + link,
                    "title": item.get("title", ""),
                    "company": site,
                    "location": "see listing",
                    "url": link,
                    "category": category,
                    "level_match": True,
                    "relocation_mentioned": True,
                    "source": site,
                })
    return results


def fetch_volunteer_opportunities():
    """Search Tyrolean volunteer-matching sites for open opportunities in
    Innsbruck via Google Custom Search."""
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):
        print("[volunteer] GOOGLE_CSE_API_KEY / GOOGLE_CSE_ID not set, skipping web search")
        return []
    results = []
    for site in VOLUNTEER_SITES:
        items = google_cse_search(f'site:{site} Innsbruck Freiwillige OR Freiwilligenarbeit')
        for item in items:
            link = item.get("link", "")
            results.append({
                "id": "volunteer:" + link,
                "title": item.get("title", ""),
                "company": site,
                "location": "Innsbruck",
                "url": link,
                "category": "Volunteer",
                "level_match": True,
                "relocation_mentioned": False,
                "source": site,
            })
    return results


def send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set, printing instead:\n" + text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except Exception as e:
        print(f"[telegram] send failed: {e}")


def chunk_message(lines, max_len=3800):
    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)
    return chunks


def format_entry(entry):
    tags = []
    if entry["category"] != "Volunteer":
        if entry["level_match"]:
            tags.append("level-match")
        if entry["relocation_mentioned"]:
            tags.append("relocation")
    tag_str = f" [{', '.join(tags)}]" if tags else ""
    return f"* {entry['title']} - {entry['company']}{tag_str}\n  {entry['url']}"


def main():
    seen = load_seen()
    all_results = fetch_arbeitnow() + fetch_web_jobs() + fetch_volunteer_opportunities()

    new_by_category = {"MLOps": [], "DevOps": [], "Volunteer": []}
    for entry in all_results:
        if entry["id"] in seen:
            continue
        seen[entry["id"]] = True
        new_by_category.setdefault(entry["category"], []).append(entry)

    lines = []
    total_new = sum(len(v) for v in new_by_category.values())
    if total_new == 0:
        print("No new postings found.")
        save_seen(seen)
        return

    lines.append(f"Innsbruck job/volunteer radar - {total_new} new result(s)\n")
    for category in ["MLOps", "DevOps", "Volunteer"]:
        entries = new_by_category.get(category, [])
        if not entries:
            continue
        lines.append(f"--- {category} ({len(entries)}) ---")
        for entry in entries:
            lines.append(format_entry(entry))
        lines.append("")

    for chunk in chunk_message(lines):
        send_telegram(chunk)

    save_seen(seen)


if __name__ == "__main__":
    main()
