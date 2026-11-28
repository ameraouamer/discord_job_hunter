"""Himalayas: official API. Empty locationRestrictions = open worldwide."""

import time

import requests

from job_radar.config import ROLES, UA
from job_radar.models import make


def fetch():
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