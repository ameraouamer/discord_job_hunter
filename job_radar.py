"""
Job Radar: posts only high-quality, fresh jobs to a Discord channel.

A job is posted only if it is recent, junior-friendly, AND at least one of these is true:
  * Its description offers relocation support or visa sponsorship (for moving abroad)
  * It is remote and genuinely open to people in Algeria (worldwide / Africa / EMEA ...)
"""

import calendar
import html
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

load_dotenv()  # reads DISCORD_WEBHOOK_URL from a local .env file if present

# =====================================================================
#  1) EDIT THESE (Clean & Simple Configuration)
# =====================================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip().strip("\"')")

# Target junior roles to search
ROLES = [
    "junior machine learning engineer",
    "junior AI engineer",
    "junior data analyst",
    "junior web developer",
    "junior mobile developer",
    "junior cybersecurity analyst",
]

# Countries to search for relocation & visa sponsorship (on-site / hybrid)
RELOCATION_COUNTRIES = [
    "Germany",
    "Netherlands",
    "Ireland",
    "United Arab Emirates",
    "Qatar"
    "USA",
    "Europe",
    "France"
]

# Regions searched with LinkedIn's Remote filter (must be open to Algeria)
REMOTE_PLACES = ["Worldwide", "Africa"]

MAX_AGE_HOURS = 4           # only jobs posted in the last N hours (apply early)
MAX_YEARS_EXPERIENCE = 2    # skip jobs asking for more years of experience (99 = off)
MAX_POSTS_PER_RUN = 15      # max jobs sent to Discord per run
LINKEDIN_DETAIL_LIMIT = 30  # LinkedIn job descriptions inspected per run (~1.5s each)

# Other job boards: title must contain one of these keywords...
TITLE_KEYWORDS = [
    "machine learning", "ml", "ai", "nlp", "llm", "mlops", "computer vision",
    "deep learning", "data", "analytics", "mobile", "android", "ios", "flutter",
    "react native", "kotlin", "swift", "web", "frontend", "front-end", "backend",
    "back-end", "full stack", "fullstack", "full-stack", "wordpress", "php",
    "laravel", "react", "vue", "node", "django", "security", "cybersecurity",
    "cyber", "pentest", "devsecops",
]

# ...and must NEVER contain any of these senior/unrelated keywords.
SKIP_TITLE_WORDS = [
    "senior", "sr", "staff", "lead", "principal", "director", "head", "manager",
    "architect", "consultant", "expert", "chief", "vp", "cto", "founding",
    "sales", "marketing", "product owner", "ii", "iii", "iv", "guard",
]

# Discord Badges (The new clean design)
BADGES = {
    "reloc": "✈️ Relocation support",
    "visa": "🛂 Visa sponsorship",
    "remote": "🌍 Remote, open to Algeria",
}

# =====================================================================
#  2) Core Logic & Filters
# =====================================================================

STATE_FILE = Path(__file__).with_name("seen_jobs.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JobRadar/1.0"}

TITLE_KEYWORDS_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in TITLE_KEYWORDS) + r")\b", re.I)
SKIP_TITLE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in SKIP_TITLE_WORDS) + r")\b", re.I)

# Visa sponsorship signals (positive offers only)
SPONSOR_RE = re.compile(
    r"\bvisa\s+sponsor\w*"
    r"|sponsor\w*(?:\s+(?:a|an|the|your|our|candidates?|work|employment)){0,3}\s+visas?"
    r"|visa\s+(?:support|assistance|provided|offered)"
    r"|work\s+permit\s+(?:support|sponsorship|assistance|provided|offered)"
    r"|blue\s+card(?:\s+(?:support|sponsorship|assistance|provided|offered))?"
    r"|sponsorship\s+(?:is\s+)?(?:available|provided|offered)"
    r"|\bvisum\b", re.I)

# Relocation support signals (positive offers only)
RELOC_RE = re.compile(
    r"relocation\s+(?:package|support|assistance|bonus|allowance|budget|help|expenses"
    r"|benefits?|stipend|services?|available|offered|provided|included|covered"
    r"|reimbursement)"
    r"|(?:offer|offers|offering|provide|provides|providing|include|includes|including"
    r"|paid|covered)\s+(?:\w+\s+)?relocation"
    r"|(?:help|assist|assists|support|supports)\w*\s+(?:you\s+)?(?:with\s+|in\s+|to\s+)?"
    r"(?:your\s+)?relocat\w*"
    r"|relocation\s+(?:and|&)\s+visa|visa\s+(?:and|&)\s+relocation"
    r"|umzugs\w*(?:hilfe|zuschuss|unterstützung|kosten)\w*"
    r"|relocation-?(?:paket|support)", re.I)

