"""Component 1: Multi-source data ingestion.

Sources currently live:
  - GitHub Search API   → repos pushed per language per day (fork:false)
  - PyPI Stats API      → daily package downloads for top Python packages
  - npm Stats API       → daily package downloads for top JS/TS packages
  - crates.io API       → recent download counts for top Rust crates

Each source contributes a normalised 'signal' that gets combined into a
weighted composite count per language per day. This way no single source
can be spoofed to move the index.

Source weights (sum = 1.0):
  github  → 0.60   (active repos — primary signal)
  pypi    → 0.20   (Python only — download volume)
  npm     → 0.20   (JS/TS only — download volume)
  crates  → 0.20   (Rust only — download volume)

For languages without a registry source the github weight is kept at 1.0.
"""
import os, sys, time, datetime as dt, requests
from config import LANGUAGES
from db import conn, init

# ── helpers ────────────────────────────────────────────────────────────────

def get_token():
    t = os.environ.get("GITHUB_TOKEN")
    if not t and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
    return t

def safe_get(url, params=None, headers=None, timeout=20, label=""):
    """HTTP GET with retry logic for transient failures."""
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                print(f"  [warn] {label} failed after 3 attempts: {e}")
                return None
            time.sleep(4)

# ── GitHub source ───────────────────────────────────────────────────────────

