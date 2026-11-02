"""Component 3: exchange engine with real pricing, clean ledger, and DEK reward distribution."""
import secrets, hashlib
from config import LANGUAGES, LANGUAGE_META, START_CASH, DEK_PER_TRADE_BPS
from db import conn

def latest_price(c, sym):
    r = c.execute("SELECT price FROM prices WHERE symbol=? ORDER BY day DESC LIMIT 1", (sym,)).fetchone()
    if not r: raise ValueError("No price yet for " + sym)
    return r["price"]

def signup(name=None, address=None):
    clean_name = (name or "Trader").strip()[:30]
    if not clean_name:
        clean_name = "Trader"
    token = address.strip() if address and len(address.strip()) > 8 else secrets.token_hex(16)
    with conn() as c:
        existing = c.execute("SELECT token FROM users WHERE token=?", (token,)).fetchone()
        if existing:
            return token
        c.execute("INSERT INTO users(name, token, cash, dek) VALUES (?,?,?,0.0)", (clean_name, token, START_CASH))
    return token

def deposit(token, amount):
    if amount <= 0:
        raise ValueError("Deposit amount must be positive")
    with conn() as c:
        u = _user(c, token)
        c.execute("UPDATE users SET cash = cash + ? WHERE id = ?", (amount, u["id"]))
        c.execute("INSERT INTO trades(user_id, symbol, side, units, price, dek_rewarded) VALUES (?, ?, ?, ?, ?, 0.0)",
                  (u["id"], "USDT", "deposit", amount, 1.0))
    return portfolio(token)

def _user(c, token):
    u = c.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    if not u: raise PermissionError("Unknown or disconnected wallet/token.")
    return u

def trade(token, sym, side, points):
    if sym not in LANGUAGES: raise ValueError("Unknown symbol")
    if side not in ("buy", "sell") or points <= 0: raise ValueError("Enter a positive amount")
    with conn() as c:
        u = _user(c, token)
        price = latest_price(c, sym)
        units = points / price
        held = c.execute("SELECT units FROM positions WHERE user_id=? AND symbol=?", (u["id"], sym)).fetchone()
        held = held["units"] if held else 0.0
        if side == "buy":
            if points > u["cash"] + 1e-9: raise ValueError(f"Insufficient balance (${u['cash']:,.2f} available)")
            c.execute("UPDATE users SET cash=cash-? WHERE id=?", (points, u["id"]))
            delta = units
        else:
            if units > held + 1e-9: raise ValueError(f"Insufficient {sym} balance ({held:,.4f} units held)")
            c.execute("UPDATE users SET cash=cash+? WHERE id=?", (points, u["id"]))
            delta = -units

        # Protocol incentive: award DEK utility reward for providing trade volume
        dek_reward = round(points * (DEK_PER_TRADE_BPS / 10000.0), 4)

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
        total = u["cash"] + holdings_val

        # fetch deposits to compute net P&L
        deposits = sum(t["units"] for t in c.execute("SELECT units FROM trades WHERE user_id=? AND side='deposit'", (u["id"],)).fetchall())
        net_invested = deposits if deposits > 0 else total
        total_pnl = total - deposits if deposits > 0 else 0.0
        total_pnl_pct = ((total / deposits) - 1.0) * 100.0 if deposits > 0 else 0.0
        dek_balance = round(u["dek"] if "dek" in u.keys() and u["dek"] is not None else 0.0, 4)

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
            "cash": round(u["cash"], 2),
            "dek": dek_balance,
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
    # Book spread around current index price
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
    return {"asks": asks, "bids": bids, "price": price}

def leaderboard(limit=20):
    with conn() as c:
        users = c.execute("SELECT id, name, token, cash, COALESCE(dek, 0.0) as dek FROM users").fetchall()
        res = []
        for u in users:
            pos = c.execute("SELECT symbol, units FROM positions WHERE user_id=? AND units>1e-9", (u["id"],)).fetchall()
            val = sum(p["units"] * latest_price(c, p["symbol"]) for p in pos)
            total = u["cash"] + val
            deposits = sum(t["units"] for t in c.execute("SELECT units FROM trades WHERE user_id=? AND side='deposit'", (u["id"],)).fetchall())
            return_pct = round(((total / deposits) - 1.0) * 100.0, 2) if deposits > 0 else 0.0
            display_addr = (u["token"][:6] + "..." + u["token"][-4:]) if len(u["token"]) > 16 else u["name"]
            res.append({
                "name": u["name"],
                "address": display_addr,
                "total": round(total, 2),
                "dek": round(u["dek"], 2),
                "return_pct": return_pct
            })
    return sorted(res, key=lambda r: -r["total"])[:limit]
