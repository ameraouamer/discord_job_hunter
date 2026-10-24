"""
Job Radar: posts only high-quality, fresh jobs to a Discord channel.
"""

import calendar
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()  # reads DISCORD_WEBHOOK_URL from a local .env file if present

# =====================================================================
#  1) EDIT THESE
# =====================================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip().strip("\"')")

# Roles to search (also used for Himalayas). Senior roles are filtered out below.
ROLES = [
    "machine learning engineer",
    "AI engineer",
    "data analyst",
    "web developer",
    "mobile developer",
    "cybersecurity analyst",
]

# LinkedIn, on-site / hybrid: searched together with "visa sponsorship"
RELOCATION_COUNTRIES = ["Germany", "Netherlands", "Ireland", "United Arab Emirates",
                        "Qatar", "United Kingdom", "France"]

# LinkedIn, remote: searched with LinkedIn's Remote filter
REMOTE_PLACES = ["Worldwide", "Africa"]

MAX_AGE_HOURS = 6           # only jobs posted in the last N hours (apply early)
MAX_YEARS_EXPERIENCE = 2    # skip jobs asking for more years of experience (99 = off)
MAX_POSTS_PER_RUN = 15      # extra jobs wait in a queue for the next run
LINKEDIN_DETAIL_LIMIT = 40  # LinkedIn job pages opened per run (about 1.5 s each)

# On the job boards, the title must contain one of these...
TITLE_KEYWORDS = [
    "machine learning", "ml", "ai", "nlp", "llm", "mlops", "computer vision",
    "deep learning", "data", "analytics", "mobile", "android", "ios", "flutter",
    "react native", "kotlin", "swift", "web", "frontend", "front-end", "backend",
    "back-end", "full stack", "fullstack", "full-stack", "wordpress", "php",
    "laravel", "react", "vue", "node", "django", "python", "software engineer",
    "software developer", "security", "cybersecurity", "cyber", "pentest", "devsecops",
]
# ...and on every site it must not contain any of these.
SKIP_TITLE_WORDS = [
    "senior", "sr", "staff", "lead", "principal", "director", "head", "manager",
    "architect", "consultant", "expert", "chief", "vp", "cto", "founding",
    "sales", "marketing", "product owner", "ii", "iii", "iv", "guard",
]

BADGES = {
    "reloc": "✈️ Relocation support",
    "visa": "🛂 Visa sponsorship",
    "remote": "🌍 Remote, open to Algeria",
    "junior": "🎓 Junior-friendly",
}

# =====================================================================
#  2) Nothing below needs editing
# =====================================================================

STATE_FILE = Path(__file__).with_name("seen_jobs.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JobRadar/1.0"}


def words_re(words):
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I)


TITLE_KEYWORDS_RE = words_re(TITLE_KEYWORDS)
SKIP_TITLE_RE = words_re(SKIP_TITLE_WORDS)
JUNIOR_RE = words_re(["junior", "entry level", "entry-level", "graduate", "intern",
                      "internship", "trainee", "werkstudent", "working student",
                      "early career", "new grad", "stagiaire", "débutant"])

# --- visa / relocation: real offers only ---
SPONSOR_RE = re.compile(
    r"\bvisa\s+sponsor\w*"
    r"|sponsor\w*(?:\s+(?:a|an|the|your|our|candidates?|work|employment)){0,3}\s+visas?"
    r"|visa\s+(?:support|assistance|provided|offered)"
    r"|work\s+permit\s+(?:support|sponsorship|assistance|provided|offered)"
    r"|blue\s+card(?:\s+(?:support|sponsorship|assistance|provided|offered))?"
    r"|sponsorship\s+(?:is\s+)?(?:available|provided|offered)"
    r"|\bvisum\b", re.I)
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
# A sentence with a negation, a question mark (screening question) or "own expense"
# is never treated as an offer.
NEG_RE = re.compile(
    r"\b(?:no|not|cannot|unable|without|never|neither|none|unfortunately|ineligible"
    r"|kein\w*|nicht|ohne|leider)\b|n['’]t\b|\bown\s+expense\b|\?", re.I)

