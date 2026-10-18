# 📡 Job Radar

**Stop refreshing job boards. Let new jobs come to your Discord.**

Job Radar is a small Python bot that watches  popular job sites for the roles you care about, then posts every new listing as a clean link in a Discord channel of your choice. It runs for free on GitHub Actions, so there's no server to rent or keep alive.

## ✨ Features

- **Smart filters:** keep the roles you want (e.g. "machine learning", "AI") and drop the ones you don't (e.g. "senior", "lead")
- **No duplicates:** remembers what it already posted in `seen_jobs.json`
- **Won't flood your channel:** the first run posts at most 10 jobs, then only new ones
- **Free to host:** a scheduled GitHub Actions workflow, or run it on your own machine
- **Tiny:** one Python file, three dependencies

## 🚀 Quick start

**1. Clone and install**

```bash
git clone https://github.com/YOUR_USERNAME/discord_job_hunter.git
cd discord_job_hunter
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**2. Create a Discord webhook**

In your server: Channel Settings → Integrations → Webhooks → New Webhook → Copy URL.

**3. Add the webhook to a `.env` file**

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Put the URL on one line, with no quotes and nothing after it. `.env` is git-ignored, so it never leaves your computer.

**4. Run it**

```bash
python job_radar.py --once   # check once and exit
python job_radar.py          # check every 30 minutes, forever
```

## ⚙️ Configuration

Everything you'd want to tweak is in the `REPLACE` block at the top of `job_radar.py`:

| Setting | What it does |
|---|---|
| `LINKEDIN_KEYWORDS` | Job titles to search for on LinkedIn |
| `LINKEDIN_LOCATIONS` | Countries or cities to search in |
| `TITLE_MUST_CONTAIN` | Titles from the other sites must include one of these words |
| `TITLE_MUST_NOT_CONTAIN` | Titles containing any of these words are skipped |
| `ENABLE` | Turn individual sources on or off |
| `CHECK_EVERY_MINUTES` | How often the loop runs |
| `LINKEDIN_MAX_AGE_HOURS` | Only show LinkedIn jobs posted within this window |
| `FIRST_RUN_LIMIT` | Maximum jobs posted on the very first run |

## ☁️ Host it for free with GitHub Actions

1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions** and add a repository secret named `DISCORD_WEBHOOK_URL` with your webhook URL.
3. The workflow in `.github/workflows/radar.yml` runs every 2 hours. You can also start it by hand from the **Actions** tab with **Run workflow**.

Each run saves `seen_jobs.json` back to the repo, so jobs are never posted twice.

## 🧠 How it works

1. Fetches listings from each source. APIs and RSS feeds are read directly.
2. Filters by title and drops anything already in `seen_jobs.json`.
3. Posts each new job to Discord through the webhook, with automatic retry if Discord rate-limits.
4. Saves the updated list of seen jobs.

## 📁 Project structure

```
├── job_radar.py                 # the whole bot
├── requirements.txt             # requests, beautifulsoup4, feedparser, python-dotenv
├── .github/workflows/radar.yml  # scheduled run on GitHub Actions
├── .env                         # your webhook URL (local only, git-ignored)
└── seen_jobs.json               # jobs already posted (created automatically)
```

## 🛣️ Ideas for later

- Add more sources (company career pages, Welcome to the Jungle, Wellfound)
- Per-source Discord channels
- Salary and seniority filters
- Rich Discord embeds instead of plain messages

---

Built with Python, Beautiful Soup, and a healthy dislike of refreshing job boards.
