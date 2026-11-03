"""Run once a day (cron / scheduler): fetch yesterday's counts, rebuild the index, and award oracle block reward.
Usage:
  python run_daily.py [node_wallet_address]
"""
import sys, os, datetime as dt
from db import init
from collector import collect
from index_engine import rebuild_prices
from trading import award_oracle_reward

init()
epoch_day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
print(f"=== Langdex Daily Epoch Process: {epoch_day} ===")

# Ingest and rebuild
collect(epoch_day)
rebuild_prices()

# Check for node reward
node_addr = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NODE_WALLET_ADDRESS")
if node_addr:
    bal = award_oracle_reward(node_addr, epoch_day)
    print(f"[REWARD MINTED] Epoch {epoch_day} validator reward (50.0 DEK) credited to {node_addr}")
    print(f"Updated Wallet Balance: {bal:.2f} DEK")
else:
    print("[NOTE] No node wallet address passed. Run with 'python run_daily.py <wallet_address>' to claim 50 DEK reward.")
