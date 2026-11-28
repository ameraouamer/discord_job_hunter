"""LinkedIn guest endpoints. Off by default (see LINKEDIN_ENABLED in config.py)."""

import time

import requests
from bs4 import BeautifulSoup

from job_radar.config import (MAX_AGE_HOURS, RELOCATION_COUNTRIES, REMOTE_PLACES,
                              ROLES, UA)
from job_radar.models import make


def fetch():
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


def description(jid):
    """Description HTML from LinkedIn's public job page (None if missing).

    Was `linkedin_description` in job_radar.py.
    """
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


def newest_first(j):
    """Sort key: LinkedIn ids grow over time, so a bigger id means a newer job.

    Was `linkedin_newest_first` in job_radar.py.
    """
    try:
        return -int(j["id"].split(":", 1)[1])
    except ValueError:
        return 0