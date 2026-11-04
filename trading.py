"""Component 3: exchange engine with native DEK denomination, strict open interest caps, and anti-whale controls."""
import secrets, hashlib
from config import (
    LANGUAGES, LANGUAGE_META, START_CASH, DEK_PER_TRADE_BPS, DEK_PER_ORACLE_DAY,
    MAX_ASSET_OPEN_INTEREST, MAX_USER_OPEN_INTEREST_RATIO, MIN_ORDER_VALUE,
    BASE_DENOMINATION, BURN_ADDRESS, DEK_MAX_SUPPLY
)
from db import conn

def latest_price(c, sym):
    r = c.execute("SELECT price FROM prices WHERE symbol=? ORDER BY day DESC LIMIT 1", (sym,)).fetchone()
    if not r: raise ValueError("No price yet for " + sym)
    return r["price"]

def signup(name=None, address=None):
    clean_name = (name or "Trader").strip()[:30]
    if not clean_name:
        clean_name = "Trader"
    if address and len(address.strip()) > 3:
        raw = address.strip()
        if " " in raw:
            norm = " ".join(raw.lower().split())
            token = "0x" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:40]
        else:
            token = raw
    else:
        token = secrets.token_hex(16)

    with conn() as c:
        existing = c.execute("SELECT token FROM users WHERE token=?", (token,)).fetchone()
        if existing:
            return token
        c.execute("INSERT INTO users(name, token, cash, dek) VALUES (?,?,?,?)",
                  (clean_name, token, START_CASH, START_CASH))
    return token

def deposit(token, amount):
    """Simulated local test deposit for demonstration and paper-trading sandbox.
    Does not represent external blockchain settlement.
    """
    if amount <= 0:
        raise ValueError("Deposit amount must be positive")
    with conn() as c:
        u = _user(c, token)
        # Sandbox simulated balance accounting
        c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) + ?, cash = COALESCE(cash, 0.0) + ? WHERE id = ?",
                  (amount, amount, u["id"]))
        c.execute("INSERT INTO trades(user_id, symbol, side, units, price, dek_rewarded) VALUES (?, ?, ?, ?, ?, 0.0)",
                  (u["id"], BASE_DENOMINATION, "deposit", amount, 1.0))
        c.execute("INSERT INTO dek_ledger(user_id, delta, reason) VALUES (?, ?, ?)",
                  (u["id"], amount, "Sandbox paper-trading DEK deposit"))
    return portfolio(token)

def burn(token, amount):
    """Burns DEK by transferring tokens to the unspendable dead address."""
    if amount <= 0:
        raise ValueError("Burn amount must be positive")
    with conn() as c:
        u = _user(c, token)
        user_dek = u["dek"] if ("dek" in u.keys() and u["dek"] is not None) else u["cash"]
        if amount > user_dek + 1e-9:
            raise ValueError(f"Insufficient DEK balance to burn ({user_dek:,.2f} available)")

        # Deduct from user
        c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) - ?, cash = COALESCE(cash, 0.0) - ? WHERE id = ?",
                  (amount, amount, u["id"]))
        c.execute("INSERT INTO dek_ledger(user_id, delta, reason) VALUES (?, ?, ?)",
                  (u["id"], -amount, f"Burned to dead address {BURN_ADDRESS[:10]}..."))
        c.execute("INSERT INTO trades(user_id, symbol, side, units, price, dek_rewarded) VALUES (?, ?, ?, ?, ?, 0.0)",
                  (u["id"], "DEK_BURN", "burn", amount, 1.0))

        # Credit unspendable dead address
        dead_user = c.execute("SELECT id FROM users WHERE token=?", (BURN_ADDRESS,)).fetchone()
        if dead_user:
            c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) + ? WHERE id = ?", (amount, dead_user["id"]))
        else:
            c.execute("INSERT INTO users(name, token, cash, dek) VALUES (?, ?, 0.0, ?)",
                      ("Dead Address", BURN_ADDRESS, amount))

    return portfolio(token)

def burn_info():
    """Returns protocol-wide burn telemetry and dead address status."""
    with conn() as c:
        row = c.execute("SELECT dek FROM users WHERE token=?", (BURN_ADDRESS,)).fetchone()
        burned = row["dek"] if row and row["dek"] else 0.0
    return {
        "burn_address": BURN_ADDRESS,
        "total_burned": round(burned, 4),
        "hard_cap": DEK_MAX_SUPPLY,
        "circulating_max": round(DEK_MAX_SUPPLY - burned, 4),
        "status": "Unspendable. No private key exists."
    }

