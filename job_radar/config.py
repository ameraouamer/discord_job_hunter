"""
Job Radar settings. This is the edit block: everything you would want to tweak.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # reads DISCORD_WEBHOOK_URL / ANTHROPIC_API_KEY from a local .env if present


def _flag(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _num(name, default):
    return float(os.getenv(name, str(default)))


# ---------------------------------------------------------------------
#  Secrets (never hardcode these)
# ---------------------------------------------------------------------
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip().strip("\"')")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# ---------------------------------------------------------------------
#  The user (becomes a profile field in the web app)
# ---------------------------------------------------------------------
USER_COUNTRY = "Algeria"    # drives the remote badge and the "eligible from" check

# ---------------------------------------------------------------------
#  What to search: role groups
# ---------------------------------------------------------------------
# Each group has the roles we search for and the words a job title must contain
# (on the job boards; LinkedIn is already searched by role). In the web app a user
# will pick their groups; here, ENABLED_GROUPS does the same job.
ROLE_GROUPS = {
    "software": {
        "roles": ["software developer", "web developer", "frontend developer",
                  "backend developer", "full stack developer", "mobile developer"],
        "keywords": ["software engineer", "software developer", "developer", "web",
                     "frontend", "front-end", "backend", "back-end", "full stack",
                     "fullstack", "full-stack", "mobile", "android", "ios", "flutter",
                     "react native", "kotlin", "swift", "wordpress", "php", "laravel",
                     "react", "vue", "node", "django", "python", "java", "javascript",
                     "typescript", ".net", "golang"],
    },
    "data_ai": {
        "roles": ["machine learning engineer", "AI engineer", "data analyst",
                  "data engineer", "data scientist", "BI analyst"],
        "keywords": ["machine learning", "ml", "ai", "nlp", "llm", "mlops",
                     "computer vision", "deep learning", "data", "analytics",
                     "analyst", "bi", "business intelligence"],
    },
    "it_infra": {
        "roles": ["IT support", "system administrator", "network engineer",
                  "cloud engineer", "devops engineer", "QA tester"],
        "keywords": ["it support", "helpdesk", "help desk", "service desk", "sysadmin",
                     "system administrator", "systems administrator", "network",
                     "cloud", "devops", "sre", "infrastructure", "qa", "tester",
                     "test engineer", "technician", "support engineer"],
    },
    "security": {
        "roles": ["cybersecurity analyst", "security engineer", "SOC analyst",
                  "penetration tester", "GRC analyst"],
        "keywords": ["security", "cybersecurity", "cyber", "pentest", "penetration",
                     "devsecops", "soc", "grc", "infosec", "compliance"],
    },
    "design": {
        "roles": ["UI/UX designer", "graphic designer", "product designer",
                  "motion designer", "video editor", "web designer"],
        "keywords": ["designer", "design", "ui", "ux", "ui/ux", "graphic", "graphics",
                     "motion", "video editor", "animator", "illustrator", "creative",
                     "brand", "3d artist", "visual"],
    },
    "product_business": {
        "roles": ["business analyst", "product analyst", "project coordinator",
                  "technical writer", "scrum master"],
        "keywords": ["business analyst", "product analyst", "product", "project",
                     "coordinator", "technical writer", "documentation", "scrum",
                     "agile", "program"],
    },
    "marketing": {
        "roles": ["digital marketing specialist", "SEO specialist", "content writer",
                  "social media specialist", "email marketing specialist"],
        "keywords": ["marketing", "seo", "sem", "content", "copywriter", "writer",
                     "social media", "community", "growth", "email marketing",
                     "brand", "pr", "communications"],
    },
    "sales_support": {
        "roles": ["customer support specialist", "customer success associate",
                  "sales development representative", "account executive", "recruiter"],
        "keywords": ["customer support", "customer success", "customer service",
                     "support specialist", "sales", "sdr", "bdr", "account executive",
                     "business development", "recruiter", "talent acquisition",
                     "sourcer"],
    },
    "ops_finance": {
        "roles": ["accountant", "financial analyst", "HR assistant",
                  "administrative assistant", "operations analyst"],
        "keywords": ["accountant", "accounting", "bookkeeper", "finance", "financial",
                     "payroll", "hr", "human resources", "people operations",
                     "administrative", "assistant", "operations", "office"],
    },
}

# Which groups to run. None = all of them.
ENABLED_GROUPS = None


def _enabled():
    return [g for g in ROLE_GROUPS if ENABLED_GROUPS is None or g in ENABLED_GROUPS]


# All roles, in group order (also used for Himalayas). Senior roles are filtered below.
ROLES = [r for g in _enabled() for r in ROLE_GROUPS[g]["roles"]]

# LinkedIn, on-site / hybrid: searched together with "visa sponsorship"
RELOCATION_COUNTRIES = ["Germany", "Netherlands", "Ireland", "United Arab Emirates",
                        "Qatar", "United Kingdom", "France"]

# LinkedIn, remote: searched with LinkedIn's Remote filter
REMOTE_PLACES = ["Worldwide", "Africa"]

# ---------------------------------------------------------------------
#  Experience levels: the user picks exactly one
# ---------------------------------------------------------------------
# years: the lowest number of years a posting asks for must fall in [min, max].
# seniority: labels from JobFacts.seniority that fit this level ("unknown" always passes).
# skip_title_words: title words that rule a job out for this level.
_JUNIOR_WORDS = ["intern", "internship", "trainee", "werkstudent", "working student",
                 "junior", "jr", "graduate", "entry level", "entry-level"]
EXPERIENCE_LEVELS = {
    "junior": {
        "label": "Junior (0-2 years)",
        "min_years": 0, "max_years": 2,
        "seniority": ["intern", "junior"],
        "skip_title_words": ["senior", "sr", "snr", "staff", "lead", "principal", "director",
                             "head", "manager", "architect", "consultant", "expert", "chief",
                             "vp", "cto", "founding", "product owner", "ii", "iii", "iv",
                             "guard"],
    },
    "mid": {
        "label": "Mid-level (2-5 years)",
        "min_years": 2, "max_years": 5,
        "seniority": ["mid"],
        "skip_title_words": ["senior", "sr", "snr", "staff", "lead", "principal", "director",
                             "head", "manager", "architect", "chief", "vp", "cto", "founding",
                             "iii", "iv", "guard"] + _JUNIOR_WORDS,
    },
    "senior": {
        "label": "Senior (5+ years)",
        "min_years": 5, "max_years": None,          # None = no upper limit
        "seniority": ["senior"],
        "skip_title_words": ["chief", "vp", "cto", "guard"] + _JUNIOR_WORDS,
    },
}

# ---------------------------------------------------------------------
#  Inputs about the user and the schedule (these are facts, not limits)
# ---------------------------------------------------------------------
USER_LEVEL = os.getenv("USER_LEVEL", "junior").strip().lower()
if USER_LEVEL not in EXPERIENCE_LEVELS:
    raise ValueError(f"USER_LEVEL must be one of {list(EXPERIENCE_LEVELS)}, got {USER_LEVEL!r}")

MAX_AGE_HOURS = _num("MAX_AGE_HOURS", 6)                   # how fresh a job must be
RUN_INTERVAL_HOURS = _num("RUN_INTERVAL_HOURS", 1)         # match the workflow's cron
RUN_TIME_BUDGET_MINUTES = _num("RUN_TIME_BUDGET_MINUTES", 15)  # under the workflow timeout
DAILY_POST_TARGET = int(os.getenv("DAILY_POST_TARGET", "0")) or None  # None = no cap

# Run limits (jobs posted per run, LinkedIn pages opened, LinkedIn roles searched) are
# not set here. job_radar/limits.py computes them every run from the inputs above.


def level_rules(level=None):
    return EXPERIENCE_LEVELS[level or USER_LEVEL]


def skip_words_for(level=None):
    return level_rules(level)["skip_title_words"]


# ---------------------------------------------------------------------
#  LLM job-facts extractor
# ---------------------------------------------------------------------
LLM_ENABLED = _flag("LLM_ENABLED", False)   # off by default: regex path only
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
LLM_DAILY_CAP = int(os.getenv("LLM_DAILY_CAP", "100"))   # max LLM calls per day

# ---------------------------------------------------------------------
#  Title filters
# ---------------------------------------------------------------------
# On the job boards, the title must contain one of these (built from the enabled groups)...
TITLE_KEYWORDS = sorted({k for g in _enabled() for k in ROLE_GROUPS[g]["keywords"]})
# ...and on every site it must not contain any of these (depends on the chosen level).
SKIP_TITLE_WORDS = skip_words_for(USER_LEVEL)

# ---------------------------------------------------------------------
#  Discord badges
# ---------------------------------------------------------------------
BADGES = {
    "reloc": "✈️ Relocation support",
    "visa": "🛂 Visa sponsorship",
    "remote": f"🌍 Remote, open to {USER_COUNTRY}",
    "junior": "🎓 Junior-friendly",
}