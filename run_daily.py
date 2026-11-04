"""Langdex Protocol: Daily data ingestion helper (no reward minting).

This script only fetches yesterday's telemetry counts and rebuilds index prices.
It does NOT mint any DEK or credit any reward.

To earn a validator block reward, run the full miner pipeline instead:
  python miner.py

That pipeline runs PoTOP proof verification, the PoW puzzle, and the full
reward function with supply-cap enforcement and Ed25519 signature binding.
"""
import datetime as dt
from db import init, backup_db
from collector import collect
from index_engine import rebuild_prices

init()
epoch_day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
print(f"=== Langdex Daily Data Ingest: {epoch_day} ===")

collect(epoch_day)
rebuild_prices()

backup_path = backup_db()
print(f"[BACKUP] Ledger snapshot saved: {backup_path}")
print("[INFO] No DEK was minted. Run 'python miner.py' to perform full validator proof and earn a reward.")