def tokenomics_summary():
    """Returns real-time transparent supply metrics across the entire protocol."""
    with conn() as c:
        minted_row = c.execute("""
            SELECT COALESCE(SUM(delta), 0.0) as total_minted
            FROM dek_ledger
            WHERE delta > 0 AND (reason LIKE 'Oracle block reward%' OR reason LIKE 'Trade incentive%')
        """).fetchone()
        total_minted = minted_row["total_minted"] if minted_row else 0.0

        dead_row = c.execute("SELECT dek FROM users WHERE token=?", (BURN_ADDRESS,)).fetchone()
        total_burned = dead_row["dek"] if dead_row and dead_row["dek"] else 0.0

        users_row = c.execute("SELECT COALESCE(SUM(dek), 0.0) as active_total FROM users WHERE token != ?", (BURN_ADDRESS,)).fetchone()
        active_holdings = users_row["active_total"] if users_row else 0.0

        blocks_row = c.execute("SELECT COUNT(DISTINCT day) as d FROM raw_counts WHERE source='github'").fetchone()
        block_height = blocks_row["d"] if blocks_row else 0

        remaining_unmined = max(0.0, DEK_MAX_SUPPLY - total_minted)
        circulating = max(0.0, total_minted - total_burned)

    return {
        "hard_cap": DEK_MAX_SUPPLY,
        "total_minted": round(total_minted, 4),
        "total_burned": round(total_burned, 4),
        "circulating_supply": round(circulating, 4),
        "remaining_unmined": round(remaining_unmined, 4),
        "active_user_holdings": round(active_holdings, 4),
        "block_height": block_height,
        "block_reward": DEK_PER_ORACLE_DAY,
        "burn_address": BURN_ADDRESS,
        "denomination": BASE_DENOMINATION
    }

def award_oracle_reward(node_address: str, epoch_day: str, potop_proof_root: str = None) -> float:
    """Awards the daily block reward (50 DEK) to an oracle validator node for a verified epoch."""
    with conn() as c:
        u = c.execute("SELECT id, name, dek FROM users WHERE token=?", (node_address,)).fetchone()
        if not u:
            clean_name = "Node-" + node_address[:8]
            c.execute("INSERT INTO users(name, token, cash, dek) VALUES (?, ?, 0.0, 0.0)", (clean_name, node_address))
            u = c.execute("SELECT id, name, dek FROM users WHERE token=?", (node_address,)).fetchone()

        reason = f"Oracle block reward for epoch {epoch_day}"
        existing = c.execute("SELECT id FROM dek_ledger WHERE user_id=? AND reason=?", (u["id"], reason)).fetchone()
        if existing:
            return u["dek"] or 0.0

        # Enforce protocol hard cap of 20,502,006 DEK
        minted_row = c.execute("""
            SELECT COALESCE(SUM(delta), 0.0) as total_minted
            FROM dek_ledger
            WHERE delta > 0 AND (reason LIKE 'Oracle block reward%' OR reason LIKE 'Trade incentive%')
        """).fetchone()
        current_minted = minted_row["total_minted"] if minted_row else 0.0
        reward = float(DEK_PER_ORACLE_DAY)

        if current_minted + reward > DEK_MAX_SUPPLY:
            reward = max(0.0, float(DEK_MAX_SUPPLY - current_minted))
            if reward <= 0.0:
                print("[!] Protocol hard cap reached: 20,502,006 DEK. No further emissions permitted.")
                return u["dek"] or 0.0

        c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) + ?, cash = COALESCE(cash, 0.0) + ? WHERE id=?",
                  (reward, reward, u["id"]))
        c.execute("INSERT INTO dek_ledger(user_id, delta, reason) VALUES (?, ?, ?)", (u["id"], reward, reason))
        c.execute("INSERT INTO trades(user_id, symbol, side, units, price, dek_rewarded) VALUES (?, 'DEK_MINING', 'mint', ?, 1.0, ?)",
                  (u["id"], reward, reward))
        new_bal = (u["dek"] or 0.0) + reward
        return new_bal

def _user(c, token):
    u = c.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    if not u: raise PermissionError("Unknown or disconnected wallet/token.")
    return u

