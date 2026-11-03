import os, sqlite3

DB = os.environ.get("LANGINDEX_DB", "techx.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_counts(
    day    TEXT,
    symbol TEXT,
    count  INTEGER,
    source TEXT,
    PRIMARY KEY(day, symbol, source)
);
CREATE TABLE IF NOT EXISTS prices(
    day    TEXT,
    symbol TEXT,
    price  REAL,
    PRIMARY KEY(day, symbol)
);
CREATE TABLE IF NOT EXISTS users(
    id    INTEGER PRIMARY KEY,
    name  TEXT,
    token TEXT UNIQUE,
    cash  REAL,
    dek   REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS positions(
    user_id INTEGER,
    symbol  TEXT,
    units   REAL,
    PRIMARY KEY(user_id, symbol)
);
CREATE TABLE IF NOT EXISTS trades(
    id      INTEGER PRIMARY KEY,
    user_id INTEGER,
    symbol  TEXT,
    side    TEXT,
    units   REAL,
    price   REAL,
    dek_rewarded REAL DEFAULT 0.0,
    ts      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dek_ledger(
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER,
    delta     REAL,
    reason    TEXT,
    ts        TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init():
    with conn() as c:
        c.executescript(SCHEMA)
        # migrate: add dek column if upgrading from older schema
        try:
            c.execute("ALTER TABLE users ADD COLUMN dek REAL DEFAULT 0.0")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE trades ADD COLUMN dek_rewarded REAL DEFAULT 0.0")
        except Exception:
            pass

def backup_db(keep_count: int = 14) -> str:
    """Creates a point-in-time ACID snapshot of the database using SQLite's online backup API.
    Maintains a rolling window of recent backups and prunes snapshots older than keep_count."""
    import datetime as dt, glob
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    dest_path = os.path.join(backup_dir, f"techx_{stamp}.db")

    with conn() as src:
        dst = sqlite3.connect(dest_path)
        src.backup(dst)
        dst.close()

    # Prune old backups beyond rolling keep_count
    existing_backups = sorted(glob.glob(os.path.join(backup_dir, "techx_*.db")))
    if len(existing_backups) > keep_count:
        for old_file in existing_backups[:-keep_count]:
            try:
                os.remove(old_file)
            except Exception:
                pass

    return dest_path
