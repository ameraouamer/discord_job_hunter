#!/usr/bin/env python3
"""
Job Radar: posts new job links to a Discord channel via webhook.

Sources: LinkedIn (public guest search), Remote OK, We Work Remotely,
Remotive, Arbeitnow (Europe).

Install:  pip install requests beautifulsoup4 feedparser
Run:      python job_radar.py          (loops forever)
          python job_radar.py --once   (single pass, for cron / Task Scheduler)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
#  1) REPLACE THESE (everything you need to edit is in this block)
# =====================================================================

# REPLACE: paste your Discord webhook URL between the quotes
# (Channel Settings -> Integrations -> Webhooks -> New Webhook -> Copy URL).
# Or leave it and set an environment variable named DISCORD_WEBHOOK_URL.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL")

# REPLACE: the job titles you want LinkedIn to search for.
LINKEDIN_KEYWORDS = [
    "junior machine learning engineer",
    "junior AI engineer",
]

# REPLACE: the places you want LinkedIn to search in.
LINKEDIN_LOCATIONS = [
    "Germany",
    "France",
    "Europe",
    "United Arab Emirates",
    "Saudi Arabia",
]

# REPLACE: for the other sites, a job is posted only if its title contains
# at least one of these words...
TITLE_MUST_CONTAIN = [
    "machine learning", "ml", "ai", "data scientist", "data science",
    "nlp", "llm", "deep learning", "computer vision", "mlops",
]
# ...and none of these.
TITLE_MUST_NOT_CONTAIN = [
    "senior", "sr", "staff", "lead", "principal", "director", "head", "manager",
]

# Turn a source off by setting it to False.
ENABLE = {
    "linkedin": True,
    "remoteok": True,
    "weworkremotely": True,
    "remotive": True,
    "arbeitnow": True,
}

CHECK_EVERY_MINUTES = 30      # how often the loop runs
LINKEDIN_MAX_AGE_HOURS = 24   # only LinkedIn jobs posted within this window
FIRST_RUN_LIMIT = 10          # on the very first run, post at most this many

# =====================================================================
#  2) Nothing below needs editing
# =====================================================================

STATE_FILE = Path(__file__).with_name("seen_jobs.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JobRadar/1.0"}
# Some APIs ask not to be hit too often: minimum minutes between calls.
MIN_MINUTES = {"remotive": 360, "linkedin": 0, "remoteok": 0,
               "weworkremotely": 0, "arbeitnow": 0}


def job(id_, title, company, location, url, source):
    return {"id": f"{source}:{id_}", "title": title.strip(),
            "company": (company or "Unknown").strip(),
            "location": (location or "Not specified").strip(),
            "url": url, "source": source}


# ---------------------------- sources -------------------------------

def fetch_linkedin():
    out = []
    seconds = LINKEDIN_MAX_AGE_HOURS * 3600
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    for kw in LINKEDIN_KEYWORDS:
        for loc in LINKEDIN_LOCATIONS:
            try:
                r = requests.get(base, headers=UA, timeout=20, params={
                    "keywords": kw, "location": loc,
                    "f_TPR": f"r{seconds}", "start": 0})
                if r.status_code != 200:
                    print(f"  linkedin {r.status_code} for '{kw}' in {loc}")
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for card in soup.select("li"):
                    a = card.select_one("a.base-card__full-link")
                    t = card.select_one(".base-search-card__title")
                    if not a or not t:
                        continue
                    c = card.select_one(".base-search-card__subtitle")
                    l = card.select_one(".job-search-card__location")
                    url = a["href"].split("?")[0]
                    jid = url.rstrip("/").split("-")[-1]
                    out.append(job(jid, t.get_text(), c.get_text() if c else "",
                                   l.get_text() if l else loc, url, "LinkedIn"))
            except requests.RequestException as e:
                print("  linkedin error:", e)
            time.sleep(2.5)  # be polite, LinkedIn throttles quickly
    return out


def fetch_remoteok():
    data = requests.get("https://remoteok.com/api", headers=UA, timeout=20).json()
    return [job(j["id"], j.get("position", ""), j.get("company"),
                j.get("location") or "Remote", j["url"], "RemoteOK")
            for j in data if isinstance(j, dict) and j.get("id")]


def fetch_weworkremotely():
    feed = feedparser.parse("https://weworkremotely.com/categories/remote-programming-jobs.rss")
    out = []
    for e in feed.entries:
        # titles look like "Company: Job title"
        company, _, title = e.title.partition(": ")
        out.append(job(e.link, title or e.title, company if title else "",
                       "Remote", e.link, "WeWorkRemotely"))
    return out


def fetch_remotive():
    out = []
    for q in ("machine learning", "ai engineer", "data scientist"):
        r = requests.get("https://remotive.com/api/remote-jobs",
                         params={"search": q}, headers=UA, timeout=20).json()
        out += [job(j["id"], j["title"], j["company_name"],
                    j.get("candidate_required_location"), j["url"], "Remotive")
                for j in r.get("jobs", [])]
    return out


def fetch_arbeitnow():
    r = requests.get("https://www.arbeitnow.com/api/job-board-api",
                     headers=UA, timeout=20).json()
    return [job(j["slug"], j["title"], j["company_name"],
                "Remote" if j.get("remote") else j.get("location"),
                j["url"], "Arbeitnow") for j in r.get("data", [])]


SOURCES = {"linkedin": fetch_linkedin, "remoteok": fetch_remoteok,
           "weworkremotely": fetch_weworkremotely, "remotive": fetch_remotive,
           "arbeitnow": fetch_arbeitnow}


# ---------------------------- logic ---------------------------------

def word_match(words, text):
    return any(re.search(rf"\b{re.escape(w)}\b", text, re.I) for w in words)


def wanted(j):
    if word_match(TITLE_MUST_NOT_CONTAIN, j["title"]):
        return False
    if j["source"] == "LinkedIn":      # already filtered by the search itself
        return True
    return word_match(TITLE_MUST_CONTAIN, j["title"])


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen": [], "last": {}, "first_run": True}


def save_state(state):
    state["seen"] = state["seen"][-5000:]
    STATE_FILE.write_text(json.dumps(state))


def post(j):
    msg = (f"**{j['title']}**\n"
           f"🏢 {j['company']}  ·  📍 {j['location']}  ·  _{j['source']}_\n"
           f"{j['url']}")
    while True:
        r = requests.post(DISCORD_WEBHOOK_URL, timeout=15,
                          json={"content": msg, "username": "Job Radar"})
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            continue
        r.raise_for_status()
        return


def run_once():
    state = load_state()
    seen = set(state["seen"])
    found = []
    for name, fn in SOURCES.items():
        if not ENABLE.get(name):
            continue
        if time.time() - state["last"].get(name, 0) < MIN_MINUTES[name] * 60:
            continue
        print(f"Checking {name}...")
        try:
            found += fn()
            state["last"][name] = time.time()
        except Exception as e:
            print(f"  {name} failed: {e}")

    new, ids = [], set()
    for j in found:
        if j["id"] in seen or j["id"] in ids or not wanted(j):
            continue
        ids.add(j["id"])
        new.append(j)

    to_post = new
    if state.get("first_run"):
        to_post = new[:FIRST_RUN_LIMIT]   # avoid flooding the channel at start
        state["first_run"] = False

    for j in to_post:
        try:
            post(j)
            time.sleep(1)
        except requests.RequestException as e:
            print("  Discord error:", e)
            ids.discard(j["id"])          # retry next time
    state["seen"] += list(ids)
    # also mark skipped first-run extras as seen
    state["seen"] += [j["id"] for j in new if j not in to_post]
    save_state(state)
    print(f"Done. Posted {len(to_post)} new job(s).")


if __name__ == "__main__":
    if not DISCORD_WEBHOOK_URL.startswith("https://discord"):
        sys.exit("Set DISCORD_WEBHOOK_URL first (see the REPLACE block at the top).")
    if "--once" in sys.argv:
        run_once()
    else:
        while True:
            run_once()
            time.sleep(CHECK_EVERY_MINUTES * 60)