def trade(token, sym, side, points):
    if sym not in LANGUAGES: raise ValueError("Unknown symbol")
    if side not in ("buy", "sell") or points <= 0: raise ValueError("Enter a positive amount")
    if points < MIN_ORDER_VALUE: raise ValueError(f"Minimum order size is {MIN_ORDER_VALUE:.1f} {BASE_DENOMINATION}")

    with conn() as c:
        u = _user(c, token)
        price = latest_price(c, sym)
        units = points / price
        user_dek = u["dek"] if ("dek" in u.keys() and u["dek"] is not None) else u["cash"]

        held_row = c.execute("SELECT units FROM positions WHERE user_id=? AND symbol=?", (u["id"], sym)).fetchone()
        held = held_row["units"] if held_row else 0.0

        if side == "buy":
            if points > user_dek + 1e-9:
                raise ValueError(f"Insufficient balance ({user_dek:,.2f} {BASE_DENOMINATION} available)")

            # Aggregate Solvency Protection: enforce global asset open interest cap in DEK
            agg_row = c.execute("SELECT SUM(units) as total FROM positions WHERE symbol=?", (sym,)).fetchone()
            curr_agg_units = agg_row["total"] if (agg_row and agg_row["total"]) else 0.0
            new_agg_exposure = (curr_agg_units + units) * price
            if new_agg_exposure > MAX_ASSET_OPEN_INTEREST:
                raise ValueError(f"Asset open interest cap reached ({MAX_ASSET_OPEN_INTEREST:,.0f} {BASE_DENOMINATION}). Solvency protection active.")

            # Anti-Whale Limit: no single account may hold more than MAX_USER_OPEN_INTEREST_RATIO of allowable exposure
            user_post_exposure = (held + units) * price
            max_user_allowed = MAX_ASSET_OPEN_INTEREST * MAX_USER_OPEN_INTEREST_RATIO
            if user_post_exposure > max_user_allowed:
                raise ValueError(f"Anti-whale limit: Single account cannot exceed {max_user_allowed:,.0f} {BASE_DENOMINATION} ({int(MAX_USER_OPEN_INTEREST_RATIO*100)}% of cap).")

            c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) - ?, cash = COALESCE(cash, 0.0) - ? WHERE id = ?",
                      (points, points, u["id"]))
            delta = units
        else:
            if units > held + 1e-9:
                raise ValueError(f"Insufficient {sym} balance ({held:,.4f} units held)")
            c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) + ?, cash = COALESCE(cash, 0.0) + ? WHERE id = ?",
                      (points, points, u["id"]))
            delta = -units

        # Protocol incentive: award DEK rebate for providing trade volume (enforcing hard cap)
        dek_reward = round(points * (DEK_PER_TRADE_BPS / 10000.0), 4)

        # Enforce protocol hard cap for trade rebates
        minted_row = c.execute("""
            SELECT COALESCE(SUM(delta), 0.0) as total_minted
            FROM dek_ledger
            WHERE delta > 0 AND (reason LIKE 'Oracle block reward%' OR reason LIKE 'Trade incentive%')
        """).fetchone()
        current_minted = minted_row["total_minted"] if minted_row else 0.0

        if current_minted + dek_reward > DEK_MAX_SUPPLY:
            dek_reward = max(0.0, float(DEK_MAX_SUPPLY - current_minted))

        c.execute("INSERT INTO positions VALUES (?,?,?) ON CONFLICT(user_id,symbol) "
                  "DO UPDATE SET units=units+?", (u["id"], sym, delta, delta))
        c.execute("INSERT INTO trades(user_id,symbol,side,units,price,dek_rewarded) VALUES (?,?,?,?,?,?)",
                  (u["id"], sym, side, units, price, dek_reward))
        if dek_reward > 0:
            c.execute("UPDATE users SET dek = COALESCE(dek, 0.0) + ? WHERE id = ?", (dek_reward, u["id"]))
            c.execute("INSERT INTO dek_ledger(user_id, delta, reason) VALUES (?, ?, ?)",
                  (u["id"], dek_reward, f"Trade incentive {side} {sym}"))

def _user_positions_with_pnl(c, user_id):
    pos = c.execute("SELECT symbol, units FROM positions WHERE user_id=? AND units>1e-9", (user_id,)).fetchall()
    trades = c.execute("SELECT symbol, side, units, price FROM trades WHERE user_id=?", (user_id,)).fetchall()
    
    cost_basis = {}
    for t in trades:
        s = t["symbol"]
        if s not in cost_basis:
            cost_basis[s] = {"total_cost": 0.0, "total_units": 0.0}
        if t["side"] == "buy":
            cost_basis[s]["total_cost"] += t["units"] * t["price"]
            cost_basis[s]["total_units"] += t["units"]

    rows = []
    for p in pos:
        sym = p["symbol"]
        units = p["units"]
        cur_p = latest_price(c, sym)
        val = units * cur_p
        
        meta = LANGUAGE_META.get(sym, {})
        cb = cost_basis.get(sym, {})
        avg_cost = (cb["total_cost"] / cb["total_units"]) if cb.get("total_units", 0) > 0 else cur_p
        invested = units * avg_cost
        pnl = val - invested
        pnl_pct = ((val / invested) - 1.0) * 100 if invested > 0 else 0.0
        
        rows.append({
            "symbol": sym,
            "name": LANGUAGES.get(sym, sym),
            "color": meta.get("color", "#666"),
            "category": meta.get("category", "Tech"),
            "units": round(units, 4),
            "current_price": round(cur_p, 2),
            "avg_cost": round(avg_cost, 2),
            "value": round(val, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2)
        })
    return rows

