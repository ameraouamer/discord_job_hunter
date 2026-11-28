"""Arbeitnow: public job-board API."""

import requests

from job_radar.config import UA
from job_radar.models import make


def fetch():
    data = requests.get("https://www.arbeitnow.com/api/job-board-api",
                        headers=UA, timeout=20).json().get("data", [])
    return [make("Arbeitnow", j["slug"], j.get("title", ""), j.get("company_name"),
                 j.get("location") or ("Remote" if j.get("remote") else ""), j.get("url", ""),
                 j.get("description", ""), remote=bool(j.get("remote")),
                 posted=j.get("created_at"))
            for j in data if isinstance(j, dict) and j.get("slug")]