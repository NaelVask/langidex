"""Fills the database with SYNTHETIC counts so you can run the app without a GitHub token.
The app shows a DEMO DATA banner while synthetic rows exist. Delete techx.db to reset."""
import random, datetime as dt
from config import LANGUAGES
from db import conn, init
from index_engine import rebuild_prices

init(); random.seed(7)
size = {"PY": 90, "JS": 100, "TS": 60, "RS": 15, "GO": 25, "JV": 70, "CPP": 40, "CS": 35,
        "PHP": 30, "KT": 12, "SW": 10, "RB": 12}
drift = {"RS": 1.012, "TS": 1.006, "PY": 1.004, "PHP": 0.994, "RB": 0.995}
today = dt.date.today()
with conn() as c:
    c.execute("DELETE FROM raw_counts")
    level = {s: size[s] * 1000.0 for s in LANGUAGES}
    for i in range(45, 0, -1):
        d = today - dt.timedelta(days=i)
        weekend = 0.7 if d.weekday() >= 5 else 1.0
        for s in LANGUAGES:
            level[s] *= drift.get(s, 1.0) * random.uniform(0.985, 1.015)
            c.execute("INSERT INTO raw_counts VALUES (?,?,?,?)",
                      (d.isoformat(), s, int(level[s] * weekend), "synthetic"))
print("prices built:", rebuild_prices())
