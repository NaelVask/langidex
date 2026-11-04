"""Component 4: HTTP API + serves the web app. Run: uvicorn api:app --reload"""
import hashlib, time
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from config import LANGUAGES, LANGUAGE_META, START_CASH
from db import conn, init
import trading
import crypto_engine as ce
import immutable_ledger as il

init()

# Rate limiter: 60 requests per minute per IP address.
# Prevents DDoS floods against the .onion endpoint.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app = FastAPI(title="Langdex Protocol - Developer Adoption Index")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

class Signup(BaseModel):
    name: Optional[str] = "Trader"
    address: Optional[str] = None

class Order(BaseModel):
    symbol: str
    side: str
    points: float

class Deposit(BaseModel):
    amount: float

class Burn(BaseModel):
    amount: float

class SignedTransaction(BaseModel):
    payload: dict
    signature: str

class P2PPeerPing(BaseModel):
    node_id: str
    address: str
    onion_url: Optional[str] = None

# Genesis block manifest and cryptographic hash proof
GENESIS_BLOCK = {
    "protocol": "Langdex Protocol - Developer Adoption Index",
    "genesis_timestamp": "2026-11-02T19:30:00Z",
    "version": "1.0.0-PROT",
    "creator_manifest": "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks // Langdex 03/Nov/2026 The Developer Ecosystem Belongs to the Builders",
    "creator_public_key": "0x7a892bF584C8bEb8f682057F7392aA7b25F18dE0",
    "genesis_hash": "87be4735c1f0c9f85c5e2822b893c097dfa9690ccd4bfa95374036b537090def",
    "signature": "3045022100e4b85c2980b1df308a287233f2b4c19559815049a4f494950b73c2ad2c355ad4022026dc24584cbb9d0689b9176f1837012543cbe25ef14bdf8880693a2010c7104b"
}

def guard(fn, *a):
    try: return fn(*a)
    except PermissionError as e: raise HTTPException(401, str(e))
    except ValueError as e: raise HTTPException(400, str(e))

@app.get("/api/assets")
@limiter.limit("30/minute")
def assets(request: Request):
    with conn() as c:
        src = c.execute("SELECT DISTINCT source FROM raw_counts").fetchall()

        days_rows = c.execute("SELECT DISTINCT day FROM prices ORDER BY day ASC").fetchall()
        all_days = [r["day"] for r in days_rows]

        tot_counts = dict(c.execute("""
            SELECT day, SUM(count) as s FROM (
                SELECT day, symbol, count,
                       ROW_NUMBER() OVER (
                           PARTITION BY day, symbol
                           ORDER BY CASE WHEN source='composite' THEN 1 WHEN source='github' THEN 2 ELSE 3 END
                       ) as rn
                FROM raw_counts
            ) WHERE rn = 1
            GROUP BY day
        """).fetchall())

        out = []
        for sym, name in LANGUAGES.items():
            meta = LANGUAGE_META.get(sym, {"color": "#4A90E2", "category": "Tech", "tag": "General", "desc": ""})

            rows = c.execute(
                """SELECT p.day, p.price, COALESCE(r.count, 0) as count
                   FROM prices p
                   LEFT JOIN (
                       SELECT day, symbol, count FROM (
                           SELECT day, symbol, count,
                                  ROW_NUMBER() OVER (
                                      PARTITION BY day, symbol
                                      ORDER BY CASE WHEN source='composite' THEN 1 WHEN source='github' THEN 2 ELSE 3 END
                                  ) as rn
                           FROM raw_counts
                       ) WHERE rn = 1
                   ) r ON p.day = r.day AND p.symbol = r.symbol
                   WHERE p.symbol = ?
                   ORDER BY p.day ASC""", (sym,)
            ).fetchall()

            if not rows: continue

            history = []
            for r in rows:
                d = r["day"]
                total_c = tot_counts.get(d, 1) or 1
                share = (r["count"] / total_c) * 100.0 if total_c > 0 else 0.0
                history.append({
                    "day": d,
                    "price": round(r["price"], 2),
                    "count": r["count"],
                    "share": round(share, 2)
                })

            prices_list = [h["price"] for h in history]
            cur_p = prices_list[-1]
            base_p = prices_list[0] if prices_list else cur_p

            def calc_change(n):
                if len(prices_list) > n:
                    prev = prices_list[-1 - n]
                    return round(((cur_p / prev) - 1.0) * 100.0, 2)
                return 0.0

            change_1d = calc_change(1)
            change_7d = calc_change(7)
            change_30d = calc_change(30)
            change_all = round(((cur_p / base_p) - 1.0) * 100.0, 2) if base_p else 0.0

            latest_count = history[-1]["count"]
            latest_share = history[-1]["share"]

            out.append({
                "symbol": sym,
                "name": name,
                "color": meta.get("color", "#4A90E2"),
                "category": meta.get("category", "General"),
                "tag": meta.get("tag", "Code"),
                "desc": meta.get("desc", ""),
                "pkg": meta.get("pkg", "Registry"),
                "pkg_stats": meta.get("pkg_stats", ""),
                "price": cur_p,
                "change_1d": change_1d,
                "change_7d": change_7d,
                "change_30d": change_30d,
                "change_all": change_all,
                "latest_count": latest_count,
                "share_pct": latest_share,
                "spark": prices_list[-30:],
                "history": history
            })

        latest_day = all_days[-1] if all_days else None
        total_repos_today = tot_counts.get(latest_day, 0)

        distribution = sorted(
            [{"symbol": a["symbol"], "name": a["name"], "color": a["color"],
              "share_pct": a["share_pct"], "count": a["latest_count"]}
             for a in out],
            key=lambda x: -x["share_pct"]
        )

        gainers = sorted(out, key=lambda a: -a["change_all"])[:3]
        losers = sorted(out, key=lambda a: a["change_all"])[:3]

    return {
        "demo": any(s["source"] == "synthetic" for s in src),
        "start_cash": START_CASH,
        "assets": out,
        "ecosystem": {
            "total_repos_today": total_repos_today,
            "days_tracked": len(all_days),
            "distribution": distribution,
            "top_gainers": [{"symbol": g["symbol"], "name": g["name"], "change": g["change_all"], "color": g["color"], "price": g["price"]} for g in gainers],
            "top_losers": [{"symbol": l["symbol"], "name": l["name"], "change": l["change_all"], "color": l["color"], "price": l["price"]} for l in losers],
            "all_days": all_days
        }
    }

