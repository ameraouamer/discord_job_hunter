"""Source registry. Every source module exposes a `fetch()` returning a list of jobs."""

from job_radar.config import LINKEDIN_ENABLED

from . import arbeitnow, himalayas, remoteok, weworkremotely

SOURCES = {
    "himalayas": himalayas.fetch,
    "remoteok": remoteok.fetch,
    "weworkremotely": weworkremotely.fetch,
    "arbeitnow": arbeitnow.fetch,
}

if LINKEDIN_ENABLED:
    from . import linkedin
    SOURCES["linkedin"] = linkedin.fetch