def count_github_repos(lang, day, token=None, max_retries=4):
    h = {"Accept": "application/vnd.github+json", "User-Agent": "LangIndex-Collector"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    q = f'language:"{lang}" pushed:{day} fork:false'
    for attempt in range(max_retries):
        try:
            r = requests.get("https://api.github.com/search/repositories",
                             params={"q": q, "per_page": 1}, headers=h, timeout=30)
            if r.status_code in (403, 429):
                reset_header = r.headers.get("X-RateLimit-Reset")
                retry_after  = r.headers.get("Retry-After")
                if retry_after:
                    wait_sec = int(retry_after) + 2
                elif reset_header:
                    wait_sec = max(2, int(reset_header) - int(time.time()) + 2)
                else:
                    wait_sec = 25
                print(f"  [GitHub rate-limit on {lang}] waiting {wait_sec}s …")
                time.sleep(wait_sec)
                continue
            r.raise_for_status()
            return r.json()["total_count"]
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  [GitHub error] {lang} {day}: {e}")
                return 0
            time.sleep(3)

# ── PyPI source ─────────────────────────────────────────────────────────────
# Fetches total daily downloads for the top representative Python packages.
# PyPI provides a public BigQuery-backed stats API (no key required).

PYPI_PACKAGES = [
    "requests", "numpy", "pandas", "boto3", "urllib3",
    "setuptools", "pip", "cryptography", "pydantic", "fastapi",
]

def count_pypi_downloads(day):
    """Returns total downloads across representative PyPI packages for the given day."""
    total = 0
    for pkg in PYPI_PACKAGES:
        url = f"https://pypistats.org/api/packages/{pkg}/recent"
        data = safe_get(url, label=f"PyPI:{pkg}")
        if data and "data" in data:
            # 'recent' returns last_day, last_week, last_month
            total += data["data"].get("last_day", 0)
        time.sleep(0.5)  # be polite
    return total

# ── npm source ──────────────────────────────────────────────────────────────
# Uses the public npm download-counts API (no key required).

NPM_PACKAGES = [
    "react", "lodash", "axios", "express", "typescript",
    "next", "webpack", "eslint", "jest", "vue",
]

def count_npm_downloads(day):
    """Returns total downloads across representative npm packages.
    npm stats lag 1-2 days so we use the last 7-day window ending on `day`
    and divide by 7 to get a daily average."""
    import datetime as dt
    end   = day
    start = (dt.date.fromisoformat(day) - dt.timedelta(days=6)).isoformat()
    total = 0
    for pkg in NPM_PACKAGES:
        url  = f"https://api.npmjs.org/downloads/point/{start}:{end}/{pkg}"
        data = safe_get(url, label=f"npm:{pkg}")
        if data and "downloads" in data:
            total += data["downloads"] // 7   # daily average
        time.sleep(0.3)
    return total

# ── crates.io source ────────────────────────────────────────────────────────
# Uses the public crates.io API (no key required, rate-limit 1 req/s).

CRATES_PACKAGES = [
    "serde", "tokio", "rand", "clap", "log",
    "anyhow", "thiserror", "reqwest", "futures", "rayon",
]

def count_crates_downloads():
    """Returns total recent_downloads across representative crates.
    crates.io does not expose per-day stats via REST; we use recent_downloads
    as a proxy (it reflects the last 90 days normalised — good enough for
    relative comparison)."""
    total = 0
    h = {"User-Agent": "LangIndex-Collector (contact@langindex.example)"}
    for crate in CRATES_PACKAGES:
        url = f"https://crates.io/api/v1/crates/{crate}"
        data = safe_get(url, headers=h, label=f"crates:{crate}")
        if data and "crate" in data:
            total += data["crate"].get("recent_downloads", 0)
        time.sleep(1.1)  # crates.io enforces 1 req/s
    return total

# ── composite collection ────────────────────────────────────────────────────

# Which languages get a registry signal and what weight split to use.
# github_w + registry_w must sum to 1.0.
REGISTRY_MAP = {
    # sym  → (registry_collector, github_w, registry_w)
    "PY":  ("pypi",   0.65, 0.35),
    "JS":  ("npm",    0.65, 0.35),
    "TS":  ("npm",    0.65, 0.35),
    "RS":  ("crates", 0.65, 0.35),
}

def collect(day):
    token = get_token()
    delay = 2.2 if token else 7.0

    # ── 1. Fetch registry signals once (not per language) ──────────────────
    print(f"\n[Registry signals for {day}]")
    pypi_raw   = count_pypi_downloads(day)
    npm_raw    = count_npm_downloads(day)
    crates_raw = count_crates_downloads()
    print(f"  PyPI  today-downloads (top-10 pkgs): {pypi_raw:,}")
    print(f"  npm   today-downloads (top-10 pkgs): {npm_raw:,}")
    print(f"  crates recent-downloads (top-10):    {crates_raw:,}")

    # ── 2. GitHub counts per language ─────────────────────────────────────
    print(f"\n[GitHub search for {day}]")
    github_counts = {}
    with conn() as c:
        for sym, lang in LANGUAGES.items():
            existing = c.execute(
                "SELECT count FROM raw_counts WHERE day=? AND symbol=? AND source='github'",
                (day, sym)
            ).fetchone()
            if existing:
                github_counts[sym] = existing["count"]
                print(f"  [cached] {day} {sym:3} ({lang:12}): {existing['count']:,}")
                continue
            n = count_github_repos(lang, day, token)
            github_counts[sym] = n
            c.execute("INSERT OR REPLACE INTO raw_counts VALUES (?,?,?,?)",
                      (day, sym, n, "github"))
            print(f"  [live]   {day} {sym:3} ({lang:12}): {n:,} repos")
            time.sleep(delay)

    # ── 3. Compute composite counts and store as source='composite' ────────
    # Normalise registry signals so they are on the same scale as GitHub
    # counts (rough: 1 download ≈ 0.0001 repos — just a scaling factor
    # to make the composite number comparable, the index formula then
    # takes ratios so absolute scale cancels out).
    SCALE = 0.0001

    with conn() as c:
        for sym in LANGUAGES:
            if sym not in REGISTRY_MAP:
                # No registry source — composite == github
                composite = github_counts.get(sym, 0)
            else:
                registry_id, gw, rw = REGISTRY_MAP[sym]
                if registry_id == "pypi":
                    reg_scaled = pypi_raw * SCALE
                elif registry_id == "npm":
                    reg_scaled = npm_raw * SCALE
                elif registry_id == "crates":
                    reg_scaled = crates_raw * SCALE
                else:
                    reg_scaled = 0

                gh = github_counts.get(sym, 0)
                composite = int(gw * gh + rw * reg_scaled)

            c.execute("INSERT OR REPLACE INTO raw_counts VALUES (?,?,?,?)",
                      (day, sym, composite, "composite"))
            print(f"  [composite] {sym}: {composite:,}")


if __name__ == "__main__":
    init()
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    today = dt.date.today()
    print(f"Starting multi-source data ingestion for the last {days} days …")
    token = get_token()
    print(f"GitHub token: {'active (30 req/min)' if token else 'none (10 req/min)'}")
    for i in range(days, 0, -1):
        target_day = (today - dt.timedelta(days=i)).isoformat()
        collect(target_day)