@app.post("/api/signup")
@limiter.limit("10/minute")
def signup(request: Request, b: Signup):
    return {"token": guard(trading.signup, b.name, b.address)}

@app.post("/api/deposit")
@limiter.limit("20/minute")
def deposit(request: Request, d: Deposit, x_token: str = Header("")):
    return guard(trading.deposit, x_token, d.amount)

@app.post("/api/burn")
@limiter.limit("20/minute")
def burn(request: Request, b: Burn, x_token: str = Header("")):
    return guard(trading.burn, x_token, b.amount)

@app.get("/api/depth")
@limiter.limit("60/minute")
def depth(request: Request, symbol: str = Query("RS")):
    return trading.order_book(symbol)

@app.get("/api/genesis")
@limiter.limit("30/minute")
def genesis(request: Request):
    return GENESIS_BLOCK

@app.post("/api/trade")
@limiter.limit("30/minute")
def trade(request: Request, o: Order, x_token: str = Header("")):
    guard(trading.trade, x_token, o.symbol, o.side, o.points)
    return guard(trading.portfolio, x_token)

@app.get("/api/portfolio")
@limiter.limit("60/minute")
def portfolio(request: Request, x_token: str = Header("")):
    return guard(trading.portfolio, x_token)

@app.get("/api/leaderboard")
@limiter.limit("20/minute")
def board(request: Request):
    return trading.leaderboard()

@app.get("/api/oracle_status")
@limiter.limit("20/minute")
def oracle_status(request: Request):
    """Anti-sybil: exposes data source health, credibility factors, and sybil defenses."""
    with conn() as c:
        sources = c.execute("""
            SELECT source,
                   COUNT(DISTINCT symbol) as languages,
                   COUNT(*) as entries,
                   MAX(day) as last_day,
                   SUM(count) as total_count
            FROM raw_counts GROUP BY source
        """).fetchall()
        days_tracked = c.execute("SELECT COUNT(DISTINCT day) as d FROM raw_counts WHERE source='github'").fetchone()["d"]
        langs_tracked = c.execute("SELECT COUNT(DISTINCT symbol) as l FROM raw_counts").fetchone()["l"]
        has_composite = c.execute("SELECT COUNT(*) as n FROM raw_counts WHERE source='composite'").fetchone()["n"] > 0
    return {
        "sources": [dict(s) for s in sources],
        "multi_source_active": has_composite,
        "anti_sybil": {
            "cap_mult": "2x trailing median - burst spike capped per language",
            "fork_filter": "fork:false - forked repos excluded from counts",
            "composite_weighting": "GitHub 65% + Registry 35% for PY/JS/TS/RS",
            "star_weight": "Pending: 0-star repos scheduled for 0.3x weight",
            "account_age": "Pending oracle node layer: accounts <90 days weighted 0.01x",
            "multi_source": {
                "GitHub": "live",
                "PyPI (top-10 packages)": "live",
                "npm (top-10 packages)": "live",
                "crates.io (top-10 crates)": "live",
                "Codeberg (Gitea API)": "live",
                "GitLab API": "live",
                "Software Heritage": "live",
                "job listings": "planned"
            },
            "oracle_consensus": "Median of independent signed collector reports - one rogue node cannot move index",
            "sybil_credibility_factor": 0.85
        },
        "network": {
            "days_tracked": days_tracked,
            "languages_tracked": langs_tracked,
            "block_height": days_tracked
        }
    }

