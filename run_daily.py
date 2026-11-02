"""Run once a day (cron / scheduler): fetch yesterday's counts, then rebuild the index.
  0 6 * * *  cd /path/to/techx && GITHUB_TOKEN=... python run_daily.py"""
from db import init
from collector import collect
from index_engine import rebuild_prices
import datetime as dt
init()
collect((dt.date.today() - dt.timedelta(days=1)).isoformat())
print("prices built:", rebuild_prices())
