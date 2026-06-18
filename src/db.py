import sqlite3


def get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS keywords (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          phrase TEXT UNIQUE NOT NULL,
          source TEXT,
          autocomplete_rank REAL,
          competing_count INTEGER,
          est_volume REAL,
          cross_listing_freq INTEGER DEFAULT 0,
          first_seen TEXT,
          updated TEXT
        );

        CREATE TABLE IF NOT EXISTS asins (
          asin TEXT PRIMARY KEY,
          brand TEXT,
          title TEXT,
          is_mine INTEGER DEFAULT 0,
          captured TEXT
        );

        CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          keyword_id INTEGER NOT NULL REFERENCES keywords(id),
          asin TEXT NOT NULL REFERENCES asins(asin),
          position INTEGER,
          slot_type TEXT,
          page INTEGER,
          observed_at TEXT,
          conditions_hash TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_keywords_phrase ON keywords(phrase);
        CREATE INDEX IF NOT EXISTS idx_obs_keyword_id ON observations(keyword_id);
        CREATE INDEX IF NOT EXISTS idx_obs_asin ON observations(asin);
    """)

    conn.commit()
    return conn