# Negations & screening questions that must NOT trigger an offer
NEG_RE = re.compile(
    r"\b(?:no|not|cannot|can\'?t|unable|without|never|neither|none|unfortunately"
    r"|ineligible|unsupported|kein\w*|nicht|ohne|leider)\b"
    r"|n[\'’]t\b"
    r"|\bown\s+expense\b"
    r"|\bnot\s+(?:available|provided|offered|possible|eligible|supported)\b"
    r"|\b(?:do|will|would|if)\s+you\s+(?:now\s+or\s+in\s+the\s+future\s+)?(?:require|need)\b"
    r"|\?", re.I)

# Locations acceptable for remote workers in Algeria
OPEN_LOC_RE = re.compile(
    r"\b(?:worldwide|anywhere|global|africa|algeria|mena)\b", re.I)

# Descriptions explicitly confirming worldwide / Algeria remote work
OPEN_DESC_RE = re.compile(
    r"work\s+from\s+anywhere(?:\s+in\s+the\s+world)?"
    r"|anywhere\s+in\s+the\s+world"
    r"|remote\s+worldwide|worldwide\s+remote"
    r"|100%\s+remote\s+(?:globally|worldwide)"
    r"|(?:hiring|open\s+to\s+candidates?)\s+(?:globally|worldwide|in\s+africa|from\s+africa|in\s+algeria|in\s+mena)", re.I)

# Country restrictions that make a remote job unavailable to Algeria
RESTRICT_RE = re.compile(
    r"must\s+(?:be\s+)?(?:located|based|reside|live)\s+in\s+(?!algeria|africa)"
    r"|(?:authori[sz]ed|eligible|right)\s+to\s+work\s+in\s+(?:the\s+)?(?:us|u\.s\.|uk|eu|germany|netherlands|canada)"
    r"|work\s+authori[sz]ation\s+(?:in|for)\s+(?:the\s+)?(?:us|u\.s\.|uk|eu|germany)"
    r"|citizens?\s+only"
    r"|security\s+clearance"
    r"|\b(?:us|u\.s\.|uk|eu)\s+only\b"
    r"|based\s+in\s+the\s+(?:us|u\.s\.|uk|eu|united states|united kingdom)\b"
    r"|residence\s+in\s+(?:germany|uk|us|europe|the\s+eu)\b"
    r"|deutschkenntnisse|flie[ßs]end\s+deutsch|german\s+(?:c1|c2|fluent|native)", re.I)

# Specific countries: if a job is in Germany/Netherlands/etc., it is NOT remote for Algeria
# unless it explicitly offers visa/relocation.
LOCAL_COUNTRY_RE = re.compile(
    r"\b(?:germany|deutschland|netherlands|ireland|france|uk|united kingdom|usa?|united states|canada|australia|switzerland|austria|spain|italy|poland)\b", re.I)

EXP_RE = re.compile(
    r"(?:(\d{1,2})\s*(?:-|–|to|à)\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?|jahre?n?|ans)\b"
    r"[^.\n]{0,40}?(?:experience|expérience|erfahrung)", re.I)


def html_lines(markup):
    """HTML -> text, one line per block, so sentences and negations stay separate."""
    return html.unescape(re.sub(r"<[^>]+>", "\n", markup or ""))


def visa_signals(text):
    """Returns set of {'visa', 'reloc'} for genuine offers found in un-negated sentences."""
    found = set()
    for sentence in re.split(r"[.\n;!•]+", text):
        sentence = sentence.strip()
        if not sentence or NEG_RE.search(sentence):
            continue
        if SPONSOR_RE.search(sentence):
            found.add("visa")
        if RELOC_RE.search(sentence):
            found.add("reloc")
    return found


def too_experienced(markup):
    """Drop jobs asking for more years of experience than MAX_YEARS_EXPERIENCE."""
    if MAX_YEARS_EXPERIENCE >= 99:
        return False
    text = BeautifulSoup(markup or "", "html.parser").get_text(" ")
    for m in EXP_RE.finditer(text):
        yrs = int(m.group(2) or m.group(1))
        if yrs > MAX_YEARS_EXPERIENCE:
            return True
    return False


def make(source, id_, title, company, location, url, desc="", remote=False, posted=None):
    return {
        "id": f"{source}:{id_}",
        "source": source,
        "title": title.strip(),
        "company": (company or "Unknown").strip(),
        "location": (location or "").strip(),
        "url": url,
        "desc": desc or "",
        "remote": remote,
        "posted": posted,
    }


# ---------------------------- sources -------------------------------