# --- remote jobs that someone in Algeria can really take ---
OPEN_LOC_RE = re.compile(r"\b(?:worldwide|anywhere|global|africa|algeria|mena|emea)\b", re.I)
OPEN_DESC_RE = re.compile(
    r"work\s+from\s+anywhere|anywhere\s+in\s+the\s+world|remote\s+worldwide"
    r"|worldwide\s+remote|100%\s+remote\s+(?:globally|worldwide)"
    r"|(?:hiring|open\s+to\s+candidates?)\s+(?:globally|worldwide|in\s+africa|from\s+africa"
    r"|in\s+algeria|in\s+mena)", re.I)
RESTRICT_RE = re.compile(
    r"must\s+(?:be\s+)?(?:located|based|reside|live)\s+in\s+(?!algeria|africa)"
    r"|(?:authori[sz]ed|eligible|right)\s+to\s+work\s+in\s+(?:the\s+)?"
    r"(?:us|u\.s\.|uk|eu|germany|netherlands|canada)\b"
    r"|work\s+authori[sz]ation\s+(?:in|for)\s+(?:the\s+)?(?:us|u\.s\.|uk|eu|germany)\b"
    r"|citizens?\s+only|security\s+clearance|\b(?:us|u\.s\.|uk|eu)\s+only\b"
    r"|based\s+in\s+the\s+(?:us|u\.s\.|uk|eu|united states|united kingdom)\b"
    r"|\bremote\s+(?:within|in)\s+(?:the\s+)?(?:eu|europe|us|usa|u\.s\.|uk|germany"
    r"|netherlands|france|canada)\b"
    r"|residence\s+in\s+(?:germany|uk|us|europe|the\s+eu)\b"
    r"|deutschkenntnisse|flie[ßs]end\s+deutsch|german\s+(?:c1|c2|fluent|native)", re.I)

EXP_RE = re.compile(
    r"(?:(\d{1,2})\s*(?:-|–|to|à)\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?|jahre?n?|ans)\b"
    r"[^.\n]{0,40}?(?:experience|expérience|erfahrung)", re.I)


def html_lines(markup):
    """HTML -> text, one line per block, so a negation stays in its own sentence."""
    return html.unescape(re.sub(r"<[^>]+>", "\n", markup or ""))


def visa_signals(text):
    """{'visa', 'reloc'} for offers found in sentences that are not negated."""
    found = set()
    for sentence in re.split(r"[.\n;!•]+", text):
        if not sentence.strip() or NEG_RE.search(sentence):
            continue
        if SPONSOR_RE.search(sentence):
            found.add("visa")
        if RELOC_RE.search(sentence):
            found.add("reloc")
    return found


def too_experienced(markup):
    """True if the job asks for more years than MAX_YEARS_EXPERIENCE ('1-3 years' counts as 1)."""
    text = BeautifulSoup(markup or "", "html.parser").get_text(" ")
    return any(int(m.group(1) or m.group(2)) > MAX_YEARS_EXPERIENCE
               for m in EXP_RE.finditer(text))


def to_epoch(value):
    """Unix seconds from seconds, milliseconds or an ISO date (None if unknown)."""
    try:
        if value in (None, ""):
            return None
        if isinstance(value, str) and not value.isdigit():
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        value = float(value)
        return value / 1000 if value > 1e11 else value
    except (ValueError, TypeError):
        return None


def make(source, id_, title, company, location, url, desc="", remote=False, posted=None):
    return {"id": f"{source}:{id_}", "source": source, "title": title.strip(),
            "company": (company or "Unknown").strip(), "location": (location or "").strip(),
            "url": url, "desc": desc or "", "remote": remote, "posted": to_epoch(posted)}


# ---------------------------- sources -------------------------------

def fetch_linkedin():
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    searches = ([(p, True) for p in REMOTE_PLACES]
                + [(c, False) for c in RELOCATION_COUNTRIES])
    out = []
    for place, remote in searches:
        for role in ROLES:
            params = {"keywords": role if remote else f"{role} visa sponsorship",
                      "location": place, "f_TPR": f"r{MAX_AGE_HOURS * 3600}"}
            if remote:
                params["f_WT"] = 2          # LinkedIn "Remote" filter
            try:
                r = requests.get(base, headers=UA, params=params, timeout=20)
                if r.status_code == 429:    # throttled: wait once, then give up
                    time.sleep(20)
                    r = requests.get(base, headers=UA, params=params, timeout=20)
                    if r.status_code == 429:
                        print("  linkedin is throttling us, stopping its searches")
                        return out
                if r.status_code != 200:
                    print(f"  linkedin HTTP {r.status_code} for '{role}' in {place}")
                    continue
                for card in BeautifulSoup(r.text, "html.parser").select("li"):
                    a = card.select_one("a.base-card__full-link")
                    t = card.select_one(".base-search-card__title")
                    if not a or not t:
                        continue
                    c = card.select_one(".base-search-card__subtitle")
                    l = card.select_one(".job-search-card__location")
                    url = a["href"].split("?")[0]
                    out.append(make("LinkedIn", url.rstrip("/").split("-")[-1],
                                    t.get_text(), c.get_text() if c else "",
                                    l.get_text() if l else place, url, remote=remote))
            except requests.RequestException as e:
                print(f"  linkedin error for '{role}' in {place}: {type(e).__name__}")
            time.sleep(2.0)  # be polite
    return out


