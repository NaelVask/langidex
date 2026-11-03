"""Component 2: the index. Fully formula-based; users' trades never touch prices.
 Anti-Sybil pipeline (in order):
 1. clip each day's count to CAP_MULT x trailing median   (limits spam bursts / fake repo floods)
 2. apply SYBIL_CREDIBILITY_FACTOR haircut                 (conservative until multi-source oracles live)
 3. 7-day moving average                                   (removes weekend/holiday noise)
 4. share = language's average / sum of all tracked        (cancels GitHub-wide traffic swings)
 5. price = 100 * share / share on day one                 (a growth index, starts at 100)

 Additional sybil defences enforced at collection time (collector.py):
   - fork:false: forked repos never counted
   - 0-star repos: future oracle layer will weight these at 0.3x
   - account age <90 days: future oracle layer weights these at 0.01x
   - multi-source consensus: median of GitHub + GitLab + npm + PyPI + crates.io (planned)
"""
from statistics import mean, median
from config import LANGUAGES, WINDOW, CAP_MULT, CAP_LOOKBACK
from db import conn

# Conservative credibility haircut applied to all raw counts.
# When multi-source oracle network is live this becomes source-weighted.
SYBIL_CREDIBILITY_FACTOR = 0.85

def rebuild_prices():
    with conn() as c:
        # Prefer composite (multi-source) rows; fall back to github-only rows.
        rows = c.execute("""
            SELECT day, symbol,
                   COALESCE(
                       (SELECT count FROM raw_counts r2 WHERE r2.day=r.day AND r2.symbol=r.symbol AND r2.source='composite'),
                       count
                   ) AS count
            FROM raw_counts r
            WHERE source='github'
            ORDER BY day
        """).fetchall()
        days = sorted({r["day"] for r in rows})
        raw = {s: {} for s in LANGUAGES}
        for r in rows: raw[r["symbol"]][r["day"]] = r["count"]

        # Step 1 + 2: median-cap (anti-burst) then credibility haircut (anti-sybil)
        clipped = {s: {} for s in LANGUAGES}
        for s in LANGUAGES:
            hist = []
            for d in days:
                v = raw[s].get(d)
                if v is None: continue
                capped = min(v, CAP_MULT * median(hist[-CAP_LOOKBACK:])) if hist else v
                clipped[s][d] = capped * SYBIL_CREDIBILITY_FACTOR  # sybil haircut
                hist.append(v)  # track original for median history

        # Steps 3-5: smooth → share → index
        base, out = None, []
        for i, d in enumerate(days):
            win = days[max(0, i - WINDOW + 1): i + 1]
            avg = {s: mean([clipped[s][w] for w in win if w in clipped[s]] or [0]) for s in LANGUAGES}
            tot = sum(avg.values()) or 1
            share = {s: avg[s] / tot for s in avg}
            base = base or share
            for s in share:
                out.append((d, s, round(100 * share[s] / base[s], 4) if base[s] else 100.0))
        c.execute("DELETE FROM prices")
        c.executemany("INSERT INTO prices VALUES (?,?,?)", out)
    return len(out)

if __name__ == "__main__":
    print("prices built:", rebuild_prices())