def fetch_linkedin():
    """Searches LinkedIn for target roles in remote places and relocation countries."""
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    searches = ([(p, True) for p in REMOTE_PLACES]
                + [(c, False) for c in RELOCATION_COUNTRIES])
    out = []
    for place, remote in searches:
        for role in ROLES:
            query = role if remote else f"{role} visa sponsorship"
            params = {
                "keywords": query,
                "location": place,
                "f_TPR": f"r{MAX_AGE_HOURS * 3600}",
            }
            if remote:
                params["f_WT"] = 2  # LinkedIn Remote filter
            try:
                r = requests.get(base, headers=UA, params=params, timeout=20)
                if r.status_code == 429:
                    print("  linkedin is throttling us, stopping searches for this run")
                    return out
                if r.status_code != 200:
                    print(f"  linkedin HTTP {r.status_code} for '{role}' in {place}")
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
                    out.append(make(
                        "LinkedIn", jid, t.get_text(),
                        c.get_text() if c else "",
                        l.get_text() if l else place,
                        url, remote=remote,
                    ))
            except requests.RequestException as e:
                print(f"  linkedin error for {role} in {place}: {type(e).__name__}")
            time.sleep(2.0)
    return out


def linkedin_description(jid):
    """Job description HTML from LinkedIn public job page (None if missing/failed)."""
    r = requests.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}",
                     headers=UA, timeout=20)
    if r.status_code == 429:
        raise RuntimeError("throttled")
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    box = (soup.select_one(".show-more-less-html__markup")
           or soup.select_one(".description__text"))
    return str(box) if box else None


def fetch_remoteok():
    r = requests.get("https://remoteok.com/api", headers=UA, timeout=20)
    if r.status_code != 200:
        return []
    data = r.json()
    return [
        make("RemoteOK", j["id"], j.get("position", ""), j.get("company"),
             j.get("location"), j["url"], j.get("description", ""),
             remote=True, posted=j.get("epoch"))
        for j in data if isinstance(j, dict) and j.get("id")
    ]


def fetch_weworkremotely():
    out = []
    categories = ("remote-programming-jobs", "remote-data-jobs", "remote-devops-sysadmin-jobs")
    for slug in categories:
        try:
            feed = feedparser.parse(f"https://weworkremotely.com/categories/{slug}.rss")
            for e in feed.entries:
                company, _, title = e.title.partition(": ")
                posted = calendar.timegm(e.published_parsed) if e.get("published_parsed") else None
                out.append(make(
                    "WeWorkRemotely", e.link, title or e.title,
                    company if title else "", e.get("region", ""), e.link,
                    e.get("summary", ""), remote=True, posted=posted,
                ))
        except Exception as e:
            print(f"  weworkremotely {slug} error: {type(e).__name__}")
    return out


def fetch_arbeitnow():
    r = requests.get("https://www.arbeitnow.com/api/job-board-api",
                     headers=UA, timeout=20)
    if r.status_code != 200:
        return []
    data = r.json().get("data", [])
    out = []
    for j in data:
        if not isinstance(j, dict) or not j.get("slug"):
            continue
        out.append(make(
            "Arbeitnow", j["slug"], j.get("title", ""), j.get("company_name", ""),
            j.get("location") or ("Remote" if j.get("remote") else ""),
            j.get("url", ""), j.get("description", ""),
            remote=bool(j.get("remote")),
            posted=j.get("created_at"),
        ))
    return out


SOURCES = {
    "linkedin": fetch_linkedin,
    "remoteok": fetch_remoteok,
    "weworkremotely": fetch_weworkremotely,
    "arbeitnow": fetch_arbeitnow,
}


# ---------------------------- logic ---------------------------------

def title_ok(j):
    title = j["title"]
    if SKIP_TITLE_RE.search(title):
        return False
    # LinkedIn queries are already role-specific; other boards must match title keywords
    return j["source"] == "LinkedIn" or bool(TITLE_KEYWORDS_RE.search(title))


def fresh(j):
    if not j["posted"]:
        return True
    try:
        ts = float(j["posted"])
        return time.time() - ts <= MAX_AGE_HOURS * 3600
    except (ValueError, TypeError):
        return True