def linkedin_description(jid):
    """Description HTML from LinkedIn's public job page (None if missing)."""
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


def fetch_himalayas():
    """Official Himalayas API. Empty locationRestrictions = open worldwide."""
    out = []
    for role in ROLES:
        r = requests.get("https://himalayas.app/jobs/api/search", headers=UA, timeout=20,
                         params={"q": role, "worldwide": "true", "sort": "recent"})
        if r.status_code != 200:
            print(f"  himalayas HTTP {r.status_code} for '{role}'")
            continue
        data = r.json()
        for j in (data.get("jobs") or data.get("data") or []):
            places = j.get("locationRestrictions") or []
            link = j.get("applicationLink") or j.get("guid") or ""   # API terms: use this link
            out.append(make("Himalayas", j.get("guid") or link, j.get("title", ""),
                            j.get("companyName", ""), ", ".join(places) or "Worldwide",
                            link, j.get("description") or j.get("excerpt", ""),
                            remote=True, posted=j.get("pubDate")))
        time.sleep(1.0)
    return out


def fetch_remoteok():
    data = requests.get("https://remoteok.com/api", headers=UA, timeout=20).json()
    # RemoteOK leaves the location empty when a job is open worldwide
    return [make("RemoteOK", j["id"], j.get("position", ""), j.get("company"),
                 j.get("location") or "Worldwide", j["url"], j.get("description", ""),
                 remote=True, posted=j.get("epoch"))
            for j in data if isinstance(j, dict) and j.get("id")]


def fetch_weworkremotely():
    out = []
    for slug in ("remote-programming-jobs", "remote-full-stack-programming-jobs",
                 "remote-front-end-programming-jobs", "remote-back-end-programming-jobs",
                 "remote-data-jobs", "remote-devops-sysadmin-jobs"):
        for e in feedparser.parse(f"https://weworkremotely.com/categories/{slug}.rss").entries:
            company, _, title = e.title.partition(": ")      # "Company: Job title"
            posted = calendar.timegm(e.published_parsed) if e.get("published_parsed") else None
            out.append(make("WeWorkRemotely", e.link, title or e.title,
                            company if title else "", e.get("region", ""), e.link,
                            e.get("summary", ""), remote=True, posted=posted))
    return out


def fetch_arbeitnow():
    data = requests.get("https://www.arbeitnow.com/api/job-board-api",
                        headers=UA, timeout=20).json().get("data", [])
    return [make("Arbeitnow", j["slug"], j.get("title", ""), j.get("company_name"),
                 j.get("location") or ("Remote" if j.get("remote") else ""), j.get("url", ""),
                 j.get("description", ""), remote=bool(j.get("remote")),
                 posted=j.get("created_at"))
            for j in data if isinstance(j, dict) and j.get("slug")]


SOURCES = {"himalayas": fetch_himalayas, "remoteok": fetch_remoteok,
           "weworkremotely": fetch_weworkremotely, "arbeitnow": fetch_arbeitnow,
           "linkedin": fetch_linkedin}


# ---------------------------- logic ---------------------------------

def title_ok(j):
    if SKIP_TITLE_RE.search(j["title"]):
        return False
    return j["source"] == "LinkedIn" or bool(TITLE_KEYWORDS_RE.search(j["title"]))


def fresh(j):
    return not j["posted"] or time.time() - j["posted"] <= MAX_AGE_HOURS * 3600


def qualifies(j):
    """Visa/relocation offered, or remote AND open to Algeria. Sets j['flags']."""
    text = html_lines(j["desc"])
    flags = visa_signals(text)
    loc = j["location"]
    if (j["remote"] and (OPEN_LOC_RE.search(loc) or OPEN_DESC_RE.search(text))
            and not RESTRICT_RE.search(text) and not RESTRICT_RE.search(loc)):
        flags.add("remote")
    if flags and JUNIOR_RE.search(f"{j['title']} {text}"):
        flags.add("junior")
    j["flags"] = sorted(flags)
    return bool(flags & {"visa", "reloc", "remote"})


