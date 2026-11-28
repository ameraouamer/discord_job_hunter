"""WeWorkRemotely: RSS feeds, one per category."""

import calendar

import feedparser

from job_radar.models import make

CATEGORIES = (
    "remote-programming-jobs",
    "remote-full-stack-programming-jobs",
    "remote-front-end-programming-jobs",
    "remote-back-end-programming-jobs",
    "remote-data-jobs",
    "remote-devops-sysadmin-jobs",
)


def fetch():
    out = []
    for slug in CATEGORIES:
        for e in feedparser.parse(f"https://weworkremotely.com/categories/{slug}.rss").entries:
            company, _, title = e.title.partition(": ")      # "Company: Job title"
            posted = calendar.timegm(e.published_parsed) if e.get("published_parsed") else None
            out.append(make("WeWorkRemotely", e.link, title or e.title,
                            company if title else "", e.get("region", ""), e.link,
                            e.get("summary", ""), remote=True, posted=posted))
    return out