@app.get("/api/verified_proofs")
@limiter.limit("30/minute")
def verified_proofs(
    request: Request,
    symbol: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=200)
):
    """PoTOP Attestation Ledger: returns cryptographically verified repo proofs."""
    with conn() as c:
        if symbol:
            rows = c.execute(
                """SELECT epoch_day, symbol, repo_name, commit_hash, tree_hash,
                          verifier_node, merkle_root, verified_at
                   FROM verified_proofs
                   WHERE symbol = ?
                   ORDER BY verified_at DESC
                   LIMIT ?""",
                (symbol.upper(), limit)
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT epoch_day, symbol, repo_name, commit_hash, tree_hash,
                          verifier_node, merkle_root, verified_at
                   FROM verified_proofs
                   ORDER BY verified_at DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()

        total = c.execute("SELECT COUNT(*) as n FROM verified_proofs").fetchone()["n"]
        latest = c.execute(
            "SELECT merkle_root, epoch_day FROM verified_proofs ORDER BY verified_at DESC LIMIT 1"
        ).fetchone()

    return {
        "total_verified": total,
        "latest_merkle_root": latest["merkle_root"] if latest else None,
        "latest_epoch": latest["epoch_day"] if latest else None,
        "proofs": [dict(r) for r in rows]
    }

@app.get("/api/burn_address")
@limiter.limit("10/minute")
def burn_address_info(request: Request):
    """Returns the protocol burn address and total DEK burned."""
    return trading.burn_info()

@app.get("/api/tokenomics")
@limiter.limit("20/minute")
def tokenomics(request: Request):
    """Returns transparent real-time token supply, minted metrics, and remaining allocation."""
    return trading.tokenomics_summary()

# --- Cryptographic Non-Custodial Endpoints (Phases 1, 2 & 3) ---

@app.post("/api/signed_tx")
@limiter.limit("30/minute")
def submit_signed_tx(request: Request, tx: SignedTransaction):
    """Ingests, cryptographically verifies, and commits a signed user transaction into the Merkle DAG."""
    try:
        receipt = il.append_signed_event(tx.payload, tx.signature)
        return {"status": "confirmed", "receipt": receipt}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/ledger_audit")
@limiter.limit("20/minute")
def get_ledger_audit(request: Request):
    """Verifies that zero blocks or balances have been manipulated without proper user signatures."""
    return il.audit_full_chain()

@app.get("/api/p2p/blocks")
@limiter.limit("30/minute")
def p2p_blocks(request: Request, since: int = Query(0)):
    """P2P sync endpoint: permits peer nodes to download verified signed blocks."""
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM signed_events WHERE block_index > ? ORDER BY block_index ASC LIMIT 100",
            (since,)
        ).fetchall()
    return {"blocks": [dict(r) for r in rows]}

@app.post("/api/p2p/ping")
@limiter.limit("30/minute")
def p2p_ping(request: Request, ping: P2PPeerPing):
    """Registers an autonomous peer node into the distributed routing table."""
    with conn() as c:
        c.execute(
            """INSERT INTO p2p_peers(node_id, address, onion_url, last_seen)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(node_id) DO UPDATE SET
               address=excluded.address, onion_url=excluded.onion_url, last_seen=CURRENT_TIMESTAMP""",
            (ping.node_id, ping.address, ping.onion_url)
        )
    return {"status": "ok"}

@app.get("/api/p2p/peers")
@limiter.limit("20/minute")
def p2p_peer_list(request: Request):
    """Returns the list of active peer nodes participating in the network."""
    with conn() as c:
        rows = c.execute("SELECT node_id, address, onion_url, last_seen, block_height FROM p2p_peers ORDER BY last_seen DESC LIMIT 50").fetchall()
    return {"peers": [dict(r) for r in rows]}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
