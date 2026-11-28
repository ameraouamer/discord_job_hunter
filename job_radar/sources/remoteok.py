"""RemoteOK: public JSON API."""

import requests

from job_radar.config import UA
from job_radar.models import make


def fetch():
    data = requests.get("https://remoteok.com/api", headers=UA, timeout=20).json()
    # RemoteOK leaves the location empty when a job is open worldwide
    return [make("RemoteOK", j["id"], j.get("position", ""), j.get("company"),
                 j.get("location") or "Worldwide", j["url"], j.get("description", ""),
                 remote=True, posted=j.get("epoch"))
            for j in data if isinstance(j, dict) and j.get("id")]