def qualifies(j):
    """
    Quality check: keep a job ONLY if:
      1) Description explicitly offers visa sponsorship or relocation support; OR
      2) It is remote and genuinely open to someone living in Algeria.
    Jobs remote *only within another country* (e.g. Germany) are dropped unless
    they offer visa or relocation.
    """
    text = html_lines(j["desc"])
    flags = visa_signals(text)

    loc = j["location"]
    is_foreign_country = bool(LOCAL_COUNTRY_RE.search(loc)) and not bool(OPEN_LOC_RE.search(loc))

    if j["remote"] and not is_foreign_country:
        is_open_location = bool(OPEN_LOC_RE.search(loc))
        is_open_desc = bool(OPEN_DESC_RE.search(text))
        is_restricted = bool(RESTRICT_RE.search(text)) or bool(RESTRICT_RE.search(loc))

        if (is_open_location or is_open_desc) and not is_restricted:
            flags.add("remote")

    j["flags"] = flags
    return bool(flags)


def score(j):
    f = j["flags"]
    return 3 * ("reloc" in f) + 2 * ("visa" in f) + ("remote" in f)


def load_seen():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                return set(data.get("seen", []))
            if isinstance(data, list):
                return set(data)
        except Exception:
            return set()
    return set()


def save_seen(seen):
    STATE_FILE.write_text(json.dumps({"seen": list(seen)[-5000:]}))


def post(j):
    badge_order = ("reloc", "visa", "remote")
    badges = " · ".join(BADGES[f] for f in badge_order if f in j["flags"])
    msg = (f"**{j['title']}**\n"
           f"🏢 {j['company']}  ·  📍 {j['location'] or 'Not specified'}  ·  _{j['source']}_\n"
           f"{badges}\n"
           f"{j['url']}")
    while True:
        r = requests.post(DISCORD_WEBHOOK_URL, timeout=15,
                          json={"content": msg, "username": "Job Radar"})
        if r.status_code == 429:
            retry_after = float(r.json().get("retry_after", 2))
            time.sleep(retry_after + 0.5)
            continue
        r.raise_for_status()
        return


def run_once():
    seen = load_seen()

    # 1) Collect jobs from all sources
    jobs = []
    for name, fn in SOURCES.items():
        try:
            items = fn()
            print(f"{name}: {len(items)} fetched")
            jobs += items
        except Exception as e:
            print(f"{name} failed: {type(e).__name__}")

    # 2) Cheap initial checks: not seen, good title, recently posted
    candidates, ids = [], set()
    for j in jobs:
        if j["id"] in seen or j["id"] in ids or not title_ok(j) or not fresh(j):
            continue
        ids.add(j["id"])
        candidates.append(j)

    # 3) Quality check (LinkedIn opens job detail pages; others already have desc)
    done, good, opened = set(), [], 0
    for j in candidates:
        if j["source"] == "LinkedIn":
            if opened >= LINKEDIN_DETAIL_LIMIT:
                continue  # not marked done -> will be checked on next run
            opened += 1
            try:
                desc = linkedin_description(j["id"].split(":", 1)[1])
            except (RuntimeError, requests.RequestException) as e:
                print("  linkedin detail fetching stopped:", type(e).__name__)
                opened = LINKEDIN_DETAIL_LIMIT
                continue
            time.sleep(1.5)
            if desc is None:
                continue
            j["desc"] = desc

        done.add(j["id"])  # evaluated: marked as processed
        if not too_experienced(j["desc"]) and qualifies(j):
            good.append(j)

    # 4) Post the best candidates to Discord
    good.sort(key=score, reverse=True)
    to_post = good[:MAX_POSTS_PER_RUN]
    done -= {j["id"] for j in good[MAX_POSTS_PER_RUN:]}  # surplus wait for next run
    posted = 0
    for j in to_post:
        try:
            post(j)
            posted += 1
            time.sleep(1)
        except requests.RequestException as e:
            code = getattr(e.response, "status_code", None)
            print("  Discord error:", code or type(e).__name__)
            done.discard(j["id"])  # retry next run
    save_seen(seen | done)
    print(f"Done. {len(candidates)} new candidates, {len(good)} passed the quality check, {posted} posted.")


def send_test():
    """python job_radar.py --test -> sends one message and reports the result."""
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, timeout=15,
                          json={"content": "✅ Job Radar test message",
                                "username": "Job Radar"})
        print(f"Discord answered HTTP {r.status_code} "
              "(204 = delivered; 401/404 = webhook URL is wrong or deleted)")
        sys.exit(0 if r.status_code in (200, 204) else 1)
    except requests.RequestException as e:
        sys.exit(f"Could not reach Discord: {type(e).__name__}")


if __name__ == "__main__":
    if not DISCORD_WEBHOOK_URL.startswith("https://discord"):
        sys.exit("DISCORD_WEBHOOK_URL is missing or invalid (set it in .env or as a secret).")
    if "--test" in sys.argv:
        send_test()
    elif "--once" in sys.argv:
        run_once()
    else:
        while True:
            run_once()
            time.sleep(30 * 60)
            time.sleep(30 * 60)
