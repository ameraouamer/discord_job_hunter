-- SQLBook: Code
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);          -- schema_version

CREATE TABLE seen_jobs (
  id         TEXT PRIMARY KEY,        -- "LinkedIn:4483..." (same IDs as today)
  source     TEXT NOT NULL,
  first_seen INTEGER NOT NULL         -- unix seconds
);

CREATE TABLE waiting (                -- qualified jobs that didn't fit in MAX_POSTS_PER_RUN
  id        TEXT PRIMARY KEY,
  job_json  TEXT NOT NULL,            -- title, company, url, flags...
  found_at  INTEGER NOT NULL
);

CREATE TABLE facts_cache (
  job_id       TEXT PRIMARY KEY,
  facts_json   TEXT NOT NULL,
  source       TEXT NOT NULL,         -- regex | llm | agent
  verified     INTEGER NOT NULL,
  extracted_at INTEGER NOT NULL,
  expires_at   INTEGER                -- NULL = never; ~3 days for "agent still unknown"
);

CREATE TABLE budget (
    day DATE NOT NULL,
    kind VARCHAR(20) NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, kind)
);