def portfolio(token):
    with conn() as c:
        u = _user(c, token)
        rows = _user_positions_with_pnl(c, u["id"])
        holdings_val = sum(r["value"] for r in rows)
        user_dek = round(u["dek"] if ("dek" in u.keys() and u["dek"] is not None) else u["cash"], 2)
        total = user_dek + holdings_val

        # fetch deposits to compute net P&L
        deposits = sum(t["units"] for t in c.execute("SELECT units FROM trades WHERE user_id=? AND side='deposit'", (u["id"],)).fetchall())
        total_pnl = total - deposits if deposits > 0 else 0.0
        total_pnl_pct = ((total / deposits) - 1.0) * 100.0 if deposits > 0 else 0.0

        recent_trades = []
        for t in c.execute("SELECT symbol, side, units, price, dek_rewarded, ts FROM trades WHERE user_id=? AND side != 'deposit' ORDER BY id DESC LIMIT 15", (u["id"],)).fetchall():
            recent_trades.append({
                "symbol": t["symbol"],
                "name": LANGUAGES.get(t["symbol"], t["symbol"]),
                "side": t["side"],
                "units": round(t["units"], 4),
                "price": round(t["price"], 2),
                "dek_rewarded": round(t["dek_rewarded"] if "dek_rewarded" in t.keys() and t["dek_rewarded"] is not None else 0.0, 4),
                "total": round(t["units"] * t["price"], 2),
                "ts": t["ts"]
            })

        return {
            "name": u["name"],
            "token": u["token"],
            "denomination": BASE_DENOMINATION,
            "cash": user_dek,
            "dek": user_dek,
            "holdings_val": round(holdings_val, 2),
            "total": round(total, 2),
            "deposits": round(deposits, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions": rows,
            "recent_trades": recent_trades
        }

def order_book(sym):
    with conn() as c:
        price = latest_price(c, sym)
    # Native DEK depth spread
    asks = []
    bids = []
    step = max(0.01, round(price * 0.0012, 2))
    for i in range(5, 0, -1):
        p = round(price + (i * step), 2)
        size = round(abs(hash(f"{sym}_{p}_ask") % 400 + 50) / 10.0, 2)
        asks.append({"price": p, "amount": size, "total": round(p * size, 2)})
    for i in range(1, 6):
        p = round(price - (i * step), 2)
        size = round(abs(hash(f"{sym}_{p}_bid") % 450 + 60) / 10.0, 2)
        bids.append({"price": p, "amount": size, "total": round(p * size, 2)})
    return {"asks": asks, "bids": bids, "price": price, "denomination": BASE_DENOMINATION}

def leaderboard(limit=20):
    with conn() as c:
        users = c.execute("SELECT id, name, token, cash, COALESCE(dek, cash, 0.0) as dek FROM users").fetchall()
        res = []
        for u in users:
            pos = c.execute("SELECT symbol, units FROM positions WHERE user_id=? AND units>1e-9", (u["id"],)).fetchall()
            val = sum(p["units"] * latest_price(c, p["symbol"]) for p in pos)
            user_dek = u["dek"] or 0.0
            total = user_dek + val
            deposits = sum(t["units"] for t in c.execute("SELECT units FROM trades WHERE user_id=? AND side='deposit'", (u["id"],)).fetchall())
            return_pct = round(((total / deposits) - 1.0) * 100.0, 2) if deposits > 0 else 0.0
            display_addr = (u["token"][:6] + "..." + u["token"][-4:]) if len(u["token"]) > 16 else u["name"]
            res.append({
                "name": u["name"],
                "address": display_addr,
                "total": round(total, 2),
                "dek": round(user_dek, 2),
                "return_pct": return_pct
            })
    return sorted(res, key=lambda r: -r["total"])[:limit]