def score(j):
    f = j["flags"]
    return 3 * ("reloc" in f) + 2 * ("visa" in f) + ("remote" in f) + ("junior" in f)


def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                return {"seen": data.get("seen", []), "waiting": data.get("waiting", [])}
            if isinstance(data, list):
                return {"seen": data, "waiting": []}
        except ValueError:
            pass
    return {"seen": [], "waiting": []}


def save_state(seen_list, new_ids, waiting):
    seen_list = seen_list + [i for i in new_ids if i not in set(seen_list)]
    STATE_FILE.write_text(json.dumps({"seen": seen_list[-5000:], "waiting": waiting}))


def post(j):
    badges = " · ".join(BADGES[f] for f in BADGES if f in j["flags"])
    msg = (f"**{j['title']}**\n"
           f"🏢 {j['company']}  ·  📍 {j['location'] or 'Not specified'}  ·  _{j['source']}_\n"
           f"{badges}\n{j['url']}")
    while True:
        r = requests.post(DISCORD_WEBHOOK_URL, timeout=15,
                          json={"content": msg, "username": "Job Radar"})
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            continue
        r.raise_for_status()
        return


def linkedin_newest_first(j):
    try:
        return -int(j["id"].split(":", 1)[1])      # LinkedIn ids grow over time
    except ValueError:
        return 0


def run_once():
    state = load_state()
    seen, now = set(state["seen"]), time.time()
    # jobs that qualified earlier but did not fit in the last post: keep while still fresh
    waiting = [w for w in state["waiting"] if now - w["found_at"] <= MAX_AGE_HOURS * 3600]

    # 1) collect
    jobs = []
    for name, fn in SOURCES.items():
        try:
            items = fn()
            print(f"[{name}] {len(items)} fetched")
            jobs += items
        except Exception as e:
            print(f"[{name}] failed: {type(e).__name__}")

    # 2) cheap checks: new, good title, recent. LinkedIn newest first.
    candidates, ids = [], set()
    for j in jobs:
        if j["id"] in seen or j["id"] in ids or not title_ok(j) or not fresh(j):
            continue
        ids.add(j["id"])
        candidates.append(j)
    candidates.sort(key=lambda j: linkedin_newest_first(j) if j["source"] == "LinkedIn" else 0)

    # 3) quality check (LinkedIn needs its job page opened to read the description)
    done, good, opened = set(), [], 0
    for j in candidates:
        if j["source"] == "LinkedIn":
            if opened >= LINKEDIN_DETAIL_LIMIT:
                continue                       # not marked done: checked on a later run
            opened += 1
            try:
                desc = linkedin_description(j["id"].split(":", 1)[1])
            except (RuntimeError, requests.RequestException) as e:
                print("  linkedin job pages stopped:", type(e).__name__)
                opened = LINKEDIN_DETAIL_LIMIT
                continue
            time.sleep(1.5)
            j["desc"] = desc or ""
        done.add(j["id"])                      # checked once, never again
        if not too_experienced(j["desc"]) and qualifies(j):
            j["found_at"] = now
            good.append({k: j[k] for k in
                         ("id", "source", "title", "company", "location", "url",
                          "flags", "found_at")})

    # 4) newest first, best first inside the same run
    queue = waiting + good
    queue.sort(key=score, reverse=True)
    queue.sort(key=lambda j: j["found_at"], reverse=True)
    print(f"{len(candidates)} new candidates, {len(good)} passed the quality check, "
          f"{len(waiting)} already waiting")

    posted, left = 0, queue[MAX_POSTS_PER_RUN:]
    for j in queue[:MAX_POSTS_PER_RUN]:
        try:
            post(j)
            posted += 1
            print(f"  posted: {j['title']} @ {j['company']} {j['flags']}")
            time.sleep(1)
        except requests.RequestException as e:
            code = getattr(e.response, "status_code", None)    # never print the URL
            print("  Discord error:", code or type(e).__name__)
            left.append(j)                                      # retry next run
    save_state(state["seen"], done, left)
    print(f"Done. {posted} posted, {len(left)} waiting for the next run.")


def send_test():
    """python job_radar.py --test  ->  sends one message and reports the result."""
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