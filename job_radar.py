"""
Job Radar: posts new job links to a Discord channel via webhook.

Roles: AI/ML, data, mobile, web, WordPress, security.
Focus: remote jobs, relocation / visa-sponsored jobs, and Algerian companies.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()  # reads DISCORD_WEBHOOK_URL from a local .env file if present

# =====================================================================
#  1) REPLACE THESE (everything you need to edit is in this block)
# =====================================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip().strip("\"')")

# ---- LinkedIn --------------------------------------------------------
LINKEDIN_KEYWORDS = [
    # AI / data
    "junior machine learning engineer",
    "junior AI engineer",
    "junior data scientist",
    "junior data analyst",
    "junior data engineer",
    # mobile / web / wordpress
    "junior mobile developer",
    "junior flutter developer",
    "junior web developer",
    "junior full stack developer",
    "junior wordpress developer",
    # security
    "junior cybersecurity analyst",
    "junior security engineer",
]

# (location, remote_only). Remote-only searches use LinkedIn's "Remote" filter.
LINKEDIN_SEARCHES = [
    ("Worldwide", True),
    ("Europe", True),
    ("Algeria", False),                 # Algerian companies / startups
    ("Germany", False),                 # on-site countries: we add "visa sponsorship"
    ("Netherlands", False),
    ("Ireland", False),
    ("Canada", False),
    ("United Kingdom", False),
    ("United Arab Emirates", False),
    ("Qatar", False),
]
LINKEDIN_VISA_SUFFIX = " visa sponsorship"   # added to on-site (non-Algeria) searches

# ---- Role categories ----------------------------------------------------
# Used to mix role types in every batch of posts (so AI/ML can't take all the
# slots). The first matching category wins, so keep the order.
CATEGORIES = {
    "WordPress": ["wordpress"],
    "Security": ["security", "cybersecurity", "cyber", "pentest", "penetration",
                 "soc", "devsecops", "infosec", "sécurité", "securite", "cybersécurité"],
    "Mobile": ["mobile", "android", "ios", "flutter", "react native", "kotlin", "swift"],
    "AI/ML": ["machine learning", "ml", "ai", "data scientist", "data science", "nlp",
              "llm", "deep learning", "computer vision", "mlops",
              "intelligence artificielle"],
    "Data": ["data analyst", "data engineer", "analytics", "business intelligence",
             "bi", "data", "données", "donnees"],
    "Web": ["web", "frontend", "front-end", "front end", "backend", "back-end",
            "back end", "full stack", "fullstack", "full-stack", "php", "laravel",
            "react", "vue", "node", "django"],
}

# ---- Title filters for the other sites --------------------------------
# A job is posted if its title contains one of these...
TITLE_MUST_CONTAIN = [
    # AI / data
    "machine learning", "ml", "ai", "data scientist", "data science", "nlp",
    "llm", "deep learning", "computer vision", "mlops", "data analyst",
    "data engineer", "analytics", "business intelligence", "bi",
    "intelligence artificielle", "données", "donnees", "data",
    # mobile
    "mobile", "android", "ios", "flutter", "react native", "kotlin", "swift",
    # web / wordpress
    "web", "wordpress", "frontend", "front-end", "front end", "backend",
    "back-end", "back end", "full stack", "fullstack", "full-stack", "php",
    "laravel", "react", "vue", "node", "django", "développeur web",
    # security
    "security", "cybersecurity", "cyber", "pentest", "penetration", "soc",
    "devsecops", "infosec", "sécurité", "securite", "cybersécurité",
]
# Generic titles: only accepted if they also look junior (or are from an
# Algerian site, see LENIENT_SOURCES).
GENERIC_TITLE_WORDS = [
    "developer", "software engineer", "engineer", "développeur", "developpeur",
    "ingénieur", "ingenieur", "informatique", "programmer",
]
# ...and none of these.
TITLE_MUST_NOT_CONTAIN = [
    "senior", "sr", "staff", "lead", "principal", "director", "head", "manager",
    "architect", "consultant", "expert", "chief", "vp", "cto", "founding",
    "product owner", "product engineer", "sales", "marketing", "ii", "iii", "iv",
    # French / Algerian listings
    "responsable", "directeur", "directrice", "chef", "confirmé", "confirme",
    "commercial", "comptable", "assistant administratif",
    # unrelated "security" jobs
    "security guard", "guard", "agent de sécurité", "agent de securite",
    "physical security", "security officer",
]

MAX_YEARS_EXPERIENCE = 2   # set to 99 to disable

REQUIRE_JUNIOR_SIGNAL = False
JUNIOR_WORDS = [
    "junior", "entry level", "entry-level", "graduate", "intern", "internship",
    "working student", "werkstudent", "trainee", "praktikum", "berufseinsteiger",
    "early career", "associate", "débutant", "debutant", "stagiaire", "stage",
    "jeune diplômé", "fresh graduate", "new grad",
]

# ---- Remote / visa focus ----------------------------------------------
# Words in a description that suggest relocation help or visa sponsorship.
VISA_WORDS = [
    "visa sponsorship", "visa sponsor", "sponsor visa", "sponsorship",
    "relocation", "relocation package", "relocation support", "relocation assistance",
    "work permit", "blue card", "we sponsor", "visa support", "visa provided",
    "relocate", "umzug", "visum",
]
# The 🌍 badge is shown only when a remote job's location says one of these.
WORLDWIDE_WORDS = ["worldwide", "anywhere", "global", "anywhere in the world",
                   "work from anywhere"]
# Sources where a job is only worth posting if it is remote OR mentions visa/relocation
# (these are mostly on-site jobs in one country).
NEEDS_REMOTE_OR_VISA = {"Arbeitnow"}
# Remote jobs that are restricted to these places are skipped (unless the
# location also says worldwide / anywhere / Europe / EMEA / Africa / MENA).
LOCATION_BLOCK = [
    "usa", "us", "united states", "north america", "canada", "uk",
    "united kingdom", "australia", "india", "latam", "latin america", "brazil",
]
LOCATION_OK = ["worldwide", "anywhere", "global", "emea", "europe", "africa",
               "mena", "middle east", "international"]

# ---- Algerian sites -----------------------------------------------------
# (name, search URL with {q}, regex a job link's URL must match, base URL).
# These are best guesses: open each one in a browser, search something, and
# adjust the URL / regex to match what you see.
ALGERIA_SITES = [
    ("Emploitic",
     "https://www.emploitic.com/offres-d-emploi?keywords={q}",
     r"/offres-d-emploi/", "https://www.emploitic.com"),
    ("Ouedkniss",
     "https://www.ouedkniss.com/emploi-offres?keywords={q}",
     r"/emploi", "https://www.ouedkniss.com"),
    ("OptionCarriere",
     "https://www.optioncarriere.dz/emploi?s={q}",
     r"/emploi/|/jobad/", "https://www.optioncarriere.dz"),
]
ALGERIA_QUERIES = [
    "développeur", "développeur web", "développeur mobile", "wordpress",
    "data scientist", "data analyst", "machine learning", "intelligence artificielle",
    "cybersécurité", "sécurité informatique",
]
LENIENT_SOURCES = {"Emploitic", "Ouedkniss", "OptionCarriere"}

# Turn a source off by setting it to False.
ENABLE = {
    "linkedin": True,
    "algeria": True,
    "remoteok": True,
    "weworkremotely": True,
    "remotive": True,
    "arbeitnow": True,
}

CHECK_EVERY_MINUTES = 30
LINKEDIN_MAX_AGE_HOURS = 24
FIRST_RUN_LIMIT = 10          # on the very first run, post at most this many
MAX_POSTS_PER_RUN = 25        # later runs: the rest wait for the next run

# =====================================================================
#  2) Nothing below needs editing
# =====================================================================

STATE_FILE = Path(__file__).with_name("seen_jobs.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JobRadar/1.0"}
MIN_MINUTES = {"remotive": 360, "linkedin": 0, "remoteok": 0,
               "weworkremotely": 0, "arbeitnow": 0, "algeria": 60}
REMOTE_SOURCES = {"RemoteOK", "WeWorkRemotely", "Remotive"}

WORD_RE = lambda words: re.compile(  # noqa: E731
    r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I)
VISA_RE = WORD_RE(VISA_WORDS)
REMOTE_RE = re.compile(r"remote|anywhere|worldwide|télétravail|teletravail|home ?office", re.I)


def word_match(words, text):
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.I) for w in words)


def categorize(*texts):
    """Role category of the first text that matches (e.g. keyword, then title)."""
    for text in texts:
        for cat, words in CATEGORIES.items():
            if word_match(words, text):
                return cat
    return "Other"


def job(id_, title, company, location, url, source, desc="", cat="",
        remote_hint=False):
    """remote_hint=True means 'came from a remote-only search' (not verified)."""
    location = (location or "Not specified").strip()
    tags = []
    if source in REMOTE_SOURCES or REMOTE_RE.search(f"{location} {title}"):
        tags.append("remote")
        if word_match(WORLDWIDE_WORDS, location):
            tags.append("worldwide")
    elif remote_hint:
        tags.append("remote?")
    if desc and VISA_RE.search(desc):
        tags.append("visa")
    if source in LENIENT_SOURCES or "algeria" in location.lower():
        tags.append("dz")
    return {"id": f"{source}:{id_}", "title": title.strip(), "desc": desc or "",
            "company": (company or "Unknown").strip(), "location": location,
            "url": url, "source": source, "tags": tags,
            "cat": cat or categorize(title)}


# ---------------------------- sources -------------------------------

def fetch_linkedin():
    out = []
    seconds = LINKEDIN_MAX_AGE_HOURS * 3600
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    for loc, remote_only in LINKEDIN_SEARCHES:
        for kw in LINKEDIN_KEYWORDS:
            query = kw
            if not remote_only and loc != "Algeria":
                query += LINKEDIN_VISA_SUFFIX
            params = {"keywords": query, "location": loc,
                      "f_TPR": f"r{seconds}", "start": 0}
            if remote_only:
                params["f_WT"] = 2          # LinkedIn "Remote" filter
            try:
                r = requests.get(base, headers=UA, timeout=20, params=params)
                if r.status_code == 429:
                    print("  linkedin is throttling us, stopping this round")
                    return out
                if r.status_code != 200:
                    print(f"  linkedin {r.status_code} for '{query}' in {loc}")
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
                    place = l.get_text() if l else loc
                    title = t.get_text()
                    j = job(jid, title, c.get_text() if c else "", place,
                            url, "LinkedIn", cat=categorize(kw, title),
                            remote_hint=remote_only)
                    if not remote_only and loc != "Algeria":
                        j["tags"].append("visa?")   # found via a visa-sponsorship search
                    out.append(j)
            except requests.RequestException as e:
                print("  linkedin error:", e)
            time.sleep(2.5)  # be polite, LinkedIn throttles quickly
    return out


def fetch_algeria():
    out = []
    for name, url_tpl, href_re, base in ALGERIA_SITES:
        found = 0
        for q in ALGERIA_QUERIES:
            try:
                r = requests.get(url_tpl.format(q=quote_plus(q)), headers=UA, timeout=25)
                if r.status_code != 200:
                    print(f"  {name} {r.status_code} for '{q}'")
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = urljoin(base, a["href"])
                    title = a.get_text(" ", strip=True)
                    if len(title) < 6 or not re.search(href_re, href):
                        continue
                    jid = href.split("?")[0].rstrip("/")
                    out.append(job(jid, title, "", "Algeria", href, name,
                                   cat=categorize(title, q)))
                    found += 1
            except requests.RequestException as e:
                print(f"  {name} error:", e)
            time.sleep(1.5)
        print(f"  {name}: {found} link(s) matched")   # 0 means fix the URL/regex
    return out


def fetch_remoteok():
    data = requests.get("https://remoteok.com/api", headers=UA, timeout=20).json()
    return [job(j["id"], j.get("position", ""), j.get("company"),
                j.get("location") or "Remote", j["url"], "RemoteOK",
                j.get("description", ""))
            for j in data if isinstance(j, dict) and j.get("id")]


WWR_FEEDS = [
    "remote-programming-jobs", "remote-full-stack-programming-jobs",
    "remote-front-end-programming-jobs", "remote-back-end-programming-jobs",
    "remote-devops-sysadmin-jobs", "remote-data-jobs",
]


def fetch_weworkremotely():
    out = []
    for slug in WWR_FEEDS:
        feed = feedparser.parse(f"https://weworkremotely.com/categories/{slug}.rss")
        for e in feed.entries:
            company, _, title = e.title.partition(": ")   # "Company: Job title"
            region = e.get("region", "") or "Remote"
            out.append(job(e.link, title or e.title, company if title else "",
                           region, e.link, "WeWorkRemotely",
                           e.get("summary", "")))
    return out


def fetch_remotive():
    out = []
    for q in ("machine learning", "ai engineer", "data scientist", "data analyst",
              "mobile", "flutter", "wordpress", "web developer", "security"):
        r = requests.get("https://remotive.com/api/remote-jobs",
                         params={"search": q}, headers=UA, timeout=20).json()
        out += [job(j["id"], j["title"], j["company_name"],
                    j.get("candidate_required_location"), j["url"], "Remotive",
                    j.get("description", ""))
                for j in r.get("jobs", [])]
    return out


def fetch_arbeitnow():
    r = requests.get("https://www.arbeitnow.com/api/job-board-api",
                     headers=UA, timeout=20).json()
    return [job(j["slug"], j["title"], j["company_name"],
                "Remote" if j.get("remote") else j.get("location"),
                j["url"], "Arbeitnow", j.get("description", ""))
            for j in r.get("data", [])]


SOURCES = {"linkedin": fetch_linkedin, "algeria": fetch_algeria,
           "remoteok": fetch_remoteok, "weworkremotely": fetch_weworkremotely,
           "remotive": fetch_remotive, "arbeitnow": fetch_arbeitnow}


# ---------------------------- logic ---------------------------------

EXP_RE = re.compile(
    r"(?:(\d{1,2})\s*(?:-|–|to|à)\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?|jahre?n?|ans)\b"
    r"[^.\n]{0,40}?(?:experience|expérience|erfahrung)", re.I)


def plain(html):
    return BeautifulSoup(html or "", "html.parser").get_text(" ")


def too_experienced(text):
    for m in EXP_RE.finditer(text):
        if int(m.group(1) or m.group(2)) > MAX_YEARS_EXPERIENCE:
            return True
    return False


def location_blocked(loc):
    if word_match(LOCATION_OK, loc):
        return False
    return word_match(LOCATION_BLOCK, loc)


def wanted(j):
    title = j["title"]
    if word_match(TITLE_MUST_NOT_CONTAIN, title):
        return False
    if j["source"] == "LinkedIn":      # already filtered by the search itself
        return True

    specific = word_match(TITLE_MUST_CONTAIN, title)
    generic = word_match(GENERIC_TITLE_WORDS, title)
    if not specific and not generic:
        return False

    text = plain(j["desc"])
    if too_experienced(text):
        return False

    junior = word_match(JUNIOR_WORDS, title + " " + text)
    lenient = j["source"] in LENIENT_SOURCES
    if generic and not specific and not junior and not lenient:
        return False
    if REQUIRE_JUNIOR_SIGNAL and not junior and not lenient:
        return False

    if j["source"] in REMOTE_SOURCES and location_blocked(j["location"]):
        return False
    if j["source"] in NEEDS_REMOTE_OR_VISA and not (
            "remote" in j["tags"] or "visa" in j["tags"]):
        return False
    return True


def priority(j):
    t = j["tags"]
    return (2 * ("visa" in t) + 2 * ("remote" in t) + 2 * ("dz" in t)
            + ("visa?" in t) + ("remote?" in t))


def pick_diverse(jobs, limit):
    """Round-robin over role categories so one type can't take every slot.
    `jobs` must already be sorted best-first; order is kept inside a category."""
    buckets = {}
    for j in jobs:
        buckets.setdefault(j["cat"], []).append(j)
    picked = []
    while len(picked) < limit and any(buckets.values()):
        for cat in list(buckets):
            if buckets[cat] and len(picked) < limit:
                picked.append(buckets[cat].pop(0))
    return picked


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen": [], "last": {}, "first_run": True}


def save_state(state):
    state["seen"] = state["seen"][-5000:]
    STATE_FILE.write_text(json.dumps(state))


def post(j):
    t = j["tags"]
    badges = [f"🏷 {j['cat']}"]
    if "remote" in t:
        badges.append("🌍 Worldwide remote" if "worldwide" in t else "🏠 Remote")
    elif "remote?" in t:
        badges.append("🏠 Remote (LinkedIn filter)")
    if "visa" in t:
        badges.append("🛂 Visa/relocation")
    elif "visa?" in t:
        badges.append("🛂 Visa search")
    if "dz" in t:
        badges.append("🇩🇿 Algeria")
    msg = (f"**{j['title']}**\n"
           f"🏢 {j['company']}  ·  📍 {j['location']}  ·  _{j['source']}_\n"
           f"{' · '.join(badges)}\n"
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
            items = fn()
            found += items
            state["last"][name] = time.time()
            ok = sum(1 for j in items if wanted(j))
            print(f"  {name}: {len(items)} fetched, {ok} pass the filters")
        except Exception as e:
            print(f"  {name} failed: {e}")

    new, ids = [], set()
    for j in found:
        if j["id"] in seen or j["id"] in ids or not wanted(j):
            continue
        ids.add(j["id"])
        new.append(j)

    new.sort(key=priority, reverse=True)   # remote / visa / Algerian first
    by_cat = {}
    for j in new:
        by_cat[j["cat"]] = by_cat.get(j["cat"], 0) + 1
    print(f"{len(found)} fetched in total, {len(new)} new after filters and dedupe: {by_cat}")

    if state.get("first_run"):
        to_post = pick_diverse(new, FIRST_RUN_LIMIT)   # avoid flooding at start
        state["first_run"] = False
        chosen = {j["id"] for j in to_post}
        skipped = [j["id"] for j in new if j["id"] not in chosen]  # mark as seen
    else:
        to_post = pick_diverse(new, MAX_POSTS_PER_RUN)  # the rest wait for next run
        skipped = []

    posted = set()
    for j in to_post:
        try:
            post(j)
            posted.add(j["id"])
            time.sleep(1)
        except requests.RequestException as e:
            print("  Discord error:", e)   # not marked seen -> retried next time
    state["seen"] += list(posted) + skipped
    save_state(state)
    print(f"Done. Posted {len(posted)} new job(s); {len(new) - len(to_post)} waiting.")


if __name__ == "__main__":
    if not DISCORD_WEBHOOK_URL.startswith("https://discord"):
        sys.exit("DISCORD_WEBHOOK_URL is missing or invalid (set it in .env or as an environment variable).")
    if "--once" in sys.argv:
        run_once()
    else:
        while True:
            run_once()
            time.sleep(CHECK_EVERY_MINUTES * 60)
